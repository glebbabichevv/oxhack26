# Inbox — Role C

Messages from other agents/teammates to Role C. Newest at the bottom.
Format: `- [HH:MM] from <role>: <what is wrong / what you need> — <file or endpoint>`
When you have handled a message, change `- [` to `- [x]` at its start.

- [14:01] from A: confirmed your PR #1 finding with the out-of-time model (train <2026-05-17, test 955 markets): slope 0.66 at 30d (3–97% band), strongest in politics 0.53; after costs the edge holds only in politics (+1.68 bankroll units), sports loses (−0.26). Pitch line in CLAUDE.md updated — don't pitch blanket "fade favourites" — CLAUDE.md "First results", backend/results/backtest.json
- [14:01] from A: your data merged to main and is great (endDate anchor correct). One gap: spread is 100% empty in horizons.csv, so costs use a 1¢ floor; if you can get historical spread or at least current spread for resolved markets, add it — data/horizons.csv "spread"
- [14:14] from A: Ayaz — merged int/polymarket into main, your 34.7k-market set is now THE team dataset (conflicts with the old sample resolved: data/ + integrations/README from your branch). Model now splits by event_slug as you asked. Result: model beats market out of time, edge mostly sports at 1–7 days — CLAUDE.md "Results", data/horizons.csv
- [14:14] from A: TheMarkz3 — your 3.1k sample's "politics, a month out" did not replicate on 11× more data (top-volume sample bias). Your scripts stay in integrations/ marked superseded; your sign-flip check is credited in the pitch as the honesty moment. Please don't push new data/*.csv without telling A first — CLAUDE.md "Results", integrations/README.md
- [14:14] from A: both — two people built the same pipeline in parallel. From now: one of you takes Devpost + pitch + backup video, the other runs /qa on B's screen and keeps data/live.csv fresh before the demo (python integrations/fetch_live.py) — TASKS.md
- [14:15] from A: domain tags look off in places: 'Will Elon Musk post 90–114 tweets' is labelled politics in live.csv. Please check the tag priority map for tweet-count / celebrity markets (culture?) — integrations/common.py, data/live.csv
