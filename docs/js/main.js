import { debounce } from './utils.js?v=8';
import { parseQuery, splitQuery, buildSearchIndex, searchRanked } from './search.js?v=8';
import { FilterState, matchesFacets } from './filters.js?v=8';
import { stateAbbreviation } from './states.js?v=8';
import {
    renderStats,
    renderStatsFor,
    renderStateOptions,
    renderTopicChips,
    renderSuggestions,
    renderResultsLine,
    renderActiveFilters,
    renderCards,
    buildCsv,
} from './render.js?v=8';

const SEARCH_DEBOUNCE_MS = 120;
const APP_VERSION = 8;
const KIND_LABELS = { state: 'State', topic: 'Issue', candidate: 'Candidate' };

let candidates = [];
let searchIndex = [];
let topicCounts = [];
let stateCounts = [];
let rawQueryTerms = [];
let suggestionActiveIndex = null;
const filters = new FilterState();

// ── Derived data ─────────────────────────────────────────────────────────

function topicCountsFrom(candidates) {
    const counts = {};
    for (const candidate of candidates) {
        for (const topic of candidate.topics || []) {
            counts[topic] = (counts[topic] || 0) + 1;
        }
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
}

function stateCountsFrom(candidates) {
    const counts = {};
    for (const candidate of candidates) {
        counts[candidate.state] = (counts[candidate.state] || 0) + 1;
    }
    return Object.entries(counts).sort((a, b) => a[0].localeCompare(b[0]));
}

function queryTerms() {
    return parseQuery(filters.q);
}

function matchedEntries(options) {
    const faceted = searchIndex.filter((entry) => matchesFacets(entry.candidate, filters));
    return searchRanked(faceted, queryTerms(), options);
}

function emptyMessage() {
    if (filters.q) return `No candidates match "${filters.q}". Try fewer or different words.`;
    if (filters.isActive) return 'No candidates match these filters.';
    return 'No candidates found.';
}

// ── Apply (single pipeline for every filter change) ──────────────────────

function apply() {
    rawQueryTerms = splitQuery(filters.q);
    const query = queryTerms();

    let entries = matchedEntries();
    let fuzzy = false;
    if (!entries.length && query.include.length) {
        entries = matchedEntries({ fuzzy: true });
        fuzzy = entries.length > 0;
    }

    document.getElementById('filter-results').textContent =
        renderResultsLine(entries.length, candidates.length);
    document.getElementById('filter-clear').classList.toggle('hidden', !filters.isActive);
    document.getElementById('active-filters').innerHTML =
        renderActiveFilters(filters, rawQueryTerms);

    const fuzzyNote = document.getElementById('fuzzy-note');
    fuzzyNote.classList.toggle('hidden', !fuzzy);
    if (fuzzy) {
        fuzzyNote.textContent =
            `No exact matches for "${filters.q}" — showing closest matches. Check the spelling or try fewer words.`;
    }

    const download = document.getElementById('filter-download');
    download.disabled = entries.length === 0;
    download.title = entries.length ? 'Download the filtered list as CSV' : 'Nothing to download';

    renderStatsFor(entries);
    document.getElementById('cards').innerHTML =
        renderCards(entries, query.include.map((term) => term.text), emptyMessage());
    filters.writeToUrl();
}

// ── Suggestions (live autocomplete) ──────────────────────────────────────

function buildSuggestions(raw) {
    const needle = raw.trim().toLowerCase();
    if (!needle) return [];

    const items = [];
    for (const [name, count] of stateCounts) {
        const abbr = stateAbbreviation(name).toLowerCase();
        if (name.toLowerCase().startsWith(needle) || abbr.startsWith(needle)) {
            items.push({
                kind: 'state', value: name,
                label: name, sub: `${KIND_LABELS.state} · ${stateAbbreviation(name)} · ${count}`,
            });
        }
    }
    for (const [topic, count] of topicCounts) {
        if (topic.toLowerCase().includes(needle)) {
            items.push({ kind: 'topic', value: topic, label: topic, sub: `${KIND_LABELS.topic} · ${count}` });
        }
    }
    for (const { candidate } of matchedEntries().slice(0, 5)) {
        if (candidate.name.toLowerCase().startsWith(needle)) {
            items.push({
                kind: 'candidate', value: candidate.name,
                label: candidate.name,
                sub: `${KIND_LABELS.candidate} · ${candidate.position} · ${candidate.state}`,
            });
        }
    }
    return prioritize(items, needle).slice(0, 9);
}

function prioritize(items, needle) {
    const priorityOf = (item) => {
        if (item.kind === 'candidate' && item.label.toLowerCase().startsWith(needle)) return 0;
        if (item.kind === 'state' && stateAbbreviation(item.value).toLowerCase() === needle) return 0;
        if (item.kind === 'state') return 1;
        if (item.kind === 'topic') return 2;
        return 3;
    };
    return items
        .map((item, index) => ({ item, priority: priorityOf(item), index }))
        .sort((a, b) => a.priority - b.priority || a.index - b.index)
        .map(({ item }) => item);
}

function renderSuggestionsList() {
    const list = document.getElementById('suggestions');
    const items = buildSuggestions(filters.q);
    list.innerHTML = renderSuggestions(items);
    list.classList.toggle('hidden', items.length === 0);
    suggestionActiveIndex = null;
}

function hideSuggestions() {
    document.getElementById('suggestions').classList.add('hidden');
    suggestionActiveIndex = null;
}

function activateSuggestion(data) {
    if (data.action === 'state') {
        filters.states = new Set([data.value]);
        syncStateCheckboxes();
        syncStateTrigger();
    } else if (data.action === 'topic') {
        toggleInclude(data.value);
        syncChips();
    } else if (data.action === 'candidate') {
        filters.q = `"${data.value}"`;
        document.getElementById('filter-q').value = filters.q;
    }
    hideSuggestions();
    apply();
}

// ── Query box ────────────────────────────────────────────────────────────

function wireQueryBox() {
    const input = document.getElementById('filter-q');

    input.addEventListener('input', debounce((event) => {
        filters.q = event.target.value;
        apply();
        renderSuggestionsList();
    }, SEARCH_DEBOUNCE_MS));

    input.addEventListener('keydown', (event) => {
        const items = document.querySelectorAll('#suggestions .suggestion');
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            if (!items.length) return;
            event.preventDefault();
            const direction = event.key === 'ArrowDown' ? 1 : -1;
            suggestionActiveIndex = suggestionActiveIndex === null
                ? (direction === 1 ? 0 : items.length - 1)
                : (suggestionActiveIndex + direction + items.length) % items.length;
            markActiveSuggestion(items);
        } else if (event.key === 'Enter' && suggestionActiveIndex !== null && items.length) {
            event.preventDefault();
            activateSuggestion(items[suggestionActiveIndex].dataset);
        } else if (event.key === 'Escape') {
            if (!document.getElementById('suggestions').classList.contains('hidden')) {
                hideSuggestions();
            } else if (filters.q) {
                filters.q = '';
                input.value = '';
                apply();
            }
        }
    });

    input.addEventListener('focus', () => renderSuggestionsList());
    input.addEventListener('blur', () => setTimeout(hideSuggestions, 150));

    document.getElementById('suggestions').addEventListener('mousedown', (event) => {
        const suggestion = event.target.closest('.suggestion');
        if (!suggestion) return;
        event.preventDefault(); // keep focus in the input
        activateSuggestion(suggestion.dataset);
    });
}

function markActiveSuggestion(items) {
    items.forEach((item, index) => {
        item.classList.toggle('active', index === suggestionActiveIndex);
        if (index === suggestionActiveIndex) item.scrollIntoView({ block: 'nearest' });
    });
}

function wireGlobalShortcuts() {
    document.addEventListener('keydown', (event) => {
        const target = event.target;
        const typing = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT';
        if (event.key === '/' && !typing) {
            event.preventDefault();
            document.getElementById('filter-q').focus();
        }
    });
}

// ── Facet chips (include / exclude) ──────────────────────────────────────

function wireTopicChips() {
    document.getElementById('filter-topics').addEventListener('click', (event) => {
        const chip = event.target.closest('.chip');
        if (!chip) return;
        const topic = chip.dataset.topic;
        if (event.shiftKey) toggleExclude(topic);
        else toggleInclude(topic);
        syncChips();
        apply();
    });
}

function toggleInclude(topic) {
    if (filters.topicsInclude.has(topic)) filters.topicsInclude.delete(topic);
    else {
        filters.topicsInclude.add(topic);
        filters.topicsExclude.delete(topic);
    }
}

function toggleExclude(topic) {
    if (filters.topicsExclude.has(topic)) filters.topicsExclude.delete(topic);
    else {
        filters.topicsExclude.add(topic);
        filters.topicsInclude.delete(topic);
    }
}

function syncChips() {
    document.querySelectorAll('#filter-topics .chip').forEach((chip) => {
        const topic = chip.dataset.topic;
        chip.classList.toggle('active-include', filters.topicsInclude.has(topic));
        chip.classList.toggle('active-exclude', filters.topicsExclude.has(topic));
    });
}

// ── Level pills ──────────────────────────────────────────────────────────

function wireLevelPills() {
    document.getElementById('filter-level').addEventListener('click', (event) => {
        const button = event.target.closest('.pill');
        if (!button) return;
        filters.level = button.dataset.level;
        syncLevelButtons();
        apply();
    });
}

function syncLevelButtons() {
    document.querySelectorAll('#filter-level .pill').forEach((button) => {
        button.classList.toggle('active', button.dataset.level === filters.level);
    });
}

// ── State picker (name or abbreviation search) ───────────────────────────

function wireStatePicker() {
    const trigger = document.getElementById('state-trigger');
    const panel = document.getElementById('state-panel');
    const search = document.getElementById('state-search');
    const options = document.getElementById('state-options');

    trigger.addEventListener('click', () => {
        const opening = panel.classList.contains('hidden');
        panel.classList.toggle('hidden', !opening);
        trigger.setAttribute('aria-expanded', String(opening));
        if (opening) {
            search.value = '';
            search.focus();
            renderStateList('');
        }
    });

    document.addEventListener('click', (event) => {
        if (!document.getElementById('state-picker').contains(event.target)) {
            panel.classList.add('hidden');
            trigger.setAttribute('aria-expanded', 'false');
        }
    });

    search.addEventListener('input', (event) => renderStateList(event.target.value));

    options.addEventListener('change', () => {
        filters.states = new Set(
            Array.from(options.querySelectorAll('input:checked')).map((input) => input.value));
        syncStateTrigger();
        apply();
    });

    document.getElementById('state-clear').addEventListener('click', () => {
        filters.states = new Set();
        syncStateCheckboxes();
        syncStateTrigger();
        apply();
    });
}

function renderStateList(query) {
    const needle = query.trim().toLowerCase();
    const filtered = stateCounts.filter(([state]) =>
        state.toLowerCase().includes(needle) ||
        stateAbbreviation(state).toLowerCase().includes(needle));
    document.getElementById('state-options').innerHTML = renderStateOptions(filtered);
    syncStateCheckboxes();
}

function syncStateCheckboxes() {
    document.querySelectorAll('#state-options input[type="checkbox"]').forEach((input) => {
        input.checked = filters.states.has(input.value);
    });
}

function syncStateTrigger() {
    const count = filters.states.size;
    document.getElementById('state-trigger').textContent =
        count === 0 ? 'All states ▾' : `${count} state${count > 1 ? 's' : ''} ▾`;
}

// ── Active filter pills ──────────────────────────────────────────────────

function wireActiveFilters() {
    document.getElementById('active-filters').addEventListener('click', (event) => {
        const pill = event.target.closest('.filter-pill');
        if (!pill) return;
        removeOneFilter(pill.dataset);
        document.getElementById('filter-q').value = filters.q;
        syncLevelButtons();
        syncChips();
        syncStateCheckboxes();
        syncStateTrigger();
        apply();
    });
}

function removeOneFilter(data) {
    if (data.removesLevel !== undefined) filters.level = '';
    if (data.removesState) filters.states.delete(data.removesState);
    if (data.removesTopicInclude) filters.topicsInclude.delete(data.removesTopicInclude);
    if (data.removesTopicExclude) filters.topicsExclude.delete(data.removesTopicExclude);
    if (data.removesQuery) {
        const rawTokens = rawQueryTerms.filter((raw) => raw !== data.removesQuery);
        filters.q = rawTokens.join(' ');
    }
}

// ── Clear / tips / download ──────────────────────────────────────────────

function wireUtilityButtons() {
    document.getElementById('filter-clear').addEventListener('click', () => {
        filters.clear();
        document.getElementById('filter-q').value = '';
        syncLevelButtons();
        syncChips();
        syncStateCheckboxes();
        syncStateTrigger();
        apply();
    });

    document.getElementById('tips-toggle').addEventListener('click', () => {
        const panel = document.getElementById('tips-panel');
        const opening = panel.classList.contains('hidden');
        panel.classList.toggle('hidden', !opening);
        document.getElementById('tips-toggle').setAttribute('aria-expanded', String(opening));
    });

    document.getElementById('filter-download').addEventListener('click', downloadFiltered);
}

function downloadFiltered() {
    const entries = matchedEntries();
    if (!entries.length) return;
    const blob = new Blob([buildCsv(entries)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `campaign-volunteer-directory-${stamp()}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
}

function stamp() {
    return new Date().toISOString().replace(/[-:]/g, '').slice(0, 13);
}

// ── Cards ────────────────────────────────────────────────────────────────

function wireCardExpansion() {
    document.getElementById('cards').addEventListener('click', (event) => {
        const card = event.target.closest('.card');
        if (!card || !event.target.closest('.card-head')) return;
        const willOpen = !card.classList.contains('open');
        document.querySelectorAll('.card.open').forEach((open) => open.classList.remove('open'));
        if (willOpen) card.classList.add('open');
    });
}

// ── Boot ─────────────────────────────────────────────────────────────────

async function loadData() {
    const unique = Math.floor(Date.now() / 60000);
    const response = await fetch(`data/candidates.json?unique=${unique}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
}

async function boot() {
    // Stale-HTML guard: versioned assets are fetched fresh by the browser,
    // but index.html itself can come from cache and mismatch the JS (missing
    // element IDs → crash). If a required element is missing, bounce once to
    // a versioned URL to force a fresh HTML fetch. writeToUrl() then strips
    // the marker on the first filter change.
    if (!document.getElementById('stat-total-sub') && !location.search.includes('v=')) {
        location.replace(`${location.pathname}?v=${APP_VERSION}`);
        return;
    }

    try {
        const data = await loadData();
        candidates = data.candidates || [];
        searchIndex = buildSearchIndex(candidates);
        topicCounts = topicCountsFrom(candidates);
        stateCounts = stateCountsFrom(candidates);

        renderStats(data);
        document.getElementById('filter-topics').innerHTML = renderTopicChips(topicCounts);

        filters.readFromUrl();
        wireQueryBox();
        wireGlobalShortcuts();
        wireTopicChips();
        wireLevelPills();
        wireStatePicker();
        wireActiveFilters();
        wireUtilityButtons();
        wireCardExpansion();
        syncChips();
        syncLevelButtons();
        syncStateCheckboxes();
        syncStateTrigger();
        apply();
    } catch (error) {
        document.getElementById('collection-date').textContent = 'failed to load data';
        console.error('Directory load failed:', error);
    }
}

boot();
