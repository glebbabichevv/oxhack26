# Horizon model v2 (candidate)

Role C candidate to replace the calibration/decision step in `backend/`. It keeps
the backend's calibration model (M0, a logistic map on the market price and
horizon) and fixes the money side: Polymarket taker fees, a one-bankroll cap on
open stakes, and Kelly size and minimum edge chosen on a validation split. The
extra features we tried (M1, M2) did not beat M0 on validation. Same time split
as the backend (cutoff 2026-05-18, 23,838 train / 10,579 test markets), test set
scored once. Return is in starting bankrolls (additive, no compounding).

## How to run
    python integrations/fetch_live.py
    python integrations/model_v2/train.py
Takes about 10-40 min. Writes `integrations/model_v2/results/*.json`.

## Comparison (test set, out of time)
| Market | Current backend (as shipped: no fees, uncapped, quarter Kelly) | v2 winner (fees + caps + tuned knobs) |
|---|---|---|
| Test log loss | 0.3917 | 0.3917 (market price: 0.394) |
| Test Brier | 0.1297 | 0.1297 (market price: 0.1305) |
| Return after costs (bankrolls) | +3.04 | +8.34 |
| 90% CI (event bootstrap) | [1.84, 4.40] | [5.61, 11.16] |
| Trades | 7,106 | 2,690 |
| Peak exposure (bankrolls) | 1.86 * | 1.0 |
| Return per $1 staked | +12.4% * | +20.3% |
| Max drawdown (bankrolls) | 0.4214 | 0.5174 |

* Peak exposure and return per $1 for the backend are not in its JSON. They come
from the controller's audit: `team/inbox/A.md`, entry "[17:52] from C (Ayaz): MODEL AUDIT".
`baseline_m0` (M0 with the same fees and cap) equals the v2 winner, since the
winner is M0.

## Where the gain comes from
Same test set, model M0, one change added at a time (measured by the controller):
| Rules | Trades | Return (bankrolls) | Per $1 staked |
|---|---|---|---|
| Old: 1c cost, quarter Kelly, no min edge, no cap | 6,984 | +3.27 | +12.9% |
| + Polymarket fees | 5,859 | +2.02 | +12.1% |
| + one-bankroll cap | 5,712 | +2.06 | +12.7% |
| + 2c minimum edge (chosen on validation) | 2,752 | +4.17 | +19.8% |
| + half Kelly (chosen on validation) | 2,690 | +8.34 | +20.3% |

The real improvement is the edge filter (return per $1 goes from 12.7% to 19.8%).
Half Kelly doubles both profit and risk: max drawdown is 0.5174 bankrolls.

## Model selection (validation, last 20% of train events, 4,921 markets)
| Candidate | Validation log loss |
|---|---|
| Market price | 0.56878 |
| M0 | 0.56433 |
| M1 C=0.1 | 0.56638 |
| M1 C=1.0 | 0.5664 |
| M2 | 0.56518 |

Chosen: M0, Kelly x0.5, minimum edge 0.02 (validation P&L 3.6033 over 873 trades;
the full grid is in `model_selection.grid`). The extra features did not beat M0 on
validation, so v2 ships M0 with the fee and exposure fixes, as the spec's fallback says.

## Profit by domain (test set)
| Domain | Trades | Return | Per $1 | 90% CI |
|---|---|---|---|---|
| sports | 2,035 | +6.59 | +21.4% | [4.39, 8.83] |
| science_tech | 39 | +0.90 | +140.3% | [0.44, 1.38] |
| politics | 133 | +0.84 | +38.9% | [0.16, 1.59] |
| economics | 30 | +0.21 | +48.3% | [-0.15, 0.61] |
| other | 1 | +0.03 | +175.1% | [0.03, 0.03] |
| crypto | 214 | +0.00 | +0.1% | [-0.80, 0.89] |
| geopolitics | 32 | -0.01 | -2.0% | [-0.32, 0.34] |
| culture | 206 | -0.23 | -7.1% | [-0.91, 0.47] |

Small domains (under 50 trades) are noise; sports carries the result.

## What did not work (`failures[]`, kind `null_strategy`)
- Sell before resolution: from 7d on, the model's edge does not predict the price move (slope ~0); selling early loses 11-16% per $1 vs +6-14% held to resolution.
- Fade/follow hourly shocks: prices revert 1-2c over 72h after jumps of 8c+, less than the 2c round trip; 0 of 24 rules profitable on train.
- Neg-risk overround: books summing >105% look like +8.9% arbitrage at snapshot prices, but on live bids only 1 of 91 events has sum(bid) > 1.
- 'Nothing Ever Happens' (buy NO on by-date markets): reversed near the deadline (+5.5pp more YES than priced at 12h).

## Contract notes for Gleb and Role B
- `results/*.json` keep the backend's shapes. New keys are additive: `peak_exposure`,
  `return_per_dollar`, `baseline_m0`, `model_selection.params/grid/kelly_mult/min_edge`,
  and `null_strategy` entries in `failures`.
- `data/live.csv` gains columns `fees_enabled` and `event_slug`. It is not committed
  on this branch; rerun `fetch_live.py`.
- Live `kelly_fraction` values are at the tuned x0.5, about 2x the current cards.
- Your call whether `backend/` adopts this; nothing outside `integrations/` is changed.
