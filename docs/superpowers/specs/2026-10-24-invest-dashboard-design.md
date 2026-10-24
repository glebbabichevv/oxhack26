# Invest dashboard — design

Date: 2026-10-24 · Branch: `int/invest-dashboard` · Status: approved in brainstorming, awaiting spec review

## Goal
A simple page that non-specialist workers can use to (1) see the profit our model has made and
(2) give it a budget ("invest $1000") that it spreads across Polymarket bets automatically,
buying only when the model sees an edge after fees. **Real money**, fully automatic inside hard limits.

## Decisions
| Question | Decision |
|---|---|
| Whose money | Real money on Polymarket (live CLOB orders via `py-clob-client`) |
| Control | Fully automatic inside per-plan hard limits; one-tap Pause / Stop |
| Profit chart | Two lines: real-money equity (solid) and the out-of-time backtest after costs (dashed, grey, labelled) |
| Where | New `/invest` page in the existing Next.js app; trading loop inside the FastAPI backend |

## 1. Screen (`frontend/app/invest/page.tsx`)
Top to bottom, plain words, no jargon:
1. **Money summary** — four tiles: Invested, Now worth, Profit ($ and %), Cash not yet used.
2. **Profit chart** — reuses `EquityChart`. Solid line "Our real money"; dashed grey line
   "If we'd followed the model since May (test, after costs)". One-line caption explains the difference.
   Hover shows date + value.
3. **Start investing card** — How much (default $1000), Max per bet (default $25),
   Daily loss stop (default 10% of budget). **Start** → PIN prompt → plain-words confirmation
   ("Up to 40 bets of up to $25, only when the model sees an edge after fees").
4. **Plan status** — "Running · checks every 10 min · last check 2 min ago"; big Pause / Resume / Stop.
   Auto-pause reasons shown in words.
5. **Recent bets feed** — "Bought YES on 'Will Arsenal win?' at 41¢, $25. Model thinks 47%. Settles in 2 days."
   Status chip: Open / Won (+$36) / Lost (−$25) / Skipped (reason).

Accessibility: large type, colour never the only signal (signs + words), keyboard-usable,
visible focus, works at phone width. Styling follows `DESIGN.md` and `frontend/design/tokens.css`.

## 2. Auto-buyer (`backend/trader.py`)
Runs every 10 minutes for each `running` plan:
1. Take current decisions (same source as `/api/live`, already net of spread, taker fee and model uncertainty).
2. Keep `BUY_YES` / `BUY_NO` with `net_edge > 0`, sorted by `net_edge` descending.
3. Stake = ¼ Kelly (`kelly_fraction`) × plan's current value, then clip to:
   - per-bet max (plan setting, ≤ global `POLYMARKET_MAX_BET_USD`);
   - ≤ 5% of plan budget per market; ≤ 10% per event (correlated legs);
   - plan's available cash; global `MAX_TOTAL_EXPOSURE_USD` across all plans;
   - skip if below Polymarket's minimum order size.
   Never buy a market the plan already holds on the opposite side.
4. Re-quote on the live order book immediately before buying (`polymarket_trading.quote`). If the
   edge after fees at the quoted worst price is ≤ 0, skip and log `edge_vanished`. Orders are
   fill-and-kill, capped at the quoted worst price.
5. Log every buy, skip, settlement and pause to `orders.json`.

**Settlement:** each cycle checks Gamma for resolved markets held by any plan → Won ($1/share) or
Lost ($0); proceeds return to plan cash and can be re-invested. Open bets are marked at the live bid.

**Auto-pause:** day's realised + marked loss > daily loss stop; 3 consecutive Polymarket errors;
model/live data older than 2 hours. **Stop** cancels future buying only — open bets ride to settlement
(selling early pays the spread twice).

**Single runner:** the loop is an asyncio task started on FastAPI startup, guarded by a lock file
(`data/raw/trader.lock`) so two processes can never trade at once.

## 3. Data, API, security
**Storage** (gitignored `data/raw/`): `plans.json` (id, created_at, budget, max_bet, daily_loss_stop,
status, cash, pause_reason) and `orders.json` (append-only events: buy, skip, settle, pause, error).

**Endpoints** (additive to API contract v1.1):
- `GET /api/plans` → plans with invested, value, profit, cash, status, last_check
- `POST /api/plans` {budget, max_bet, daily_loss_stop} — PIN
- `POST /api/plans/{id}/pause|resume|stop` — PIN
- `GET /api/orders?plan=&limit=` → feed events, newest first
- `GET /api/pnl` → `{real: [{t, value}], backtest: [{t, value}]}` (backtest rescaled to $ of the plan budget, labelled)

**PIN:** `DASHBOARD_PIN` in `.env.local`, sent as `X-Dashboard-Pin` header, checked server-side on
every write. 3 wrong tries → writes locked 5 minutes. Reads need no PIN.

**Keys and caps:** Polymarket private key only in backend `.env.local`, never sent to the browser.
`POLYMARKET_MAX_BET_USD` raised to 25 and remains the hard ceiling; new `MAX_TOTAL_EXPOSURE_USD`.

**Hosting:** the backend must run on an always-on host (not a sleeping laptop) for the loop to trade.

## 4. Rollout
1. Build and test in **paper mode** (real prices, simulated fills); run a $1000 paper plan end to end.
2. Flip `POLYMARKET_LIVE=1` with a **$50** real plan; watch one full cycle including a settlement.
3. Then $1000.

## 5. Files and owners
| File | Owner |
|---|---|
| `backend/trader.py` (new), `backend/app.py` (+ endpoints) | Role A |
| `integrations/polymarket_trading.py` (settlement / resolution check, min order size) | Role C |
| `frontend/app/invest/page.tsx` + small components | Role B |

All on `int/invest-dashboard`, one PR, inbox notes to A and B for review.

## Testing
- Unit tests for sizing/clipping (`trader.size_bet`) and the auto-pause rules — pure functions, no network.
- Paper-mode end-to-end: create plan → one cycle → buys appear in feed → settle a resolved market.
- UI: `/qa` walk of create → pause → resume → stop at desktop and phone width.

## Out of scope
Multiple user accounts, selling positions early, a database, notifications.
