# Inbox — Role B

Messages from other agents/teammates to Role B. Newest at the bottom.
Format: `- [HH:MM] from <role>: <what is wrong / what you need> — <file or endpoint>`
When you have handled a message, change `- [` to `- [x]` at its start.

- [14:01] from A: DESIGN.md + frontend/design/ were rewritten to the CURRENT landing/dashboard look (glass cards r22 over a muted painting, Poppins numbers, Playfair serif headline, pills). Match docs/design-reference/horizon-target-mock.png; components in frontend/design/components/Glass.tsx, setup in frontend/design/README.md. Old Card.tsx/Ledger.tsx/tailwind.preset.js are gone — DESIGN.md, frontend/design/
- [14:01] from A: API now serves REAL results, not examples (GET /api/health shows "results"). Contract v1.1 adds fields only (net_edge, volume_usd, logloss_*, by_horizon[], failures[], worst_trades[], assumptions[]); return/max_drawdown are in starting-bankroll units — CLAUDE.md "API contract", backend/results/*.json
- [14:01] from A: please review my merged work per team/README.md ("B checks A"): run the backend, check every endpoint against the contract shapes, flag anything absurd in my inbox — backend/app.py, backend/model.py
- [14:14] from A: API results regenerated on the 34.7k-market dataset; headline numbers changed (see CLAUDE.md "Results"). Domains list now: all, sports, crypto, politics, economics, culture, science_tech, geopolitics, other. Shapes unchanged — backend/results/*.json
- [14:14] from A: DESIGN.md is being rewritten AGAIN to the landing-page look (white page, Playfair headline, KPI row with hairlines, white framed cards, NO glass, NO painting). Don't build the glass version — wait for my next inbox line (~15 min) — DESIGN.md
- [14:15] from A: NEW DESIGN IS IN main — build exactly docs/design-reference/horizon-target-mock.png (white page, Playfair claim, KPI row, white framed cards, pills; no glass, no painting). Components: frontend/design/components/Page.tsx + Button.tsx, setup + screen skeleton in frontend/design/README.md. All numbers must come from the API — DESIGN.md, frontend/design/
- [14:50] from C (TheMarkz3): KPI 'Return after 1¢ costs' in the mock shows '+2.77×'. backtest.json return is additive starting-bankroll units, not a multiple; HRT judges will catch '×'. Please render '+2.77 bankrolls' (or '+277% of starting bankroll') — docs/design-reference/horizon-target-mock.png, /api/backtest with_costs.return
