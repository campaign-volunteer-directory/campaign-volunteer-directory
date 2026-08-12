#!/usr/bin/env python3
"""Deterministic analysis of scraped Discord data: who's who, patterns, links.

Usage: python3 analyze.py [DIR]

Prints per-channel message counts, top authors, most-linked domains, and a
rolling activity view. All deterministic — no network, no LLM.
"""
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DIR = HERE.parent.parent / "scratch" / "discord"


def load_all(data_dir):
    channels = {}
    for f in sorted(data_dir.glob("*.json")):
        if f.name == "scrape.log":
            continue
        try:
            channels[f.stem] = json.loads(f.read_text())
        except Exception as e:
            print(f"  (skipping {f.name}: {e})", file=sys.stderr)
    return channels


def clean_author(name):
    return (name or "").strip() or "(unknown)"


def analyze(data_dir):
    channels = load_all(data_dir)
    print(f"channels: {len(channels)}")
    print(f"{'channel':<34} {'msgs':>5}  top authors")
    for name, msgs in sorted(channels.items(), key=lambda kv: -len(kv[1])):
        authors = Counter(clean_author(m["author"]) for m in msgs)
        top = ", ".join(f"{a}×{c}" for a, c in authors.most_common(3))
        print(f"{name:<34} {len(msgs):>5}  {top}")

    all_msgs = [m for msgs in channels.values() for m in msgs]
    print(f"\ntotal messages: {len(all_msgs)}")

    authors = Counter(clean_author(m["author"]) for m in all_msgs)
    print("\nwho's who (top 25 authors):")
    for a, c in authors.most_common(25):
        print(f"  {c:>4}  {a}")

    domains = Counter()
    for m in all_msgs:
        for link in m.get("links", []):
            try:
                domain = link.split("/")[2].lower()
            except Exception:
                continue
            if "discord.com" in domain or "discord.gg" in domain:
                continue
            domains[domain] += 1
    print("\ntop link domains:")
    for d, c in domains.most_common(12):
        print(f"  {c:>4}  {d}")

    # candidate-ish authors: names containing for/district or a state abbrev
    candidates = Counter()
    for name, msgs in channels.items():
        for m in msgs:
            a = clean_author(m["author"])
            if any(k in a for k in (" for ", "for ", "District", "Congress")):
                candidates[a] += 1
    if candidates:
        print("\nlikely candidate accounts:")
        for a, c in candidates.most_common(20):
            print(f"  {c:>3}  {a}")


def main():
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    analyze(data_dir)


if __name__ == "__main__":
    main()
