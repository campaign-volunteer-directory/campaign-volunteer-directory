/**
 * FTS5-inspired full-text search over candidates.
 *
 * Mirrors the parts of SQLite's FTS5 that matter for this directory:
 *   - tokenized fields (lowercased, alphanumeric terms)
 *   - prefix queries (`term*`), with implicit prefix matching for
 *     partially-typed terms the way users expect
 *   - AND semantics across query terms
 *   - weighted ranking: fields closer to "what the candidate is" weigh more
 *     (name > position > topics > party/location > stances), and exact
 *     token hits outrank prefix hits which outrank substring hits.
 *
 * A real inverted index isn't warranted for ~150 rows; per-document token
 * maps keep the code readable and the queries sub-millisecond.
 */

export const FIELD_WEIGHTS = {
    name: 5,
    position: 4,
    topics: 3,
    party: 2,
    state: 2,
    govt_level: 1,
    district: 2,
    stances: 1,
};

const MATCH_EXACT = 1.0;
const MATCH_PREFIX = 0.8;
const MATCH_SUBSTRING = 0.4;

export function tokenize(text) {
    return String(text || '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, ' ')
        .split(' ')
        .filter(Boolean);
}

export function parseQuery(raw) {
    return String(raw || '')
        .toLowerCase()
        .replace(/[^a-z0-9\s*]+/g, ' ')
        .split(/\s+/)
        .filter(Boolean)
        .map((term) => term.endsWith('*')
            ? { text: term.slice(0, -1), prefix: true }
            : { text: term, prefix: false });
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
 * Rank the index entries that match every query term.
 * Returns [{candidate, score}] sorted by score desc, then name asc.
 * With no query terms, every entry passes with score 0 (name order).
 */
export function searchRanked(index, queryTerms) {
    const scored = [];
    for (const entry of index) {
        const score = scoreEntry(entry, queryTerms);
        if (score !== null) {
            scored.push({ candidate: entry.candidate, score });
        }
    }
    scored.sort((a, b) =>
        b.score - a.score || a.candidate.name.localeCompare(b.candidate.name));
    return scored;
}

function scoreEntry(entry, queryTerms) {
    if (queryTerms.length === 0) return 0;
    let total = 0;
    for (const term of queryTerms) {
        const fieldScore = bestFieldScore(entry, term);
        if (fieldScore === null) return null; // AND semantics: all terms must match
        total += fieldScore;
    }
    return total;
}

function bestFieldScore(entry, term) {
    let best = null;
    for (const [field, tokens] of Object.entries(entry.fields)) {
        const hit = matchTokens(tokens, term);
        if (hit) {
            const score = FIELD_WEIGHTS[field] * hit.count * hit.kind;
            if (best === null || score > best) best = score;
        }
    }
    return best;
}

function matchTokens(tokens, term) {
    let count = 0;
    let kind = null;
    for (const token of tokens.tokens) {
        const tokenKind = matchKind(token, term);
        if (tokenKind) {
            count += tokens.counts.get(token);
            kind = Math.max(kind || 0, tokenKind);
        }
    }
    return kind ? { count, kind } : null;
}

function matchKind(token, term) {
    if (!token.startsWith(term.text)) {
        return token.includes(term.text) ? MATCH_SUBSTRING : null;
    }
    if (token === term.text) return MATCH_EXACT;
    return term.prefix || MATCH_PREFIX;
}
