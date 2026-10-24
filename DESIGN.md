---
name: Horizon
description: Is the prediction-market time bias tradable? A calibration and decision dashboard.
colors:
  backdrop-base: "#dedee3"
  scrim: "rgba(244,244,247,0.60)"
  page-plain: "#ffffff"
  ink: "#0a0a0a"
  ink-strong: "#111113"
  ink-muted: "#676e7e"
  ink-faint: "rgba(9,9,11,0.42)"
  ink-second-line: "rgba(10,10,10,0.42)"
  hairline: "rgba(9,9,11,0.07)"
  graphite: "#3f3f46"
  ash: "#a1a1aa"
  up: "#16a34a"
  up-tint: "rgba(22,163,74,0.10)"
  down: "#e11d48"
  down-tint: "rgba(225,29,72,0.10)"
  night: "#0a0a0a"
typography:
  serif-display:
    fontFamily: "Playfair Display, Georgia, serif"
    fontSize: "64px"
    fontWeight: 400
    lineHeight: 1.05
    letterSpacing: "-0.02em"
  serif-quiet:
    fontFamily: "Cormorant Garamond, Georgia, serif"
    fontSize: "30px"
    fontWeight: 300
    lineHeight: 1.15
  number:
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
  lead:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    fontFeature: "tnum"
  tick:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 400
rounded:
  bar: "2px"
  control: "11px"
  tooltip: "12px"
  mock: "16px"
  card: "22px"
  pill: "9999px"
spacing:
  xs: "6px"
  sm: "12px"
  md: "16px"
  lg: "24px"
  xl: "40px"
  section: "120px"
components:
  glass-card:
    backgroundColor: "rgba(255,255,255,0.32)"
    rounded: "{rounded.card}"
    padding: "24px"
  button-primary:
    backgroundColor: "{colors.ink-strong}"
    textColor: "{colors.page-plain}"
    rounded: "{rounded.pill}"
    padding: "8px 16px"
    height: "32px"
  button-cta:
    backgroundColor: "#5b5b5f"
    textColor: "{colors.page-plain}"
    rounded: "{rounded.pill}"
    padding: "14px 32px"
    height: "54px"
  button-glass:
    backgroundColor: "rgba(255,255,255,0.68)"
    textColor: "{colors.ink-strong}"
    rounded: "{rounded.pill}"
    padding: "8px 16px"
    height: "36px"
  segmented-track:
    backgroundColor: "rgba(9,9,11,0.05)"
    rounded: "{rounded.pill}"
    padding: "3px"
  segmented-active:
    backgroundColor: "{colors.page-plain}"
    textColor: "{colors.ink-strong}"
    rounded: "{rounded.pill}"
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
  action-no-trade:
    backgroundColor: "rgba(9,9,11,0.05)"
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

**Look at the references first:** `docs/design-reference/dashboard/dashboard-top.png` is the screen to match. Landing and extension shots in the same folder show buttons, nav, type and the dark section. Code tokens and components: `frontend/design/`.

## Overview

**Creative North Star: "Glass over the Horizon"**

Frosted glass panels floating over an old painting of the sea. The painting is held back (half-desaturated, under a pale scrim) so it only shows as soft movement behind the glass; the panels carry the data. Numbers are set big in a round geometric face, everything else is quiet grey in a friendly sans, and the few headlines that need gravitas are set in a classical serif with a greyed second line.

It is calm, expensive-looking and monochrome. Colour only enters for meaning: green up/buy-YES, rose down/buy-NO. Charts are graphite: gradient bars and two stepped lines, one near-black and one grey.

**Key Characteristics:**
- Separate glass cards (22px radius, white rim, soft shadow) on a fixed, slowly drifting, muted painting backdrop.
- Poppins semibold numbers (34–40px) and panel titles; Plus Jakarta Sans for all text.
- Serif display (Playfair Display) for page-level headlines, second line in grey; Cormorant Garamond for quiet serif moments.
- Everything small is a pill: buttons, tabs, trend chips, action chips, tags.
- Glass header bar that condenses into a floating pill on scroll.

## Colors

Zinc and white glass over a muted painting, plus two signal hues.

### Primary
- **Ink** (#111113): primary buttons, the model series in every chart, numbers. Text is #0a0a0a.

### Neutral
- **Backdrop Base** (#dedee3): solid colour under the painting; what shows if the image fails.
- **Scrim** (rgba(244,244,247,0.50 → 0.86 → 0.58), vertical gradient): veil over the painting, heaviest behind the masthead text.
- **Glass White** (rgba(255,255,255,0.32) + diagonal highlight): card surface. See Elevation.
- **Slate Muted** (#676e7e): labels, subtitles, secondary text; at 70% for hints.
- **Second-Line Grey** (rgba(10,10,10,0.42)): the greyed second line of a serif headline.
- **Hairline** (rgba(9,9,11,0.07)): dividers inside glass cards, chart gridlines.
- **Graphite → Ash** (#3f3f46 → #a1a1aa): bar gradient; Ash alone is the market / baseline / without-costs series.
- **Night** (#0a0a0a): optional dark band (e.g. the "how we measured it" section) with dark glass cards.

### Semantic
- **Signal Green** (#16a34a, tint 10%): up, profit, BUY YES.
- **Signal Rose** (#e11d48, tint 10%): down, loss, drawdown, BUY NO.

### Named Rules
**The Two Hues Rule.** Green and rose are the only hues in the interface. They mark direction or action, never decoration. The painting supplies all other colour, and it is held at half saturation.
**The NO_TRADE Is A Result Rule.** NO TRADE uses the same chip size in neutral grey. Never hidden or faded.

## Typography

**Numbers & titles:** Poppins 500/600 (Google Fonts, OFL)
**Text:** Plus Jakarta Sans 400/600 (Google Fonts, OFL)
**Serif display:** Playfair Display 400 (Google Fonts, OFL); quiet serif: Cormorant Garamond 300 (Google Fonts, OFL)

**Character:** round geometric numbers against a warm humanist sans; a classical serif only where the page makes a statement.

### Hierarchy
- **Serif display** (Playfair 400, 48–64px, lh 1.05, -0.02em): page headline, two lines, second line in Second-Line Grey ("Is the time bias tradable? / Only in politics, and only a month out.").
- **Number** (Poppins 600, 34px mobile / 40px desktop, lh 1, -0.025em, tabular): KPI values.
- **Headline** (Poppins 600, 26–30px): masthead on the dashboard.
- **Title** (Poppins 600, 19px, -0.02em): glass card titles.
- **Lead** (Jakarta 400, 17px, lh 1.6, Slate Muted): one-paragraph intro under a headline, max 60ch.
- **Body** (Jakarta 400, 14px, lh 1.45): subtitles, labels, reasons.
- **Label** (Jakarta 600, 13px, tabular): deltas, chips, numbers in tables.
- **Tick** (Jakarta 400, 11px, Tick Grey rgba(9,9,11,0.42)): chart axes.

### Named Rules
**The Tabular Rule.** Every number is tabular and carries its unit (`72%`, `4.2¢`, `30d`, `+1.65×`).

## Layout

- Backdrop: three fixed layers: Backdrop Base, the painting (`object-cover`, `filter: grayscale(0.5) contrast(1.08) brightness(1.04)`, drifting slowly via a CSS transform animation), and the Scrim gradient.
- Header: 56px glass bar, full-bleed at the top; after 12px of scroll it insets to a floating `rounded-2xl` pill (max-w-5xl, 12px from the edges) over 300ms. Left: wordmark "Horizon" + "/" + section in Slate Muted. Right: muted text links + a glass pill button.
- Masthead: headline + one muted line, glass pill button aligned right; 40px above the cards.
- Cards: separate glass cards with 16px gaps. Row 1: 4 KPI cards. Row 2: 2 chart cards. Row 3: 3 cards (~5/3/6 columns). Single column under 768px, KPIs 2-up.
- Card padding 20px mobile / 24px. Charts 240px tall. Max content width 1600px, side padding 16/24px.
- Landing-style sections (if any): 120px vertical rhythm, text column left (max 640px), product mock right.

## Elevation & Depth

Depth is glass: translucent white surfaces with a bright rim and a soft, low shadow, lifted off a moving backdrop. The backdrop is what makes the glass read; on a flat background the cards become plain white boxes, so never drop it.

### Shadow & material vocabulary
- **Glass card**: `background: linear-gradient(125deg, rgba(255,255,255,.60) 0%, rgba(255,255,255,.16) 35%, rgba(255,255,255,.04) 52%, rgba(255,255,255,.30) 100%), rgba(255,255,255,.32); backdrop-filter: blur(20px) saturate(180%); border: 1px solid rgba(255,255,255,.70); box-shadow: inset 0 1px 0 rgba(255,255,255,.95), inset 0 -1px 0 rgba(255,255,255,.25), inset 1px 0 0 rgba(255,255,255,.40), inset -1px 0 0 rgba(255,255,255,.40), 0 2px 10px rgba(15,23,42,.07), 0 8px 24px rgba(15,23,42,.05)`.
- **Glass card hover** (clickable cards only): `translateY(-2px)` and shadow `0 4px 14px rgba(15,23,42,.09), 0 16px 40px rgba(15,23,42,.09)` over 260ms `cubic-bezier(0.34,1.4,0.64,1)`.
- **Glass bar** (header, pill buttons): `rgba(255,255,255,.68)`, `blur(26px) saturate(200%)`, border `rgba(255,255,255,.54)`, `0 2px 16px rgba(0,0,0,.06)`. Condensed header adds `0 8px 32px rgba(15,23,42,.10)`.
- **Tooltip**: `rgba(255,255,255,.72)`, `blur(26px) saturate(200%)`, border `rgba(255,255,255,.6)`, `inset 0 1px 0 rgba(255,255,255,.85), 0 8px 28px rgba(0,0,0,.10)`, radius 12.
- **Product mock card** (landing-style): white, radius 16, `0 20px 60px rgba(15,23,42,.08)` inside a faint 8px outer frame.

### Named Rules
**The Backdrop Rule.** Glass only exists over the backdrop. No glass on plain white, no glass inside glass.

## Shapes

- Glass cards 22px; condensed header 16px; product mocks 16px; inputs/controls 11px; tooltips 12px; bars 2px top corners.
- Pills (9999px) for every button, tab, chip and tag.
- Icons: thin line icons (lucide-style, 1.6–1.9 stroke, round caps), 12–16px. No emoji, no unicode arrows as icons.

## Components

- **KPI card:** label (Body, Slate Muted) → Number 12px below → delta row 12px below: ↑ arrow + `28.4%` (Label, green/rose) + muted suffix "vs market". No comparison → muted hint, never an empty delta.
- **Card head:** Title + trend pill on one line; subtitle (Body, Slate Muted) 6px below.
- **Trend pill:** pill, 10% tint, Label in the same hue, 12px ↗ icon.
- **Action chip:** BUY YES (green tint), BUY NO (rose tint), NO TRADE (5% ink tint, muted text). Same size.
- **Decision card (live markets):** question (Body, ink, 2 lines max) + domain tag + "30d to resolution" (muted). Market price vs model q as two 26px Poppins numbers; q interval as an Ash band on a thin 0–100 track with an Ink tick for q; net edge in ¢ coloured by sign; action chip; ¼-Kelly size; reason (muted Body).
- **Segmented tabs** (horizons 30d / 7d / 3d / 1d / 12h, domains): pill track `rgba(9,9,11,0.05)`, 3px inset, active item white pill with `0 1px 3px rgba(0,0,0,0.08)`, Label text; inactive Slate Muted.
- **Buttons:** primary = Ink pill, white text, 32–40px (nav "Add to Chrome" style); hero CTA = 54px grey glass pill with inner highlight and soft drop shadow, white text + →; secondary = glass pill ("Manage billing" style).
- **Charts:** bars with `linearGradient` #3f3f46 → #a1a1aa, radius [2,2,0,0], gap 22%, no y-axis, x ticks only. Lines 2px, `stepAfter` for equity and `monotone` for calibration, no dots, active dot r=3 with white ring; Ink = model / with costs, Ash = market / without costs; horizontal Hairline grid only. Calibration: dashed Hairline diagonal.
- **Tables in cards:** header row Slate Muted 14px, 56–64px rows, Hairline dividers, numbers right-aligned tabular.
- **Empty state:** centred muted Body in the chart area. Never fake numbers.

## Do's and Don'ts

**Do**
- Keep the painting backdrop behind every glass surface; keep it muted.
- Make the numbers the biggest thing in each card.
- Put market (Ash) next to model (Ink) wherever a model number appears.
- Keep every NO TRADE visible.

**Don't**
- No glass on a flat background, no nested glass, no glass for decoration on the landing hero text.
- No hues beyond green/rose; no gradient text; no neon or glow.
- No eyebrow/kicker labels above headings, no 01/02/03 numbers on the data screen.
- No names, logos, copy or imagery from earlier products: wordmark is **Horizon**, the painting is our own public-domain choice.
