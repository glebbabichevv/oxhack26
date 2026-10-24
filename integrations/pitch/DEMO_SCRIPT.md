# Demo script — 90 seconds (DRAFT, Role C)

Status: draft written 24 Oct 14:00 against `integrations/calibration_check.py` (favourite-longshot bias, slope b < 1).
Numbers in [brackets] come from `/api/backtest` and `/api/live` once Gleb's out-of-time model lands. Never say a number
that is not on the screen or in the backtest. If the model shows no edge after costs, use the "no edge" ending.

## 0:00–0:15 — the question (Time theme)
"Prediction markets give you a price. A price is a probability, and a probability has a *when*: how far out you are
from resolution. We asked one trader's question: does the market's error depend on time to resolution, and is it big
enough to trade after costs?"

## 0:15–0:35 — the data and the honest finding
Screen: calibration chart by horizon.
"3,122 resolved Polymarket markets, priced 30 days, 7 days, 3 days, 1 day and 12 hours before their scheduled end.
Published research (arXiv 2602.19520) found prices compressed toward 50%. On our sample we found the opposite:
favourites are overpriced and longshots underpriced, at every horizon, most of all a month out. An 85¢ favourite
30 days out has won about 75% of the time."
(Point at the 30d curve under the diagonal on the right.)

## 0:35–0:55 — the model vs the baseline
Screen: Brier / log loss panel.
"Baseline is the market price itself, which is a hard baseline. Our calibration model is trained on markets that
resolved before [cutoff] and tested on the ones after. Brier [market] → [model] on the held-out set."

## 0:55–1:15 — the decision (the step most teams skip)
Screen: live decision card. Hero market: *Will the Democratic Party control the House after the 2026 midterms?*
91.5¢, ~11 days to resolution, 1¢ spread, $12M volume.
"Market says 91.5%. Our model says [q]%. Edge [q − p] against a 1¢ spread plus fees: [buy NO / no trade]. Size at
quarter-Kelly: [x]% of bankroll. The card also says *when*: the edge is largest at [horizon]."

## 1:15–1:30 — where it fails + close
Screen: backtest equity curve with vs without costs, and the "where it fails" panel.
"Without costs, [+r%]. With costs, [+r%]. It fails in [domain / horizon]: there we say no trade.
The time bias is real; the question is *when* it pays. Horizon tells you."

### "No edge" ending (if the backtest with costs is flat or negative)
"The bias is real and statistically clear, but after a 1¢ spread and fees it is not tradable on these markets.
That's the honest answer, and Horizon tells you exactly where the line is."

## Likely judge questions (HRT)
- *How did you avoid look-ahead?* Prices are the last trade at or before the horizon time; horizons are anchored on
  the scheduled end date; rows after market close are dropped; train/test split by resolution date.
- *Aren't markets in one event correlated?* Yes. CIs bootstrap whole events (1,020 events), not single markets.
- *Which costs?* Live spread from the order book (median 1¢), plus [fee assumption]. Historical spread is unknown;
  we use [assumption] and show the sensitivity.
- *Sample bias?* Top-volume events, Politics and Sports heavy; Geopolitics/Tech only ~100–200 rows each.
- *The midterm markets all resolve on one night.* Correct: treat them as one bet when sizing.

## Backup
Live markets with a 1¢ spread for a second example: Fed +25 bps after the October 2026 meeting (5.5¢, ~4.6 days),
US × Iran ceasefire through Oct 28 (87.5¢, ~4.6 days).
