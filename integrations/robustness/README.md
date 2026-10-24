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

## 4. Cost sensitivity on test (`costs_and_time.py`, `costs.png`) — descriptive, not used for selection
The shipped model and V3 are re-run under higher costs: taker fee ×{1, 1.5, 2}, half-spread floor {1, 2, 3}¢ and Kelly ×{⅛, ¼, ½}. Higher costs also change which trades pass, as they would live.
- **The edge survives 2× Polymarket's fees and a 2¢ half-spread floor:**
  - fee ×2, 1¢ floor: +15.7¢ [+9, +22] (3,104 trades);
  - fee ×2, 2¢ floor: +13.8¢ [+5, +22] (1,638 trades).
- **At a 3¢ floor, almost nothing clears:** 700, 305 or 36 trades, and the CI touches 0 at fee ×1.5.
- Kelly changes drawdown, not ¢ per $1 (a ratio): ⅛ → DD 0.19, ¼ → 0.38, ½ → 0.79 at shipped costs.

## 5. Shin's z by horizon (`shin_time.png`) — the TIME slide
Shin's insider share is fitted per horizon on all of train (23,838 markets), with 90% CIs from 200 event-bootstrap refits:

| horizon | 30 days | 7 days | 3 days | 1 day | 12 hours |
|---|---|---|---|---|---|
| z | −0.012 [−0.032, +0.013] | −0.048 [−0.063, −0.033] | −0.064 [−0.081, −0.047] | −0.073 [−0.090, −0.055] | −0.072 [−0.089, −0.052] |

Shin assumes z > 0 (overpriced longshots). Polymarket is the opposite, increasingly so as the end nears; a month out it is indistinguishable from fair.

## 6. Capacity from live books (`capacity.py`, `capacity.json`) — live snapshot 2026-10-24 22:30 UTC, not historical
For each market, we walk the CLOB asks of the side bought at $10 / $100 / $1k / $10k and recompute the net edge with the average fill price + fee.
- **Tonight's 3 V3 trades** (Barcelona–Real draw, Real Madrid win, Brighton win): the edge holds flat at **+2.3 to +3.2¢ per share even at $10k each**, the top of the test. These are deep football books.
- **Plus the 15 WAIT markets' would-be side** (their book will differ when they enter):
  - median capacity ~$1k per market;
  - many go negative at $10k (Brazil/Serbia elections, BTC, Bank of Canada);
  - sum of positive-edge sizes ≈ $70k.
- Headline: "edge survives up to ~$10k per market on liquid football books, ~$1k on typical ones; tonight's eligible trades take ~$30k". One snapshot, small n.
