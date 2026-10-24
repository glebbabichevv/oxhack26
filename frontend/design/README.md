# Horizon design kit (for Role B)

Tokens only; spec lives in `/DESIGN.md` (Impeccable and gstack read it from there).

- `tokens.css` — CSS variables (light + dark) and a Tailwind v4 `@theme` block. Import it in `app/globals.css` after `@import "tailwindcss";`.
- `tailwind.preset.js` — same tokens for Tailwind v3 (`presets: [require("./design/tailwind.preset.js")]`), only if the app is on v3.
- `components/Button.tsx`, `components/Card.tsx` (Card, CardHeader, Metric, ActionChip) — dependency-free starters; move or replace with shadcn equivalents styled with these tokens.

Fonts (free, OFL): Inter + JetBrains Mono via `next/font/google`:
```tsx
import { Inter, JetBrains_Mono } from "next/font/google";
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains" });
// <html className={`${inter.variable} ${mono.variable}`}>
```

Origin: values distilled from our earlier minimalist-white work (no code, logos or names carried over).
