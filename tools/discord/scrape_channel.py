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


def run_js(tab_id, code, attempts=4):
    last = None
    for i in range(attempts):
        try:
            result = rpc(tab_id, "EVAL", {"code": code})
            if "value" in result:
                return result["value"]
            last = f"no value: {json.dumps(result)[:150]}"
        except Exception as e:
            last = str(e)[:150]
        time.sleep(1.2)
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


def collect_messages(tab_id):
    """Walk the whole list from top to bottom, collecting unique messages."""
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
            if (content || author) out.push({id, author, ts, content, links});
        }
        return JSON.stringify(out);
    """
    total = list_height(tab_id)
    viewport = run_js(tab_id, f"return ({SCROLL_JS}).clientHeight")
    y = 0
    while y < total:
        run_js(tab_id, f"return ({SCROLL_JS}.scrollTop = {y}, true)")
        time.sleep(0.25)
        try:
            batch = json.loads(run_js(tab_id, code))
        except Exception:
            batch = []
        for m in batch:
            key = m["id"] or (m["author"] + m["ts"] + m["content"][:40])
            if key not in seen:
                seen.add(key)
                messages.append(m)
        y += viewport
    return messages


def main():
    tab_id, channel_id, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    rpc(tab_id, "NAVIGATE", {"url": CHANNEL_URL.format(ch=channel_id)})
    time.sleep(4)
    height = scroll_to_top(tab_id)
    print(f"loaded history: {height}px", file=sys.stderr)
    messages = collect_messages(tab_id)
    with open(out_path, "w") as f:
        json.dump(messages, f, ensure_ascii=False, indent=1)
    print(f"saved {len(messages)} messages -> {out_path}")


if __name__ == "__main__":
    main()
