---
name: Horizon
description: Is the prediction-market time bias tradable? A calibration and decision screen.
colors:
  page: "#ffffff"
  frame: "#fafafa"
  card: "#ffffff"
  ink: "#0a0a0a"
  ink-strong: "#111113"
  ink-muted: "#676e7e"
  ink-faint: "#71717a"
  ink-second-line: "rgba(10,10,10,0.50)"
  hairline: "rgba(9,9,11,0.08)"
  hairline-soft: "rgba(9,9,11,0.06)"
  fill-soft: "rgba(15,23,42,0.05)"
  ash: "#a1a1aa"
  up: "#15803d"
  up-tint: "rgba(21,128,61,0.10)"
  down: "#e11d48"
  down-tint: "rgba(225,29,72,0.10)"
typography:
  display:
    fontFamily: "Playfair Display, Georgia, serif"
    fontSize: "56px"
    fontWeight: 400
    lineHeight: 1.06
    letterSpacing: "-0.02em"
  section:
    fontFamily: "Playfair Display, Georgia, serif"
    fontSize: "32px"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  lead:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.6
  number:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "30px"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.02em"
    fontFeature: "tnum"
  title:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    fontFeature: "tnum"
  tick:
    fontFamily: "Plus Jakarta Sans, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 400
rounded:
  bar: "2px"
  input: "11px"
  card: "16px"
  frame: "22px"
  pill: "9999px"
spacing:
  xs: "8px"
  sm: "16px"
  md: "24px"
  lg: "40px"
  xl: "56px"
  hero-top: "72px"
components:
  card:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.card}"
    padding: "20px"
  frame:
    backgroundColor: "{colors.frame}"
    rounded: "{rounded.frame}"
    padding: "8px"
  button-primary:
    backgroundColor: "{colors.ink-strong}"
    textColor: "{colors.page}"
    rounded: "{rounded.pill}"
    padding: "8px 16px"
    height: "36px"
  button-cta:
    backgroundColor: "#1c1c1f"
    textColor: "{colors.page}"
    rounded: "{rounded.pill}"
    padding: "14px 30px"
    height: "52px"
  button-quiet:
    backgroundColor: "{colors.fill-soft}"
    textColor: "{colors.ink-strong}"
    rounded: "{rounded.pill}"
    padding: "8px 16px"
    height: "36px"
  segmented-track:
    backgroundColor: "{colors.page}"
    rounded: "{rounded.pill}"
    padding: "3px"
  segmented-active:
    backgroundColor: "{colors.ink-strong}"
    textColor: "{colors.page}"
    rounded: "{rounded.pill}"
  chip-buy-yes:
    backgroundColor: "{colors.up-tint}"
    textColor: "{colors.up}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "3px 10px"
  chip-buy-no:
    backgroundColor: "{colors.down-tint}"
    textColor: "{colors.down}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "3px 10px"
  chip-no-trade:
    backgroundColor: "{colors.fill-soft}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "3px 10px"
  nav:
    backgroundColor: "rgba(250,250,250,0.9)"
    rounded: "{rounded.pill}"
    height: "52px"
---

# Design System: Horizon

**Target:** `docs/design-reference/horizon-target-mock.png` (rendered from these tokens). Source looks: `docs/design-reference/landing/` and `extension/`. Code: `frontend/design/`.

## Overview

**Creative North Star: "The Quiet Page"**

A white editorial page that makes one argument, like a newspaper data story. A big classical serif headline states the finding, its second line in grey; directly under it the hero figure (how often a 15¢ contract wins, by time left) is drawn on the page and annotated in place in italic serif; numbers sit in a single ruled row; each piece of evidence is a figure under a 1px Ink rule, not a card. Nothing is glass, nothing blurs, nothing is boxed, nothing floats except the navigation pill.

The material is soft matte: opaque white surfaces, an 8% hairline, a very low and wide shadow. Depth comes from the faint grey frame around each card, not from effects. The only object with real volume is the dark call-to-action pill, which sits on its own soft grounding shadow.

**Key Characteristics:**
- White page, generous whitespace, content max 1120px.
- Playfair Display headlines (second line grey), Plus Jakarta Sans for everything else.
- KPIs as one ruled row with hairline separators, not as cards.
- Evidence as editorial figures: 1px Ink rule on top, title + Faint meta on one line, the chart below. No boxes, frames or card shadows (changed 15:55: the framed cards read as generic and blocky).
- One hero figure under the headline, annotated in place (italic Playfair notes, leader-free), with 90% intervals.
- Pills everywhere: nav, buttons, tabs, chips. Green and rose only for meaning.

## Colors

White and zinc with two signal hues.

### Primary
- **Ink** (#111113): primary buttons, the active tab, the model line in charts. Body text #0a0a0a.

### Neutral
- **Page White** (#ffffff): page and card surface.
- **Frame Grey** (#fafafa): the 8px frame around each evidence card.
- **Slate Muted** (#676e7e): lead paragraphs, labels, secondary text.
- **Faint** (#71717a): meta text (n = 573, dates), axis labels; passes 4.5:1 on white. **Ash** (#a1a1aa) stays for the market / baseline chart series only.
- **Second-Line Grey** (rgba(10,10,10,0.50), 3.8:1, large text only): the second line of a serif headline.
- **Hairline** (rgba(9,9,11,0.08)): KPI row rules, card borders, nav border; soft hairline 6% for rows inside cards.
- **Soft Fill** (rgba(15,23,42,0.05)): quiet chips, quiet buttons, hover wash.

### Semantic
- **Signal Green** (#15803d, tint 10%; #16a34a failed 4.5:1 for small labels): up, profit, BUY YES.
- **Signal Rose** (#e11d48, tint 10%): down, loss, BUY NO, "no lift".

### Named Rules
**The Two Hues Rule.** Green and rose are the only hues on the screen and they always mean direction or action.
**The NO_TRADE Is A Result Rule.** NO TRADE chips are the same size, in Soft Fill grey. Never hidden.

## Typography

**Display Font:** Playfair Display 400 (Google Fonts, OFL), fallback Georgia
**Body Font:** Plus Jakarta Sans 400/500/600 (Google Fonts, OFL), fallback system-ui

**Character:** an editorial serif for the claim, a warm geometric sans for the evidence.

### Hierarchy
- **Display** (Playfair 400, 56px desktop / 40px mobile, lh 1.06, -0.02em): the page claim, two lines, the second in Second-Line Grey.
- **Section** (Playfair 400, 32px, lh 1.2): section heads in the left column ("A month out, favourites are overpriced").
- **Lead** (Jakarta 400, 17px, lh 1.6, Slate Muted, max 560px): one paragraph under each heading.
- **Number** (Jakarta 600, 30px, -0.02em, tabular): KPI values.
- **Title** (Jakarta 600, 15px): card titles.
- **Body** (Jakarta 400, 14px): rows, labels.
- **Label** (Jakarta 600, 12px, tabular): chips, deltas.
- **Tick** (Jakarta 400, 11px, Faint): chart axes.

### Named Rules
**The Tabular Rule.** Every number is tabular and carries its unit (`72%`, `15¢`, `30d`, `+1.65×`).
**The One Serif Rule.** Serif only for display and section heads. Never for numbers, buttons or labels.

## Layout

- Nav: floating pill bar, 16px from the top, max 1120px, 52px tall. Left wordmark "Horizon." (the dot in Faint), centre text links in Slate Muted, right one Ink pill button.
- Hero: 72px below the nav. Display headline, lead 18px below.
- KPI row: 44px below the lead; 4 columns, hairline top and bottom, hairline separators between columns, 20–24px padding. Label → Number → small coloured note.
- Sections: two columns (text 1fr, evidence 1.25fr), 40px gap, 56px between sections. Left: Section head, Lead, controls (horizon tabs). Right: framed card.
- Mobile (<768px): one column, KPIs 2×2, framed card full width under its text.

## Elevation & Depth

Soft matte. Surfaces are opaque; there is no blur and no glass anywhere. Depth is the frame: a white card with a hairline border inside a slightly grey frame that casts one wide, faint shadow. Popovers and tooltips are the only other things with a shadow.

### Shadow Vocabulary
- **Frame** (`box-shadow: 0 24px 60px -32px rgba(15,23,42,0.18)`): the evidence frame.
- **Nav pill** (`box-shadow: 0 2px 16px rgba(0,0,0,0.06)`; border 1px rgba(0,0,0,0.04)).
- **Popover / tooltip** (`box-shadow: 0 8px 28px rgba(15,23,42,0.10)`; white, hairline border, radius 12).
- **CTA grounding** (a separate blurred layer under the pill: `background: rgba(0,0,0,0.55); filter: blur(14px); transform: translateY(6px) scale(0.94); opacity: .7`, rising to `translateY(9px) scale(.96)` / `.85` on hover): only on the big CTA.

### Named Rules
**The No Glass Rule.** No backdrop-filter, no translucent panels over imagery, no specular streaks.

## Shapes

- Cards 16px inside 22px frames; inputs 11px; tooltips 12px; bars 2px top corners.
- Pills (9999px) for nav, buttons, tabs, chips.
- Icons: thin line icons (lucide-style, 1.6–1.9 stroke), 14–16px. No emoji or unicode arrows as icons except the → in button labels.

## Components

- **KPI row:** see Layout. Note line uses Label in green/rose for direction, Slate Muted otherwise.
- **Framed card:** frame (Frame Grey, 8px, radius 22, Frame shadow) → card (white, radius 16, 1px Soft Hairline, 20px padding). Head: Title left, Faint meta right (`n = 573`).
- **Horizon tabs (segmented):** white track with 1px hairline (10%), 3px inset; active item Ink pill with white text; inactive Slate Muted. Same as the pricing Monthly/Annual toggle.
- **Decision rows (live markets):** grid `question | price | model q | chip`. Question Body 500, under it Faint `politics · 11d`; price and q right-aligned tabular, q in 600; chip BUY YES / BUY NO / NO TRADE; optional q interval as a thin Ash band. Rows separated by Soft Hairline.
- **Buttons:** primary Ink pill 36px (nav); CTA 52px dark pill with grounding shadow and → that nudges 2px on hover; quiet Soft Fill pill.
- **Charts (Recharts):** model line Ink 2px, market line Ash 2px, both `monotone` for calibration and `stepAfter` for equity, no dots; dashed hairline diagonal for perfect calibration; bars `linearGradient` #3f3f46 → #a1a1aa radius [2,2,0,0]; horizontal hairline grid only; ticks 11px Faint; tooltip as Popover.
- **Empty / loading:** skeleton blocks in Soft Fill; empty chart says why in Slate Muted. Never show placeholder numbers as real.

## Do's and Don'ts

**Do**
- State the finding in the headline; let every section prove one sentence.
- Put market (Ash) next to model (Ink) wherever a model number appears.
- Keep NO TRADE visible.

**Don't**
- No glass, blur, painting backdrops or translucent panels.
- No dashboards-of-cards: KPIs are a ruled row, evidence is one framed card per section.
- No hues beyond green/rose, no gradient text, no eyebrow labels above headings, no 01/02 numbers.
- No names, logos, copy or imagery from earlier products: wordmark is **Horizon**.
