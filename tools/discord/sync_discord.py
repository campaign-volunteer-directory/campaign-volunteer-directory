#!/usr/bin/env python3
"""Daily sync of the Lime Accordion Discord server into scratch/discord/.

Deterministic pipeline:
  1. bridge daemon healthy? find a logged-in Discord tab, read session token
  2. per channel: incremental pull (newest-first, stop at last known id)
  3. threads: discover active + archived public, pull each too
  4. download new media into the content-addressed store (dedupe)
  5. write sync-state.json (per-channel cursors) + status.json
  6. optional: escalate to a headless agent session for analysis of what's new
  7. ntfy alert on failure or on new content

Usage: python3 sync_discord.py [--agentic] [--full]
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from media_store import MediaStore, fetch_bytes, sha256, ext_of, kind_of  # noqa: E402
import scrape_api  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = ROOT / "scratch" / "discord"
STATUS = Path.home() / ".cache" / "campaign-volunteer-directory" / "status.json"
DAEMON = "http://127.0.0.1:8224"

CHANNELS = json.loads((HERE / "channels.json").read_text())["channels"]


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_status(state):
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(STATUS)


def load_state():
    state_path = OUT / "sync-state.json"
    if state_path.exists():
        return json.loads(state_path.read_text())
    return {}


def save_state(state):
    (OUT / "sync-state.json").write_text(json.dumps(state, indent=1))


def find_tab_and_token():
    """Find a live Discord tab, return (tab_id, token)."""
    state = json.load(urllib.request.urlopen(f"{DAEMON}/state", timeout=10))
    now = time.time()
    for t in state["tabs"]:
        url = t.get("url") or ""
        if "discord.com" in url and now - t.get("last_seen", 0) < 600:
            try:
                token = scrape_api.get_token(t["tab_id"])
                return t["tab_id"], token
            except Exception:
                continue
    raise RuntimeError("no logged-in Discord tab found (bridge enabled, logged in, recent)")


def download_media(records, channel, store, token):
    downloaded = deduped = 0
    for m in records:
        msg_id = m.get("id") or "msg"
        for item in m.get("media", []):
            if item.get("local"):
                continue
            url = item["url"]
            known = store.known_url(channel, msg_id, url)
            if known:
                item["local"] = known[1]
                deduped += 1
                continue
            try:
                req = urllib.request.Request(url, headers={"Authorization": token, "User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = resp.read(50 * 1024 * 1024 + 1)
                if len(data) > 50 * 1024 * 1024:
                    raise ValueError("too big")
            except Exception:
                continue
            digest = sha256(data)
            existing = store.lookup_hash(digest)
            if existing:
                item["local"] = existing
                deduped += 1
            else:
                blob = store.blob_root / f"{digest}.{ext_of(url)}"
                blob.write_bytes(data)
                item["local"] = str(blob)
                downloaded += 1
            store.add(channel, msg_id, url, digest, len(data), kind_of(url), ext_of(url), item["local"], m.get("ts", ""))
    return downloaded, deduped


def agentic_summary(new_total, report_path):
    """Escalate to a headless agent session to analyze the new messages.

    Tries `opencode run` (deepseek on the opencode-go subscription, the same
    setup as an interactive session); falls back to `claude -p`; then plain
    skip. The prompt constrains the agent to read-only analysis + report."""
    prompt = (
        f"{new_total} new Discord messages were synced into scratch/discord/ "
        "(channel JSON files with {id, author, ts, content, links, media}). "
        "Analyze ONLY messages with ts after the last report date, then: "
        "1) summarize notable conversations/patterns in 3-6 bullets, "
        "2) update the candidate coverage gap list (candidate accounts vs "
        "docs/data/candidates.json names), 3) append a dated section to the "
        f"report file {report_path}. Be concise. Do not post anything anywhere."
    )
    attempts = [
        ["opencode", "run", "--command", prompt, str(report_path)],
        ["claude", "-p", prompt + f"\n\nAppend to: {report_path}"],
    ]
    for cmd in attempts:
        try:
            result = subprocess.run(cmd, timeout=1800, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"agentic analysis done via {cmd[0]}")
                return
            print(f"agentic via {cmd[0]} failed (rc={result.returncode}): {result.stderr[:120]}")
        except Exception as e:
            print(f"agentic via {cmd[0]} failed: {e}")
    print("agentic analysis skipped (no working headless agent)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agentic", action="store_true", help="run headless agent analysis after sync")
    ap.add_argument("--full", action="store_true", help="re-pull everything, ignore cursors")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    store = MediaStore(OUT / "media.db", OUT / "media" / "blobs")
    state = load_state()
    start = utcnow()
    new_total = 0
    errors = []

    try:
        tab_id, token = find_tab_and_token()
        for ch in CHANNELS:
            cursor = None if args.full else state.get("channels", {}).get(ch["id"])
            try:
                records = scrape_api.scrape_channel(token, ch["id"], newest_known=cursor)
            except Exception as e:
                errors.append(f"{ch['name']}: {e}")
                continue
            if not records:
                continue
            dl, dd = download_media(records, ch["name"], store, token)
            new_total += len(records)
            state.setdefault("channels", {})[ch["id"]] = records[0]["id"]
            path = OUT / f"{ch['name']}.json"
            existing = json.loads(path.read_text()) if path.exists() else []
            merged = {m["id"]: m for m in existing}
            for m in records:
                merged[m["id"]] = m
            path.write_text(json.dumps(sorted(merged.values(), key=lambda m: m.get("ts") or ""), ensure_ascii=False, indent=1))
            print(f"{ch['name']}: +{len(records)} (media +{dl} new, {dd} deduped)", flush=True)

        # threads
        for ch in CHANNELS:
            try:
                for thread in scrape_api.list_threads(token, ch["id"]):
                    cursor = None if args.full else state.get("threads", {}).get(thread["id"])
                    records = scrape_api.scrape_channel(token, thread["id"], newest_known=cursor)
                    if records:
                        dl, dd = download_media(records, f"{ch['name']}::thread", store, token)
                        new_total += len(records)
                        state.setdefault("threads", {})[thread["id"]] = records[0]["id"]
                        path = OUT / f"thread-{thread['id']}.json"
                        path.write_text(json.dumps(records, ensure_ascii=False, indent=1))
                        print(f"  thread {thread['name'][:30]}: +{len(records)}", flush=True)
            except Exception:
                pass
    except Exception as e:
        errors.append(str(e))

    save_state(state)
    write_status({
        "last_run": start,
        "finished": utcnow(),
        "new_messages": new_total,
        "errors": errors,
    })
    print(f"sync done: +{new_total} new messages, errors: {errors or 'none'}")

    if new_total:
        subprocess.run(["alert", "ntfy", "Discord sync", f"Lime Accordion server: {new_total} new messages synced"], timeout=60)
    if errors:
        subprocess.run(["alert", "ntfy", "Discord sync FAILED", "; ".join(errors)[:200], "--priority", "high"], timeout=60)

    if args.agentic and new_total:
        report = OUT / "reports" / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
        report.parent.mkdir(exist_ok=True)
        agentic_summary(new_total, report)


if __name__ == "__main__":
    main()
