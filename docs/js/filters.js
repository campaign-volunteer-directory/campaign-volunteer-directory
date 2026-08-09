/**
 * Facet filters (level / state / topics) and their URL round-trip.
 * Filters are stored in the query string so views are shareable and the
 * browser back button restores the previous filter state.
 */

export class FilterState {
    constructor() {
        this.q = '';
        this.level = '';
        this.states = new Set();
        this.topics = new Set();
    }

    readFromUrl() {
        const params = new URLSearchParams(location.search);
        this.q = params.get('q') || '';
        this.level = params.get('level') || '';
        this.states = new Set(params.get('state') ? params.get('state').split(',') : []);
        this.topics = new Set(params.get('topics') ? params.get('topics').split(',') : []);
    }

    writeToUrl() {
        const params = new URLSearchParams();
        if (this.q) params.set('q', this.q);
        if (this.level) params.set('level', this.level);
        if (this.states.size) params.set('state', [...this.states].join(','));
        if (this.topics.size) params.set('topics', [...this.topics].join(','));
        const query = params.toString();
        history.replaceState(null, '', query ? `?${query}` : location.pathname);
    }

    clear() {
        this.q = '';
        this.level = '';
        this.states = new Set();
        this.topics = new Set();
    }

    get isActive() {
        return Boolean(this.q || this.level || this.states.size || this.topics.size);
    }
}

export function matchesFacets(candidate, filters) {
    if (filters.level && candidate.govt_level !== filters.level) return false;
    if (filters.states.size && !filters.states.has(candidate.state)) return false;
    if (filters.topics.size) {
        const tags = new Set(candidate.topics || []);
        for (const topic of filters.topics) {
            if (!tags.has(topic)) return false;
        }
    }
    return true;
}
