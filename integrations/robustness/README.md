# Robustness of the shipped policy (Role C, TheMarkz3) — `robustness.py`

Shipped spec only: M0 + V3, Polymarket fees, ¼ Kelly capped 5%, open stake ≤ 1 bankroll. No new variants. Charts: `by_month.png`, `placebo.png`, `deflated_sharpe.png`. Numbers: `results.json`.

## 1. Edge by month (walk-forward over the whole history)
Each month, M0 is refitted on every event that ended earlier. V3 then trades only that month's markets.
- **Positive in 13 of 15 months** (months with ≥30 trades); the 90% CI is above 0 in 10 of them, and **in no month is the whole CI below 0**.
- The model's Brier beats the market's in 18 of 21 months.
- The 5 test-period months (2026-05 to 2026-09) are +11¢ to +44¢, each CI above 0. The bias is not shrinking as Polymarket grows.
- Jan to Jun 2025 have 0 trades: with < 6k markets of history the model's own uncertainty band blocks every trade. The rule is conservative when data is thin.

## 2. Placebo (shipped model, the same 3,653 test trades, outcomes re-drawn 1,000×)
| null | mean ¢/$ | 90% range | real +17.2¢: p |
|---|---|---|---|
| prices are right: outcome ~ Bernoulli(price) | −9.8¢ | [−15.9, −3.5] | **0.000** (0 of 1,000) |
| outcomes shuffled within 5¢ price bin × horizon × domain (A's spec) | +18.1¢ | [+16.2, +20.0] | 0.77 |

How to read it:
- Against a calibrated market, the same trades lose 9.8¢ (the fees). The real result is 27¢ above that, and no draw comes close.
- The within-cell shuffle keeps each cell's win rate, so it keeps the bias itself, and it earns the same.
- So the edge **is** the cell-level time × price bias, not some finer per-market signal. That is exactly our claim.

## 3. Deflated Sharpe (Bailey & López de Prado 2014)
| | trades | Sharpe/trade | P(true SR > 0) | DSR |
|---|---|---|---|---|
| V3 on validation, picked among 15 trials (V0–V3 + 11 model_eval members) | 1,373 | 0.110 | 0.99999 | **0.45** |
| same, picked among the 4 playoff trials only | 1,373 | 0.110 | 0.99999 | **0.9999** |
| V3 on test (out of sample, not used to choose) | 3,653 | 0.069 | **0.999996** | n/a |

How to read it:
- With all 15 trials counted as independent, V3's validation Sharpe sits at the luck threshold, so the selection itself proves nothing.
- The trials are not independent: every model reads the same price (error correlations ~0.99), so N=15 overstates luck and N=4 understates it.
- The clean evidence is the test row. It was not used to choose, and it gives P(true Sharpe > 0) = 0.999996 on 3,653 trades.
