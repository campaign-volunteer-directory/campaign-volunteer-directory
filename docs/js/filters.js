/**
 * Facet filters (level / state / topics) and their URL round-trip.
 * Filters live in the query string so views are shareable and the browser
 * back button restores the previous filter state.
 *
 * URL encoding:
 *   level=State
 *   state=Massachusetts,Maine
 *   topics=Housing,-Workers%20%26%20Wages   ('-' prefix = exclude)
 */

export class FilterState {
    constructor() {
        this.q = '';
        this.level = '';
        this.states = new Set();
        this.topicsInclude = new Set();
        this.topicsExclude = new Set();
    }

    readFromUrl() {
        const params = new URLSearchParams(location.search);
        this.q = params.get('q') || '';
        this.level = params.get('level') || '';
        this.states = new Set(params.get('state') ? params.get('state').split(',') : []);
        const topics = params.get('topics') ? params.get('topics').split(',') : [];
        this.topicsInclude = new Set(topics.filter((t) => !t.startsWith('-')));
        this.topicsExclude = new Set(topics.filter((t) => t.startsWith('-')).map((t) => t.slice(1)));
    }

    writeToUrl() {
        const params = new URLSearchParams();
        if (this.q) params.set('q', this.q);
        if (this.level) params.set('level', this.level);
        if (this.states.size) params.set('state', [...this.states].join(','));
        const topics = [
            ...this.topicsInclude,
            ...[...this.topicsExclude].map((t) => `-${t}`),
        ];
        if (topics.length) params.set('topics', topics.join(','));
        const query = params.toString();
        history.replaceState(null, '', query ? `?${query}` : location.pathname);
    }

    clear() {
        this.q = '';
        this.level = '';
        this.states = new Set();
        this.topicsInclude = new Set();
        this.topicsExclude = new Set();
    }

    get isActive() {
        return Boolean(this.q || this.level || this.states.size ||
            this.topicsInclude.size || this.topicsExclude.size);
    }
}

export function matchesFacets(candidate, filters) {
    if (filters.level && candidate.govt_level !== filters.level) return false;
    if (filters.states.size && !filters.states.has(candidate.state)) return false;
    if (filters.topicsInclude.size) {
        const tags = new Set(candidate.topics || []);
        for (const topic of filters.topicsInclude) {
            if (!tags.has(topic)) return false;
        }
    }
    if (filters.topicsExclude.size) {
        const tags = new Set(candidate.topics || []);
        for (const topic of filters.topicsExclude) {
            if (tags.has(topic)) return false;
        }
    }
    return true;
}
