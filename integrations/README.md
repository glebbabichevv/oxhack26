# Sponsor integrations & demo data — Role C. See CLAUDE.md.

## Data pipeline (Polymarket)
```
pip install requests pandas
python integrations/polymarket.py horizons   # -> data/horizons.csv (~15 min, cached in data/raw/)
python integrations/polymarket.py live       # -> data/live.csv: 500 most liquid open binary markets resolving within 30 days
python integrations/sanity.py                # counts per horizon/domain, leakage + resolution checks
```

How `horizons.csv` is built:
- Top closed events by volume (Gamma `/events`), keep binary Yes/No markets with volume ≥ $10k.
- Outcome must be a clean 1/0 (`outcomePrices` = `[1,0]` or `[0,1]`); 50/50, cancelled and unresolved markets are dropped.
- Horizons 720/168/72/24/12 h are measured back from the scheduled `endDate`. A row is dropped if the market had already closed at that time, or if the last trade before it is more than 12 h old.
- Price = last CLOB `prices-history` point at or before the horizon time (hourly fidelity, requested in 15-day `startTs`/`endTs` chunks), so nothing from the future leaks in.
- Domain = first match of event tags/title against the keyword list in `DOMAINS`; otherwise `Other`.
- Extra columns beyond the contract: `end_date`, `event_id` (markets in one event are correlated — group by it when splitting or sizing).
- `spread` is empty for historical rows (Polymarket has no historical order book); `live.csv` has the real current spread.

## Full dataset (Ayaz) — `data/horizons_full.csv`, `data/live_full.csv`
A larger pull made by a separate set of scripts. `horizons.csv` / `live.csv` above stay the canonical files the model reads until Role A switches.
```
python integrations/fetch_horizons.py --since 2024-01-01 --min-volume 100000   # -> data/horizons_full.csv (~35 min first time, cached in data/raw/)
python integrations/fetch_live.py                                               # -> data/live_full.csv (open markets resolving within 45 days)
python integrations/check_data.py                                               # checks the _full files (or pass paths)
```
- **34,677 markets, 120,058 rows** (volume ≥ $100k, resolved 2024-01 → 2026-10) vs 3,122 markets in `horizons.csv`. Same schema plus `price_ts`, `neg_risk`, `event_slug`, `tags`; `event_id` is present for clustering.
- Same rules: horizons measured back from the scheduled `endDate`, a row only if the market was still open then, clean 1/0 outcomes only, last price at most 6 h stale.
- Markets are listed by end-date window through Gamma `/markets`; windows over the 2,000-offset cap are split, not truncated.
- Domains (lowercase, matching the API): sports > crypto > economics > politics > geopolitics > tech > culture > other, from tags in `common.py`. Fed/rates markets count as **economics** here (they were politics in `horizons.csv`).
- Rows by horizon: 12h 30.1k · 24h 30.1k · 72h 29.9k · 168h 20.5k · 720h 9.5k. Out-of-time cutoff 2026-04-01 gives ~20k train / ~14.7k test markets.
