# Demo script — 90 seconds (Role C, TheMarkz3)

Built against `docs/design-reference/horizon-target-mock.png` and the numbers in `backend/results/*.json` (14:25 Sat).
Rule: say only numbers that are on the screen or in `backend/results/`. If Gleb regenerates results, update this file.
Live cards change hourly — pick the hero card on the morning of the demo (see "Hero card" below).
Length: ~215 spoken words ≈ 90 s at a calm 145 wpm. Rehearse with a timer; if over, cut the line marked (cut first).

## 0:00–0:10 — hook · screen: headline
"A prediction-market price is a probability with a clock on it. Research says those prices are off, depending on the
clock. We asked a trader's question: can you make money on it, and *when*?"

## 0:10–0:25 — honest test · screen: subline + KPI row
"34,677 resolved Polymarket markets. We train on events that ended before mid-May, test on the 10,839 after, never a
random split. Out of sample, our model beats the market price: Brier 0.1274 against 0.1281."

## 0:25–0:45 — what it learned, and when · screen: calibration chart, 1d → 30d
"Prices are overconfident. A day out, contracts around 15 cents win 20% of the time. The model learns how far to pull each
price back."
(Click 30d.) "A month out, the correction buys nothing. The edge only shows up in the last week."

## 0:45–1:05 — the decision · screen: Live decisions
"So, for every open market right now: price, our probability, and a call after a one-cent cost."
(Point at hero card.) "[Question]: market [p], model [q]. Buy YES, quarter-Kelly."
(Point at a NO_TRADE card.) "Here the gap doesn't cover costs: no trade. Most markets are no trade."

## 1:05–1:30 — money + honesty · screen: KPI "Return"
"On the held-out markets that's 7,228 trades and 2.77 starting bankrolls of profit after costs, interval 1.4 to 4.1.
Always backing the favourite loses 7."
(cut first) "Our first small sample said 'politics, a month out'. It didn't replicate on 11 times more data, so we threw it out."
"Horizon tells you when a market is wrong enough to trade, and when it isn't."

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
