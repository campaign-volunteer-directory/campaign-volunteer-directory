export function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export function escapeRegex(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function debounce(fn, waitMs) {
    let timer = null;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), waitMs);
    };
}

export function firstUrl(text) {
    const match = String(text || '').match(/https?:\/\/\S+/i);
    return match ? match[0].replace(/[),.\]]+$/, '') : null;
}

export function firstEmail(text) {
    const match = String(text || '').match(/[\w.+-]+@[\w-]+\.[\w.-]+/);
    return match ? match[0] : null;
}

/** Classic edit-distance; used for fuzzy "closest match" fallback. */
export function levenshtein(a, b) {
    if (a === b) return 0;
    const m = a.length;
    const n = b.length;
    if (!m) return n;
    if (!n) return m;
    let prev = Array.from({ length: n + 1 }, (_, i) => i);
    for (let i = 1; i <= m; i++) {
        const current = [i];
        for (let j = 1; j <= n; j++) {
            current[j] = Math.min(
                prev[j] + 1,
                current[j - 1] + 1,
                prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
        }
        prev = current;
    }
    return prev[n];
}
