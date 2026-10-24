# Tasks

Claim a task by writing your name in brackets. Move it to Done when merged.
Roles are in CLAUDE.md (A = model + backend, B = frontend, C = data pipeline, then pitch).
Project: **Horizon** — is the prediction-market time bias tradable? (see "What we are building" in CLAUDE.md)

## Now (13:15 → 16:30 gate)
### Role A — model + backend (Gleb)
- [x] [Gleb] FastAPI skeleton in `backend/` serving the 3 contract endpoints with the example JSON (so B is unblocked in 15 min) — PR `gleb/api-skeleton`
- [x] [Gleb] Load `data/horizons.csv`, out-of-time split, baseline (market price) vs calibration model; Brier + reliability per horizon
- [x] [Gleb] Decision rule + backtest with/without costs; replace example JSON with real numbers
- [x] [Gleb] `/api/live` from `data/live.csv`
- [ ] [Gleb] Public URL for the API (Vercel deploy needs Gleb's OK) + split requirements so the bundle fits

### Role B — frontend
- [x] [Gleb] Design preset in `DESIGN.md` + tokens/Tailwind preset/starter components in `frontend/design/` — PR `gleb/design-preset`
- [ ] `/impeccable init` for `PRODUCT.md`
- [ ] Next.js app in `frontend/` built against the contract's example JSON: live decision cards, calibration chart, backtest equity curve, "where it fails" panel
- [ ] Deploy to Vercel early (public URL by 16:30)

### Role C — data pipeline
- [x] [Ayaz] Polymarket: list resolved binary markets (with volume + category) → prices at 30d/7d/3d/1d/12h before resolution (explicit startTs/endTs chunks) → `data/horizons.csv` — **team dataset: 34.7k markets** (`integrations/fetch_horizons.py`)
- [x] [Ayaz] Open markets → `data/live.csv` (`integrations/fetch_live.py`)
- [x] [Ayaz] Sanity checks (`integrations/check_data.py`)
- [x] [TheMarkz3] First pipeline + 3.1k-market sample and the calibration check that caught the sign flip (`integrations/polymarket.py`, `calibration_check.py`) — superseded as the main dataset by Ayaz's
- [ ] If Polymarket blocks you for >30 min: switch to Manifold (`/v0/search-markets?filter=resolved` + `/v0/bets`)

### Everyone
- [ ] `git pull`, read CLAUDE.md "What we are building" + contracts
- [ ] Read `team/README.md`; check your inbox `team/inbox/<role>.md` before every task
- [ ] Delta: at least 2 of us collaborate in a Delta thread (Zed track requirement); save links

## Gate 16:30
- [ ] One real end-to-end path: real data → model → `/api/live` → card on the public URL (`/qa`)

## Evening
- [ ] Pivot checkpoint 18:00–20:00: `/plan-ceo-review` on the working product
- [ ] (stretch) Gemini labels "Other" markets into domains

## Pitch (Role C, from Saturday evening)
- [ ] [TheMarkz3] Demo script, 90 seconds, one scenario end to end
- [ ] [TheMarkz3] Backup demo video recorded by Sunday morning
- [ ] [TheMarkz3] Devpost page: what it does, how we built it, sponsor tech used, what we brought in vs built here; cite arXiv 2602.19520
- [ ] [TheMarkz3] Collect best Delta thread links (ideation, build, testing) for the Zed track
- [ ] [TheMarkz3] Rehearse pitch 5x with a timer
- [ ] Before the repo goes public: delete `docs/design-reference/` (old-product screenshots)

## Done
