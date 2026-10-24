# Tasks

Claim a task by writing your name in brackets. Move it to Done when merged.
Roles are in CLAUDE.md (A = model + backend, B = frontend, C = data pipeline, then pitch).
Project: **Horizon** — is the prediction-market time bias tradable? (see "What we are building" in CLAUDE.md)

## Now (13:15 → 16:30 gate)
### Role A — model + backend (Gleb)
- [ ] FastAPI skeleton in `backend/` serving the 3 contract endpoints with the example JSON (so B is unblocked in 15 min)
- [ ] Load `data/horizons.csv`, out-of-time split, baseline (market price) vs calibration model; Brier + reliability per horizon
- [ ] Decision rule + backtest with/without costs; replace example JSON with real numbers
- [ ] `/api/live` from `data/live.csv`

### Role B — frontend
- [ ] Paste Argos preset into `DESIGN.md`; `/impeccable init` for `PRODUCT.md`
- [ ] Next.js app in `frontend/` built against the contract's example JSON: live decision cards, calibration chart, backtest equity curve, "where it fails" panel
- [ ] Deploy to Vercel early (public URL by 16:30)

### Role C — data pipeline
- [ ] Polymarket: list resolved binary markets (with volume + category) → prices at 30d/7d/3d/1d/12h before resolution (explicit startTs/endTs chunks) → `data/horizons.csv`
- [ ] Open markets → `data/live.csv`
- [ ] Sanity checks: counts per horizon/domain, no cancelled/MKT resolutions, no future leakage in prices
- [ ] If Polymarket blocks you for >30 min: switch to Manifold (`/v0/search-markets?filter=resolved` + `/v0/bets`)

### Everyone
- [ ] `git pull`, read CLAUDE.md "What we are building" + contracts
- [ ] Delta: at least 2 of us collaborate in a Delta thread (Zed track requirement); save links

## Gate 16:30
- [ ] One real end-to-end path: real data → model → `/api/live` → card on the public URL (`/qa`)

## Evening
- [ ] Pivot checkpoint 18:00–20:00: `/plan-ceo-review` on the working product
- [ ] (stretch) Gemini labels "Other" markets into domains

## Pitch (Role C, from Saturday evening)
- [ ] Demo script, 90 seconds, one scenario end to end
- [ ] Backup demo video recorded by Sunday morning
- [ ] Devpost page: what it does, how we built it, sponsor tech used, what we brought in vs built here; cite arXiv 2602.19520
- [ ] Collect best Delta thread links (ideation, build, testing) for the Zed track
- [ ] Rehearse pitch 5x with a timer

## Done
