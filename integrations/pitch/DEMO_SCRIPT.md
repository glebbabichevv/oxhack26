# Demo script — 90 seconds (Role C, TheMarkz3)

Follows A's decisions v2 (inbox C 18:54): **three moments — insight (curve) → decision on a match page → agent sets up
2–3 bets + Journal.** Bridge / scan / MCP / Kalshi / crypto go to Q&A only. Never say "gamble". No demo money: the
extension fills the Polymarket ticket, a human presses Trade (in the demo we stop before Trade).
Audience: people who trade on Polymarket, or read "Polymarket says 70%" in the news.
Walked against https://web-production-c7376.up.railway.app and /journal (20:40 Sat, model 2026-10-24-390c312, fees on).
Say only numbers that are on the screen. ~205 spoken words ≈ 85 s at 145 wpm. Rehearse with a timer.

## Setup (before you start talking)
- Tab 1: the site, scrolled to the top. Tab 2: a Polymarket **match page** with a Buy card, ending 12–48 h out
  (pick it on Sunday morning, see "Match page"). Tab 3: /journal. Horizon side panel open, bankroll set to $100.
- Agent ready in the side panel. Don't type the prompt in advance; the judges should see it run.

## 1 · Insight — 0:00–0:30 · Tab 1: hero curve + KPI
"When the news says 'Polymarket gives this 15%', how often does it actually happen? We checked 10,579 markets that
resolved after our model was trained.
(Point along the curve.) A month before the end, a 15-cent contract wins 13%: fair. Twelve hours before, the same
price wins 20%. Prices get overconfident as the end gets close, and that's when correcting them pays.
(Point at the KPI.) Out of sample, after Polymarket's fees: plus 12.7 cents per dollar staked, 90% interval 7 to 19."

## 2 · Decision — 0:30–0:55 · Tab 2: match page + Horizon card
"That's history. Here's a match tonight.
(Point at the verdict.) Market [p] cents, Horizon [q]%, with its range. Buy YES, [k] dollars of a hundred, and it's
inside the 12-to-24-hour window where this paid best.
(Click the button: the ticket fills.) Horizon fills the order. The human presses Trade, not us.
(Point at a No-trade leg if there is one.) And here it says don't: the gap doesn't cover the fee."

## 3 · Agent + Journal — 0:55–1:25 · side panel agent, then Tab 3
"Now the agent. (Type:) *Find me two or three bets tonight in sports and set them up.*
(While it runs.) It scans tonight's markets, checks each one with the same model, and prepares the tickets.
(Switch to /journal.) Every call lands here with the time, the price and our probability, including the ones where
it said 'don't'. Each one is scored when the market resolves, and nothing can be edited.
(Scroll to Seals.) Yesterday we hashed our predictions and timestamped them in Bitcoin before the outcomes. They open at
12:30: [result, read it off the screen, whatever it says]."

## Close — 1:25–1:30
"Horizon tells you when a market is wrong enough to act on, and when it isn't."

## Match page (pick on Sunday morning)
A sports match ending in 12–48 h (the card's best window), volume ≥ $1M, with **one Buy leg and one No-trade leg** on
the same page if possible (moneyline + draw markets usually give both). Check the ticket fills before judging starts.

## Say it right
- Headline is **+12.7¢ per $1 staked**, CI +7.0¢ to +19.1¢ (event bootstrap; C re-ran it independently:
  +12.7¢ [+6.9¢, +18.8¢]). The bankroll view (+199%, ≤ 1 bankroll at risk) is for Q&A, with "mostly sports".
- "After fees" = the spread (1¢ floor) + Polymarket's own taker fee for each market.
- A month out it loses (−19% a trade); 12–24 h out it makes 12.6–14.8% a trade. Never "100× per day".
- Agent prepares, human presses Trade. No demo money anywhere.
- The Journal is real usage from the extension and the agent today; if asked, every row has a timestamp and the
  outcome comes from Polymarket's resolution.

## Backup if the Wi-Fi or the extension fails
Play `integrations/pitch/backup_demo.webm` (site walk) and say moment 2 and 3 over the Journal page.

## Likely HRT questions → `QA_CHEATSHEET.md`
