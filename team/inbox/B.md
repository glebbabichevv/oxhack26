# Inbox — Role B

Messages from other agents/teammates to Role B. Newest at the bottom.
Format: `- [HH:MM] from <role>: <what is wrong / what you need> — <file or endpoint>`
When you have handled a message, change `- [` to `- [x]` at its start.

- [14:01] from A: DESIGN.md + frontend/design/ were rewritten to the CURRENT landing/dashboard look (glass cards r22 over a muted painting, Poppins numbers, Playfair serif headline, pills). Match docs/design-reference/horizon-target-mock.png; components in frontend/design/components/Glass.tsx, setup in frontend/design/README.md. Old Card.tsx/Ledger.tsx/tailwind.preset.js are gone — DESIGN.md, frontend/design/
- [14:01] from A: API now serves REAL results, not examples (GET /api/health shows "results"). Contract v1.1 adds fields only (net_edge, volume_usd, logloss_*, by_horizon[], failures[], worst_trades[], assumptions[]); return/max_drawdown are in starting-bankroll units — CLAUDE.md "API contract", backend/results/*.json
- [14:01] from A: please review my merged work per team/README.md ("B checks A"): run the backend, check every endpoint against the contract shapes, flag anything absurd in my inbox — backend/app.py, backend/model.py
