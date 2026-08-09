(() => {
    const $table = $('#directory-table');
    let table;

    function linkCell(value, preferredLabel) {
        const v = (value || '').trim();
        if (!v) return '<span class="plain">—</span>';
        const urls = v.match(/https?:\/\/\S+/gi) || [];
        if (urls.length === 1) {
            const url = urls[0].replace(/[),.\]]+$/, '');
            return `<a class="url" href="${url}" target="_blank" rel="noopener noreferrer">${preferredLabel || url}</a>`;
        }
        return `<span class="plain">${v.replace(/</g, '&lt;')}</span>`;
    }

    function stateShort(name) {
        const map = {
            'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR',
            'California': 'CA', 'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE',
            'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI', 'Idaho': 'ID',
            'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA', 'Kansas': 'KS',
            'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME', 'Maryland': 'MD',
            'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN',
            'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE',
            'Nevada': 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ',
            'New Mexico': 'NM', 'New York': 'NY', 'North Carolina': 'NC',
            'North Dakota': 'ND', 'Ohio': 'OH', 'Oklahoma': 'OK', 'Oregon': 'OR',
            'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC',
            'South Dakota': 'SD', 'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT',
            'Vermont': 'VT', 'Virginia': 'VA', 'Washington': 'WA',
            'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY'
        };
        return map[name] || name;
    }

    function esc(s) {
        return String(s == null ? '' : s).replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    async function init() {
        try {
            const resp = await fetch('data/candidates.json');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            document.getElementById('collection-date').textContent =
                (data.updated_at || '').replace('T', ' ').slice(0, 16) || 'unknown';

            const byLevel = data.by_level || {};
            document.getElementById('stat-total').textContent = data.count;
            document.getElementById('stat-states').textContent = data.states.length;
            document.getElementById('stat-federal').textContent = byLevel.Federal || 0;
            document.getElementById('stat-state').textContent = byLevel.State || 0;
            document.getElementById('stat-local').textContent = byLevel.Local || 0;

            const rows = (data.candidates || []).map(c => [
                esc(c.name),
                esc(c.state),
                esc(c.govt_level),
                esc(c.position),
                esc(c.party),
                `<span class="district-cell">${esc(c.district)}</span>`,
                `<span class="stance-cell">${esc(c.stances)}</span>`,
                linkCell(c.info, 'site'),
                linkCell(c.volunteer, 'sign up')
            ]);

            table = $table.DataTable({
                data: rows,
                pageLength: 25,
                responsive: true,
                columnDefs: [
                    { orderable: false, targets: [5, 6, 7, 8] },
                    { className: 'dt-body-left', targets: '_all' },
                    { visible: false, targets: [1] }
                ],
                layout: {
                    top1: {
                        searchPanes: {
                            cascadePanes: true,
                            layout: 'columns-3',
                            columns: [1, 2]
                        }
                    }
                }
            });
        } catch (e) {
            document.getElementById('collection-date').textContent = 'failed to load data';
            console.error('Directory load failed:', e);
        }
    }

    init();
})();
