import { escapeHtml, firstUrl, firstEmail } from './utils.js?v=4';
import { highlightTerms } from './highlight.js?v=4';

/**
 * Pure render helpers: every function maps data to HTML strings.
 * No DOM access, no event wiring — keep rendering testable and predictable.
 */

export function renderStats(data) {
    const byLevel = data.by_level || {};
    setText('stat-total', data.count);
    setText('stat-states', data.states.length);
    setText('stat-federal', byLevel.Federal || 0);
    setText('stat-state', byLevel.State || 0);
    setText('stat-local', byLevel.Local || 0);
    setText('collection-date', (data.updated_at || '').replace('T', ' ').slice(0, 16) || 'unknown');
}

export function renderStateOptions(states) {
    return states
        .map((state) => `<option value="${escapeHtml(state)}">${escapeHtml(state)}</option>`)
        .join('');
}

export function renderTopicChips(topicsWithCounts) {
    return topicsWithCounts
        .map(([topic, count]) =>
            `<button class="chip" data-topic="${escapeHtml(topic)}">` +
            `${escapeHtml(topic)} <span class="chip-count">${count}</span></button>`)
        .join('');
}

export function renderResultsLine(matchCount, total) {
    return `${matchCount} of ${total} candidates`;
}

export function renderCards(entries, terms) {
    if (!entries.length) {
        return '<div class="empty-state">No candidates match these filters.</div>';
    }
    return entries.map((entry) => cardMarkup(entry, terms)).join('');
}

function cardMarkup({ candidate: c }, terms) {
    const tags = (c.topics || []).map((t) => `<span class="topic">${escapeHtml(t)}</span>`).join('');
    const badges = [
        badge(c.govt_level, `level-${escapeHtml(c.govt_level)}`),
        badge(c.state),
        c.party ? badge(c.party) : '',
    ].join('');
    return `
        <article class="card">
            <div class="card-head" role="button" aria-expanded="false">
                <div class="card-main">
                    <div class="card-name">${highlightTerms(c.name, terms)}</div>
                    <div class="card-meta">${highlightTerms(c.position, terms)}</div>
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
    return firstUrl(rawText) || (firstEmail(rawText) ? `mailto:${firstEmail(rawText)}` : '');
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
    document.getElementById(id).textContent = value;
}
