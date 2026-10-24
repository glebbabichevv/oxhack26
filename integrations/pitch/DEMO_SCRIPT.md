# Demo script — 90 seconds (Role C, TheMarkz3)

Built against `docs/design-reference/horizon-target-mock.png` and the numbers in `backend/results/*.json` (14:25 Sat).
Rule: say only numbers that are on the screen or in `backend/results/`. If Gleb regenerates results, update this file.
Live cards change hourly — pick the hero card on the morning of the demo (see "Hero card" below).

## 0:00–0:12 — hook (Time theme) · screen: headline
"Every Polymarket price is a probability with a clock on it: how long until it resolves.
Published research (arXiv 2602.19520) says those prices are miscalibrated depending on that clock.
We asked the trader's question: can you actually make money on it, and *when*?"

## 0:12–0:30 — data + honest test · screen: subline + KPI row
"34,677 resolved Polymarket markets, each priced 30 days, 7 days, 3 days, 1 day and 12 hours before its scheduled end.
We train on events that ended before 18 May 2026 and test on the 10,839 that ended after. No random split, and every
market from one event stays on the same side."
(Point at Brier.) "Our model beats the market price out of sample: Brier 0.1274 against 0.1281. Small, but the market
is a hard baseline."

## 0:30–0:50 — what the model learned · screen: calibration chart, 1d selected
"Prices are overconfident. A day out, contracts priced 10 to 20 cents resolve YES about 20% of the time, and favourites
win less than their price says. The model learns how far to pull each price back toward the middle, per horizon and domain."
(Click 30d.) "A month out, that correction buys nothing: no lift. Time matters."

## 0:50–1:10 — the decision · screen: Live decisions
"So for every open market: price, our probability, and a call after a 1-cent cost."
(Point at hero card.) "[Question], [h] hours out. Market [p]¢, model [q]%. Net edge [x]¢ after cost, so buy YES at a
quarter-Kelly stake. Right below, a market where the model agrees with the price: no trade. Most of the screen is no trade,
and that's on purpose."

## 1:10–1:30 — money + honesty · screen: KPI "Return" + backtest
"Backtested on the held-out markets: 7,228 trades, plus 2.77 times the starting bankroll after costs, 90% interval 1.4 to 4.1.
Mostly sports, in the last week. The naive 'always back the favourite' strategy loses 7.1 on the same markets.
And our first 3,000-market sample said 'politics, a month out'. It didn't replicate on eleven times more data, so we dropped it.
Horizon tells you when a prediction market is wrong enough to trade, and when it isn't."

## Hero card (pick on the day)
Prefer a **sports BUY_YES** card at 1–7 days, ≥ $1M volume, and a **NO_TRADE** card right next to it.
At 14:25 Sat that was *Will Kylian Mbappé win the 2026 Ballon d'Or?*: 18.65¢, model 22.7% (interval 22.2–23.1%),
net edge 2.6¢, ¼-Kelly stake 0.8% of bankroll, ~63 h out, $5.9M volume. It will have resolved by Sunday.

## Say it right (judges will check)
- "+2.77" is **starting-bankroll units, additive** (positions overlap, so no compounding). Say "2.77 times the starting
  bankroll in profit", never "2.77× return". Mock shows "+2.77×": ask B to label it "bankroll units".
- Max drawdown with costs is **42%** of the starting bankroll; the equity curve goes down before it goes up.
  Don't hide it, say it if asked.
- Top 10 events make up 1.03 of the 2.77. The edge is concentrated, and the event bootstrap CI already includes that.
- Hit rate is 24%. It's a longshot strategy: many small losses, a few big wins.
- Costs = max(live spread / 2, 1¢), no fee. Historical spreads don't exist in the API, so 1¢ is a floor, not a measurement.
- "Longshots underpriced" holds for roughly 10–35¢. Under 10¢ a day out, contracts win ~3%: very cheap ones are not underpriced.

## Likely HRT questions
- *Look-ahead?* Clock = scheduled end date (what a trader knows), price = last trade at or before the horizon, a row
  exists only if the market was still open, split by time, event legs kept together.
- *Why does the bias exist?* We measure it; we don't claim to explain it. Candidate stories: longshot demand, thin
  books close to resolution. Don't speculate past that.
- *Capacity?* Not measured. Median live spread is about 1¢ on ≥ $50k-volume markets; size is ¼ Kelly capped at 5%.
- *Where does it fail?* 30 days out (no lift), crypto (no lift at 1–7 days), politics at most horizons; "other" has
  2–3 test markets, too few to trust. All of these are on the "where it fails" panel.
