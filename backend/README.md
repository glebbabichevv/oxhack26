# Backend & model — Role A (Gleb). See CLAUDE.md.

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app:app --reload   # http://localhost:8000
```

Endpoints (contract v1 in CLAUDE.md): `GET /api/live`, `GET /api/calibration?domain=all`, `GET /api/backtest`, plus `GET /api/health`.

Each endpoint serves `results/<name>.json` once the model pipeline writes it, else the contract example in `examples/<name>.json`. `/api/health` shows which one is live.
