# Campaign Volunteer Directory

Progressive 2026 candidates across the US looking for volunteers — compiled by
[Lime Accordion](https://linktr.ee/limeaccordion).

Live site: https://campaign-volunteer-directory.github.io/campaign-volunteer-directory/

This is **not an endorsement** of any candidate. It is a collection of campaigns
who need help — research candidates before getting involved.

## Structure
- `docs/` — GitHub Pages site (browse/filter the directory)
- `docs/data/` — generated JSON index of candidates (auto-synced)
- `scripts/build_index.py` — fetches the published source spreadsheet, validates
  and normalizes the data, writes `docs/data/candidates.json`
- `.github/workflows/sync.yml` — twice-daily sync + validation + publish to Pages

## Updating
The data is pulled automatically from the public spreadsheet every 12 hours.
Candidates can add themselves via the sign-up form on
[Lime Accordion's linktree](https://linktr.ee/limeaccordion).

## Local build
```bash
python3 scripts/build_index.py   # fetch + validate + write docs/data/candidates.json
```

## Contributing
Bug reports and improvements via issues/PRs.
