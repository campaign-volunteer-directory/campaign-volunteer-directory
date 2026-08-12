#!/usr/bin/env python3
"""Scrape Discord channels via Discord's REST API using the session token
read from the bridge-enabled tab's localStorage. Complete, deterministic,
no DOM scrolling.

Usage: python3 scrape_api.py <tab_id> [channel_ids...] [--out DIR]

Message shape: {id, author, ts, content, links, media:[{url,kind,filename,size}]}
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

DAEMON = "http://127.0.0.1:8224"
API = "https://discord.com/api/v10/channels/{ch}/messages?limit=100{before}"
MAX_PAGES = 2000
URL_RE = re.compile(r"https?://[^\s<>\"']+")


def bridge(tab_id, cmd_type, payload=None, timeout=30):
    body = json.dumps({"tab_id": int(tab_id), "cmd_type": cmd_type,
                       "payload": payload or {}}).encode()
    req = urllib.request.Request(f"{DAEMON}/enqueue", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        enq = json.load(resp)
    url = f"{DAEMON}/await_result?tab_id={enq['tab_id']}&cmd_id={enq['cmd_id']}&timeout_ms={timeout * 1000}"
    with urllib.request.urlopen(url, timeout=timeout + 10) as resp:
        return json.load(resp)


def get_token(tab_id):
    """Read the Discord session token from the tab's localStorage.

    The multi-account `tokens` map holds the live session token; the plain
    `token` key can be stale (kept after logout), so it is only a fallback."""
    result = bridge(tab_id, "STORAGE_GET", {"kind": "local"})
    items = result.get("items") or {}
    token = None
    tokens = json.loads(items.get("tokens") or "{}")
    for key, value in tokens.items():
        if key != "__analytics__":
            token = value
            break
    if not token:
        token = items.get("token")
    if not token:
        raise RuntimeError("no token in tab localStorage — is this tab logged into Discord?")
    return token


def fetch_page(token, channel, before):
    url = API.format(ch=channel, before=f"&before={before}" if before else "")
    req = urllib.request.Request(url, headers={
        "Authorization": token,
        "User-Agent": "Mozilla/5.0",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        return json.load(resp)


def to_record(m):
    author = (m.get("author") or {}).get("username") or ""
    content = m.get("content") or ""
    links = list(dict.fromkeys(URL_RE.findall(content)))
    for e in m.get("embeds") or []:
        if e.get("url"):
            links.append(e["url"])
    media = []
    for a in m.get("attachments") or []:
        url = a.get("url")
        if not url:
            continue
        filename = (a.get("filename") or "").lower()
        if any(filename.endswith(x) for x in ("png", "jpg", "jpeg", "gif", "webp")):
            kind = "image"
        elif any(filename.endswith(x) for x in ("mp4", "webm", "mov")):
            kind = "video"
        else:
            kind = "file"
        media.append({"url": url, "kind": kind, "filename": a.get("filename"),
                      "size": a.get("size")})
    return {"id": m.get("id") or "", "author": author, "ts": m.get("timestamp") or "",
            "content": content, "links": list(dict.fromkeys(links)), "media": media}


def scrape_channel(token, channel_id):
    records = []
    before = None
    for _ in range(MAX_PAGES):
        msgs = fetch_page(token, channel_id, before)
        if not msgs:
            break
        records.extend(to_record(m) for m in msgs)
        if len(msgs) < 100:
            break
        before = msgs[-1]["id"]
        time.sleep(0.3)
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tab_id")
    ap.add_argument("channel_ids", nargs="*")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out_dir = Path(args.out) if args.out else Path(__file__).resolve().parent.parent.parent / "scratch" / "discord"
    out_dir.mkdir(parents=True, exist_ok=True)
    token = get_token(args.tab_id)

    channels = args.channel_ids or [c["id"] for c in
                                    json.loads((Path(__file__).resolve().parent / "channels.json").read_text())["channels"]]
    for ch in channels:
        records = scrape_channel(token, ch)
        out = out_dir / f"{ch}.json"
        out.write_text(json.dumps(records, ensure_ascii=False, indent=1))
        print(f"{ch}: {len(records)} messages -> {out.name}", flush=True)


if __name__ == "__main__":
    main()
