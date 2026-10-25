# Demo script — 90 seconds (Role C, TheMarkz3)

Gleb runs the demo. Three moments: **insight (curve) → decision on a match page → agent sets up 2–3 bets + Journal**.
Bridge / MCP / Kalshi / crypto / robustness go to Q&A only. Never say "gamble". No demo money: the extension fills the
Polymarket ticket, a human presses Trade (in the demo we stop before Trade).
Audience: people who trade on Polymarket, or read "Polymarket says 70%" in the news.
Numbers = shipped policy **COH** (backend/results, model 2026-10-24-390c312). Say only numbers that are on the screen.
~200 spoken words ≈ 85 s at 145 wpm. Rehearse with a timer.

## Setup (before you start talking)
- Tab 1: https://web-production-c7376.up.railway.app scrolled to the top. Tab 2: a Polymarket **match page** with a
  Buy card, ending 12–24 h out (pick Sunday morning, see "Match page"). Tab 3: /journal. Horizon side panel open,
  bankroll set to $100.
- Agent ready in the side panel. Don't type the prompt in advance; the judges should see it run.

## 1 · Insight — 0:00–0:30 · Tab 1: hero curve + KPI
"When the news says 'Polymarket gives this 15%', how often does it actually happen? We checked 10,579 markets that
resolved after our model was trained.
(Point along the curve.) A month before the end, a 15-cent contract wins about 13%: fair. A day before, the same price
wins 20%. Prices get overconfident as the end gets close, and that's when correcting them pays.
(Point at the KPI.) Out of sample, after Polymarket's fees: plus 31 cents per dollar staked, one bet per event."

## 2 · Decision — 0:30–0:55 · Tab 2: match page + Horizon card
"That's history. Here's a match tonight.
(Point at the verdict.) Market [p] cents, Horizon [q]%, with its range. Buy, [k] dollars of a hundred, inside the last
24 hours, where this pays.
(Click the button: the ticket fills.) Horizon fills the order. The human presses Trade, not us.
(Point at a Wait or Skip leg if there is one.) And here it says not yet, or not this one: one bet per match."

## 3 · Agent + Journal — 0:55–1:25 · side panel agent, then Tab 3
"Now the agent. (Type:) *Find me two or three bets tonight in sports and set them up.*
(While it runs.) It scans tonight's markets, checks each with the same model, and prepares the tickets.
(Switch to /journal.) Every call lands here with the time, the price and our probability, including the ones where it
said 'don't'. Each is scored when the market resolves; nothing can be edited.
(Scroll to Seals.) Last night we hashed our predictions and timestamped them in Bitcoin before the outcomes. They open
at 12:30: [result — read it off the screen, whatever it says]."

## Close — 1:25–1:30
"We lose two bets in three and still make 31 cents on every dollar. Horizon tells you when a market is wrong enough to
act on, and when it isn't."

## Match page (pick Sunday morning)
A sports match ending in 12–24 h, volume ≥ $1M, ideally with one **Buy** leg and one **Wait/Skip** leg on the same
page (moneyline + draw usually give both; COH keeps only the largest-edge leg per event). Check the ticket fills before
judging starts.

## Say it right
- Headline: **+31¢ per $1 staked after fees** (site shows +31.3¢), 90% CI **+22¢ to +41¢**, 1,827 test bets, max
  drawdown 0.22. Same model without the event rule (V3): +17¢, 3,653 bets, drawdown 0.38. Total profit about the same
  (+4.4 vs +4.0 bankrolls): COH earns it with half the bets and half the drawdown.
- Rule: only within 24 h of the end · net edge ≥ 1¢ after spread + Polymarket's fee · probabilities of an event's
  outcomes scaled to sum to 100% · one bet per event.
- "Ten models compared on validation; the test was opened for the two finalists." Never "test opened once" alone.
- "Sports carries most of it; culture is the one domain that lost." Never "sports is well calibrated".
- Agent prepares, human presses Trade. No demo money anywhere.

## Backup if the Wi-Fi or the extension fails
Play `integrations/pitch/backup_demo.webm` (site walk) and say moments 2 and 3 over the Journal page.

## Likely HRT questions → `QA_CHEATSHEET.md`
