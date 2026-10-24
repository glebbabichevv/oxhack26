# Judge Q&A cheat sheet — HRT (Role C)

Short answers first, detail only if they push. Every number is from `backend/results/*.json` or `backend/model.py` (15:20 Sat).
Golden rule: if you don't know, say "we didn't measure that", then say what we would do. Never guess a number.

## The 20 numbers to know cold
| what | value |
|---|---|
| markets total / train / test | 34,677 / 23,838 / 10,839 |
| split | by time: train = events ended before **18 May 2026**, test = after; all legs of an event on one side |
| horizons | 30d, 7d, 3d, 1d, 12h before the **scheduled** end date |
| price band modelled & traded | 3–97¢ |
| calibration slope | ≈ 0.85 at every horizon (< 1 = prices overconfident) |
| Brier, model vs market (test) | **0.1274 vs 0.1281** |
| log loss, model vs market (test) | 0.3851 vs 0.3871 |
| validation log loss, market / simple / full | 0.5688 / 0.5645 / 0.5682 → "simple" chosen |
| trades (with costs) | 7,228 |
| profit after costs | **+2.77 starting bankrolls**, additive, 90% CI [1.41, 4.07] (event bootstrap) |
| profit without costs | +7.06 (8,209 trades) |
| hit rate | 24% (longshot-heavy) |
| max drawdown | **42%** of starting bankroll |
| concentration | top 10 events = 1.03 of the 2.77 |
| naive "always back the favourite" | **−7.1** (2% flat stakes, 73% hit rate, same markets) |
| return per $1 trade by entry horizon (costs) | 30d −0.4% · 7d +2.5% · 3d +6.5% · 1d +13.8% · 12h +15.5% |
| cost | max(live spread / 2, 1¢) per contract, fee 0 |
| stake | ¼ Kelly on the conservative q, capped at 5% of starting bankroll |

## Model
**Q: What exactly is the model?** Logistic regression, 4 coefficients: intercept, logit(price), log(horizon) and
logit(price) × log(horizon). It learns how much to shrink each price toward 50%, and how that changes with time to
resolution.

**Q: Why so simple? Did you try more?** Yes. A "full" version with domain terms (and their interactions) scored worse on
validation (log loss 0.5682 vs 0.5645), so it overfit. We picked on validation (last 20% of train by time) and never
touched test while choosing.

**Q: Brier 0.1274 vs 0.1281 is tiny. Is that significant?** The market is a very strong baseline, so a small gain is
what you'd expect. Significance is in the money test, not the Brier: the 90% CI on profit, bootstrapped by event, is
[1.41, 4.07] and excludes zero. And we only trade where the edge clears costs *and* the model's own 10–90% interval.

**Q: Why does the bias exist?** We measure it, we don't explain it. Plausible stories: demand for cheap lottery-ticket
contracts, thin order books near resolution. Don't go further than that.

**Q: Isn't this just the favourite-longshot bias?** Largely yes, and from horse racing that's a known pattern. What we add
is the *when*: it is only tradable in the last week, and it's worth nothing a month out.

## Look-ahead and leakage (they WILL ask)
**Q: How do you know there's no look-ahead?**
1. The clock is the scheduled end date, which a trader knows in advance. The actual close time would leak the outcome:
   markets close early when the answer is known.
2. Price = last trade at or before the horizon moment.
3. A row only exists if the market was still open at that moment.
4. The train/test split is by time, and all markets of one event stay on one side.
5. The model is chosen on validation inside train; test is touched once.

**Q: Correlated markets?** "Who wins the Ballon d'Or" is ~30 markets that are basically one bet. That's why the split
keeps events together, and every CI resamples whole events, not markets.

## Backtest
**Q: How is P&L computed?** One trade per market, at the earliest horizon where the net edge is positive, held to
resolution. Return per $1 = payout / (price + cost) − 1. Stake ¼ Kelly. P&L is added up, not compounded, because
positions overlap in time.

**Q: 42% drawdown?** Yes. The equity curve falls before it rises: a longshot strategy loses often and wins big. That's the
honest picture at ¼ Kelly with a 5% cap. A real deployment would size smaller.

**Q: Is it a few lucky events?** Top 10 events are 1.03 of 2.77. That's concentrated, so the CI is computed by
resampling events, and it still excludes zero.

**Q: Costs?** max(half the quoted spread, 1¢) per contract, no fee. Polymarket's API has no historical order book, so
for resolved markets it's the 1¢ floor. Live markets show a median spread around 1¢ (≥ $50k volume).
*Weak spot, say it before they do:* fills are assumed at the historical last-trade price plus the cost. Real fills at the
ask could be worse. Next step: on-chain fills for true historical spreads.

**Q: Capacity?** Not measured. Volume filter is ≥ $50k per market; stakes capped at 5%. We'd need order-book depth.

**Q: Why does 12h look better per trade than 1–7d, if "the edge is 1–7 days"?** The per-horizon chart answers "if you could
only trade at this horizon". The main backtest enters at the *earliest* horizon with an edge, so most profit is booked
from 1–7 days out.

**Q: Why does the test equity curve start in 2025 if the cutoff is May 2026?** The split is by *event*: an event goes
to test if its last market resolved after the cutoff, so early legs of long events (e.g. a tennis major's "winner"
markets) resolved earlier. That's 260 of 10,839 test markets (2.4%). It keeps correlated legs together; for those 260 the model
was trained on slightly later data. [A to confirm whether dropping them changes the result.]

**Q: Test period?** Markets resolved after 18 May 2026: about five months, one regime. That's a fair limitation.

## Where it fails (say it proudly)
- 30 days out: no lift (Brier 0.1020 vs 0.1019).
- Crypto at 1–7 days, politics at most horizons: no lift.
- "Other" domain: 2–3 test markets, too few to say anything.
- Under 10¢ a day out, contracts resolve YES ~3%. Very cheap longshots are *not* underpriced; the effect is ~10–35¢.
- By domain after the tweet-count relabel (A, 14:29): sports +1.84 of the 2.77 (4,484 trades).

## The honesty story (use it if asked "what went wrong?")
Our first 3,100-market sample said "politics, a month out". On 34,677 markets that didn't replicate: the small sample
was top-volume and politics-heavy. The direction (overconfident prices) held; the location didn't. We dropped it.

## Team / process
Three roles with Claude Code agents. Agents message each other through per-role inbox files in the repo and review each
other's PRs from a different role. The sign flip went data → model → pitch in under an hour.
