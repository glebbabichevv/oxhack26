# Backend & model — Role A (Gleb). See CLAUDE.md.

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-model.txt
.venv/bin/uvicorn app:app --reload   # http://localhost:8000
```

Endpoints (contract v1 in CLAUDE.md): `GET /api/live`, `GET /api/calibration?domain=all`, `GET /api/backtest`, plus `GET /api/health`.

Each endpoint serves `results/<name>.json` once the model pipeline writes it, else the contract example in `examples/<name>.json`. `/api/health` shows which one is live.

Deploy (API only, serves the JSON in `results/`): `cd backend && vercel deploy --prod`. The deploy installs `requirements.txt` (fastapi only); regenerate results locally with `.venv/bin/python model.py` and commit them before deploying.
