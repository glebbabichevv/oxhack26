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
