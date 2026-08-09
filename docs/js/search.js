/**
 * FTS5-inspired full-text search over candidates.
 *
 * Query grammar (sqlite-FTS5 flavored):
 *   word          — required term; implicit prefix matching on tokens
 *   -word         — term that must NOT match anywhere
 *   word*         — explicit prefix term
 *   "a b c"       — exact consecutive-token phrase
 *
 * Ranking: AND across required terms, exclusion wins, weighted fields
 * (name > position > topics > party/location > stances), exact token >
 * prefix > substring. When a strict search finds nothing, the caller can
 * retry with fuzzy fallback: unmatched terms get a cheap edit-distance
 * pass (≤1 edit for ≥4-char terms, ≤2 for ≥6-char terms) at reduced weight.
 *
 * A real inverted index isn't warranted for ~150 rows; per-document token
 * maps keep the code readable and queries sub-millisecond.
 */

import { levenshtein } from './utils.js?v=10';
import { stateAbbreviation } from './states.js?v=10';

export const FIELD_WEIGHTS = {
    name: 5,
    position: 4,
    topics: 3,
    party: 2,
    state: 2,
    state_abbr: 2,
    govt_level: 1,
    district: 2,
    stances: 1,
};

const MATCH_EXACT = 1.0;
const MATCH_PREFIX = 0.8;
const MATCH_SUBSTRING = 0.4;
const MATCH_FUZZY = 0.2;

export function tokenize(text) {
    return String(text || '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, ' ')
        .split(' ')
        .filter(Boolean);
}

/** Split a raw query into raw tokens, keeping quoted phrases whole. */
export function splitQuery(raw) {
    const tokens = [];
    const source = String(raw || '');
    const phrasePattern = /"([^"]+)"/g;
    let remainder = source.replace(phrasePattern, (match, phrase) => {
        if (tokenize(phrase).length) tokens.push(match);
        return ' ';
    });
    remainder = remainder.toLowerCase().replace(/[^a-z0-9\s*+-]/g, ' ');
    for (const piece of remainder.split(/\s+/)) {
        if (piece && piece !== '-' && piece !== '+') tokens.push(piece);
    }
    return tokens;
}

export function parseQuery(raw) {
    const include = [];
    const exclude = [];
    const phrases = [];
    for (const token of splitQuery(raw)) {
        if (token.startsWith('"') && token.endsWith('"')) {
            phrases.push(tokenize(token));
        } else if (token.startsWith('-')) {
            exclude.push(termFrom(token.slice(1)));
        } else if (token.startsWith('+')) {
            include.push(termFrom(token.slice(1)));
        } else {
            include.push(termFrom(token));
        }
    }
    return { include, exclude, phrases };
}

function termFrom(raw) {
    const text = raw.replace(/\*/g, '');
    return { text, prefix: raw.endsWith('*') };
}

export function buildSearchIndex(candidates) {
    return candidates.map((candidate) => ({
        candidate,
        fields: {
            name: tokenizeField(candidate.name),
            position: tokenizeField(candidate.position),
            topics: tokenizeField((candidate.topics || []).join(' ')),
            party: tokenizeField(candidate.party),
            state: tokenizeField(candidate.state),
            state_abbr: tokenizeField(stateAbbreviation(candidate.state)),
            govt_level: tokenizeField(candidate.govt_level),
            district: tokenizeField(candidate.district),
            stances: tokenizeField(candidate.stances),
        },
    }));
}

function tokenizeField(text) {
    const tokens = tokenize(text);
    const counts = new Map();
    for (const token of tokens) {
        counts.set(token, (counts.get(token) || 0) + 1);
    }
    return { tokens, counts };
}

/**
 * Rank the index entries matching the query.
 * Returns [{candidate, score, exact}] sorted by:
 *   1. entries with an exact token match for any term first (so "VA" ranks
 *      Virginia over "valley", and "war" ranks "war" over "ward"),
 *   2. then score desc, then name asc.
 * With no query terms, every entry passes with score 0 (name order).
 * Pass { fuzzy: true } for the did-you-mean fallback pass.
 */
export function searchRanked(index, query, options = {}) {
    const scored = [];
    for (const entry of index) {
        if (matchesExclusion(entry, query)) continue;
        const result = scoreEntry(entry, query, options);
        if (result !== null) {
            scored.push({
                candidate: entry.candidate,
                score: result.score,
                exact: result.exact,
            });
        }
    }
    scored.sort((a, b) =>
        (b.exact - a.exact) || (b.score - a.score) ||
        a.candidate.name.localeCompare(b.candidate.name));
    return scored;
}

function matchesExclusion(entry, query) {
    for (const term of query.exclude) {
        if (bestFieldScore(entry, term, { substring: false }) !== null) return true;
    }
    return false;
}

function scoreEntry(entry, query, options) {
    if (!query.include.length && !query.phrases.length) return { score: 0, exact: false };
    let total = 0;
    let exact = false;
    for (const term of query.include) {
        const fieldScore = bestFieldScore(entry, term, options);
        if (fieldScore === null) return null; // AND semantics: all terms must match
        total += fieldScore.score;
        exact = exact || fieldScore.exact;
    }
    for (const phrase of query.phrases) {
        const phraseScore = bestPhraseScore(entry, phrase);
        if (phraseScore === null) return null;
        total += phraseScore.score;
        exact = true; // phrases are consecutive exact tokens
    }
    return { score: total, exact };
}

function bestFieldScore(entry, term, options = { substring: true, fuzzy: false }) {
    let best = null;
    for (const [field, tokens] of Object.entries(entry.fields)) {
        const hit = matchTokens(tokens, term, options);
        if (hit) {
            const score = FIELD_WEIGHTS[field] * hit.count * hit.kind;
            if (best === null || score > best.score) {
                best = { score, exact: hit.kind === MATCH_EXACT };
            }
        }
    }
    return best;
}

function bestPhraseScore(entry, phrase) {
    let best = null;
    for (const [field, tokens] of Object.entries(entry.fields)) {
        const hit = matchPhrase(tokens, phrase);
        if (hit) {
            const score = FIELD_WEIGHTS[field] * hit.count * MATCH_EXACT;
            if (best === null || score > best.score) {
                best = { score, exact: true };
            }
        }
    }
    return best;
}

function matchTokens(tokens, term, options) {
    const strict = matchTokensWith(tokens, term, MATCH_PREFIX);
    if (strict) return strict;
    if (options.substring && matchTokensWith(tokens, term, MATCH_SUBSTRING)) {
        return matchTokensWith(tokens, term, MATCH_SUBSTRING);
    }
    if (options.fuzzy) return matchTokensWith(tokens, term, MATCH_FUZZY);
    return null;
}

function matchTokensWith(tokens, term, kind) {
    let count = 0;
    let bestKind = null;
    for (const token of tokens.tokens) {
        const matchedKind = tokenKindMatches(token, term, kind);
        if (matchedKind) {
            count += tokens.counts.get(token);
            bestKind = Math.max(bestKind || 0, matchedKind);
        }
    }
    return bestKind ? { count, kind: bestKind } : null;
}

function tokenKindMatches(token, term, kind) {
    if (kind === MATCH_PREFIX) {
        if (!token.startsWith(term.text)) return false;
        return token === term.text ? MATCH_EXACT : MATCH_PREFIX;
    }
    if (kind === MATCH_SUBSTRING) {
        return token.includes(term.text);
    }
    if (kind === MATCH_FUZZY) {
        return withinEditDistance(term.text, token);
    }
    return false;
}

function withinEditDistance(query, token) {
    if (query.length < 4 || token.length < 4) return false;
    const tolerance = query.length >= 6 ? 2 : 1;
    if (Math.abs(query.length - token.length) > tolerance) return false;
    return levenshtein(query, token) <= tolerance;
}

function matchPhrase(tokens, phrase) {
    const { tokens: stream } = tokens;
    let count = 0;
    for (let i = 0; i + phrase.length <= stream.length; i++) {
        if (stream.slice(i, i + phrase.length).join(' ') === phrase.join(' ')) {
            count++;
            i += phrase.length - 1;
        }
    }
    return count ? { count } : null;
}
