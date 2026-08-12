#!/usr/bin/env python3
"""Scrape every channel in channels.json via the chrome-bridge daemon.

Usage: python3 scrape_all.py <tab_id> [--out DIR] [--only channel1,channel2]

Requires: chrome-bridge daemon running (localhost:8224), a Chrome tab with
the bridge enabled on the Discord server, and nobody touching that tab while
this runs (the scraper needs full control of the scroll position).

Output: one JSON file per channel: {channel}.json with
[{id, author, ts, content, links}] plus a scrape log in out_dir/../scrape.log
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE.parent.parent / "scratch" / "discord"


def load_channels():
    with open(HERE / "channels.json") as f:
        meta = json.load(f)
    return meta["server_id"], meta["channels"]


def scrape_one(tab_id, server_id, channel, out_path):
    url = f"https://discord.com/channels/{server_id}/{channel['id']}"
    result = subprocess.run(
        [sys.executable, str(HERE / "scrape_channel.py"), tab_id, channel["id"], str(out_path)],
        capture_output=True, text=True, timeout=1800)
    return result.returncode, (result.stderr or result.stdout).strip().splitlines()[-1:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tab_id")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    server_id, channels = load_channels()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    only = {c.strip() for c in args.only.split(",") if c.strip()}
    targets = [c for c in channels if not only or c["name"] in only]

    log = out_dir / "scrape.log"
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(log, "a") as f:
        f.write(f"\n=== scrape_all started {started} ({len(targets)} channels) ===\n")

    for channel in targets:
        out_path = out_dir / f"{channel['name']}.json"
        code, tail = scrape_one(args.tab_id, server_id, channel, out_path)
        n = 0
        if out_path.exists():
            try:
                n = len(json.loads(out_path.read_text()))
            except Exception:
                n = -1
        line = f"{channel['name']}: rc={code} messages={n} {tail}"
        print(line, flush=True)
        with open(log, "a") as f:
            f.write(line + "\n")
        time.sleep(2)

    print(f"done -> {out_dir}")


if __name__ == "__main__":
    main()
