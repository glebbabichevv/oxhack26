# Horizon model v2 (candidate)

Role C candidate to replace the calibration/decision step in `backend/`. It keeps
the backend's calibration model (M0, a logistic map on the market price and
horizon) and fixes the money side: Polymarket taker fees, per-trade/per-event caps,
a bankroll cap that tracks equity, a minimum edge chosen on validation, and a test
embargo. Kelly stays at the house x0.25. The extra features we tried (M1, M2) did
not beat M0 on validation. Same time split as the backend (cutoff 2026-05-18,
23,838 train / 10,579 test markets), test set scored once.
Return is in starting bankrolls (additive, no compounding).

## Headline (test set, out of time, x0.25 Kelly)
+2.27 bankrolls after fees and caps, 90% CI [1.25, 3.40] (event bootstrap),
4,086 trades, +11.9% per $1 staked, max drawdown 0.3408,
peak open exposure 0.9977. Minimum edge 1c, chosen on validation.

## How to run
    python integrations/fetch_live.py
    python integrations/model_v2/train.py
Takes about 10-40 min. Writes `integrations/model_v2/results/*.json`.

## Comparison (test set, out of time)
| Metric | Current backend (as shipped: no fees, uncapped, x0.25 Kelly) | v2 (fees + caps + min edge, x0.25 Kelly) |
|---|---|---|
| Test log loss | 0.3917 | 0.3917 (market price: 0.394) |
| Test Brier | 0.1297 | 0.1297 (market price: 0.1305) |
| Return after costs (bankrolls) | +3.04 | +2.27 |
| 90% CI (event bootstrap) | [1.84, 4.40] | [1.25, 3.40] |
| Trades | 7,106 | 4,086 |
| Peak exposure (bankrolls) | 1.86 * | 0.9977 |
| Return per $1 staked | +12.4% * | +11.9% |
| Max drawdown (bankrolls) | 0.4214 | 0.3408 |
| Hit rate | 0.2433 | 0.211 |

* Not in the backend JSON; from the controller's audit (`team/inbox/A.md`,
entry "[17:52] from C (Ayaz): MODEL AUDIT").
The backend charges no fees, so its return is not achievable on today's Polymarket.

## Where the result comes from (`decomposition` in backtest.json)
Same test set and model (M0), same test embargo, one change added at a time:
| Rules | Trades | Return (bankrolls) | Per $1 staked |
|---|---|---|---|
| old rules: 1c cost, x0.25 Kelly, no min edge, no caps | 6,626 | +3.14 | +12.9% |
| + Polymarket fees | 5,664 | +1.97 | +12.2% |
| + caps (5%/trade, 10%/event, equity-capped bankroll) | 5,522 | +1.98 | +12.5% |
| + min edge 1c (chosen on validation) | 4,086 | +2.27 | +11.9% |
| + half Kelly (variant) | 3,420 | +4.96 | +15.6% |

Row 1 is not the shipped backend's +3.04: v2 refits M0 with its own bootstrap
band and event-level validation split, and drops test trades entered before the cutoff.
Fees are the big cost. The minimum edge raises total return on test but not return per $1
(it frees capital for later trades rather than picking better ones). The headline is row 4.

### Half Kelly (variant, not the headline)
| Policy | Trades | Return | 90% CI | Per $1 | Max drawdown | Peak exposure |
|---|---|---|---|---|---|---|
| x0.25 Kelly (headline) | 4,086 | +2.27 | [1.25, 3.40] | +11.9% | 0.3408 | 0.9977 |
| x0.5 Kelly (`variants.half_kelly`) | 3,420 | +4.96 | [2.85, 7.12] | +15.6% | 0.6321 | 1.0 |

Kelly is not tuned: additive P&L rises with stake size, so tuning it on P&L just
picks the largest multiplier. Half Kelly roughly doubles both profit and drawdown.

## Baselines and caveats
- Naive "always back the favourite" (flat 2%, our fee-aware costs): -9.33
  over 8,372 trades (backend's version, 1c cost only: -7.41). Compare sign, not size.
- `without_costs` (+6.60, 3,857 trades) is a separate zero-cost policy run
  with different trades, not the headline trades minus fees.
- Hit rate is 0.211: every test trade buys the side priced under 50c. The money comes from
  longshots winning a bit more often than priced, so most trades lose.
- Fees: Cost per contract = max(spread/2, 1c) + Polymarket taker fee rate x p x (1-p) on markets with fees enabled (today's rates, whole period).
  Fees were on for about 64% of validation markets but about 94% of test markets
  (measured on `fees_on`), so the minimum edge was chosen under lighter fees than it faces in test.
- Test trades must enter on or after the cutoff (no position opened before 2026-05-18 is scored).
- Max drawdown is on resolved P&L in resolution order, not mark-to-market.
- Live cards with under 12h to resolution are NO_TRADE (outside the trained 12h-30d range).
- Live `kelly_fraction` is per card and uncapped: it does not apply the per-event or bankroll caps.
- Live `kelly_fraction` is still x0.25, so live sizes match the current cards.

## Model selection (validation, last 20% of train events, 4,921 markets)
| Candidate | Validation log loss |
|---|---|
| Market price | 0.56878 |
| M0 | 0.56433 |
| M1 C=0.1 | 0.56638 |
| M1 C=1.0 | 0.5664 |
| M2 | 0.56518 |

Chosen: M0, Kelly x0.25 (fixed), minimum edge 1c (validation P&L
1.9734 over 1,682 trades; the grid is in `model_selection.grid`). The extra
features did not beat M0, so v2 ships M0 with the fee, cap and edge fixes, as the spec's fallback says.

## Profit by domain (test set)
| Domain | Trades | Return | Per $1 | 90% CI |
|---|---|---|---|---|
| sports | 2,692 | +1.79 | +14.8% | [1.12, 2.49] |
| science_tech | 54 | +0.37 | +113.7% | [0.15, 0.62] |
| politics | 220 | +0.15 | +14.0% | [-0.18, 0.49] |
| geopolitics | 64 | +0.15 | +46.2% | [-0.05, 0.37] |
| other | 1 | +0.03 | +491.7% | [0.03, 0.03] |
| economics | 77 | +0.01 | +3.4% | [-0.13, 0.16] |
| culture | 508 | -0.10 | -4.5% | [-0.36, 0.18] |
| crypto | 470 | -0.13 | -5.1% | [-0.67, 0.38] |

Small domains (under 100 trades) are noise; sports carries the result.

## What did not work (`failures[]`, kind `null_strategy`)
- Sell before resolution: from 7d on, the model's edge does not predict the price move (slope ~0); selling early loses 11-16% per $1 vs +6-14% held to resolution.
- Fade/follow hourly shocks: prices revert 1-2c over 72h after jumps of 8c+, less than the 2c round trip; 0 of 24 rules profitable on train.
- Neg-risk overround: books summing >105% look like +8.9% arbitrage at snapshot prices, but on live bids only 1 of 91 events has sum(bid) > 1.
- 'Nothing Ever Happens' (buy NO on by-date markets): reversed near the deadline (+5.5pp more YES than priced at 12h).

## Contract notes for Gleb and Role B
- `results/*.json` keep the backend's shapes. New keys are additive: `peak_exposure`,
  `return_per_dollar`, `baseline_m0`, `variants.half_kelly`, `decomposition`,
  `model_selection.params/grid/kelly_mult/min_edge`, and `null_strategy` entries in `failures`.
- `baseline_m0` equals the headline (same trades and CI) because the winner is M0.
- `data/live.csv` gains columns `fees_enabled` and `event_slug`. It is not committed
  on this branch; rerun `fetch_live.py`.
- Live `kelly_fraction` is x0.25, like today's cards.
- Your call whether `backend/` adopts this; nothing outside `integrations/` is changed.
