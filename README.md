# Campaign Volunteer Directory

Progressive 2026 candidates across the US looking for volunteers.

Live site: https://campaign-volunteer-directory.github.io/campaign-volunteer-directory/

**Independent project** — not affiliated with, sponsored by, or endorsed by
Lime Accordion or any candidate. Data comes from the public campaign volunteer
spreadsheet. Listing here is **not an endorsement** — research candidates
before getting involved.

## Structure
- `docs/` — GitHub Pages site (browse/filter the directory)
- `docs/data/` — generated JSON index of candidates (auto-synced)
- `scripts/build_index.py` — fetches the published source spreadsheet, validates
  and normalizes the data, writes `docs/data/candidates.json`.

Issue categories come from the spreadsheet: if the sheet has an "Issues:"
column, its values are used verbatim (candidates self-tag). Without that
column, topics are keyword-tagged from the stances text as a fallback.
- `.github/workflows/sync.yml` — twice-daily sync + validation + publish to Pages

## Updating
The data is pulled automatically from the public spreadsheet every 12 hours.

## Issue categories
The site's topic chips are **terms from the spreadsheet itself**, never
invented labels:
- If the sheet has an `Issues:` column, its values are used verbatim
  (candidates self-tag).
- Otherwise, the vocabulary is extracted deterministically from the stance
  texts (`scripts/vocabulary.py`, yake keyphrase extraction) and each
  candidate is matched against it. No hand-written keyword lists.
- Optional: if a `FIREWORKS_API_KEY` secret is set, an LLM pass
  (`scripts/llm_topics.py`) tags the residual candidates, constrained to the
  same vocabulary — it may only pick terms that already exist in the data.

## Local build
```bash
python3 scripts/build_index.py   # fetch + validate + write docs/data/candidates.json
```

## Contributing
Bug reports and improvements via issues/PRs.
