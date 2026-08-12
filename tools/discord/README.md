# Discord toolkit (via chrome-bridge)

Read-only Discord server scraping + analysis, driven through the local
[chrome-bridge](https://github.com/bvakili-xcures/chrome-bridge) daemon. No
bot token, no API — just a bridge-enabled Chrome tab logged into Discord.

## Prerequisites

1. chrome-bridge daemon running (`localhost:8224`)
2. Chrome open on the Discord server with the bridge enabled on that tab
3. **Nobody touches the tab while scraping** — the scraper needs full control
   of the scroll position

## Usage

```bash
# Scrape all channels in channels.json -> ../../scratch/discord/<channel>.json
python3 scrape_all.py 83

# Scrape a subset
python3 scrape_all.py 83 --only main-chat,resources

# Single channel (tab_id channel_id out.json)
python3 scrape_channel.py 83 1451461285551145012 out.json

# Low-level bridge RPC helper (tab_id cmd_type payload-json)
python3 bridge_client.py 83 EVAL '{"code": "return document.title"}'

# Analysis: who's who, patterns, links (deterministic, no network)
python3 analyze.py
```

## Output

`scratch/discord/` (gitignored — Discord content stays out of the public repo):

- `<channel>.json` — `[{id, author, ts, content, links[]}]`
- `scrape.log` — run log with per-channel message counts

`channels.json` — the server + channel manifest (ids for "Lime Accordion and
friends", server `1450359255386554502`).

## Notes / gotchas

- The scroll container is the ancestor `scroller__` div, **not** the
  `[data-list-id=chat-messages]` list — the scraper walks up to the first
  scrollable ancestor automatically.
- Discord only loads older history on real scroll events, so the scraper
  alternates scroll positions; it can't run while the tab is being used.
- `bridge_client.py` returns values only for `return ...` expressions.
