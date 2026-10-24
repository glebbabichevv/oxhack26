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

## Crypto: exchange-implied probability (null result)
`crypto_implied.py` prices Polymarket's crypto threshold markets as options on the coin: "above K on date" = digital call
N(d2), "between" = digital spread, "reach / dip to K" = one-touch by the reflection principle, with spot and realised
volatility from Binance hourly candles before the price time (sigma × √time-to-expiry).

```bash
python integrations/crypto_implied.py fetch      # Binance hourly candles -> data/raw/ (gitignored)
python integrations/crypto_implied.py evaluate   # -> integrations/crypto/results.json
```

Out of time (backend `split_by_time`, cutoff 2026-05-18; 2,007 rows, 1,106 markets): market Brier 0.1399, exchange
0.1471, blend 0.1408. Trading the exchange signal with the 1¢ half-spread + each market's own taker fee (all test rows:
crypto 0.07·p(1−p)) loses −16.5%/$ (90% event-bootstrap CI [−29%, −4%]); the blend is +3.3% [−13%, +20%], i.e. nothing. Even a spot taken up to an hour *after* the price time only
ties the market (0.1412). Polymarket's crypto ladders are already priced like options: no edge from spot + volatility.

## Earlier pipeline (superseded)
`polymarket.py`, `sanity.py`, `calibration_check.py` (TheMarkz3) built the first 3.1k-market sample. The team dataset is now the one above (Ayaz, 34.7k markets).
