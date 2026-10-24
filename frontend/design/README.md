# Horizon design kit — "The Ledger" (for Role B)

Spec: `/DESIGN.md` (Impeccable and gstack read it from the repo root). Look first: `docs/design-reference/dashboard-light.png` is the exact look to hit.

- `tokens.css` — CSS variables + Tailwind v4 `@theme` + the `.ledger` hairline grid. Import in `app/globals.css` after `@import "tailwindcss";`.
- `tailwind.preset.js` — same tokens for Tailwind v3, only if the app is on v3.
- `components/Ledger.tsx` — `Ledger` (grid), `Cell`, `PanelHead`, `Kpi`, `TrendPill`, `ActionPill`, `Tag`, `PanelLink`.
- `components/Button.tsx` — dark pill (`primary`) and outline pill (`outline`).
- `components/chartTheme.ts` — Recharts props: axis ticks, gridlines, glass tooltip, bar gradient, line style, calibration diagonal.

Fonts (free, OFL) via `next/font/google`:
```tsx
import { Poppins, Plus_Jakarta_Sans, Playfair_Display } from "next/font/google";
const poppins = Poppins({ subsets: ["latin"], weight: ["500", "600"], variable: "--font-poppins" });
const jakarta = Plus_Jakarta_Sans({ subsets: ["latin"], variable: "--font-jakarta" });
const playfair = Playfair_Display({ subsets: ["latin"], weight: ["500"], variable: "--font-playfair" });
// <html className={`${poppins.variable} ${jakarta.variable} ${playfair.variable}`}>
```

Layout skeleton for our screen:
```tsx
<Ledger className="grid-cols-2 lg:grid-cols-4">{/* 4 × <Kpi/> : Brier market vs model, return with costs, trades, hit rate */}</Ledger>
<Ledger className="grid-cols-1 lg:grid-cols-2">{/* <Cell> calibration chart | <Cell> equity with vs without costs */}</Ledger>
<Ledger className="grid-cols-1 lg:grid-cols-[5fr_3fr_6fr]">{/* live decisions | by-horizon summary | where it fails */}</Ledger>
```

Origin: values distilled from our earlier dashboard (no code logic, logos or names carried over).
