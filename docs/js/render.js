import { escapeHtml, firstUrl, firstEmail } from './utils.js?v=10';
import { highlightTerms } from './highlight.js?v=10';
import { stateAbbreviation } from './states.js?v=10';

/**
 * Pure render helpers: every function maps data to HTML strings (or, for
 * buildCsv, a CSV document). No DOM access, no event wiring — keep rendering
 * testable and predictable.
 */

export function renderStats(data) {
    setText('collection-date', (data.updated_at || '').replace('T', ' ').slice(0, 16) || 'unknown');
}

/**
 * The live summary bar: current counts with their values, plus clickable
 * level pills showing each level's share of the current view.
 */
export function renderSummary(entriesCount, statesCount, totals, levelCounts, levelFilter) {
    const pills = ['Federal', 'State', 'Local'].map((level) => {
        const active = levelFilter === level ? ' active' : '';
        const count = levelCounts[level] || 0;
        return `<button class="level-pill${active}" data-level="${level}">${level} <b>${count}</b></button>`;
    }).join('');

    return `
        <div class="summary-line">
            <b>${entriesCount}</b> of ${totals.candidates} candidates ·
            <b>${statesCount}</b> of ${totals.states} states
        </div>
        <div class="summary-levels">${pills}</div>`;
}

/**
 * The "in this view" breakdown: the actual state and issue values present in
 * the current result set, as clickable chips (click to add/remove that
 * filter). Top values only, "+N more" keeps the panel compact.
 */
export function renderBreakdown(statesInView, topicsInView, filters, TOP_N = 12) {
    if (!statesInView.length && !topicsInView.length) return '';

    const stateChips = chipsFor(statesInView, 'state', filters.states, TOP_N);
    const topicChips = chipsFor(topicsInView, 'topic', filters.topicsInclude, TOP_N);
    if (!stateChips && !topicChips) return '';

    return `
        <div class="breakdown-label">In this view</div>
        ${stateChips ? `<div class="breakdown-row">${stateChips}</div>` : ''}
        ${topicChips ? `<div class="breakdown-row">${topicChips}</div>` : ''}`;
}

function chipsFor(values, kind, activeSet, topN) {
    if (!values.length) return '';
    const chips = values.map(([label, count], index) => {
        const overflowClass = index >= topN ? ' chip-overflow' : '';
        const active = activeSet.has(label) ? ' active' : '';
        return `<button class="chip${active}${overflowClass}" data-breakdown="${kind}" data-value="${escapeHtml(label)}">${escapeHtml(label)} <span class="chip-count">${count}</span></button>`;
    }).join('');
    const rest = values.length - topN;
    if (rest <= 0) return chips;
    // Expandable "+N more": toggles .expanded on the row, revealing the
    // overflow chips (hidden via CSS until then).
    return chips + `<button class="chips-more" data-kind="${kind}" data-count="${rest}">+${rest} more</button>`;
}

export function renderResultsLine(matchCount, total) {
    return `${matchCount} of ${total} candidates`;
}

export function renderStateOptions(statesWithCounts) {
    return statesWithCounts
        .map(([state, count]) => `
            <label class="state-option">
                <input type="checkbox" value="${escapeHtml(state)}">
                <span>${escapeHtml(state)}</span>
                <span class="state-option-abbr">${escapeHtml(stateAbbreviation(state))}</span>
                <span class="state-option-count">${count}</span>
            </label>`)
        .join('');
}

export function renderTopicChips(topicsWithCounts) {
    return topicsWithCounts
        .map(([topic, count]) => `
            <button class="chip" data-topic="${escapeHtml(topic)}" title="Click to include · Shift-click to exclude">
                ${escapeHtml(topic)} <span class="chip-count">${count}</span>
            </button>`)
        .join('');
}

export function renderSuggestions(items) {
    return items
        .map((item) => `
            <button class="suggestion ${item.kind}" data-action="${item.kind}" data-value="${escapeHtml(item.value)}" role="option">
                <span class="suggestion-label">${escapeHtml(item.label)}</span>
                <span class="suggestion-sub">${escapeHtml(item.sub)}</span>
            </button>`)
        .join('');
}

export function renderCards(entries, terms, emptyMessage) {
    if (!entries.length) {
        return `<div class="empty-state">${escapeHtml(emptyMessage)}</div>`;
    }
    return entries.map((entry) => cardMarkup(entry, terms)).join('');
}

/**
 * The removable "active filter" pills: query terms (+/-), topics (+/-),
 * states and level. Each pill carries data-removes attributes the main
 * module uses to undo that single filter.
 */
export function renderActiveFilters(filters, rawQueryTerms) {
    const pills = [];

    for (const raw of rawQueryTerms) {
        const negated = raw.startsWith('-');
        pills.push(filterPill({
            label: raw,
            cls: negated ? 'filter-pill exclude' : 'filter-pill',
            removes: { query: raw },
        }));
    }
    for (const topic of filters.topicsInclude) {
        pills.push(filterPill({ label: `+${topic}`, cls: 'filter-pill', removes: { topicInclude: topic } }));
    }
    for (const topic of filters.topicsExclude) {
        pills.push(filterPill({ label: `−${topic}`, cls: 'filter-pill exclude', removes: { topicExclude: topic } }));
    }
    for (const state of filters.states) {
        pills.push(filterPill({
            label: `${state} (${stateAbbreviation(state)})`,
            cls: 'filter-pill',
            removes: { state },
        }));
    }
    if (filters.level) {
        pills.push(filterPill({ label: filters.level, cls: 'filter-pill', removes: { level: true } }));
    }
    return pills.join('');
}

function filterPill({ label, cls, removes }) {
    // Dashed attribute names so dataset keys map back to camelCase cleanly:
    // "topicInclude" -> data-removes-topic-include -> dataset.removesTopicInclude
    const attrs = Object.entries(removes)
        .map(([key, value]) => {
            const dashed = key.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
            return `data-removes-${dashed}="${escapeHtml(String(value))}"`;
        })
        .join(' ');
    return `<button class="${cls}" ${attrs} title="Remove this filter">${escapeHtml(label)} <span class="pill-x">×</span></button>`;
}

export function buildCsv(entries) {
    const header = [
        'Name', 'State', 'Level', 'Position', 'Party',
        'District / Location', 'Topics', 'Stances', 'Info', 'Volunteer',
    ];
    const rows = entries.map(({ candidate: c }) => [
        c.name, c.state, c.govt_level, c.position, c.party,
        c.district, (c.topics || []).join('; '), c.stances, c.info, c.volunteer,
    ]);
    const lines = [header, ...rows].map((row) => row.map(csvCell).join(','));
    return '\uFEFF' + lines.join('\r\n'); // BOM so Excel opens UTF-8 correctly
}

function csvCell(value) {
    const text = String(value == null ? '' : value);
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function cardMarkup({ candidate: c }, terms) {
    const tags = (c.topics || []).map((t) => `<span class="topic">${escapeHtml(t)}</span>`).join('');
    const badges = [
        badge(c.govt_level, `level-${escapeHtml(c.govt_level)}`),
        badge(c.state),
        c.party ? badge(c.party) : '',
    ].join('');
    const stanceExcerpt = excerpt(c.stances, 150);
    return `
        <article class="card">
            <div class="card-head" role="button" aria-expanded="false">
                <div class="card-main">
                    <div class="card-name">${highlightTerms(c.name, terms)}</div>
                    <div class="card-meta">${highlightTerms(c.position, terms)}</div>
                    ${stanceExcerpt ? `<div class="card-stance">${highlightTerms(stanceExcerpt, terms)}</div>` : ''}
                    <div class="card-badges">${badges}</div>
                    ${tags ? `<div class="card-badges">${tags}</div>` : ''}
                </div>
                <span class="card-chevron">▸</span>
            </div>
            <div class="card-details">
                <div class="detail-grid">
                    ${detailBlock('Stances', highlightTerms(c.stances, terms) || '—')}
                    ${detailBlock('District / Location', highlightTerms(c.district, terms) || '—')}
                    ${detailBlock('More info', linkify(c.info))}
                    ${detailBlock('Volunteer', linkify(c.volunteer))}
                </div>
                <div class="card-actions">
                    ${actionButton(c.info, 'Campaign site')}
                    ${actionButton(c.volunteer, 'Sign up to volunteer', 'btn-ghost-link')}
                </div>
            </div>
        </article>`;
}

/** First `max` characters of text, cut at a word boundary, with an ellipsis. */
function excerpt(text, max) {
    const source = String(text || '').replace(/\s+/g, ' ').trim();
    if (!source) return '';
    if (source.length <= max) return source;
    const cut = source.slice(0, max);
    const lastSpace = cut.lastIndexOf(' ');
    return (lastSpace > max * 0.6 ? cut.slice(0, lastSpace) : cut) + '…';
}

function badge(text, extraClass = '') {
    if (!text) return '';
    return `<span class="badge ${extraClass}">${escapeHtml(text)}</span>`;
}

function detailBlock(label, html) {
    return `<div class="detail-block">
        <div class="detail-label">${label}</div>
        <div class="detail-text">${html}</div>
    </div>`;
}

function actionButton(rawText, label, className = 'btn') {
    const href = linkTarget(rawText);
    if (!href) return '';
    return `<a class="${className}" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
}

function linkTarget(rawText) {
    const url = firstUrl(rawText);
    if (url) return url;
    const email = firstEmail(rawText);
    return email ? `mailto:${email}` : '';
}

function linkify(text) {
    if (!text) return '<span class="plain">—</span>';
    const tokens = String(text).split(/\s+/).filter(Boolean);
    const urlPattern = /^(https?:\/\/\S+)$/i;
    const emailPattern = /^[\w.+-]+@[\w-]+\.[\w.-]+$/;
    return tokens
        .map((token) => {
            if (urlPattern.test(token)) {
                const url = token.replace(/[),.\]]+$/, '');
                return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(url)}</a>`;
            }
            if (emailPattern.test(token)) {
                return `<a href="mailto:${escapeHtml(token)}">${escapeHtml(token)}</a>`;
            }
            return `<span class="plain">${escapeHtml(token)}</span>`;
        })
        .join(' ');
}

function setText(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
}
