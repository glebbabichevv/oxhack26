# Backend & model — Role A (Gleb). See CLAUDE.md.

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-model.txt
.venv/bin/uvicorn app:app --reload   # http://localhost:8000
```

Endpoints (contract v1 in CLAUDE.md): `GET /api/live`, `GET /api/calibration?domain=all`, `GET /api/backtest`, plus `GET /api/health`.

Each endpoint serves `results/<name>.json` once the model pipeline writes it, else the contract example in `examples/<name>.json`. `/api/health` shows which one is live.

Deploy (API only, serves the JSON in `results/`): `cd backend && vercel deploy --prod`. The deploy installs `requirements.txt` (fastapi only); regenerate results locally with `.venv/bin/python model.py` and commit them before deploying.

## Live data and model refresh (v1.3)
- `/api/live` is computed on request from live Gamma prices (`live.py`, 5 min cache per instance); `results/live.json` is only the fallback snapshot (`python live.py` refreshes it).
- `results/model.json` is the registry entry: `version`, out-of-time `metrics`, `fee_rates`.
- `.venv/bin/python refit.py` pulls newly resolved markets, refits, and promotes only if out-of-time Brier is not worse; `--candidate m.json` gates an external model; `--dry-run`, `--no-fetch`, `--rescore`. Log: `results/model_candidates/decisions.jsonl`.
- Schedule: `scripts/refresh.sh` (refit, redeploy on promotion); launchd: `scripts/com.horizon.refresh.plist` (instructions inside).
- Parity: `python3 horizon_mcp.py parity ../capsule/seal-<ts>.json`; with fees: `.venv/bin/python parity_fees.py` then `python3 horizon_mcp.py parity ../data/raw/parity_fees.json` and `node ../extension-module/parity.mjs ../data/raw/parity_fees.json`.

## Invest dashboard (`invest/`, `invest_router.py`)
Auto-invest plans that bet on the model's `BUY_*` calls (1/4 Kelly, capped) and a profit chart. Paper by default; real USDC only with `POLYMARKET_LIVE=1` and wallet keys in `.env.local`.
- **What runs where:** Vercel serves reads only. The always-on host runs `TRADER_ENABLED=1 uvicorn app:app --host 0.0.0.0 --port 8000` with `.env.local` (single worker only).
- **Writes need the trader:** create/pause/resume/stop return 503 unless the process has `TRADER_ENABLED=1`; reads always work. So the frontend's `NEXT_PUBLIC_TRADER_URL` must point at the trader host (it defaults to `NEXT_PUBLIC_API_URL`).
- **PIN:** `DASHBOARD_PIN` is read from the repo-root `.env.local` (loaded by `invest_router` at import) or the environment. Writes send it as `X-Dashboard-Pin`; repeated wrong PINs are locked out (429).
- **The three JSON files** live in `INVEST_DATA_DIR` (default `data/raw`): `plans.json` (plans, cash, positions), `orders.json` (every buy/skip/settle event), `equity.json` (equity curve points for the profit chart).
- **Plan states:** Pause only from running; Resume only from paused. A plan auto-paused with reason `check_fill` means an order may have gone through without being recorded: check polymarket.com before resuming.
- **Single trader:** `trader.lock` in the data folder prevents two traders. After a hard kill the lock can block a restarted trader for up to 30 minutes; delete `trader.lock` if you are sure no other trader runs.
- **Redemption (live mode):** winning shares must be redeemed on polymarket.com ("Claim") before that USDC can fund new bets; the plan's cash is bookkeeping.
