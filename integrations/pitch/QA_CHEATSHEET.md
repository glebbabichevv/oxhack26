# Judge Q&A cheat sheet — HRT (Role C)

Short answers first, detail only if they push. Every number is from `backend/results/*.json` (A's 14:46 rerun, after
dropping the 260 pre-cutoff test legs) or `backend/model.py`. Checked against the live screen at 15:55 Sat.
Golden rule: if you don't know, say "we didn't measure that", then say what we would do. Never guess a number.

## The numbers to know cold
| what | value |
|---|---|
| markets used / train / test | 34,417 / 23,838 / 10,579 (34,677 pulled; 260 test legs that resolved before the cutoff dropped) |
| split | by time: train = events ended before **18 May 2026**; test = markets of later events that resolved after it |
| horizons | 30d, 7d, 3d, 1d, 12h before the **scheduled** end date |
| price band modelled & traded | 3–97¢ |
| calibration | slope ≈ 0.85 pooled; 30d test about fair (15¢ → 12.8%, n=492), 7d–12h overconfident (15¢ → 18–20%) |
| Brier, model vs market (test) | **0.1297 vs 0.1305** |
| log loss, model vs market (test) | 0.3917 vs 0.3940 |
| validation log loss, market / simple / full | 0.5688 / 0.5645 / 0.5672 → "simple" chosen |
| trades (with costs) | 7,106 (6,286 buy YES, 820 buy NO) |
| profit after costs | **+304% of starting bankroll** (3.05 bankrolls, summed), 90% CI [+184%, +440%] (event bootstrap) |
| profit without costs | +759% (8,054 trades) |
| hit rate | 24% (longshot-heavy) |
| max drawdown | **42%** of starting bankroll |
| concentration | top 10 events = 1.03 of the 3.05 bankrolls; without them +2.02 |
| by domain | sports **+185%** [+111%, +263%] (4,475 trades), science/tech +42% [+16%, +72%]; all others' CIs include 0 |
| naive "always back the favourite" | **−741%** (2% flat stakes, 8,372 trades, 73% hit rate, same markets) |
| return per $1 trade by entry horizon (costs) | 30d +4.6% · 7d +4.6% · 3d +7.3% · 1d +14.3% · 12h +16.3% |
| cost | max(live spread / 2, 1¢) per contract, fee 0 |
| stake | ¼ Kelly on the conservative q, capped at 5% of starting bankroll |
| forward test | snapshot 15:43 Sat, 163 open markets ending within 48 h, 75 trades; see `integrations/forward/score.json` |

## Model
**Q: What exactly is the model?** Logistic regression, 4 coefficients: intercept, logit(price), log(horizon) and
logit(price) × log(horizon). It learns how much to shrink each price toward 50%, and how that changes with time to
resolution.

**Q: Why so simple? Did you try more?** Yes. A "full" version with domain terms (and their interactions) scored worse on
validation (log loss 0.5672 vs 0.5645), so it overfit. We picked on validation (last 20% of train by time) and never
touched test while choosing.

**Q: Brier 0.1297 vs 0.1305 is tiny. Is that significant?** The market is a very strong baseline, so a small gain is
what you'd expect. Significance is in the money test, not the Brier: the 90% CI on profit, bootstrapped by event, is
[+184%, +440%] and excludes zero. And we only trade where the edge clears costs *and* the model's own 10–90% interval.

**Q: Why does the bias exist?** We measure it, we don't explain it. Plausible stories: demand for cheap lottery-ticket
contracts, thin order books near resolution. Don't go further than that.

**Q: Isn't this just the favourite-longshot bias?** Largely yes; it's a known pattern from horse racing. What we add is
the *when*: the market is about fair a month out and gets overconfident as resolution nears, and the return per trade
roughly triples from 30 days out (+4.6%) to a day out (+14.3%).

## Look-ahead and leakage (they WILL ask)
**Q: How do you know there's no look-ahead?**
1. The clock is the scheduled end date, which a trader knows in advance. The actual close time would leak the outcome:
   markets close early when the answer is known.
2. Price = last trade at or before the horizon moment.
3. A row only exists if the market was still open at that moment.
4. The split is by time, all markets of one event stay on one side, and test markets that resolved before the cutoff
   are dropped (260 of them: early legs of long events, caught in our own QA).
5. The model is chosen on validation inside train; test is touched once.
6. And the forward test can't have look-ahead at all: the calls were pushed to GitHub before the outcomes existed.

**Q: Correlated markets?** "Who wins the Ballon d'Or" is ~30 markets that are basically one bet. That's why the split
keeps events together, and every CI resamples whole events, not markets.

## Forward test (the one nobody can overfit)
**Q: How do we know you didn't pick the snapshot after seeing results?** The snapshot file is in a commit pushed to
GitHub at 15:43 Sat (PR timeline shows the push time), before the matches. Every 2 hours after that a new snapshot was
pushed, and the scorer takes each market from its *earliest* snapshot. q is a deterministic function of the price and
the clock, from the same model as the screen (refit reproduces live.json to 5e-5).
**Q: Which markets are scored?** Only markets whose *scheduled* end date has passed. Scoring "whatever resolved early"
would select on the outcome ("X by Friday" resolves early only if X happened).
**Q: So does it prove the edge?** No: a day of trades is far too few. It proves the pipeline makes real calls in real
time and that we're not fitting history. The evidence for the edge is the backtest's interval.

## Backtest
**Q: How is P&L computed?** One trade per market, at the earliest horizon where the net edge is positive, held to
resolution. Return per $1 = payout / (price + cost) − 1. Stake ¼ Kelly. P&L is added up, not compounded, because
positions overlap in time. "+304%" = the sum of stakes × returns, as a share of the starting bankroll.

**Q: 42% drawdown?** Yes. The equity curve falls before it rises: a longshot strategy loses often and wins big. That's the
honest picture at ¼ Kelly with a 5% cap. A real deployment would size smaller.

**Q: Is it a few lucky events?** Top 10 events are 1.03 of the 3.05 bankrolls, several of them Bitcoin-price ladders.
Without them it's still +2.02. The CI is computed by resampling events, and it excludes zero.

**Q: Costs?** max(half the quoted spread, 1¢) per contract, no fee. Polymarket's API has no historical order book, so
for resolved markets it's the 1¢ floor. Live markets show a median spread around 1¢ (≥ $50k volume).
*Weak spot, say it before they do:* fills are assumed at the historical last-trade price plus the cost. Real fills at the
ask could be worse. Next step: on-chain fills for true historical spreads.

**Q: Capacity?** Not measured. Volume filter is ≥ $50k per market; stakes capped at 5%. We'd need order-book depth.

**Q: The per-horizon bars don't add up to 7,106 trades.** Each bar is its own backtest: "if you could only trade at this
horizon". The main backtest enters at the *earliest* horizon with an edge, once per market.

**Q: 30 days out calibration is "about fair", but the bar says +4.6%?** The bar is 841 trades, a small, noisy edge;
the calibration bins at 30d are within noise of fair. We don't claim a month-out edge.

**Q: Test period?** Markets resolved after 18 May 2026: about five months, one regime. That's a fair limitation.

## Where it fails (say it proudly)
- 30 days out: no Brier lift (0.1050 vs 0.1051).
- Crypto at every horizon, culture at every horizon, politics at 3–7 days: no lift. 26 cells in total on the screen.
- Only sports is solid by domain; everything else's CI includes 0.
- "Other" domain: 2–3 test markets, too few to say anything.
- Under 10¢ a day out, contracts resolve YES ~3%. Very cheap longshots are *not* underpriced; the effect is ~10–35¢.

## The honesty story (use it if asked "what went wrong?")
Our first 3,100-market sample said "politics, a month out". On 34,677 markets that didn't replicate: the small sample
was top-volume and politics-heavy. The direction (overconfident prices) held; the location didn't. We dropped it.
Second catch: 260 test markets had resolved before the cutoff (early legs of long events). We dropped them and reran.

## Team / process
Three roles with Claude Code agents. Agents message each other through per-role inbox files in the repo and review each
other's PRs from a different role. The sign flip went data → model → pitch in under an hour.
