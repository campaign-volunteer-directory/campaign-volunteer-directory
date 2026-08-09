import { escapeHtml, escapeRegex } from './utils.js?v=7';

/**
 * Highlight query terms in text with <mark>, escaping all HTML.
 *
 * Terms match whole tokens that start with the term (covers exact and prefix
 * matches), found against the ORIGINAL text so HTML entities like &amp; can
 * never be highlighted by accident. Overlapping ranges are merged so marks
 * never nest.
 */
export function highlightTerms(text, terms) {
    const source = String(text == null ? '' : text);
    if (!terms.length || !source) return escapeHtml(source);

    const ranges = findMatchRanges(source, terms);
    const merged = mergeRanges(ranges);
    if (!merged.length) return escapeHtml(source);

    let output = '';
    let cursor = 0;
    for (const [start, end] of merged) {
        output += escapeHtml(source.slice(cursor, start));
        output += `<mark>${escapeHtml(source.slice(start, end))}</mark>`;
        cursor = end;
    }
    return output + escapeHtml(source.slice(cursor));
}

function findMatchRanges(source, terms) {
    const ranges = [];
    for (const rawTerm of terms) {
        const term = String(rawTerm || '');
        if (!term) continue;
        const matcher = new RegExp(`\\b${escapeRegex(term)}\\w*`, 'gi');
        let match;
        while ((match = matcher.exec(source))) {
            ranges.push([match.index, match.index + match[0].length]);
            if (matcher.lastIndex === match.index) matcher.lastIndex += 1;
        }
    }
    return ranges;
}

function mergeRanges(ranges) {
    if (!ranges.length) return [];
    ranges.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
    const merged = [ranges[0]];
    for (const range of ranges.slice(1)) {
        const last = merged[merged.length - 1];
        if (range[0] <= last[1]) {
            last[1] = Math.max(last[1], range[1]);
        } else {
            merged.push(range);
        }
    }
    return merged;
}
