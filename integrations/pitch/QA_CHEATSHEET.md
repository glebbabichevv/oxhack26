# Judge Q&A cheat sheet — HRT (Role C)

Short answers first, detail only if they push. Every number is from `backend/results/*.json` (model 2026-10-24-390c312,
policy COH), `integrations/ensemble/`, `integrations/robustness/`, `integrations/model_eval/` or
`integrations/methods/summary.json`.
Golden rule: if you don't know, say "we didn't measure that", then what we would do. Never guess a number.

## The numbers to know cold
| what | value |
|---|---|
| markets: pulled / train / test | 34,677 / 23,838 / 10,579 (260 test legs that resolved before the cutoff dropped) |
| split | by time: train = events ended before **18 May 2026**; test = markets of later events resolved after it; events never straddle |
| horizons | 30d, 7d, 3d, 1d, 12h before the **scheduled** end date |
| 15¢ contract wins… (test) | 30d ~13% (fair, within noise) · 7d–12h 18–20% |
| model | logistic regression, 4 coefficients: logit(p), log(hours), their product, intercept |
| Brier, model vs market (test) | 0.1297 vs 0.1305 (log loss 0.3917 vs 0.3940) |
| **headline: COH** | **+31¢ per $1 staked after fees** (site +31.3¢), 90% CI **[+22.2¢, +40.5¢]**, 1,827 bets, +4.38 bankrolls [3.12, 5.68], hit rate 31%, max DD 0.22, peak open stake 0.42 |
| COH, stale/event-over filters | +30.0¢ [21.6, 40.0] |
| V3 beside it (no event rule) | +17.2¢ [+11.8, +23.5], 3,653 bets, +4.01 bankrolls, max DD 0.38 |
| naive "always back the favourite" | −8.70 bankrolls (8,159 bets, 73% hit rate) |
| rule (COH) | ≤ 24 h before end · net edge ≥ 1¢ after spread + fee + model band · event's outcome probabilities scaled to sum 1 (books summing 0.95–1.25) · max one bet per event · ¼ Kelly capped 5% · open stake ≤ 1 bankroll |
| why 24 h | return per trade by entry horizon: 7d +7.8%, 3d +8.8%, 1d +13.8%, 12h +18.5%; 30d: nothing clears 1¢ after fees |
| models compared | 10 candidates on validation (V3, COH, beta, mean ensemble, agreement filter, time-weighted pool, Shin, power, isotonic, hierarchical) |
| model errors correlate | 0.987–0.9999 ("every model reads the same price") |
| by month (V3, refit monthly) | positive in **13 of 15** months, CI below 0 in none; all 5 test months positive · COH: **14 of 15** (months with 30+ bets; 15 of 17 counting 1- and 4-bet months) |
| placebo "prices are right" | same COH trades with outcome ~ Bernoulli(price): −8.1¢ [−15.2, −0.6]; real +31.2¢; **0 of 1,000** draws |
| deflated Sharpe | COH 0.9999 (12 trials) · V3 test P(true SR > 0) 0.999996 |
| costs ×2 | V3 survives double Polymarket fees: +15.7¢ [9, 22] (1¢ floor), +13.8¢ [5, 22] (2¢ floor) |
| capacity (one live snapshot) | ~$10k per market on deep football books, ~$1k on typical ones |
| by domain (test, descriptive) | COH sports +34.7¢ [25, 45]; politics +65¢ [14, 119] (116 bets); culture −13.5¢ (only negative); crypto ≈ 0 |

## Model
**Q: What exactly is the model?** Logistic regression on logit(price), log(hours to the scheduled end) and their
product. It learns how much to stretch each price, and how that changes with time to resolution.

**Q: Why so simple? Did you try more?** Ten candidates, chosen on validation only. Their errors correlate 0.987–0.9999:
every model reads the same price, so no fancier model adds much. What won wasn't a better formula, it was a rule about
events (COH).

**Q: What is COH?** In a multi-outcome event (e.g. home / draw / away), our probabilities are scaled to sum to 100%
across the outcomes, and we take at most one bet per event (the largest net edge). Validation, paired against V3:
+8.8¢ per $1 [+0.7, +17.3]. Test, opened for the two finalists: COH +31¢ vs V3 +17¢, total profit about the same,
half the drawdown. The gain comes from **one bet per event**, not from picking the leg: a random eligible leg earns about
the same (+33.5¢), and all legs without the cap only +24.3¢.

**Q: Brier 0.1297 vs 0.1305 is tiny.** The market is a strong baseline. Significance is in the money: the event-bootstrap
CI on ¢ per $1 excludes zero, and we only trade where the edge clears costs *and* the model's own 10–90% band.

**Q: Isn't this the favourite-longshot bias?** Largely, and it's known from horse racing. What we add is the *when*: a
month out the market is about fair; within the last day, longshots in the 10–35¢ band win more often than priced.

**Q: Why does the bias exist?** We measure it, we don't explain it. Plausible: thin books near resolution, demand for
favourites. Don't go further.

## The paper and the literature
**Q: The paper you cite says prices are compressed toward 50% far from resolution.** Yes, and **we did NOT reproduce
that direction**: on our test, prices are about fair a month out and too extreme near resolution.

**Q: Didn't Cardozo & Rivero-Wildemauwe (arXiv 2609.12878) find longshots OVERpriced?** Under 10¢, yes. On our data,
before costs, those buys win more than priced (+21¢ per $1). After a realistic spread they lose 16.6¢: a 1¢ half-spread
on a 3¢ contract is a 33% haircut. Their −6.3¢ is measured on executed trades, which pay that spread, and it's why we
never trade under 10¢. Their event-grouped +4.1¢ is the same mechanism as our one-bet-per-event rule. In the 10–35¢ band
within 24 h, the edge doesn't depend on the weighting (+22¢ vs +24¢ gross, +15.7¢ after costs).

**Q: Anyone else see this?** A public 46k-market study (github.com/hrishi-tailor/prediction-market-calibration) finds the
same overconfidence on Polymarket near resolution (slope 0.91–0.93; ours ≈ 0.85), and the opposite on Kalshi.
Qiu & Qiu (arXiv 2610.13593, Polymarket weather) find favourites overpriced most in the final 1–12 h: an independent
replication in a domain we don't trade.

**Q: What about Kalshi?** On 931 sports events listed on both venues (702 events, matched by text and date), the prices
a day out agree within half a cent (median; 89% within 2¢) and are equally accurate (Brier 0.2083 vs 0.2094, paired
difference inside noise). Both are overconfident (calibration slope 0.95 Polymarket, 0.87 Kalshi). So in sports near
resolution we don't see the opposite Kalshi bias the 46k study reports. (`integrations/kalshi/match.json`, PR #21)

**Q: The classic de-vig models (Shin, power)?** They get Polymarket backwards. Shin assumes longshots are overpriced;
fitted freely per horizon, Shin's insider share is negative everywhere: −0.012 a month out (≈ fair), −0.073 a day out.
Trading Shin loses money (−6.9¢ per $1 walk-forward, 670 trades).

## Costs, fees, exposure (HRT will go here)
**Q: Fees?** Each market's own Polymarket taker-fee schedule: fee per share = rate × p(1−p) (sports mostly 3–5%, crypto
7%, geopolitics 0), plus max(half the spread, 1¢). We assume we always take. Caveat: the API only has today's schedule.

**Q: What if costs are higher?** Descriptive grid on test: V3 survives double the fees (+15.7¢) and a 2¢ half-spread floor
(+13.8¢). At a 3¢ floor almost nothing clears the 1¢ rule.

**Q: Fills / historical spreads?** Entry price = last trade at or before the target moment (prior prints only; 98.9% of
trades ≤ 1 h old). Historical spreads aren't available, which is a stated limitation. Dropping stale prices and markets
already over leaves COH at +30.0¢.

**Q: Capacity?** One live snapshot, walking the actual order book: tonight's football bets kept +2.3–3.2¢ net per share
up to $10k each. Typical markets: ~$1k before slippage eats the edge.

**Q: Leverage?** Open stakes are capped at one bankroll (peak 0.42 for COH). The headline is per dollar staked, which
doesn't depend on leverage.

## Look-ahead and leakage (they WILL ask)
1. Clock = the **scheduled** end date (known in advance). The actual close time would leak the outcome.
2. Price = last trade at or before the horizon moment, prior prints only.
3. A row exists only if the market was still open then.
4. Split by time, events kept whole, test legs resolved before the cutoff dropped (260), test trades entered on/after the
   cutoff only (embargo).
5. Models and rules chosen on validation (last 20% of train). The test was opened for the two finalists (V3, COH), shown
   side by side. V1/V2 earlier came from teammates who had seen test numbers, so the choice used validation only.
6. COH's books use only legs in our dataset; checked: on Gamma-complete books only, validation +42.4¢ vs +43.1¢.
7. The sealed predictions can't have look-ahead at all: hashed and timestamped in Bitcoin before the outcomes.

## Is it luck? (robustness)
**Q: One lucky period?** Refit monthly over the whole history: V3 positive in 13 of 15 months, CI below zero in none;
COH positive in 14 of 15 months with 30+ bets. All five test months positive: the bias isn't fading as Polymarket grows.
**Q: Placebo?** If prices were exactly right (outcome drawn from the price), the same COH trades lose 8¢ per $1. We make
+31¢. Zero of 1,000 draws came close.
**Q: Multiple testing?** Deflated Sharpe for COH among 12 trials: 0.9999. The trials are near-copies (errors correlate
0.99), so deflation is conservative.
**Q: Losing streaks?** Hit rate 31%: we lose about two bets in three. Longest losing streak on test: 25 (bets within one
event are correlated). The site shows the real streak.

## Where it fails (say it proudly)
- A month out: no edge after fees; nothing clears 1¢.
- Culture is the only negative domain (COH −13.5¢); crypto ≈ 0. Shown, not cut: cutting after seeing the test would be
  snooping.
- Crypto priced as options from Binance (1,106 markets): the market already does it better (Brier 0.1399 vs 0.1471).
- Under 10¢: costs eat it.
- Selling before resolution didn't beat holding on validation: hold to the end.

## The honesty story ("what went wrong?")
1. Our first 3,100-market sample said "politics, a month out". On 34,677 markets it didn't replicate.
2. 260 test markets had resolved before the cutoff. Dropped, rerun.
3. Fees and leverage were missing: +304% became +190%. We kept the lower number.
4. Our first placebo kept the bias by construction; a teammate caught it, and the Bernoulli null is the honest one.

## Next steps (if asked)
- Polymarket combos are priced by request-for-quote; Kalshi research (arXiv 2607.14430) finds parlays ~3% per leg above
  the product of their legs. Same calibration lens once quotes are observable.
- Do skilled wallets trade against us? Classify accounts by sign-randomised P&L (Gómez-Cram, Guo, Jensen & Kung 2026)
  and split our bets by informed flow.
- Historical spreads from on-chain fills.

## Team / process
Three roles with Claude Code agents. Agents message each other through per-role inbox files in the repo and review each
other's PRs from a different role. Every number above was challenged by another role's agent before it reached the screen.
