# Horizon — Devpost draft (Role C)

Paste section by section into Devpost. Placeholders: `[public URL]`, `[video]`, `[Delta thread links]`, `[team names]`.
Numbers from `backend/results/*.json` (14:25 Sat) — re-check before submitting.

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
- Shows the evidence on one page: calibration curves per horizon, the backtest with and without costs, and a panel
  listing where the model does **not** work.

## Results (out of sample)
Train: events that ended before 18 May 2026 (23,838 markets). Test: the 10,839 after. All markets of one event stay
on the same side of the split.
- Prices are overconfident at every horizon (calibration slope ≈ 0.85): favourites win less than priced, 10–35¢
  contracts win more.
- The model beats the market price: Brier 0.1274 vs 0.1281, log loss 0.3851 vs 0.3871.
- Backtest after a 1¢ cost: 7,228 trades, +2.77 starting bankrolls (¼ Kelly, additive), 90% CI [1.41, 4.07] from an
  event-level bootstrap. Max drawdown 42%. Hit rate 24%.
- The edge sits 1–7 days before resolution, mostly in sports. 30 days out: no lift.
- Baseline "always back the favourite" on the same markets: −7.1.

## How we built it
- **Data:** Python against Polymarket's Gamma and CLOB APIs. Each horizon is measured from the *scheduled* end date
  (what a trader knows in advance), the price is the last trade at or before that moment, and a row exists only if the
  market was still open then. Cancelled and 50-50 resolutions are dropped.
- **Model:** logistic regression with four coefficients: logit(price), log(horizon) and their interaction. A version with
  domain terms overfit on validation and lost. Uncertainty intervals come from bootstrapping whole events.
- **Decision:** edge = model − price; trade only if the edge clears max(spread / 2, 1¢) and the model's bootstrap
  interval; stake = ¼ Kelly capped at 5%.
- **App:** FastAPI serving results, Next.js + Tailwind front end.
- **Team workflow:** three roles (model/backend, front end, data/pitch), each with Claude Code agents. Agents talk
  through per-role inbox files in the repo and review each other's PRs. Collaboration in Zed's Delta: [Delta thread links].

## Challenges
- **Our first result was wrong, and we caught it.** A first 3,100-market sample showed the bias biggest in politics a
  month out. A 34,700-market pull didn't replicate it: the small sample was top-volume and politics-heavy. We kept the
  bigger result and kept this story in the pitch.
- **Look-ahead traps everywhere:** markets that close early, the actual close time vs the scheduled one, correlated
  legs of one event leaking across a random split.
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
- `integrations/pitch/when_to_trade.png`: mean return per trade after costs by entry horizon (30d −0.4% → 12h +15.5%).
  Regenerate with `python integrations/pitch/make_charts.py` whenever backend/results change.
