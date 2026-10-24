# Demo script — 90 seconds (Role C, TheMarkz3)

Walked against the live screen (15:55 Sat; site now https://horizon-two-gilt.vercel.app, API https://horizon-api-iota.vercel.app — old *-jet-mu URLs are frozen, never show them) and `backend/results/*.json` (A's 14:46 rerun).
Rule: say only numbers that are on the screen or in `backend/results/` / `integrations/forward/score.json`. If results change, update this file.
Live cards change hourly. Pick the hero card on the morning of the demo (see "Hero card" below).
Length: ~225 spoken words ≈ 93 s at 145 wpm; ~200 (≈ 83 s) without the (cut first) line. Rehearse with a timer.

## 0:00–0:10 — hook · screen: headline
"A prediction-market price is a probability with a clock on it. Research says those prices are off, depending on the
clock. We asked a trader's question: can you make money on it, and *when*?"

## 0:10–0:22 — honest test · screen: subline + KPI row
"34,417 resolved Polymarket markets. We train on events that ended before mid-May and test on the 10,579 after, never a
random split. Out of sample, our model beats the market price: Brier 0.1297 against 0.1305."

## 0:22–0:35 — what it learned · screen: calibration chart (1d, then 30d)
"As resolution nears, prices get overconfident: a day out, 15-cent contracts win 20% of the time."
(Click 30d.) "A month out, the market is about fair."

## 0:35–0:55 — the decision · screen: Live decisions
"So, for every open market right now: price, our probability, and a call after a one-cent cost."
(Point at hero card.) "[Question]: market [p], model [q]. Buy YES, stake [k]% of bankroll."
(Point at a "No trade" card.) "Here the gap is inside the model's uncertainty: no trade."

## 0:55–1:10 — the forward test · screen: Forward test strip (or terminal `score.json` if it isn't on the screen)
"Backtests are still history. So yesterday at 3:43 we committed [163] live calls to GitHub, before the matches were
played. [N] have resolved since: [n] trades, [hit] won, [P&L]." *(Say the real numbers, whatever they are. If it lost:
"it's [n] trades, far too few to judge, which is why we report the backtest's interval.")*

## 1:10–1:30 — money, and *when* · screen: equity chart + "When to act" bars
"On the held-out test: 7,106 trades, plus 304% of the starting bankroll after costs, interval 184 to 440.
Always backing the favourite loses 741."
(Point at "When to act".) "And the time part: a week or a month out, about 4 to 5% a trade. 12 to 24 hours out, about 14 to 15%, and the money is tied up 30 times less time."
(cut first) "Our first small sample said 'politics, a month out'. It didn't replicate on 11 times more data, so we threw it out."
"Horizon tells you when a market is wrong enough to trade, and when it isn't."

## Hero card (pick on the day)
Prefer a **sports BUY_YES** card at 1–3 days, ≥ $1M volume, and a **No trade** card right next to it.
Good: a card that is *also* in the forward-test snapshot, so you can say "this one is in the frozen set too".

## Say it right (judges will check)
- "+304%" is **profit as a share of the starting bankroll, summed** (positions overlap, so no compounding). Never "3× return".
- Max drawdown with costs is **42%** of the starting bankroll; the curve dips before it rises. Say it if asked.
- Top 10 events make up 1.03 of the 3.05 bankrolls; without them it's still +2.02. The event-bootstrap CI includes that.
- Only **sports** is solid on its own (+185%, CI +111% to +263%). Every other type's CI includes 0.
- Hit rate 24%: a longshot strategy, many small losses, a few big wins.
- Costs = max(live spread / 2, 1¢), no fee. Historical spreads aren't in the API, so 1¢ is a floor, not a measurement.
- "Longshots underpriced" holds for roughly 10–35¢ from a week out. Under 10¢ a day out, contracts win ~3%: about fair.
- Never say "100× per day" (A, 16:41: different market sets, no liquidity, ~25% hit rate). Say "short trades tie up capital ~30× less time".
- Per-horizon numbers after dropping markets whose event was already over: 12h +14.3%, 1d +15.0% (A, 16:41) → say "≈14–15% 12–24h out, ≈7% at 3d, ≈4–5% at 7–30d".
- **Fees:** Polymarket charges takers a fee on most markets; the screen's +304% has none. With the exact per-market fee schedule it's +205%, CI [+109%, +306%], 6,102 trades (PR #11). If asked, say that number. If A reruns with fees before the demo, the screen and this script switch to it.
- 30 days out the *calibration* is about fair, yet the per-trade return is +4.6% (841 trades). It's a small, noisy edge
  there; don't claim more.

## Likely HRT questions → `QA_CHEATSHEET.md`
