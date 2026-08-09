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
