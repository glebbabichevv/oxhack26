# Frontend & demo screen — Role B. See CLAUDE.md and DESIGN.md.

One page (`app/page.tsx`) built to `docs/design-reference/horizon-target-mock.png`, every number from the API.

```bash
cd frontend
npm install
npm run dev            # http://localhost:3000, expects the API on :8000
```

API base URL: `NEXT_PUBLIC_API_URL` (see `.env.example`), default `http://localhost:8000`. On Vercel set it to the public API URL.

- `design/` — Gleb's design kit (tokens, `Page.tsx`, `Button.tsx`, `chartTheme.ts`).
- `lib/api.ts` — contract types, fetch, number formatting.
- `components/` — `CalibrationChart`, `EquityChart` (Recharts).

`npm run dev` runs Node with `--use-system-ca` because the venue Wi-Fi breaks TLS to Google Fonts.
