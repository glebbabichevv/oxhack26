# Horizon extension module

The Chrome extension is **our existing product Argos** (a browser agent we built before the hackathon), with Horizon added on top. The Argos shell stays in its private repo; this folder is everything written for Horizon at OxHack '26:

- `horizon.ts`: the calibration map and decision rule from `backend/model.py`, computed in the browser from `GET /api/model` (fitted coefficients + 40 bootstrap sets) and live Gamma prices. Parity with Python: `node extension-module/parity.mjs capsule/seal-<ts>.json` (359 markets, all actions equal, max |diff| 5e-5 = rounding in the seal file).
- `HorizonCard.tsx`: the side-panel card shown on `polymarket.com/event/*`: market price vs Horizon's q with its 10–90% interval, Buy YES / Buy NO / No trade, edge after the spread, ¼ Kelly stake, and the best window to act (12–24h before the end, from the out-of-time backtest).

The Argos client layer (page reading and actions) is unchanged; the card is one component mounted in the panel.
