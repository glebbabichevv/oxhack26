# Horizon — how the day went (story log)

Source material for the pitch, Devpost and the dev.to post. Times are London, from git commits
and team inboxes. Append new chapters at the bottom; keep every number traceable to a file.

## 1. Morning — the bet on one question (11:00–13:15)
- 11:00 Repo, three roles (A model+backend, B frontend, C data → pitch), agent inboxes so three Claude
  agents and three humans can argue in writing.
- 11:51 Theme announced: **TIME**. We read it as "when?": not *what* will happen, but *when to act*.
- 13:13 Idea locked. A published paper (arXiv 2602.19520, 292M trades) says prediction-market prices are
  miscalibrated as a function of time to resolution. It measures calibration. We ask the trader's
  question: **does that edge survive spreads, fees and an honest out-of-time test — and when is it worth acting?**
- Zed/Delta track dropped at 13:58 (tool too slow). HRT only.

## 2. First data, first surprise (13:30–14:20)
- 13:38 3,122 resolved Polymarket markets. 13:44 first model: the bias runs the **opposite** way to the
  paper's headline: Polymarket is *over*confident, cheap outcomes win more often than they cost.
- 14:07 Dataset grows to **34,677 markets / 120k rows**. 14:13 all legs of an event kept on one side of
  the time split (no leakage between "Barça wins" and "Real wins").
- 14:20 Domain bug caught by a teammate: tweet-count and mention markets were labelled "politics".

## 3. Honesty fights (14:30–16:45)
- 14:46 A time leak in the split found and fixed by our own review.
- Stale-price worry (could the backtest buy at an old price after news broke?): checked — last trade print
  ≤1 h before entry on ~100% of trades; returns unchanged.
- 16:19 **Time capsule** designed: expectations and rules committed *before* any seal.
- 16:31 **Seal 1**: 359 live markets, SHA-256 `31d2510c…3326`, OpenTimestamps proof (Bitcoin).
  Hash posted in the event Discord at 20:45. Amendment 1 (before any opening): only markets that close
  after the public post count.

## 4. From a chart to a product (16:40–19:30)
- 16:41 Chrome extension: Horizon reads the live Polymarket page and says *Price too low / Wait / Skip*.
  Browser layer is Gleb's own pre-hackathon code; model, data, capsule and integration built here.
- 16:49 MCP server so an agent can call Horizon. 18:08 Gemini agent: "set up my 3 best bets tonight".
- Rule from the team: **the agent fills the ticket, the human presses Trade.** No demo money.
- 18:09 C's audit: we had **ignored Polymarket taker fees and leverage**. "+304%" became "+190%".
  We kept the lower number. 19:47 hosting moved to Railway (Vercel deploy limit burned by auto-deploys).

## 5. The rule about time (19:00–20:30)
- Optimal-entry study (C): acting a month out loses after fees (−19% per trade at 30d); the edge lives
  in the last day. Policy **V3**: trade only within 24 h of the end and only if the edge after all costs
  is ≥ 1¢; earlier = **Wait**, with the time to come back.
- 20:27 V3 shipped: **+17.2¢ per $1 staked after fees, 90% CI [+11.8, +23.5]**, 3,653 test trades.
- We stopped saying "test opened once" when it wasn't strictly true; we show all variants side by side.

## 6. The night of the formulas (22:45–01:00)
- "Deposit, deposit, deposit, something hits": we lose ~3 of 4 bets and still make money per dollar.
  The real test: longest losing streak is **25** (not the ~1% a naive formula promised — bets in one event
  are correlated). The site shows the real streak.
- Ten candidate models, chosen **on validation only**: Shin (1993), power method, isotonic, hierarchical
  by domain, beta calibration, mean ensemble, model-agreement filter, a time-weighted log pool, and
  **event coherence (COH)**: probabilities across all outcomes of an event sum to 1, at most one bet per event.
- **"The General Ensembly voted unanimously"**: model errors correlate 0.987–0.9999 — every model reads
  the same price, so no ensemble can add much.
- The time-weighted pool overfit (weights ±9.35 on two identical models) and the held-out half caught it.
- The classic betting model gets Polymarket backwards: Shin's insider share is **negative** at every
  horizon (−0.072 at 12 h → −0.012 at 30 d): longshots are *under*priced, most near resolution.
- **Test opened once for V3 and COH**: COH **+31.2¢ per $1 [22.8, 39.8]**, half the bets, max drawdown
  0.23 vs 0.45, total profit about the same.

## 7. Trying to break it (23:00–01:00)
- Walk-forward: edge **positive in 13 of 15 months**, CI below zero in none; all 5 test months positive.
  The bias is not fading as Polymarket matures.
- Placebo: if prices were right, the same trades would lose **−9.8¢**; real **+17.2¢**; 0 of 1,000 draws.
  (Our first placebo design kept the bias by construction; a teammate caught it.)
- Deflated Sharpe: P(true Sharpe > 0) = 0.999996 on 3,653 test trades.
- Edge is not only in thin markets: >$1M volume +21.3¢, $100k–1M +16.5¢. Sports carries most of it;
  culture is the one negative domain (shown, not cut — cutting it after seeing the test would be snooping).
- Independent replication found later: a public 46k-market study shows the same overconfidence on
  Polymarket and the *opposite* bias on Kalshi.

## Open threads (update as they land)
- [ ] Ship COH everywhere (Gleb's decision) · Seal 2 at 01:30 with model-version hash · freeze 02:00
- [ ] COH robustness (months, placebo, deflated Sharpe, leg choice) — Ayaz
- [ ] Exit before resolution / dynamic hold-or-sell — Ayaz
- [ ] Capacity from live books, cost sensitivity, Kalshi direction, Combos — TheMarkz3
- [ ] Informed-flow / adverse-selection check (exploratory) — whoever frees up
- [ ] Seal 3 at 08:00 · capsule opening 12:30 · result shown whatever it is

## Lines worth keeping
- "We lose most of our bets and still make 17–31¢ on every dollar. That's what an edge looks like."
- "Horizon tells you not only what, but when — and most of the time, *not yet*."
- "A calibrated market would have lost 10¢ on the same trades."
- "We tried ten models. They all agreed, because they all read the same price."
