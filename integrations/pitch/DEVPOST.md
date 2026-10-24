# Horizon — Devpost draft (Role C)

Paste section by section into Devpost. Placeholders: `[public URL]`, `[video]`, `[Delta thread links]`, `[team names]`.
Numbers from `backend/results/*.json` (A's 14:46 rerun) — re-check before submitting.

## Tagline
Prediction markets are overconfident. Horizon tells you when it pays to trade against them.

## Inspiration
The theme was *time*, and HRT asked for data used to predict and decide. A prediction-market price is a probability
with a clock attached: how long until it resolves. Published work (arXiv 2602.19520, 292M trades on Kalshi and
Polymarket) shows these prices are miscalibrated depending on that clock. A paper measuring a bias is not a trader
making money from it, so we asked the trader's question: does the edge survive costs and an honest out-of-sample test,
and how far before resolution should you act?

## What it does
- Collects 34,677 resolved yes/no Polymarket markets and the price each one had 30 days, 7 days, 3 days, 1 day and
  12 hours before its scheduled end.
- Learns a calibration map: the probability a contract really resolves YES, given its price and time to resolution.
- Turns that into a decision for every open market: buy YES, buy NO, or **no trade, costs eat the edge**, with a
  quarter-Kelly stake.
- Runs a **forward test**: the model's calls on open markets are pushed to GitHub *before* they resolve, then scored.
- Shows the evidence on one page: calibration curves per horizon, the backtest with and without costs, and a panel
  listing where the model does **not** work.

## Results (out of sample)
Train: events that ended before 18 May 2026 (23,838 markets). Test: the 10,579 markets of later events that resolved
after it. All markets of one event stay on the same side of the split.
- Prices get overconfident as resolution nears: a month out the test set is about fair; from a week out, favourites
  win less than priced and 10–35¢ contracts win more (a day out, 15¢ contracts win 20%).
- The model beats the market price: Brier 0.1297 vs 0.1305, log loss 0.3917 vs 0.3940.
- Backtest after a 1¢ cost: 7,106 trades, +304% of the starting bankroll (¼ Kelly, summed, no compounding), 90% CI
  [+184%, +440%] from an event-level bootstrap. Max drawdown 42%. Hit rate 24%.
- The edge grows as resolution nears: mean return per trade +4.6% a month out, +14.3% a day out. Only sports is solid
  on its own (+185%, CI +111% to +263%); every other market type's interval includes zero.
- Baseline "always back the favourite" on the same markets: −741%.

## How we built it
- **Data:** Python against Polymarket's Gamma and CLOB APIs. Each horizon is measured from the *scheduled* end date
  (what a trader knows in advance), the price is the last trade at or before that moment, and a row exists only if the
  market was still open then. Cancelled and 50-50 resolutions are dropped.
- **Model:** logistic regression with four coefficients: logit(price), log(horizon) and their interaction. A version with
  domain terms overfit on validation and lost. Uncertainty intervals come from bootstrapping whole events.
- **Decision:** edge = model − price; trade only if the edge clears max(spread / 2, 1¢) and the model's bootstrap
  interval; stake = ¼ Kelly capped at 5%.
- **Forward test:** `integrations/forward_test.py` freezes the model's calls on open markets ending within 48 h and
  pushes them to GitHub every 2 h; after resolution it scores only markets whose *scheduled* end has passed (no
  selection on early resolutions). Result by Sunday: [N resolved, n trades, hit rate, P&L — fill from score.json].
- **App:** FastAPI serving results, Next.js + Tailwind front end.
- **Team workflow:** three roles (model/backend, front end, data/pitch), each with Claude Code agents. Agents talk
  through per-role inbox files in the repo and review each other's PRs. Collaboration in Zed's Delta: [Delta thread links].

## Challenges
- **Our first result was wrong, and we caught it.** A first 3,100-market sample showed the bias biggest in politics a
  month out. A 34,700-market pull didn't replicate it: the small sample was top-volume and politics-heavy. We kept the
  bigger result and kept this story in the pitch.
- **Look-ahead traps everywhere:** markets that close early, the actual close time vs the scheduled one, correlated
  legs of one event leaking across a random split, and early legs of long events that resolved before our cutoff
  (260 of them, caught in QA, dropped and rerun).
- **No historical order book:** Polymarket's API has no past spreads, so costs use a 1¢ floor plus live spreads.

## What we learned
A tiny Brier improvement can still be worth money if you only act where the edge clears costs, and most of the job
is saying "no trade".

## What's next
Real historical spreads (on-chain fills) for honest costs, Kalshi as a second venue, and capacity: how much you could
actually put on before moving the price.

## Built with
python, pandas, scikit-learn, fastapi, next.js, tailwind, recharts, polymarket-api, claude-code, zed-delta

## Sponsor tracks
- **HRT — Best use of data for predictions & decision making:** real data → calibrated probability → decision with
  expected value after costs, evaluated out of sample against the market as baseline.
- **Zed — Built with Delta:** [Delta thread links + one sentence on what happened in each].

## What we brought in vs built here
Brought in: the published finding (arXiv 2602.19520), public Polymarket APIs, open-source libraries, a starter
design preset. Built at OxHack: the data pipeline, the dataset, the model, the backtest, the API and the app.

## Gallery images
- `integrations/pitch/when_to_trade.png`: mean return per trade after costs by entry horizon (30d +4.6% → 12h +16.3%).
  Regenerate with `python integrations/pitch/make_charts.py` whenever backend/results change.
