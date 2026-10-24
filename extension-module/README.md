# Horizon extension module

The Chrome extension is **our existing product Argos** (a browser agent we built before the hackathon), with Horizon added on top. The Argos shell stays in its private repo; this folder is everything written for Horizon at OxHack '26:

- `horizon.ts`: the calibration map and decision rule from `backend/model.py`, computed in the browser from `GET /api/model` (fitted coefficients + 40 bootstrap sets) and live Gamma prices. Parity with Python: `node extension-module/parity.mjs capsule/seal-<ts>.json` (359 markets, all actions equal, max |diff| 5e-5 = rounding in the seal file).
- `HorizonCard.tsx`: the side-panel card shown on `polymarket.com/event/*`: market price vs Horizon's q with its 10–90% interval, Buy YES / Buy NO / No trade, edge after the spread, ¼ Kelly stake, and the best window to act (12–24h before the end, from the out-of-time backtest).

The Argos client layer (page reading and actions) is unchanged; the card is one component mounted in the panel.

## Horizon tools for the Argos agent (MCP)

`backend/horizon_mcp.py` is an MCP server with two tools, served by the public API at
**`https://horizon-api-iota.vercel.app/mcp`** (also `/api/mcp`). Same math as `horizon.ts`, in pure Python from
`results/model.json`; parity: `python3 backend/horizon_mcp.py parity capsule/seal-20261024T153130Z.json`
(359 markets, 0 action mismatches, max |diff| 5e-5).

- `horizon_check(slug)`: every yes/no leg of a Polymarket event (slug or full URL): market mid, Horizon q with its
  10–90% interval, BUY_YES / BUY_NO / NO_TRADE, net edge after the spread, ¼ Kelly stake, hours to end, reason,
  plus the best-window note from the out-of-time backtest.
- `horizon_scan(tag="sports", within_hours=24, top=5)`: the 2,100 most-traded open markets with that tag ending inside
  the window (Gamma `/markets`, offset cap 2100), yes/no, two-sided book, 3–97%, ranked by net edge.

Transport: stateless Streamable HTTP. `POST` takes JSON-RPC (single or batch) and answers `application/json`;
notifications get 202; `GET`/`DELETE` are 405 (no SSE stream, no sessions). No auth token. Tested with
`@modelcontextprotocol/sdk` 1.28.0's `StreamableHTTPClientTransport` + `Client` (the same client Argos's backend uses).

### Add it in Argos
1. Argos side panel → Integrations → MCP servers → Add.
2. Name: `Horizon` (the agent then sees `mcp_horizon_horizon_check` and `mcp_horizon_horizon_scan`). URL:
   `https://horizon-api-iota.vercel.app/mcp`. Leave the token empty. Save: Argos probes the server and should show 2 tools.
3. Needs a Pro account: on the free tier Argos strips all MCP tools from the agent.

### Demo script (3 steps)
1. Open a match page, e.g. `https://polymarket.com/event/lal-bar-rea-2026-10-25`. The Horizon card shows the verdict.
2. Ask the agent: *"Should I buy?"* → it calls `horizon_check` with the page's slug and answers per leg: price vs
   Horizon's q and interval, buy / no trade, edge after the spread, ¼ Kelly stake, and that 12–24h before the end was
   historically the best window.
3. Ask: *"Where else is there edge tonight?"* → it calls `horizon_scan` (sports, next 24h) and lists the top 5 markets
   by net edge with links. If it does not pick the tool by itself, say "use Horizon".

Local fallback (only if Argos's backend runs on the same machine; production Argos blocks localhost URLs):
`cd backend && .venv/bin/uvicorn app:app --port 8000` → `http://localhost:8000/mcp`.
