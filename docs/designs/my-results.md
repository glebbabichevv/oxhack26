# Design: "My results" (personal cabinet)

Office hours, Sat 24 Oct 21:10 · Mode: Builder (hackathon) · Status: APPROVED (option B)

## Problem
A user asks "am I making or losing money with Horizon?". The site proves the model; nothing shows the user's own record. The agent should answer "show my stats" by opening it.

## Decision (B: Journal + optional wallet)
- **Journal part (always):** from the extension's Decision Journal (install id, no login): decisions shown / set up / placed / skipped; for placed bets: won/lost, P&L $, per $1 after fees, hit rate. Counterfactual "if you had followed every Horizon pick shown to you" and "skipped picks: how they did". Labelled: placed bets are self-reported.
- **Wallet part (optional):** user pastes a public Polymarket address (read-only, never keys) → real positions and P&L from Polymarket's public data API, each tagged "followed Horizon" (same conditionId + side in the user's Journal) or "own". The server does not store the address.
- **Agent:** tool `open_my_results` + phrases ("show my stats", "how am I doing") → opens `/me?id=…&wallet=…` and replies with a one-line summary.
- Rejected: accounts with login and sync (after the hackathon); Invest auto-trading (not merged).

## Owners / deadline (23:30)
- Agent ①: `GET /api/me`, `/me` page, nav link, Railway deploy.
- Agent ②: wallet setting, "Open my results", agent tool, `agent_router.py` schema.
- A: merge, deploy, end-to-end check.

## Honest limits
- Without a wallet the numbers are self-reported.
- On the demo laptop (GB) there may be no wallet with positions: show the Journal part and say the wallet part reads real positions.
