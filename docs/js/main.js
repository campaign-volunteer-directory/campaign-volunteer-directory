import { debounce } from './utils.js?v=4';
import { parseQuery, buildSearchIndex, searchRanked } from './search.js?v=4';
import { FilterState, matchesFacets } from './filters.js?v=4';
import {
    renderStats,
    renderStateOptions,
    renderTopicChips,
    renderResultsLine,
    renderCards,
} from './render.js?v=4';

const SEARCH_DEBOUNCE_MS = 120;

let candidates = [];
let searchIndex = [];
let topicCounts = [];
const filters = new FilterState();

function topicCountsFrom(candidates) {
    const counts = {};
    for (const candidate of candidates) {
        for (const topic of candidate.topics || []) {
            counts[topic] = (counts[topic] || 0) + 1;
        }
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
}

function queryTerms() {
    return parseQuery(filters.q);
}

function matchedEntries() {
    const faceted = searchIndex.filter((entry) => matchesFacets(entry.candidate, filters));
    return searchRanked(faceted, queryTerms());
}

function apply() {
    const entries = matchedEntries();
    document.getElementById('filter-results').textContent =
        renderResultsLine(entries.length, candidates.length);
    document.getElementById('filter-clear').classList.toggle('hidden', !filters.isActive);
    document.getElementById('cards').innerHTML =
        renderCards(entries, queryTerms().map((term) => term.text));
    filters.writeToUrl();
}

// ── Controls ────────────────────────────────────────────────────────────

function wireControls() {
    const searchInput = document.getElementById('filter-q');
    searchInput.addEventListener('input', debounce((event) => {
        filters.q = event.target.value;
        apply();
    }, SEARCH_DEBOUNCE_MS));

    document.getElementById('filter-level').addEventListener('click', (event) => {
        const button = event.target.closest('.pill');
        if (!button) return;
        filters.level = button.dataset.level;
        syncLevelButtons();
        apply();
    });

    document.getElementById('filter-state').addEventListener('change', (event) => {
        filters.states = event.target.value ? new Set([event.target.value]) : new Set();
        apply();
    });

    document.getElementById('filter-topics').addEventListener('click', (event) => {
        const chip = event.target.closest('.chip');
        if (!chip) return;
        const topic = chip.dataset.topic;
        if (filters.topics.has(topic)) filters.topics.delete(topic);
        else filters.topics.add(topic);
        chip.classList.toggle('active', filters.topics.has(topic));
        apply();
    });

    document.getElementById('filter-clear').addEventListener('click', () => {
        filters.clear();
        document.getElementById('filter-q').value = '';
        document.getElementById('filter-state').value = '';
        syncLevelButtons();
        document.querySelectorAll('#filter-topics .chip').forEach((chip) => {
            chip.classList.remove('active');
        });
        apply();
    });
}

function syncLevelButtons() {
    document.querySelectorAll('#filter-level .pill').forEach((button) => {
        button.classList.toggle('active', button.dataset.level === filters.level);
    });
}

function restoreControls() {
    document.getElementById('filter-q').value = filters.q;
    document.getElementById('filter-state').value = filters.states.size === 1 ? [...filters.states][0] : '';
    syncLevelButtons();
    document.querySelectorAll('#filter-topics .chip').forEach((chip) => {
        chip.classList.toggle('active', filters.topics.has(chip.dataset.topic));
    });
}

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
    try {
        const data = await loadData();
        candidates = data.candidates || [];
        searchIndex = buildSearchIndex(candidates);
        topicCounts = topicCountsFrom(candidates);

        renderStats(data);
        document.getElementById('filter-state').innerHTML =
            `<option value="">All states</option>` + renderStateOptions(data.states);
        document.getElementById('filter-topics').innerHTML = renderTopicChips(topicCounts);

        filters.readFromUrl();
        wireControls();
        wireCardExpansion();
        restoreControls();
        apply();
    } catch (error) {
        document.getElementById('collection-date').textContent = 'failed to load data';
        console.error('Directory load failed:', error);
    }
}

boot();
