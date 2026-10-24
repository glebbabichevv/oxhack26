# Horizon design kit — "Glass over the Horizon" (for Role B)

Spec: `/DESIGN.md`. **Match this screenshot:** `docs/design-reference/dashboard/dashboard-top.png` (glass cards over a muted painting). Landing / extension shots in the same folder show nav, buttons, serif headlines, tabs and the dark section.

## Files
- `tokens.css` — colours, fonts, radii (Tailwind v4 `@theme`), the backdrop layers (`.hz-backdrop-*`), glass materials (`.hz-glass-card`, `.hz-glass-hover`, `.hz-glass-bar`) and the hero CTA (`.hz-cta`).
- `components/Glass.tsx` — `Backdrop`, `Header` (condenses to a floating pill on scroll), `GlassCard`, `CardHead`, `Kpi`, `TrendPill`, `ActionPill` (BUY_YES / BUY_NO / NO_TRADE), `Tag`, `Segmented` (horizon tabs), `SerifHeadline`.
- `components/Button.tsx` — `primary` (ink pill), `cta` (big grey glass pill with →), `glass` (glass pill).
- `components/chartTheme.ts` — Recharts props: ticks, hairline grid, glass tooltip, bar gradient, 2px lines (Ink = model / with costs, Ash = market / without costs), calibration diagonal.
- `assets/backdrop-turner.jpg` — J. M. W. Turner, *The Fighting Temeraire* (1839), public domain. Copy to `frontend/public/backdrop.jpg`.

## Setup
```css
/* app/globals.css */
@import "tailwindcss";
@import "../design/tokens.css";
```
```tsx
// app/layout.tsx — all free (OFL) Google fonts
import { Poppins, Plus_Jakarta_Sans, Playfair_Display, Cormorant_Garamond } from "next/font/google";
const poppins = Poppins({ subsets: ["latin"], weight: ["500", "600"], variable: "--font-poppins" });
const jakarta = Plus_Jakarta_Sans({ subsets: ["latin"], variable: "--font-jakarta" });
const playfair = Playfair_Display({ subsets: ["latin"], variable: "--font-playfair" });
const cormorant = Cormorant_Garamond({ subsets: ["latin"], weight: ["300"], variable: "--font-cormorant" });
// <html className={`${poppins.variable} ${jakarta.variable} ${playfair.variable} ${cormorant.variable}`}>
```

## Screen skeleton
```tsx
<Backdrop />
<Header section="Live" right={<Button variant="glass">How we measured it</Button>} />
<main className="mx-auto max-w-[1600px] px-4 pb-16 sm:px-6">
  <section className="flex items-end justify-between pt-10 pb-8">
    <SerifHeadline first="Is the time bias tradable?" second="Only in politics, and only a month out." />
  </section>
  <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{/* 4 × <Kpi/> from /api/backtest */}</div>
  <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">{/* calibration chart + <Segmented/> horizons | equity with vs without costs */}</div>
  <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[5fr_3fr_6fr]">{/* live decisions | by horizon | where it fails */}</div>
</main>
```
The headline copy above is a placeholder; the real numbers must come from the API.
