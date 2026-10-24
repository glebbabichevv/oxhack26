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
