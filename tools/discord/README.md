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

## Automatic daily sync

`sync_discord.py` is the deterministic updater (launchd: `com.cvd.discord-sync`,
daily 06:45):

1. Finds a live bridge-enabled Discord tab, reads the session token from
   localStorage (`tokens` map — the plain `token` key can be stale)
2. Incremental pull per channel + thread (newest-first, stops at the stored
   cursor in `sync-state.json`) — ~15s when nothing changed
3. Downloads new media into the content-addressed store (dedupe)
4. Merges into the channel JSONs; writes `status.json` +
   `~/.cache/campaign-volunteer-directory/status.json`
5. ntfy alert on new content or failure
6. `--agentic`: escalates to a headless agent (opencode run → claude -p
   fallback) to summarize new messages and append
   `scratch/discord/reports/YYYY-MM-DD.md`

Requirements: Chrome with the bridge extension enabled on a logged-in Discord
tab (the cvd profile), bridge daemon running.
