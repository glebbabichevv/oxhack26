# Demo script — 90 seconds (Role C, TheMarkz3)

Walked against https://web-production-c7376.up.railway.app (18:25 Sat, model 2026-10-24-390c312, fees on) and `backend/results/*.json`.
Old *-jet-mu URLs are frozen: never show them. Rule: say only numbers that are on the screen. If results change, update this file.
Live cards change hourly. Pick the hero card on the morning of the demo (see "Hero card" below).
Length: ~215 spoken words ≈ 90 s at 145 wpm; ~190 (≈ 80 s) without the (cut first) line. Rehearse with a timer.

## 0:00–0:10 — hook · screen: headline
"A prediction-market price is a probability with a clock on it. Research says those prices are off, depending on the
clock. We asked a trader's question: can you make money on it, and *when*?"

## 0:10–0:35 — the time curve · screen: hero curve "How often a 15¢ contract wins, by time left"
"We trained on 23,838 resolved Polymarket markets and tested out of time on the 10,579 after mid-May.
Take a 15-cent contract. A month out it wins 13%: about fair. Twelve hours out it wins 20%. Prices get overconfident
as resolution nears."
(Point along the curve.) "After the spread and Polymarket's fees, a trade a month out loses 19%. A day out it makes
12.6%. That's the *when*."

## 0:35–0:50 — the model and the money · screen: KPI row
"A four-number model corrects it and beats the market price, Brier 0.1297 against 0.1305. Trading it on the test set,
never more than one bankroll at risk: plus 190%, interval 94 to 285. Always backing the favourite loses 908."

## 0:50–1:05 — the decision · screen: Live decisions
"For every open market right now: price, our probability, and the call after costs."
(Point at hero card.) "[Question]: market [p], model [q]. Buy YES, stake [k]% of bankroll."
(Point at a "No trade" card.) "Here the gap is inside the model's uncertainty: no trade."

## 1:05–1:25 — sealed before the outcomes · screen: "Sealed" section
"A backtest can always be tuned. So yesterday afternoon we hashed our probabilities for every market ending before
judging, timestamped them in Bitcoin, and froze 87 trade calls on GitHub. [Result: Brier model vs market, n trades,
n won, P&L — read it off the screen, whatever it says.]" *(If it lost or is inconclusive: "That's one night,
far too little to judge, and we said so before the seal.")*
(cut first) "Our first small sample said 'politics, a month out'. It didn't replicate on 11 times more data, so we threw it out."

## 1:25–1:30 — close
"Horizon tells you when a market is wrong enough to trade, and when it isn't."

## Hero card (pick on the day)
Prefer a **sports BUY_YES** card at 12–48 h out (the curve says that's where it pays), ≥ $1M volume, and a **No trade** card next to it.
Good: a card that is *also* in the forward-test snapshot, so you can say "this one is in the frozen set too".

## Say it right (judges will check)
- "+190%" = profit as a share of the starting bankroll, summed (no compounding), with total open stakes capped at one
  bankroll. Uncapped it's +205% (open stakes peaked at 1.20 bankrolls). Never "3× return".
- **Per dollar actually staked: +12%** (+11.9% capped, +12.7% uncapped). The leverage-free number; use it if pushed.
- Costs = max(spread / 2, 1¢) + Polymarket's taker fee, rate × p(1−p) from each market's own fee schedule (93.5% of
  test rows have fees on; sports mostly 3% or 5%, crypto 7%). Historical spreads aren't in the API, so 1¢ is a floor.
- Max drawdown 31% capped (29% uncapped). Hit rate 21%: a longshot strategy, many small losses, a few big wins.
- Only **sports** is solid on its own (+132%, CI +77% to +192%). Every other type's CI includes 0; crypto −4%.
- A month out loses after fees (−19.0% a trade, 313 trades, noisy). The edge is a last-week effect.
- Never "100× per day" (A, 16:41). Say "short trades tie up capital ~30× less time".
- "Longshots underpriced" holds for roughly 10–35¢ from a week out. Under 10¢ a day out, contracts win ~3%: about fair.

## Likely HRT questions → `QA_CHEATSHEET.md`
