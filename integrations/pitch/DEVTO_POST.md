---
title: "Prediction markets get overconfident as the end nears. We spent OxHack finding out when that's worth money."
published: false
description: "34,677 Polymarket markets, an out-of-time test, and the moment our first result fell apart. Built in 24 hours at OxHack '26."
tags: hackathon, python, datascience, machinelearning
cover_image: [raw GitHub URL of integrations/robustness/shin_time.png once the repo is public]
---

<!-- Before posting: check the MLH × DEV challenge rules at mlh.link/oxhack (required tag / link back), fill [brackets]. -->

The OxHack '26 theme was **time**. One of the sponsor challenges, from Hudson River Trading, asked for the best use of
data for predictions *and* decisions. We built **Horizon**, a tool that tells you when a prediction market is wrong
enough to trade against, and when it isn't.

## The idea

A Polymarket price is a probability with a clock attached: how long until the market resolves. Published research
([arXiv 2602.19520](https://arxiv.org/abs/2602.19520), 292M trades on Kalshi and Polymarket) shows these prices are
miscalibrated depending on that clock. We didn't discover that. We wanted to answer the question a trader would ask
next: **after costs, on markets the model has never seen, does it make money? And how long before resolution should
you act?**

## The data

We pulled resolved yes/no markets from Polymarket's public APIs and recorded the price each one had 30 days, 7 days,
3 days, 1 day and 12 hours before its *scheduled* end. Three details mattered more than anything else:

- **Use the scheduled end date as the clock, not the actual close time.** A trader only knows the scheduled date.
  Markets often close early, for example when a team gets knocked out. Measuring back from the real close time quietly
  leaks the outcome.
- **A row exists only if the market was still open at that moment.** Otherwise you'd be "trading" a market that had
  already resolved.
- **Split by time and keep events together.** "Who wins the Ballon d'Or?" is thirty correlated yes/no markets. A random
  split puts some in train and some in test, and the test score becomes fiction.

The final dataset has 34,677 markets. We trained on events that ended before 18 May 2026 and tested on the 10,579
that resolved after.

## Our first result was wrong

Early on Saturday, one of us had a 3,100-market sample and a quick check: fit `outcome ~ logit(a + b·logit(price))` per
horizon, with confidence intervals from bootstrapping whole events. The slope came out **below 1** at every horizon,
which means prices are *too extreme*, not compressed toward 50% as our pitch assumed. Longshots won more often than
priced, and favourites less. The sample also said the effect was biggest in politics, a month out.

We rewrote the pitch around that. Then a teammate's 34,677-market pull arrived, and "politics, a month out" didn't
replicate. The small sample had been top-volume and politics-heavy. The direction of the bias held; the story about
where it lived didn't. We kept the bigger result and kept this episode in the pitch, because a quant firm will trust
you more for showing it.

## What held up

On the held-out markets:

- Prices get overconfident as resolution nears: about fair a month out, clearly too extreme in the last week. Far
  from resolution that is *not* the direction the paper we started from reports, and we say so.
- A four-coefficient calibration model (logistic regression on logit(price), log(hours) and their product) beats the
  market price itself: **Brier 0.1297 vs 0.1305**. That's a small gain, but the market price is a hard baseline.
- Our first version had no fees and showed +304%. A teammate's agent audited it: 93% of our test markets charge takers
  a fee. We added each market's real fee schedule, capped leverage, and moved the headline to *per dollar staked*, so
  nothing could flatter it.

The part that fits the theme is *when*. Return per trade by entry time, after fees: a week out +7.8%, a day out
+13.8%, 12 hours out +18.5%. A month out, nothing clears the fees. So Horizon only trades in the last 24 hours, and
before that it says **Wait**, with the time to come back.

## The night of ten models

On Saturday night we threw everything at it, choosing on validation only:
- Shin (1993) and the power method, the classic ways bookmakers' odds are "de-vigged";
- isotonic regression;
- a hierarchical model by domain;
- beta calibration;
- an ensemble, an agreement filter and a time-weighted log pool.

They agreed with each other almost perfectly: errors correlate 0.987–0.9999, because every model reads the same price.
Two findings came out of it:

- **The classic betting model gets Polymarket backwards.** Shin assumes longshots are *over*priced. Fitted freely,
  Shin's insider share comes out negative at every horizon: about zero a month out, most negative in the last day.
  That one curve is our whole thesis.

  ![Shin's insider share by time to resolution](integrations/robustness/shin_time.png)
  <!-- replace with the raw GitHub URL -->

- **The winner wasn't a formula, it was a rule about events.** In a multi-outcome event (home / draw / away), scale the
  probabilities to sum to 100% and place **at most one bet per event**. On the test set, which we opened for the two
  finalists: **+31¢ per dollar staked after fees, 90% CI +22¢ to +41¢, on 1,827 bets.** The same model without the rule
  makes +17¢ on 3,653 bets. Total profit is about the same, with half the bets and half the drawdown. "Always back the
  favourite" on the same markets loses 8.7 bankrolls.

## Trying to break it

- **Refit every month** over the whole history: positive in 14 of 15 months with 30+ bets, and all five test months positive. The
  bias isn't fading as Polymarket grows.
- **Placebo:** if prices were exactly right, the same bets would lose 8¢ per dollar. None of 1,000 draws came close to
  +31¢. Our first placebo shuffled outcomes within price buckets, which kept the bias by construction, so of course it
  "passed". A teammate caught it.
- **Costs:** the edge survives double Polymarket's fees. Walking tonight's live order books, it holds up to ~$10k per
  market on big football matches, ~$1k on typical ones.
- **We lose two bets in three.** The longest losing streak on test was 25. That's what an edge on longshots looks like.

## What doesn't work

- A month out there's nothing to trade after fees.
- Culture is the one domain that lost money; crypto is about zero. We show them rather than cut them: cutting after
  seeing the test would be snooping.
- Under 10¢, the spread eats everything. That's also why a 2026 paper finds cheap longshots *over*priced on executed
  trades: fills pay the spread.
- Historical spreads aren't in the API, so a 1¢ floor stands in. That's the first thing we'd fix.

## How we worked

Three roles (model/backend, front end, data/pitch), each running Claude Code agents. The agents talked through
per-role inbox files in the repo: one blunt line each, like "your CSV breaks the data contract here". They also
reviewed each other's pull requests. That's how the sign flip travelled from the data agent to the model agent to the
pitch in under an hour. Every number in this post was challenged by another role's agent before it reached the screen.

**Stack:** Python, pandas, scikit-learn, FastAPI, Next.js, Tailwind, Recharts, a Chrome extension, MCP, Gemini, Railway.

Repo: https://github.com/glebbabichevv/oxhack26 · Demo: https://web-production-c7376.up.railway.app · Devpost: [Devpost URL]

*Built at OxHack '26, Mathematical Institute, Oxford, by [team names].*
