#!/usr/bin/env python3
"""Build docs/data/candidates.json from the published Campaign Volunteer Directory sheet.

Fetches the CSV export of the Google Sheet (published to web), normalizes
states, validates required fields, detects problems (duplicates, missing
data, abrupt row-count changes) and writes:

  docs/data/candidates.json  - full normalized dataset + summary stats
  docs/data/sync-meta.json   - sync metadata (previous count, issues)

The workflow fails the run if the data fails hard validation, so GitHub Pages
never publishes a broken or emptied index.
"""

import csv
import io
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"

SOURCE_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vQyQUWTOqZ6iqYMXd-GpkXivMRIgGCnkL58y-oLrX53e8M68zdQo5xO1P8LEMd06mpOVxshd0F9aC24/"
    "pub?gid=0&single=true&output=csv"
)

EXPECTED_HEADER = [
    "Name:", "State:", "Govt Level:", "Position:", "Running as a:",
    "District Location:", "Stances Include (but at not limited to):",
    "Find more info:", "How to sign up to Volunteer:",
]

# State abbreviations -> full names (sheet mixes "AR", "Alabama", "Connecticut- 04", ...)
STATE_MAP = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

LEVELS = {"Local", "State", "Federal"}


def normalize_state(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    key = raw.upper().split("-")[0].split(",")[0].strip()
    if key in STATE_MAP:
        return STATE_MAP[key]
    # "Connecticut- 04" style or already full names
    title = raw.title().replace("- ", "-")
    if title in STATE_MAP.values():
        return title
    return title


def normalize_level(raw: str) -> str:
    raw = raw.strip().lower()
    if "local" in raw:
        return "Local"
    if "state" in raw:
        return "State"
    if "federal" in raw:
        return "Federal"
    return raw


def fetch_csv() -> str:
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8-sig")


def parse_rows(raw: str):
    reader = csv.reader(io.StringIO(raw))
    rows = [r for r in reader if any(c.strip() for c in r)]
    header_idx = None
    for i, row in enumerate(rows[:8]):
        if [c.strip() for c in row[:9]] == EXPECTED_HEADER:
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Could not locate the candidate header row in the sheet")
    records = []
    for row in rows[header_idx + 1:]:
        cells = (row + [""] * 9)[:9]
        rec = {
            "name": cells[0].strip(),
            "state": normalize_state(cells[1]),
            "govt_level": normalize_level(cells[2]),
            "position": cells[3].strip(),
            "party": cells[4].strip(),
            "district": cells[5].strip(),
            "stances": cells[6].strip(),
            "info": cells[7].strip(),
            "volunteer": cells[8].strip(),
        }
        if rec["name"]:
            records.append(rec)
    return records


def validate(records, prev_count):
    issues = []
    if not records:
        issues.append("FATAL: zero candidate rows parsed")
    if prev_count and len(records) < prev_count * 0.5:
        issues.append(
            f"FATAL: row count dropped from {prev_count} to {len(records)} "
            "(>50% loss, refusing to publish)"
        )
    seen = {}
    for i, r in enumerate(records):
        for field in ("name", "state", "position"):
            if not r[field]:
                issues.append(f"row {i + 1}: missing {field}")
        if r["govt_level"] not in LEVELS:
            issues.append(f"row {i + 1}: unknown govt level {r['govt_level']!r}")
        key = (r["name"].lower(), r["state"].lower(), r["position"].lower())
        if key in seen:
            issues.append(f"row {i + 1}: duplicate of row {seen[key]} ({r['name']})")
        else:
            seen[key] = i + 1
    return issues


def main():
    try:
        raw = fetch_csv()
    except Exception as e:
        print(f"ERROR: failed to fetch sheet: {e}", file=sys.stderr)
        return 1

    records = parse_rows(raw)

    prev_count = None
    meta_path = DATA_DIR / "sync-meta.json"
    if meta_path.exists():
        prev_count = json.loads(meta_path.read_text()).get("count")

    issues = validate(records, prev_count)
    for issue in issues:
        print(f"issue: {issue}")

    fatal = [i for i in issues if i.startswith("FATAL")]
    if fatal:
        print("ABORT: refusing to publish broken index", file=sys.stderr)
        return 1

    states = sorted({r["state"] for r in records if r["state"]})
    by_level = Counter(r["govt_level"] for r in records)

    DATA_DIR.mkdir(exist_ok=True)
    # Reuse the previous timestamp when the dataset is unchanged, so a
    # timestamp-only diff can't leave "TBD" on the live site or churn commits.
    prev_updated_at = None
    prev_path = DATA_DIR / "candidates.json"
    if prev_path.exists():
        try:
            prev_payload = json.loads(prev_path.read_text())
            prev_payload.pop("updated_at", None)
            prev_updated_at = prev_payload
        except Exception:
            prev_updated_at = None
    payload = {
        "source": "Campaign Volunteer Directory by Lime Accordion",
        "source_url": "https://linktr.ee/limeaccordion",
        "sheet_url": SOURCE_URL.split("?")[0].replace("/pub", "/pubhtml"),
        # replaced with a commit-time stamp by the workflow on real data changes
        "updated_at": "TBD",
        "count": len(records),
        "states": states,
        "by_level": dict(by_level),
        "issues": issues,
        "candidates": records,
    }
    if prev_updated_at is not None:
        new_payload = dict(payload)
        new_payload.pop("updated_at", None)
        if new_payload == prev_updated_at:
            old = json.loads(prev_path.read_text())
            payload["updated_at"] = old.get("updated_at", "TBD")
    (DATA_DIR / "candidates.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False)
    )
    (DATA_DIR / "sync-meta.json").write_text(
        json.dumps({"count": len(records)}, indent=1)
    )
    print(f"OK: {len(records)} candidates, {len(states)} states, {len(issues)} issues")
    return 0


if __name__ == "__main__":
    sys.exit(main())
