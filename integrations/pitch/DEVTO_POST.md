---
title: "Prediction markets are overconfident. We spent OxHack finding out when that's worth money."
published: false
description: "34,677 Polymarket markets, an out-of-time test, and the moment our first result fell apart. Built in 24 hours at OxHack '26."
tags: hackathon, python, datascience, machinelearning
cover_image: [raw GitHub URL of integrations/pitch/when_to_trade.png once the repo is public]
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

The final dataset has 34,677 markets. We trained on events that ended before 18 May 2026 and tested on the 10,839
that ended after.

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

- Prices are overconfident at every horizon (calibration slope ≈ 0.85).
- A four-coefficient calibration model (logistic regression on logit(price), log(horizon) and their product) beats the market
  price itself: **Brier 0.1274 vs 0.1281**. That's a small gain, but the market price is a hard baseline.
- Trading only where the edge clears a 1¢ cost and the model's bootstrap interval, at a quarter-Kelly stake:
  **7,228 trades, +2.77 starting bankrolls**, 90% CI [1.41, 4.07]. Max drawdown 42%. Hit rate 24%: lots of small
  losses, a few large wins.
- "Always back the favourite" on the same markets: **−7.1**.

And the part that fits the theme:

![Mean return per trade after costs by time to resolution](integrations/pitch/when_to_trade.png)
<!-- replace with the raw GitHub URL -->

30 days out, the correction buys nothing. The edge shows up in the last week, mostly in sports.

## What doesn't work

Every page needs an honest "where it fails" section, so ours is on the screen too: no lift 30 days out, none in crypto at
1–7 days, little in politics, and too few test markets in "other" to say anything. Historical spreads aren't available
from the API, so a 1¢ cost floor stands in for real costs. That's the first thing we'd fix.

## How we worked

Three roles (model/backend, front end, data/pitch), each running Claude Code agents. The agents talked through
per-role inbox files in the repo: one blunt line each, like "your CSV breaks the data contract here". They also
reviewed each other's pull requests. That's how the sign flip travelled from the data agent to the model agent to the
pitch in under an hour. [One line about Delta, if used.]

**Stack:** Python, pandas, scikit-learn, FastAPI, Next.js, Tailwind, Recharts.

Repo: [GitHub URL] · Demo: [public URL] · Devpost: [Devpost URL]

*Built at OxHack '26, Mathematical Institute, Oxford, by [team names].*
