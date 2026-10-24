# Judge Q&A cheat sheet — HRT (Role C)

Short answers first, detail only if they push. Every number is from `backend/results/*.json` (model 2026-10-24-390c312,
fees on, 18:15 Sat) and matches https://horizon-two-gilt.vercel.app at 18:25.
Golden rule: if you don't know, say "we didn't measure that", then say what we would do. Never guess a number.

## The numbers to know cold
| what | value |
|---|---|
| markets: pulled / train / test | 34,677 / 23,838 / 10,579 (260 test legs that resolved before the cutoff dropped) |
| split | by time: train = events ended before **18 May 2026**; test = markets of later events that resolved after it |
| horizons | 30d, 7d, 3d, 1d, 12h before the **scheduled** end date |
| price band modelled & traded | 3–97¢ |
| 15¢ contract wins… | 30d 13% (n=492, within noise of 15%) · 7d 18% · 3d 19% · 1d 20% · 12h 20% |
| Brier, model vs market (test) | **0.1297 vs 0.1305** (log loss 0.3917 vs 0.3940) |
| validation log loss, market / simple / full | 0.5688 / 0.5645 / 0.5672 → "simple" chosen |
| cost | max(spread / 2, 1¢) + Polymarket taker fee rate × p(1−p), each market's own schedule (93.5% of test rows fee-on) |
| **profit, headline** | **+190% of starting bankroll**, 90% CI [+94%, +285%], 6,013 trades, open stakes capped at 1 bankroll |
| uncapped | +205% [+115%, +306%], 6,102 trades, open stakes peak at 1.20 bankrolls |
| per $1 actually staked | **+11.9%** capped · +12.7% uncapped |
| max drawdown / hit rate | 31% capped (29% uncapped) / 21% (longshot-heavy) |
| before any costs | +759% (8,054 trades) |
| naive "always back the favourite" | **−908%** (2% flat stakes, 8,372 trades, 73% hit rate, same markets) |
| return per $1 trade by entry horizon | 30d **−19.0%** (313 trades) · 7d +2.3% · 3d +5.0% · 1d +12.6% · 12h +14.8% |
| by domain | sports **+132%** [+77%, +192%] (3,770 trades), science/tech +30% [+9%, +53%]; all others' CIs include 0; crypto −4% |
| stake | ¼ Kelly on the conservative q, capped at 5% of starting bankroll per trade |
| sealed (A) | Seal 1, Sat 16:31: 359 markets, SHA-256 + OpenTimestamps; metric pre-registered = Brier |
| frozen calls (C) | from Sat 15:43, a snapshot every 2 h: open markets ending ≤ 48 h, trade calls + P&L (`integrations/forward/score.json`) |

## Model
**Q: What exactly is the model?** Logistic regression, 4 coefficients: intercept, logit(price), log(horizon) and
logit(price) × log(horizon). It learns how much to move each price, and how that changes with time to resolution.

**Q: Why so simple? Did you try more?** Yes. A "full" version with domain terms scored worse on validation (log loss
0.5672 vs 0.5645), so it overfit. We picked on validation (last 20% of train by time) and never touched test while choosing.

**Q: Brier 0.1297 vs 0.1305 is tiny. Is that significant?** The market is a very strong baseline, so a small gain is
expected. Significance is in the money test: the 90% CI on profit, bootstrapped by event, is [+94%, +285%] and excludes
zero. And we only trade where the edge clears costs *and* the model's own 10–90% interval.

**Q: Why does the bias exist?** We measure it, we don't explain it. Plausible stories: demand for cheap lottery-ticket
contracts, thin order books near resolution. Don't go further than that.

**Q: Isn't this just the favourite-longshot bias?** Largely yes; it's known from horse racing. What we add is the
*when*: a month out the market is about fair and trading loses 19% a trade after fees; 12–24 hours out it makes 12–15%.

## Costs, fees, exposure (HRT will go here)
**Q: Did you include Polymarket's fees?** Yes. Each market's own taker-fee schedule from Polymarket's API:
fee per share = rate × p(1−p) (sports mostly 3% or 5%, crypto 7%, politics 4% or 0, geopolitics 0), plus half the
spread with a 1¢ floor. Makers pay no fee, so we assume we always take. Caveat: the API only has today's schedule.
Without fees it was +304%; Ayaz on our team audited the model and caught it.

**Q: Stakes are fractions of the starting bankroll, but positions overlap. Leverage?** Uncapped, open stakes peaked at
1.20 bankrolls. The headline re-runs the same trades with total open stake capped at one bankroll: +190%. Per dollar
actually staked: +11.9%.

**Q: Fills?** Assumed at the historical last-trade price plus the cost. Real fills at the ask could be worse. Next step:
on-chain fills for true historical spreads.

**Q: Capacity?** Not measured. Volume filter ≥ $50k per market; stakes capped at 5%. We'd need order-book depth.

## Look-ahead and leakage (they WILL ask)
**Q: How do you know there's no look-ahead?**
1. The clock is the scheduled end date, which a trader knows in advance. The actual close time would leak the outcome:
   markets close early when the answer is known.
2. Price = last trade at or before the horizon moment (≤ 1 h stale on ~100% of traded rows).
3. A row only exists if the market was still open at that moment.
4. The split is by time, all markets of one event stay on one side, and test markets that resolved before the cutoff
   are dropped (260 early legs of long events, caught in our own QA).
5. The model is chosen on validation inside train; test is touched once.
6. The sealed predictions can't have look-ahead at all: hashed and timestamped before the outcomes existed.

**Q: Correlated markets?** "Who wins the Ballon d'Or" is ~30 markets that are basically one bet. That's why the split
keeps events together, and every CI resamples whole events, not markets.

## Sealed before the outcomes
**Q: How do we know you didn't pick the snapshot after seeing results?** Two layers. Gleb's Seal 1 (Sat 16:31) is a
SHA-256 of the probabilities, timestamped in Bitcoin with OpenTimestamps, with the metric written down first (Brier).
My frozen calls are commits pushed to GitHub every 2 h from 15:43; the PR timeline shows each push time. Each market is
scored from its *earliest* snapshot.
**Q: Which markets are scored?** Only ones whose *scheduled* end date has passed. Scoring "whatever resolved early"
would select on the outcome ("X by Friday" resolves early only if X happened).
**Q: So does it prove the edge?** No: one night is far too few markets, and we said so before sealing. It proves the
calls are real and made before the answer existed. The evidence for the edge is the backtest's interval.

## Backtest
**Q: How is P&L computed?** One trade per market, at the earliest horizon where the net edge is positive, held to
resolution. Return per $1 = payout / (price + cost) − 1. Stake ¼ Kelly. P&L is added up, not compounded.

**Q: Drawdown?** 31% of the starting bankroll with the cap. A longshot strategy loses often and wins big.

**Q: The per-horizon numbers don't add up to 6,102 trades.** Each is its own backtest: "if you could only trade at this
horizon". The main backtest enters at the *earliest* horizon with an edge, once per market.

**Q: "Trading is 100× better per day near resolution"?** Don't claim it: different market sets, ~21% hit rate, no
liquidity data. Say short trades tie up capital ~30× less time.

**Q: Test period?** Markets resolved after 18 May 2026: about five months, one regime. That's a fair limitation.

## Where it fails (say it proudly)
- A month out: no Brier lift (0.1050 vs 0.1051), and trading loses 19% a trade after fees.
- Crypto loses money (−4%, 865 trades); crypto and culture show no lift at any horizon; politics none at 3–7 days.
  27 cells in total on the screen.
- We also priced 1,106 crypto threshold markets as options from Binance spot and volatility: the market already does
  it (Brier 0.1399 market vs 0.1471 exchange formula; trading the formula loses 16.5% per $ after fees). Null result, PR #10.
- Only sports is solid by domain.
- Under 10¢ a day out, contracts resolve YES ~3%. Very cheap longshots are *not* underpriced; the effect is ~10–35¢.

## The honesty story (use it if asked "what went wrong?")
1. Our first 3,100-market sample said "politics, a month out". On 34,677 markets it didn't replicate: the small sample
   was top-volume and politics-heavy. The direction held; the location didn't.
2. 260 test markets had resolved before the cutoff. Dropped, rerun.
3. Fees were missing: +304% became +190% with Polymarket's real fees and an exposure cap. The edge survived.

## Team / process
Three roles with Claude Code agents. Agents message each other through per-role inbox files in the repo and review each
other's PRs from a different role. Every number above was challenged by another role's agent before it reached the screen.
