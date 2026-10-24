# Sponsor integrations & demo data — Role C. See CLAUDE.md.

Polymarket data pipeline for Horizon. No API key needed. Run everything from the repo root:

```bash
python integrations/fetch_horizons.py --since 2024-01-01 --min-volume 50000   # ~15-25 min first time, cached after
python integrations/fetch_live.py                                              # ~5 s, rerun before the demo
python integrations/check_data.py                                              # sanity checks + summary tables
```

## Outputs (Data contract in CLAUDE.md, plus extra columns at the end)
- `data/horizons.csv` — one row per (resolved market, horizon ∈ 720/168/72/24/12 h).
  Extra columns: `end_date`, `price_ts` (time of the price used), `neg_risk` (leg of a multi-outcome event), `event_slug`, `tags`.
- `data/live.csv` — open yes/no markets resolving within 45 days, volume ≥ $50k.
  `price_yes` = order-book midpoint, `spread` = best ask − best bid. Extra: `best_bid`, `best_ask`, `end_date`, `liquidity_usd`, `neg_risk`, `fetched_at`.

## Decisions the model should know about
- **Clock = scheduled end date**, not the actual close time. A trader only knows the scheduled date; using the real close time would leak the future. Same clock in both files.
- A (market, horizon) row exists only if the market was **still open** at `end_date − horizon`. Markets that resolved early ("X by date" that happened) have no late rows — they were not tradable then.
- Price = last trade print at or before the target time, at most 6 h stale (hourly history).
- Dropped: non yes/no markets, 50-50 / cancelled / unresolved outcomes, markets under $50k volume.
- Historical spreads are not available from the API (`spread` is empty in `horizons.csv`); use live spreads (median ≈ 1¢) as the cost assumption.
- `event_slug` groups legs of the same event (e.g. every Oscars nominee) — their outcomes are correlated, so keep an event's legs on one side of the train/test split.
- Domains come from Polymarket tags via a priority map in `common.py` (tweet/post-count + mention markets → culture first, then sports > crypto > economics > politics > geopolitics > science_tech > culture > other).

## Optimal entry time (`optimal_entry.py`)
Enter now or wait? Backward induction (optimal stopping) on empirical TRAIN price transitions 30d→7d→3d→1d→12h, same
model and fees as the backtest. Rule chosen on validation, confirmed once on test (`integrations/entry/results.json`):
**don't enter earlier than 24 h before the scheduled end** → test +4.16 bankrolls vs +1.90 for "enter at the first edge"
(capped at 1 bankroll), gain +2.26, 90% CI [1.35, 3.19] by event bootstrap. `live` writes `integrations/entry/live.json`.

## Earlier pipeline (superseded)
`polymarket.py`, `sanity.py`, `calibration_check.py` (TheMarkz3) built the first 3.1k-market sample. The team dataset is now the one above (Ayaz, 34.7k markets).
