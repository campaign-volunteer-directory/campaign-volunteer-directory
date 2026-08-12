#!/usr/bin/env python3
"""Read-only check for newly submitted candidates in the public sheet.

Fetches the spreadsheet, diffs against the committed docs/data/candidates.json
and prints any new candidates as JSON — used by the local daily sync to alert
on fresh signup-form submissions. Never writes anything.

Usage: python3 check_new_candidates.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_index  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    try:
        raw = build_index.fetch_csv().decode("utf-8-sig")
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        return 1
    records = build_index.parse_rows(raw, with_topics=False)
    new = build_index.find_new_candidates(records, ROOT / "docs" / "data" / "candidates.json")
    print(json.dumps({"count": len(new), "new_candidates": new}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
