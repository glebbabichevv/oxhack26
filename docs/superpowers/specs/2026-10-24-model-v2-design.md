# Horizon model v2 — design

Owner: Role C (Ayaz). Candidate for Role A (Gleb) to adopt into `backend/`. Branch `int/model-v2`.

## Goal

The most accurate calibration we can honestly measure, and the highest after-cost return we can honestly
achieve with one bankroll, on Polymarket binary markets. "Honestly" means: every choice (model, features,
Kelly multiplier, minimum edge) is made on a validation slice of train; the out-of-time test set is scored
once, after everything is frozen. We do not promise "highest returns"; we report what the test says.

## What is carried over from earlier findings (2026-10-24)

- Keep: time-dependent calibration (prices overconfident, slope ≈ 0.85), hold to resolution, out-of-time
  split by event (cutoff 2026-05-18), event bootstrap for intervals.
- Fix (from the model audit, inbox 17:52): Polymarket taker fees are missing; open stakes reach 1.86
  bankrolls; model-selection validation splits by market instead of event.
- Exclude as strategies (null after costs): price drift / exit before resolution, shock fade/follow,
  neg-risk overround arbitrage, "Nothing Ever Happens", short-horizon theta. Some survive only as features.

## Layout

```
integrations/model_v2/
  features.py   # build the feature table from data/ (no model code)
  train.py      # playoff, decision layer, backtest, write results/
  results/      # calibration.json, backtest.json, live.json — same shapes as backend/results/
```

Inputs: `data/horizons.csv`, `data/live.csv`, `data/raw/hist/*.json` (hourly YES prices, keyed by Gamma id),
`data/raw/markets_*.json` (Gamma id → conditionId, `feesEnabled`). Run: `python integrations/model_v2/train.py`.

## Features (all computed from information available at that horizon)

| Feature | Definition | Source |
|---|---|---|
| `lp` | logit(price), price clipped to [0.01, 0.99] | horizons.csv |
| `lh` | log(clip(hours, 12, 720) / 24) | horizons.csv |
| `lp_lh` | lp × lh | — |
| `domain` | one-hot, domains with ≥ 50 train rows, else `other` | horizons.csv |
| `by_date` | question matches "by/before <month/date/end/Q/year>" | question text |
| `n_legs`, `book_share` | legs of the event present at this horizon; price / Σ prices of those legs (1.0 for single markets) | event_slug, neg_risk |
| `mom24`, `mom72` | price now − price 24 h / 72 h earlier (0 if missing) | hourly paths |
| `vol72` | std of hourly price changes over the previous 72 h (0 if < 12 points) | hourly paths |
| `fees_on` | `feesEnabled` of the market — used for costs only, not for prediction | raw dump |

Excluded on purpose: `volume_usd` (lifetime volume, includes trading after the horizon → leakage).
Hourly-path features use only points with timestamp ≤ the horizon's `price_ts`.
Live markets: `fetch_live.py` gains a fetch of the last 72 h of hourly prices per live market (cached) and a
`fees_enabled` column, so the same features exist at prediction time.

## Models in the playoff

- **M0** — current simple calibration (logistic on lp, lh, lp_lh), copied from `backend/model.py`.
- **M1** — logistic regression on all features above (standardised; C chosen from {0.1, 1}).
- **M2** — market-anchored gradient boosting: `HistGradientBoostingClassifier` on all features
  (max_depth 3, learning_rate 0.05, max_iter ≤ 300 with early stopping inside the fit slice,
  min_samples_leaf 200), then anchored to the market: `q = σ(lp + clip(logit(q_gbm) − lp, −0.7, 0.7))`,
  so it can move the market's log-odds by at most ±0.7.

Selection: train is split by **event** into fit (events ending in the first 80% of time) and validation
(last 20%). Each model is fitted on fit, scored by log loss on validation (3–97¢ rows). Winner = lowest
log loss; ties within 0.0005 go to the simpler model (M0 < M1 < M2). Winner is refitted on all train.
Uncertainty band: 10th–90th percentile of q over 40 event-bootstrap refits (M2: 20 refits).

## Decision layer

- `cost = max(spread/2, 0.01) + fees_on × fee_rate[domain] × p × (1 − p)`; fee rates from
  docs.polymarket.com/trading/fees: sports 0.05, crypto 0.07, politics 0.04, science_tech 0.04,
  economics 0.05, culture 0.05, other 0.05, geopolitics 0. Charged on entry only (held to resolution).
  Today's rates are applied to the whole test period, which is conservative (sports was reportedly 0.03
  before July 2026).
- Trade if `q_lo − (p + cost) > min_edge` (BUY_YES) or `(p − cost) − q_hi > min_edge` (BUY_NO), 3–97¢ only.
- Stake = `kelly_mult × (q* − c)/(1 − c)` on the conservative q*, capped 5% per trade, 10% per event.
- One trade per market, at the earliest horizon that qualifies; hold to resolution.
- Exposure cap: replay trades in entry-time order (entry = end_date − horizon); a trade is scaled down so
  that the sum of open stakes ≤ 1.0 bankroll; stakes are released at `resolved_at`. Additive P&L.
- `kelly_mult` ∈ {1/8, 1/4, 1/2} and `min_edge` ∈ {0, 0.01, 0.02, 0.03} chosen by validation P&L
  (the winning model, fitted on fit, traded on validation with the same rules).

## Evaluation (test set, scored once)

Reported in `results/backtest.json` (existing keys kept, new keys added):
- Brier and log loss: market, M0, winner; by horizon and domain (calibration.json).
- With costs+fees: return (bankrolls), 90% event-bootstrap CI, hit rate, max drawdown, peak exposure,
  return per $1 staked, by domain, by horizon; same without costs; naive favourite.
- `model_selection`: validation log loss of M0/M1/M2, chosen model, chosen `kelly_mult` / `min_edge`.
- `failures[]`: existing kinds plus `kind: "null_strategy"` entries for the four null probes (text only,
  numbers from the inbox notes of 16:52 and 17:45).
- `assumptions[]`: updated for fees and the exposure cap.

Fallback: if M1 and M2 do not beat M0 on validation, v2 ships M0 with the fee and exposure fixes.

## Handoff

PR `int/model-v2` → main with a comparison table (current backend vs v2, same test set) and a note in
`team/inbox/A.md`. Gleb decides whether `backend/` imports v2 or copies the decision fixes. The API contract
does not change (shapes identical; new keys are additive).

## Out of scope

Exit-before-resolution trading, news/LLM features, cross-venue data, compounding, live order placement.
