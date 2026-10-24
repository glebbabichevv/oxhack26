# Horizon time capsule: pre-registered expectations

Written and committed **before** the first seal (Sat 24 Oct 2026). Every seal file records the SHA-256 of this file, so these rules cannot change after a seal without the change being visible.

## What is sealed
`backend/capsule.py seal` takes every open Polymarket market that passes this deterministic filter at seal time:
- yes/no market, accepting orders, a two-sided order book (0 < best bid < best ask < 1);
- scheduled end date after the seal and **before Sun 25 Oct 2026 13:00 UTC** (judging starts);
- mid price (best bid + best ask) / 2 inside 3%–97% (the band the model is fitted on);
- volume ≥ $1,000 at seal time; one row per market.

For each market it records the market price and Horizon's probability q with its 10–90% interval, computed by **the same model that produced the published backtest** (time split at 2026-05-18, simple 4-coefficient model, seed 0, code commit recorded in the seal).

## Two analyses, both always reported
- **Primary:** markets with volume ≥ $10,000 at seal time, the closest we can get to the training population (≥ $50,000 at close; open markets are still gaining volume).
- **Secondary:** all sealed markets (≥ $1,000).

## Two seals, scored separately
- **Seal 1** (Saturday ~16:45 London, sealed as soon as these rules were committed and the site moved) is the primary seal. **Seal 2** (around 01:30 Sunday) is secondary.
- Both are always reported. Within a seal each market counts once; the overlap between seals is expected and is not merged.

## What counts at opening
- Only markets with a **final YES or NO** resolution on Polymarket are scored.
- Markets that are still open, disputed, cancelled, postponed, or resolved 50/50 are excluded, and **their number is reported next to the score**. There are no other exclusions.

## Metric
Brier score of Horizon's q against the market price, on the same markets, with a 90% bootstrap interval for (market Brier − model Brier) that resamples by event. P&L is **not** the metric: our backtest hit rate is ~24%, so a handful of bets says nothing.

## What we expect
Every sealed market is under ~19 hours from its scheduled end, so the capsule tests **only the ≤24 h horizons**. It says nothing about 3d, 7d or 30d.

Reference numbers from the out-of-time test set (10,579 markets, results in `backend/results/calibration.json`):

| Slice | 1 day out (model / market) | 12 h out (model / market) |
|---|---|---|
| All markets | 0.1275 / 0.1285 | 0.1246 / 0.1258 |
| Sports | 0.1789 / 0.1804 | 0.1802 / 0.1819 |
| Crypto | 0.0530 / 0.0530 | 0.0450 / 0.0451 |

1. **All markets:** model Brier below market Brier, by about 0.001.
2. **Sports:** same direction, by about 0.0015.
3. **Crypto:** no difference.
4. **Noise:** a gap of ~0.001 is about the size of one day's sampling noise at these sample sizes (tens to a few hundred markets). An **inconclusive or reversed result is a likely outcome**, and we will report it as such, with its interval. The capsule tests whether we say in advance what we will see; one day of markets cannot prove or disprove the edge.

## Amendment 1 (Sat 24 Oct, ~19:00 London, before any seal is opened)
Stricter rule, decided by the team lead: a sealed market counts only if it **resolved after the moment its seal's SHA-256 was posted publicly in the event Discord**. The Discord message time is recorded in `capsule/posts.json` (`{"seal-<ts>.json": "2026-10-24T18:05:00+00:00"}`, UTC ISO). Markets that resolved between the seal and the post are excluded and their number is reported. This only removes markets; it cannot add any.
More seals: Seal 2 around 01:30 Sunday, Seal 3 around 08:00 Sunday (more Sunday markets); each hash is posted as soon as it is sealed. Seal 1 stays primary; all seals are always reported. Opening at 12:30 Sunday.
