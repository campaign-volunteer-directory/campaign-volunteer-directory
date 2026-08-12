#!/usr/bin/env python3
"""Scrape a Discord channel's full message history via the chrome-bridge daemon.

Usage: discord_scrape.py <tab_id> <channel_id> <out.json>

Scrolls to the top to load the full (virtualized) history, then walks the list
collecting structured messages: {id, author, ts, content, links[]}.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

from media_store import MediaStore, fetch_bytes, sha256, ext_of, kind_of

DAEMON = "http://127.0.0.1:8224"
CHANNEL_URL = "https://discord.com/channels/1450359255386554502/{ch}"

LIST_JS = "document.querySelector('[data-list-id=chat-messages]')"
SCROLL_JS = ("(function() { let el = document.querySelector('[data-list-id=chat-messages]'); "
             "for (let i = 0; i < 10 && el; i++) { if (el.scrollHeight > el.clientHeight) return el; "
             "el = el.parentElement; } return document.querySelector('[data-list-id=chat-messages]'); })()")


def rpc(tab_id, cmd_type, payload=None, timeout=40):
    body = json.dumps({"tab_id": int(tab_id), "cmd_type": cmd_type,
                       "payload": payload or {}}).encode()
    req = urllib.request.Request(f"{DAEMON}/enqueue", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        enq = json.load(resp)
    url = f"{DAEMON}/await_result?tab_id={enq['tab_id']}&cmd_id={enq['cmd_id']}&timeout_ms={timeout * 1000}"
    with urllib.request.urlopen(url, timeout=timeout + 10) as resp:
        result = json.load(resp)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result


def run_js(tab_id, code, attempts=5):
    last = None
    for i in range(attempts):
        try:
            result = rpc(tab_id, "EVAL", {"code": code})
            if "value" in result:
                return result["value"]
            last = f"no value: {json.dumps(result)[:150]}"
        except Exception as e:
            last = str(e)[:150]
        time.sleep(3)
    raise RuntimeError(f"run_js failed after {attempts}: {last}")


def scroller(tab_id):
    return run_js(tab_id, f"return ({SCROLL_JS})" )

def list_height(tab_id):
    return run_js(tab_id, f"return ({SCROLL_JS}).scrollHeight")


def scroll_to_top(tab_id, max_rounds=400):
    """Keep scrolling to the top until the list stops growing.

    Alternates scroll positions (0 / 80) so a scroll event always fires —
    setting scrollTop to 0 when it's already 0 triggers no event, and Discord
    only loads older history on real scroll events."""
    prev = 0
    for i in range(max_rounds):
        try:
            h = run_js(tab_id, f"return ({SCROLL_JS}.scrollTop = {i % 2 and 0 or 80}, ({SCROLL_JS}).scrollHeight)")
        except Exception:
            time.sleep(1.5)
            continue
        time.sleep(0.8)
        if h == prev:
            break
        prev = h
    return prev


def collect_messages(tab_id, max_passes=4):
    """Walk the list top->bottom, repeating until a full pass adds nothing new.

    Discord renders lazily: scrolling fast skips windows (React hasn't painted
    them yet). So we walk slowly, re-measuring the list height each step, and
    converge: each full pass from top to bottom collects everything currently
    in the DOM; when a pass adds zero new messages we're done.
    """
    seen = set()
    messages = []
    code = """
        const list = document.querySelector('[data-list-id=chat-messages]');
        const out = [];
        for (const art of list.querySelectorAll('li[id^="chat-messages-"], article')) {
            const id = art.id || art.getAttribute('data-list-item-id') || '';
            const authorEl = art.querySelector('h3 span[class*=username], span[class*=username]');
            const author = authorEl ? authorEl.textContent : '';
            const timeEl = art.querySelector('time');
            const ts = timeEl ? (timeEl.getAttribute('datetime') || timeEl.title || '') : '';
            const contentEl = art.querySelector('[id^="message-content-"], [class*=messageContent]');
            const content = contentEl ? contentEl.innerText : '';
            const links = [...(art.querySelectorAll('a[href^="http"]'))].map(a => a.href);
            const media = [];
            const addMedia = (rawUrl, kind) => {
                if (!rawUrl) return;
                let url = rawUrl.replace(/^https:\\/\\/media\\.discordapp\\.net/, 'https://cdn.discordapp.com');
                if (!media.some(m => m.url === url)) media.push({url, kind});
            };
            for (const a of art.querySelectorAll('a[href*="attachments"]')) {
                const href = a.getAttribute('href') || '';
                const ext = href.split('?')[0].split('.').pop().toLowerCase();
                addMedia(href, ['png','jpg','jpeg','gif','webp'].includes(ext) ? 'image' :
                                ['mp4','webm','mov'].includes(ext) ? 'video' : 'file');
            }
            for (const img of art.querySelectorAll('img[src*="discord"]')) {
                addMedia(img.src, 'image');
            }
            for (const v of art.querySelectorAll('video[src*="discord"]')) {
                addMedia(v.src, 'video');
            }
            if (content || author || media.length) out.push({id, author, ts, content, links, media});
        }
        return JSON.stringify(out);
    """
    for _ in range(max_passes):
        run_js(tab_id, f"return ({SCROLL_JS}.scrollTop = 0, true)")
        time.sleep(1.0)
        total = list_height(tab_id)
        viewport = run_js(tab_id, f"return ({SCROLL_JS}).clientHeight")
        step = max(viewport * 0.6, 100)
        y = 0
        new_this_pass = 0
        while y < total:
            run_js(tab_id, f"return ({SCROLL_JS}.scrollTop = {int(y)}, true)")
            time.sleep(0.6)
            try:
                batch = json.loads(run_js(tab_id, code))
            except Exception:
                batch = []
            for m in batch:
                key = m["id"] or (m["author"] + m["ts"] + m["content"][:40])
                if key not in seen:
                    seen.add(key)
                    messages.append(m)
                    new_this_pass += 1
            # the list grows while old history loads; extend the walk
            total = max(total, list_height(tab_id))
            y += step
        print(f"  pass complete: {new_this_pass} new ({len(messages)} total)", file=sys.stderr)
        if new_this_pass == 0:
            break
    return collect_bottom(tab_id, seen, messages, code)


def collect_bottom(tab_id, seen, messages, code, rounds=4):
    """Re-scan the newest messages at the very bottom.

    Scrolling far into history makes Discord prune the newest messages behind
    a "jump to latest" divider; they only re-render when the scroller is
    pushed to (and past) the end. Walk the last few viewports and keep
    scrolling past the end until nothing new appears.
    """
    for _ in range(rounds):
        total = list_height(tab_id)
        viewport = run_js(tab_id, f"return ({SCROLL_JS}).clientHeight")
        for y in range(max(0, total - viewport * 3), total + viewport, max(viewport // 2, 100)):
            run_js(tab_id, f"return ({SCROLL_JS}.scrollTop = {int(y)}, true)")
            time.sleep(0.7)
            try:
                batch = json.loads(run_js(tab_id, code))
            except Exception:
                batch = []
            for m in batch:
                key = m["id"] or (m["author"] + m["ts"] + m["content"][:40])
                if key not in seen:
                    seen.add(key)
                    messages.append(m)
        time.sleep(1.0)
    return messages


def main():
    tab_id, channel_id, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    out_dir = Path(out_path).parent
    channel_name = Path(out_path).stem
    store = MediaStore(out_dir / "media.db", out_dir / "media" / "blobs")
    rpc(tab_id, "NAVIGATE", {"url": CHANNEL_URL.format(ch=channel_id)})
    time.sleep(4)
    height = scroll_to_top(tab_id)
    print(f"loaded history: {height}px", file=sys.stderr)
    messages = collect_messages(tab_id)
    downloaded, skipped = download_media(messages, channel_name, store)
    with open(out_path, "w") as f:
        json.dump(messages, f, ensure_ascii=False, indent=1)
    print(f"saved {len(messages)} messages ({downloaded} downloaded, {skipped} deduped) -> {out_path}")


def download_media(messages, channel, store):
    """Content-addressed download: identical files stored once.

    Per media item: known URL -> reuse stored blob; otherwise download, hash,
    dedupe against existing blobs, record reference. Sets item['local']."""
    downloaded = 0
    deduped = 0
    for msg in messages:
        msg_id = msg.get("id") or "msg"
        for item in msg.get("media", []):
            url = item["url"]
            known = store.known_url(channel, msg_id, url)
            if known:
                item["local"] = known[1]
                deduped += 1
                continue
            try:
                data = fetch_bytes(url)
            except Exception as e:
                print(f"  media fail {url}: {e}", file=sys.stderr)
                continue
            digest = sha256(data)
            existing = store.lookup_hash(digest)
            if existing:
                item["local"] = existing
                deduped += 1
            else:
                ext = ext_of(url)
                blob = store.blob_root / f"{digest}.{ext}"
                blob.write_bytes(data)
                item["local"] = str(blob)
                downloaded += 1
            store.add(channel, msg_id, url, digest, len(data),
                      kind_of(url), ext_of(url), item["local"], msg.get("ts", ""))
    return downloaded, deduped


if __name__ == "__main__":
    main()
