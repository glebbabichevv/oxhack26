---
name: Horizon
description: Is the prediction-market time bias tradable? A calibration and decision dashboard.
colors:
  page: "#f4f4f5"
  cell: "#ffffff"
  seam: "rgba(9,9,11,0.08)"
  ink: "#0a0a0a"
  ink-strong: "#18181b"
  ink-muted: "#676e7e"
  ink-faint: "rgba(9,9,11,0.42)"
  graphite: "#3f3f46"
  ash: "#a1a1aa"
  up: "#16a34a"
  up-tint: "rgba(22,163,74,0.10)"
  down: "#e11d48"
  down-tint: "rgba(225,29,72,0.10)"
  hover-wash: "rgba(9,9,11,0.035)"
typography:
  wordmark:
    fontFamily: "Playfair Display, Georgia, serif"
    fontSize: "22px"
    fontWeight: 500
    letterSpacing: "-0.01em"
  display:
    fontFamily: "Poppins, system-ui, sans-serif"
    fontSize: "40px"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "-0.025em"
    fontFeature: "tnum"
  headline:
    fontFamily: "Poppins, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Poppins, system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.3
    fontFeature: "tnum"
  tick:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 400
rounded:
  none: "0px"
  bar: "2px"
  tooltip: "12px"
  pill: "9999px"
spacing:
  seam: "1px"
  xs: "6px"
  sm: "12px"
  md: "20px"
  lg: "24px"
  xl: "40px"
components:
  cell:
    backgroundColor: "{colors.cell}"
    rounded: "{rounded.none}"
    padding: "24px"
  button-primary:
    backgroundColor: "{colors.ink-strong}"
    textColor: "{colors.cell}"
    rounded: "{rounded.pill}"
    padding: "10px 20px"
    height: "44px"
  button-outline:
    backgroundColor: "{colors.cell}"
    textColor: "{colors.ink-strong}"
    rounded: "{rounded.pill}"
    padding: "8px 18px"
    height: "40px"
  trend-pill-up:
    backgroundColor: "{colors.up-tint}"
    textColor: "{colors.up}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "4px 10px"
  trend-pill-down:
    backgroundColor: "{colors.down-tint}"
    textColor: "{colors.down}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "4px 10px"
  action-buy-yes:
    backgroundColor: "{colors.up-tint}"
    textColor: "{colors.up}"
    rounded: "{rounded.pill}"
    padding: "4px 10px"
  action-buy-no:
    backgroundColor: "{colors.down-tint}"
    textColor: "{colors.down}"
    rounded: "{rounded.pill}"
    padding: "4px 10px"
  action-no-trade:
    backgroundColor: "{colors.page}"
    textColor: "{colors.ink-muted}"
    rounded: "{rounded.pill}"
    padding: "4px 10px"
  tooltip:
    backgroundColor: "rgba(255,255,255,0.72)"
    textColor: "{colors.ink}"
    rounded: "{rounded.tooltip}"
    padding: "7px 11px"
---

# Design System: Horizon

Reference screenshots: `docs/design-reference/` (start with `dashboard-light.png`). Code tokens: `frontend/design/`.

## Overview

**Creative North Star: "The Ledger"**

A trading desk's ledger, not an app. One sheet of white cells ruled by hairlines, sitting on a pale zinc page. Numbers are set large in a geometric face and carry the screen; everything else is quiet, grey and small. Colour appears only when it means something: green for up and buy-YES, rose for down and buy-NO. Charts are monochrome graphite with one dark and one grey series.

The density is that of a well-made admin dashboard: KPI strip on top, two charts side by side, tables and lists below, all welded into one grid with 1px seams. Nothing floats, nothing glows. The only decorative touch is the serif wordmark in the header.

**Key Characteristics:**
- Hairline grid: cells butted together with `gap-px` over a seam colour, no gaps, no card shadows, square corners.
- Big Poppins numbers (34–40px, semibold, tabular), Plus Jakarta Sans for every word.
- Monochrome charts: graphite gradient bars, stepped lines in near-black and ash.
- Green/rose only for direction and action; pills for every small status.
- Outline pill buttons; one dark pill for the main action.

## Colors

Zinc greys on white, with exactly two semantic hues.

### Primary
- **Ledger Ink** (#18181b): main text on headings, the primary series in every chart (model curve, with-costs equity), the dark pill button.

### Neutral
- **Zinc Page** (#f4f4f5): page background and the colour that shows through the 1px seams.
- **Cell White** (#ffffff): every panel/cell surface.
- **Seam** (rgba(9,9,11,0.08)): grid seams, table row dividers, horizontal chart gridlines.
- **Slate Muted** (#676e7e): labels, panel subtitles, secondary text. Use at 70% opacity for hints ("vs last week", "n = 312").
- **Tick Grey** (rgba(9,9,11,0.42)): axis ticks only.
- **Graphite** (#3f3f46) → **Ash** (#a1a1aa): the bar gradient (top → bottom). Ash alone is the secondary chart series (market price, without-costs equity, baseline).

### Semantic
- **Signal Green** (#16a34a, tint rgba(22,163,74,0.10)): positive delta, profit, BUY_YES.
- **Signal Rose** (#e11d48, tint rgba(225,29,72,0.10)): negative delta, loss, drawdown, BUY_NO.

### Named Rules
**The Two Hues Rule.** Green and rose are the only colours on the screen. They mean direction or action, never decoration, never a heading, never a background bigger than a pill.
**The NO_TRADE Is A Result Rule.** NO_TRADE is shown in neutral grey at the same size as a trade, not hidden or faded. "Costs eat the edge" is a finding.

## Typography

**Display Font:** Poppins (Google Fonts, OFL), fallback system-ui
**Body Font:** Plus Jakarta Sans (Google Fonts, OFL), fallback system-ui
**Wordmark:** Playfair Display (Google Fonts, OFL), header wordmark only

**Character:** a round geometric display face for numbers and titles against a friendly humanist sans for reading. The contrast is size and weight, not colour.

### Hierarchy
- **Display** (Poppins 600, 34px mobile / 40px desktop, line-height 1, tracking -0.025em, tabular): KPI values (Brier, return, trades, hit rate).
- **Headline** (Poppins 600, 26–30px, tracking -0.025em): page masthead ("Is the time bias tradable?").
- **Title** (Poppins 600, 19px, tracking -0.02em): panel titles ("Calibration by horizon", "Backtest").
- **Body** (Plus Jakarta Sans 400, 14px, line-height 1.45, Slate Muted): panel subtitles, KPI labels, reason text. Max 70ch.
- **Label** (Plus Jakarta Sans 600, 13px, tabular): deltas, pills, table numbers.
- **Tick** (Plus Jakarta Sans 400, 11px, Tick Grey): chart axes.

### Named Rules
**The Tabular Rule.** Every number uses tabular figures and carries its unit (`72%`, `4.2¢`, `30d`, `+1.65×`).

## Layout

- Page: Zinc Page background, container max-width 1600px, side padding 16px (mobile) / 24px (sm+).
- Header: 56px tall, full-bleed white bar with a bottom seam. Left: wordmark + `/` + section name in Slate Muted ("Horizon / Live"). Right: muted text links and one outline pill.
- Masthead: headline + one muted line, 40px top padding, outline pill aligned right.
- The Ledger grid: `grid gap-px bg-[seam]` with white cells. Row 1: 4 KPI cells. Row 2: 2 chart cells (1/2 + 1/2). Row 3: 3 cells (list / summary / list) at ~5/3/6 columns. Collapses to 1 column below 768px, 2 columns for KPIs.
- Cell padding 20px (mobile) / 24px. Panel head: title, pill beside it, subtitle 6px below. Charts are 240px tall.
- Tables inside cells: header row in Slate Muted 14px, rows 64px with seam dividers, numbers right-aligned.

## Elevation & Depth

Flat. Depth comes from the seam grid and tonal contrast (white on zinc), never from card shadows. The only lifted surfaces are transient: tooltips and menus.

### Shadow Vocabulary
- **Tooltip** (`box-shadow: inset 0 1px 0 rgba(255,255,255,0.85), 0 8px 28px rgba(0,0,0,0.10)`; background rgba(255,255,255,0.72) with `backdrop-filter: blur(26px) saturate(200%)`; 1px border rgba(255,255,255,0.6)): chart tooltips.
- **Menu** (`box-shadow: 0 8px 32px rgba(15,23,42,0.10)`): dropdowns, popovers.

### Named Rules
**The Flat Sheet Rule.** Cells never get a shadow or their own radius. Hover is a wash (`rgba(9,9,11,0.035)` or `bg-white/40` on links), not a lift.

## Shapes

- Grid and cells: square (0px). Only the outer edge of the grid may take a radius if the page needs it; inner cells never do.
- Pills: fully rounded (9999px) for buttons, trend pills, action chips, domain tags.
- Bars: 2px top corners. Tooltips: 12px.
- Icons: 12px inline SVG arrows, stroke 1.6–1.9, round caps (↑ ↓ ↗ ↘); no emoji or unicode arrows as icons.

## Components

- **KPI cell:** label (Body, Slate Muted) → value (Display) 12px below → delta row 12px below: arrow + `28.4%` in Label coloured up/down + muted suffix ("vs market"). If nothing to compare, a muted hint instead, never an empty delta.
- **Panel head:** Title + optional trend pill on one line, subtitle in Body below.
- **Trend pill:** rounded-full, 10% tint background, Label text in the same hue, 12px ↗ icon.
- **Action pill (Horizon):** BUY YES (green tint), BUY NO (rose tint), NO TRADE (zinc page bg, muted text). Same size for all three.
- **Decision row/card (live markets):** question (Body 14px, ink, 2 lines max) + domain pill + `30d to resolution` (muted). Right side: market price vs model q as two Display-small numbers (26px) with the q interval as a thin ash band on a 0–100 track and a dark tick for q; net edge in ¢ coloured by sign; action pill; ¼-Kelly size; reason in muted Body.
- **Bar chart:** vertical bars with `linearGradient` #3f3f46 → #a1a1aa, radius [2,2,0,0], category gap 22%, x-axis ticks only, no y-axis, no gridlines.
- **Line chart:** `type="stepAfter"` (or monotone for calibration curves), 2px, no dots, active dot r=3 with 2px white ring. Primary series Ledger Ink, secondary Ash. Horizontal gridlines in Seam only, y-axis hidden. Calibration chart: dashed seam diagonal for perfect calibration, market as Ash, model as Ink.
- **Tooltip:** see Elevation; label in muted ink, value in ink.
- **Buttons:** primary = dark pill (Ledger Ink, white text, 44px); secondary = outline pill (white, 1px seam-strength border `rgba(9,9,11,0.12)`, 40px). Text links: 14px semibold ink at 75%, arrow nudges 4px right on hover.
- **Empty state:** centered muted Body in the chart area ("Not enough markets at this horizon to plot."). Never fake numbers.

## Do's and Don'ts

**Do**
- Weld panels into one hairline grid.
- Let the numbers be the biggest thing on screen.
- Show the market (Ash) next to the model (Ink) everywhere a model number appears.
- Keep every NO TRADE visible.

**Don't**
- No card shadows, floating cards, gaps between panels or nested cards.
- No colours beyond green/rose; no gradients except the bar fill; no glass on panels.
- No eyebrow/kicker labels above headings, no 01/02/03 section numbers.
- No emoji, no unicode glyphs as icons.
- No names, logos or imagery from earlier products: this is **Horizon**.
