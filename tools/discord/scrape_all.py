#!/usr/bin/env python3
"""Scrape every channel in channels.json via the chrome-bridge daemon,
distributed round-robin across multiple bridge-enabled Discord tabs.

Usage: python3 scrape_all.py --tabs 9,13,1376457635,1376457636 [--out DIR] [--only c1,c2]

Requires: chrome-bridge daemon (localhost:8224), N Chrome tabs with the bridge
enabled on the Discord server (one per --tabs entry), nobody touching the tabs
while this runs.

Output: one JSON file per channel (messages + media URLs, media files under
media/<channel>/), plus scrape.log in the output dir.
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
        [sys.executable, str(HERE / "scrape_channel.py"), str(tab_id), channel["id"], str(out_path)],
        capture_output=True, text=True, timeout=1800)
    tail = (result.stderr or result.stdout).strip().splitlines()
    return result.returncode, tail[-1:] if tail else [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tabs", required=True, help="comma-separated tab ids")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    tabs = [int(t) for t in args.tabs.split(",") if t.strip()]
    if not tabs:
        sys.exit("no tabs given")

    server_id, channels = load_channels()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    only = {c.strip() for c in args.only.split(",") if c.strip()}
    targets = [c for c in channels if not only or c["name"] in only]

    log = out_dir / "scrape.log"
    with open(log, "a") as f:
        f.write(f"\n=== parallel scrape started {time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"({len(targets)} channels, {len(tabs)} tabs) ===\n")

    # Round-robin channel -> tab, then run one subprocess per channel with
    # all tabs busy concurrently. Each channel retries (up to 3x) rotating
    # to the next tab, since tabs stall under sustained load.
    jobs = []
    for i, channel in enumerate(targets):
        tab = tabs[i % len(tabs)]
        out_path = out_dir / f"{channel['name']}.json"
        jobs.append((tab, channel, out_path))

    results = {}
    procs = []
    queue = list(jobs)
    while queue or procs:
        while len(procs) < len(tabs) and queue:
            tab, channel, out_path = queue.pop(0)
            p = subprocess.Popen(
                [sys.executable, str(HERE / "scrape_channel.py"), str(tab), channel["id"], str(out_path)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            procs.append((p, channel, tab))
        done = [j for j in procs if j[0].poll() is not None]
        for p, channel, tab in done:
            procs.remove((p, channel, tab))
            out, _ = p.communicate()
            out_path = out_dir / f"{channel['name']}.json"
            n = 0
            if out_path.exists():
                try:
                    n = len(json.loads(out_path.read_text()))
                except Exception:
                    n = -1
            attempts = 1
            while p.returncode != 0 and attempts < 3 and n == 0:
                # stall recovery: retry on the next tab after a pause
                attempts += 1
                time.sleep(20)
                ntab = tabs[(tabs.index(tab) + 1) % len(tabs)]
                rc2, _ = scrape_one(ntab, server_id, channel, out_path)
                p = type("R", (), {"returncode": rc2})()
                if out_path.exists():
                    try:
                        n = len(json.loads(out_path.read_text()))
                    except Exception:
                        n = -1
            line = f"{channel['name']}: rc={p.returncode} attempts={attempts} messages={n} {out.strip().splitlines()[-1:] if out.strip() else ''}"
            print(line, flush=True)
            with open(log, "a") as f:
                f.write(line + "\n")
        time.sleep(2)

    print(f"done -> {out_dir}")


if __name__ == "__main__":
    main()
