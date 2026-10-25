# Horizon — Devpost draft (Role C)

Paste section by section into Devpost. Placeholders: `[video]`, `[team names]`, `[capsule result at 12:30]`.
Numbers: shipped policy COH, `backend/results/*.json` (model 2026-10-24-390c312). Re-check against the site before submitting.

## "Try it out" links (Devpost field)
- Demo: https://web-production-c7376.up.railway.app (methods: /methods · decision journal: /journal)
- API: https://oxhack26-production.up.railway.app/api/backtest
- Code: https://github.com/glebbabichevv/oxhack26
- Video: [video]

## Tagline
Prediction markets get overconfident as the end nears. Horizon tells you when that's worth trading, and when it isn't.

## Inspiration
The theme was *time*, and HRT asked for data used to predict and decide. A prediction-market price is a probability
with a clock attached: how long until it resolves. Published work (arXiv 2602.19520, 292M trades) says these prices are
miscalibrated depending on that clock. A paper measuring a bias is not a trader making money from it, so we asked the
trader's question: does the edge survive fees and an honest out-of-time test, and *when* should you act?

## What it does
- Collects 34,677 resolved yes/no Polymarket markets and the price each had 30 days, 7 days, 3 days, 1 day and 12 hours
  before its scheduled end.
- Learns a calibration map: the probability a contract really resolves YES, given its price and the time left.
- Turns it into a decision on every open market: **Buy**, **Wait** (with when to come back) or **Skip**, with a
  quarter-Kelly stake. This works through a Chrome extension on the Polymarket page and an agent that sets up bets.
  The extension fills the ticket; the human presses Trade.
- Logs every decision to a public journal, scored when the market resolves.
- Seals predictions before the outcomes with a SHA-256 hash timestamped in Bitcoin (OpenTimestamps).
- Shows the evidence on one page, including where it does **not** work.

## Results (out of time)
Train: events that ended before 18 May 2026 (23,838 markets). Test: the 10,579 markets of later events that resolved
after it. All markets of one event stay on one side.
- **The bias, by time:** a month out, a 15¢ contract wins about 13% (fair); from a week out to 12 hours out, 18–20%.
  Prices get overconfident as resolution nears. Far from resolution this is **not** the direction the paper we started
  from reports, and we say so.
- **The model beats the market price:** Brier 0.1297 vs 0.1305, log loss 0.3917 vs 0.3940.
- **The decision (policy COH):**
  - The rule:
    - trade only within 24 h of the end;
    - only with at least 1¢ of net edge after the spread, Polymarket's own taker fee and the model's uncertainty;
    - the probabilities of an event's outcomes are scaled to sum to 100%;
    - one bet per event.
  - Result: **+31¢ per $1 staked after fees, 90% CI +22¢ to +41¢** (event bootstrap), on 1,827 bets, with a max drawdown
    of 0.22 bankrolls.
  - The same model without the event rule makes +17¢ on 3,653 bets, with a drawdown of 0.38. Total profit is about the
    same; COH earns it with half the bets and about half the drawdown.
- **Why 24 hours:** return per trade by entry time is +7.8% a week out, +13.8% a day out and +18.5% 12 hours out.
  A month out, nothing clears the fees.
- **Baseline:** "always back the favourite" on the same markets loses 8.7 bankrolls.
- **Where:** sports carries most of it (+35¢ per $1); culture is the one domain that lost; crypto is about zero.
- **Is it luck?**
  - Refitted every month, the edge is positive in 14 of 15 months with 30 or more bets. For the simpler rule it is 13 of 15, never
    significantly negative. All five test months are positive.
  - If prices were exactly right, the same bets would lose 8¢ per $1; none of 1,000 placebo draws came close.
  - Deflated Sharpe: 0.9999.
  - The edge survives double Polymarket's fees.
  - A live order-book walk puts capacity at ~$10k per market on deep football books, ~$1k on typical ones.

## How we built it
- **Data:** Python against Polymarket's Gamma and CLOB APIs.
  - Each horizon is measured from the *scheduled* end (what a trader knows in advance).
  - The price is the last trade at or before that moment.
  - A row exists only if the market was still open.
- **Model:** logistic regression with four coefficients (logit price, log hours, their product, intercept). Uncertainty
  bands come from bootstrapping whole events.
- **Choosing honestly:** ten candidate models and rules were compared on validation only: Shin (1993), power method,
  isotonic, hierarchical, beta calibration, an ensemble, an agreement filter, a time-weighted pool, V3 and COH. Their
  errors correlate 0.987–0.9999: every model reads the same price. The test was opened for the two finalists, side by
  side.
- **App:** FastAPI backend, Next.js + Tailwind site, a Chrome extension, an MCP server and a Gemini agent, on Railway.
- **Team workflow:** three roles (model/backend, front end, data/pitch), each with Claude Code agents. The agents argue
  in writing through per-role inbox files in the repo, and every PR is reviewed by an agent of another role.

## Challenges
- **Our first result was wrong, and we caught it.** A 3,100-market sample said "politics, a month out". 34,677 markets
  didn't replicate it. We kept the bigger result and tell this story.
- **Look-ahead traps**, all caught by our own review and rerun:
  - markets that close early;
  - the actual close time vs the scheduled one;
  - correlated legs of one event leaking across a split;
  - 260 early legs that resolved before our cutoff.
- **Fees and leverage:** at first we had ignored Polymarket's taker fees, and "+304%" became "+190%". We kept the lower
  number, then switched the headline to per dollar staked so leverage can't flatter it.
- **A placebo that couldn't fail:** our first null kept the bias by construction. A teammate caught it; the honest null
  is "prices are right".
- **No historical order book:** costs use live spreads with a 1¢ floor, a stated limitation.

## What we learned
- Ten models agreed because they all read the same price. The money came from a rule about *events* and *time*, not a
  cleverer formula.
- The classic betting model (Shin) gets Polymarket backwards: its insider share comes out negative at every horizon.
- We lose two bets in three and still make money per dollar. Most of the job is saying "not yet".

## What's next
- Polymarket combos (priced by request-for-quote), through the same calibration lens.
- Whether skilled wallets trade against us (Gómez-Cram et al. 2026).
- Historical spreads from on-chain fills.
- Kalshi, where a public study finds the opposite bias.

## Built with
python, pandas, scikit-learn, fastapi, next.js, tailwind, recharts, polymarket-api, chrome-extension, mcp, gemini, railway, opentimestamps, claude-code

## Sponsor track
- **HRT — Best use of data for predictions & decision making:** real data → calibrated probability with uncertainty →
  a Buy / Wait / Skip decision with expected value after fees. Evaluated out of time against the market as baseline,
  with robustness checks, and with the failures shown.

## What we brought in vs built here
- **Brought in:** the published finding (arXiv 2602.19520), public Polymarket APIs, open-source libraries, the browser
  layer of the extension (Gleb's pre-hackathon code), a starter design preset.
- **Built at OxHack:** the data pipeline, the dataset, the model and its evaluation, the decision rule, the backtest and
  robustness checks, the API, the site, the agent, the journal and the sealed predictions.

## Gallery images
- `integrations/robustness/shin_time.png`: the TIME slide. The classic model's insider share by time to resolution:
  ≈ 0 a month out, most negative in the last day.
- `integrations/robustness/by_month.png`: edge by month, refitted monthly.
- `integrations/robustness/placebo.png`: real result vs "prices are right" placebo.
- `integrations/robustness/costs.png`: cost sensitivity.
