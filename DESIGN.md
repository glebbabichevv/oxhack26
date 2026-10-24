# Design preset — Horizon

Minimalist white, graphite accent, quiet status colours. A serious trading tool, not a "purple AI app".
Impeccable and gstack `/design-*` read this file from the repo root; every screen follows it.
Code tokens live in `frontend/design/` (`tokens.css`, `tailwind.preset.js`, `components/`).

## Principles
- White page, near-black text, one graphite accent. Colour is reserved for meaning (buy / sell / no trade, model vs market), never decoration.
- Numbers are the product: tabular figures, right-aligned in tables, units always shown (`72%`, `¢`, `h`, `£`).
- Uncertainty is visible: every probability that has an interval shows it (bar, band or `71–79%`).
- Few sizes, few radii, few durations. If a value is not in this file, don't invent it.
- Brand: name is **Horizon**. No logos or names from earlier projects.

## Colour
| Token | Light | Dark | Use |
|---|---|---|---|
| `background` | `#FFFFFF` | `#020617` | page |
| `surface` | `#F5F4F2` | `#1C1C1E` | panels, chart wells, table header |
| `card` | `#FFFFFF` | `#111113` | cards on surface |
| `border` | `rgba(0,0,0,0.07)` (`#E5E7EB` solid) | `rgba(255,255,255,0.08)` | hairlines |
| `text` | `#0F172A` | `#F9FAFB` | primary text |
| `text-muted` | `#64748B` | `#A1A1AA` | labels, captions, axes |
| `primary` | `#52525B` (zinc-600) | `#71717A` (zinc-500) | accent, focus ring, active tab |
| `primary-hover` | `#3F3F46` | `#A1A1AA` | hover |
| `primary-soft` | `rgba(82,82,91,0.12)` | `rgba(113,113,122,0.16)` | selected row, chips |

Semantic (muted, legible by hue, never shouting):
| Meaning | Text / line | Soft background | Use |
|---|---|---|---|
| positive / BUY_YES / profit | `#577B65` | `#E4EDE8` | action chip, equity above 1.0 |
| negative / BUY_NO / loss | `#976060` | `#ECDEDE` | action chip, drawdown |
| neutral / NO_TRADE | `#72777E` | `#F4F4F5` | action chip, "costs eat the edge" |
| warning / low sample | `#B09360` | `#F5EFE3` | `n < 30` bins, thin data |
| info / model line | `#505F79` | `#E4E8EE` | model curve, q interval band |

Charts: market / baseline = `#A1A1AA` dashed; model = `#505F79` solid 2px; perfect calibration diagonal = `#E5E7EB` 1px; interval band = model colour at 15% opacity; with-costs equity = `#0F172A`, without-costs = `#A1A1AA`.

## Typography
- Sans: **Inter** (Google Fonts, OFL), fallback `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`.
- Mono (ids, code only): **JetBrains Mono** (Google Fonts, OFL).
- All numbers: `font-variant-numeric: tabular-nums` (`tabular-nums` utility).
- Weights: 400 body, 500 labels/buttons, 600 headings and key numbers. No 700+.

Scale (7 steps; tracking tightens as size grows; nothing below 11px):
| Token | Size / line-height / tracking | Use |
|---|---|---|
| `caption` | 11 / 1.45 / +0.005em | axis ticks, footnotes, "n = 312" |
| `footnote` | 12 / 1.5 / 0 | table cells, chip labels |
| `body` | 13 / 1.55 / -0.006em | default text |
| `subhead` | 15 / 1.4 / -0.014em | card titles, market question |
| `title` | 17 / 1.32 / -0.021em | section headings |
| `display` | 22 / 1.22 / -0.028em | key metric in a card (edge, return) |
| `hero` | 28 / 1.16 / -0.035em | the one headline number on the screen |

## Spacing & layout
- 4px base: 4, 8, 12, 16, 20, 24, 32, 48, 64.
- Card padding 16 (dense) or 20; gap between cards 16; section gap 32–48.
- Page container max 1280px, side padding 24 (16 on mobile).
- Dense tables: row height 36, cell padding 8×12.

## Radius (bigger surface → rounder)
| Token | Value | Use |
|---|---|---|
| `chip` | 7px | action chips, badges, tags |
| `control` | 11px | buttons, inputs, tabs, tooltips |
| `card` | 15px | cards, chart wells |
| `panel` | 20px | large panels, side sheets |
| `sheet` | 26px | modals |

## Shadow (very subtle; borders do most of the work)
| Token | Value | Use |
|---|---|---|
| `shadow-card` | `0 1px 2px rgba(15,23,42,0.04), 0 3px 12px rgba(15,23,42,0.06)` | cards at rest (optional) |
| `shadow-raised` | `0 4px 14px rgba(15,23,42,0.10)` | hover on clickable cards, menus |
| `shadow-overlay` | `0 8px 40px rgba(15,23,42,0.16)` | popovers, modals |
Dark mode: no shadows, use borders only.

## Motion
- Durations: `fast` 140ms (hover, press), `base` 240ms (enter/leave), `slow` 420ms (panel/chart transitions).
- Curve: `soft` = `cubic-bezier(0.22, 1, 0.36, 1)`; plain `ease` only for opacity.
- Animate only colour, opacity, transform, box-shadow (`transition-ui`), never width/height.
- Respect `prefers-reduced-motion`: no movement, opacity only.

## Components
**Button** (radius `control`, height 32 sm / 36 md, padding x 12/14, text `footnote`/`body` 500):
- primary: bg `#0F172A`, text white, hover `#1E293B`.
- secondary: bg white, border `border`, text `text`, hover bg `surface`.
- ghost: transparent, text `text-muted`, hover bg `primary-soft`.
- Focus: 2px outline `primary` at 75%, offset 2px. Disabled: 50% opacity, no hover.

**Card** (radius `card`, bg `card`, 1px border `border`, padding 16–20, no shadow at rest):
- Header: `subhead` 600 title + `caption` muted meta on the right.
- Key number: `display` 600 tabular; label above in `caption` muted uppercase-free (sentence case).

**Decision card** (the hero of `/api/live`):
- Top: market question (`subhead`, 2 lines max, ellipsis) + domain chip + hours to resolution (`caption`).
- Middle: market price vs model q as two numbers (`display`), with the q interval as a thin band on a 0–100 bar; edge in ¢ coloured by sign.
- Bottom: action chip (BUY_YES / BUY_NO / NO_TRADE in semantic colours), Kelly size, one-line `reason` in `footnote` muted.
- NO_TRADE cards are not hidden or greyed out: "costs eat the edge" is a result.

**Chip** (radius `chip`, height 22, padding x 8, `caption` 500, soft background + text colour from the semantic table).

**Tabs / segmented control** (radius `control`, bg `surface`, active item white with `shadow-card`).

**Tables**: header `caption` muted on `surface`, hairline row borders, numbers right-aligned tabular.

**Empty / loading / error**: skeleton blocks in `surface` with shimmer 2s; errors in plain sentence + retry ghost button. Never show example numbers as if real once the API is live.

## Don't
- No gradients, glows, glassmorphism, neon, purple accents, emoji in UI.
- No more than one accent colour per chart besides semantic colours.
- No pill buttons, no italic headings, no all-caps tracked labels.
