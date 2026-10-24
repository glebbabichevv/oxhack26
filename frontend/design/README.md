# Horizon design kit — "The Quiet Page" (for Role B)

Spec: `/DESIGN.md`. **Build this:** `docs/design-reference/horizon-target-mock.png` (white page, serif claim, KPI row, white framed cards; real numbers from `backend/results/`). Look references: `docs/design-reference/landing/` and `extension/`. **No glass, no painting backdrop.**

## Files
- `tokens.css` — colours, fonts, radii, shadows (Tailwind v4 `@theme`) + the big CTA (`.hz-cta-*`).
- `components/Page.tsx` — `Nav` (floating pill), `Hero` (serif claim + grey second line + lead), `KpiRow` (one ruled row), `Section` (text column + evidence column), `FramedCard` (white card in a soft grey frame), `Segmented` (pricing-style toggle for 30d / 7d / 3d / 1d / 12h), `ActionChip`, `DecisionRow`.
- `components/Button.tsx` — `Button` (`primary` ink pill, `quiet` soft-fill pill) and `CtaButton` (dark pill on a blurred grounding shadow).
- `components/chartTheme.ts` — Recharts props. Calibration: market = dashed Ash diagonal, model = Ink line, observed = white dots with ink ring. Tooltip: white popover, hairline, radius 12.

## Setup
```css
/* app/globals.css */
@import "tailwindcss";
@import "../design/tokens.css";
```
```tsx
// app/layout.tsx — free (OFL) Google fonts
import { Playfair_Display, Plus_Jakarta_Sans } from "next/font/google";
const playfair = Playfair_Display({ subsets: ["latin"], variable: "--font-playfair" });
const jakarta = Plus_Jakarta_Sans({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-jakarta" });
// <html className={`${playfair.variable} ${jakarta.variable}`}>
```

## Screen skeleton (matches the mock)
```tsx
<Nav links={[{label:"Live",href:"#live"},{label:"Calibration",href:"#calibration"},{label:"Backtest",href:"#backtest"},{label:"Method",href:"#method"}]}
     action={<Button>See the backtest</Button>} />
<main className="mx-auto max-w-[1120px] px-4 pb-24">
  <Hero first="…claim from /api/backtest…" second="…" lead="…n markets, cutoff…" />
  <KpiRow items={[/* return after costs + CI, Brier model/market, where it pays, trades + hit rate */]} />
  <Section title="A day out, 15¢ contracts win 20% of the time" lead="…" controls={<Segmented …/>}>
    <FramedCard title="Calibration, 1 day out" meta="n = …">{/* Recharts */}</FramedCard>
  </Section>
  <Section title="Live decisions" lead="…"><FramedCard>{/* DecisionRow × n from /api/live */}</FramedCard></Section>
  <Section title="Where it fails" lead="…"><FramedCard>{/* /api/backtest failures[] */}</FramedCard></Section>
</main>
```
Every number and sentence with a number must come from the API, not from the mock.
