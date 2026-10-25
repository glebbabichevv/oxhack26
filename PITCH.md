# Horizon — pitch card (5 minutes)

Full reference (every answer, every section): the "Horizon — полный гид для питча" doc. This file is what you
need at the table.

## Before judges arrive
- Tab 1: https://web-production-c7376.up.railway.app (top of the page, the arrows)
- Tab 2: a Polymarket match that ends 12–24 h from now (closer than 12 h shows "Not sure here")
- Tab 3: https://web-production-c7376.up.railway.app/journal (scrolled to the capsule)
- Horizon side panel open, budget $100–500 (with $10 every bet rounds up to Polymarket's $1 minimum)
- Backup video open in the background; phone hotspot ready

## What to say (≈2 min), then questions

**1. Idea — Gleb, Tab 1, drag the slider from 30 days to 12 hours**
> We checked 34,000 Polymarket markets. The closer a market gets to the end, the more overconfident people get.
> Cheap outcomes win more often than their price says. Horizon corrects that.

**2. Proof — Ayaz, Tab 1, the headline number**
> On 10,000 markets the model never saw, after fees, it made about 30 cents per dollar.
> It was profitable in 15 of 17 months. Most single bets lose; it works over hundreds of bets.

**3. Demo — Gleb, Tab 2**
> This is a real match. The market says [p], Horizon says [q], so the price is too low. It suggests [k] dollars.
> *(click)* It fills in the order. I press Trade myself.

**4. Capsule — Ayaz, Tab 3**
> Yesterday we sealed our live predictions and posted the fingerprint in the hackathon Discord, so we couldn't
> change them. Here's how they did. *(read the result, whatever it is)*

## Questions — who answers
- Ayaz: overfitting, validation, the ten models, placebo, fees, capacity, the formula, the papers
- Gleb: the product, the agent, why a human presses Trade, the UK, what's next, "built in 24 h?"

## One-line answers
- **Overfitting?** Time split; ten variants chosen on validation; test opened for the final two; 15 of 17 months positive.
- **What if prices were right?** Same bets with fair outcomes lose ~10¢ per dollar; 0 of 1,000 runs matched us.
- **Fees?** Each market's own Polymarket fee + half the spread (min 1¢). Survives double fees.
- **Capacity?** ~$10k per market on liquid football, ~$1k on typical markets (one live snapshot).
- **Why so simple?** Boosting and ensembles didn't beat it; all models' errors correlate at 0.99.
- **The paper?** They measured calibration; we tested money after costs and when to act. Their month-out result didn't hold on our data.
- **Where does it fail?** Culture loses, crypto ≈ 0, no advice under 12 h (never tested there).
- **Is it ML?** Yes, a small one: logistic regression, 4 coefficients learned from 23,000 markets. The agent is the AI part.
- **Built in 24 h?** The browser layer is Gleb's own code from before; model, data, rules, capsule and integration were built here.

## If something breaks
- No internet → phone hotspot; the site shows its cached copy.
- Extension or agent hangs → play the backup video, don't debug in front of judges.
- Card says "Not sure here" → "It closes too soon; we never tested under 12 hours, so it won't advise." Switch to the backup match.

## Commands (VS Code terminal, repo root)
```bash
git pull origin main
python integrations/reproduce.py        # re-runs the pipeline, diffs every headline number
python backend/capsule.py open --all --dry-run   # capsule result, publishes nothing
python backend/capsule.py open --all             # 12:30: the real opening
```

## Proof trail (if they ask for logs)
- GitHub commits + PRs reviewed by another role
- `team/inbox/` — agents and people, timestamped: who found the fee bug, the time leak, COH
- `team/STORY.md` — the day as a timeline
- `integrations/ensemble/results.json`, `integrations/robustness/` — model tournament and stress tests
- `capsule/` — sealed files, `.ots` timestamps, `posts.json` (Discord post times), `EXPECTATIONS.md`
