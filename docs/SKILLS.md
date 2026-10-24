# Skills playbook — what to use, when, and what never to combine

Read this before invoking any skill. Agents: follow it exactly.
There are three kinds of tools in this repo:

1. **Auto skills** — Claude loads them on its own when the task fits. You never need to call them.
2. **Manual skills** — they never load by themselves. Use them only by typing `/name`, and only in the situations listed below.
3. **gstack commands** — the team workflow (`/office-hours`, `/qa`, …). Installed per machine by `scripts/setup.sh`.

Everything in `.claude/skills/` arrives with `git pull`. Nothing else needs installing except gstack.

---

## The golden rules

1. **One design voice at a time.** Impeccable is the only UI skill that runs automatically. Never run two of the "visual direction" skills (Impeccable, frontend-design, taste, ui-ux-pro-max, hallmark) on the same screen in the same session. Pick one, finish, move on.
2. **`DESIGN.md` (repo root) wins over every skill.** If a skill's taste conflicts with our preset, the preset wins. A skill may change `DESIGN.md` only when the team agreed to change the visual direction.
3. **Planning skills only at planning moments.** Idea and scope work happens at the start and at the pivot checkpoint, not in the middle of building.
4. **Read-only skills first, writers second.** Audit skills (`/improve-animations`, `/find-animation-opportunities`, `/review-animations`, `/break-ui` report, `/review`) produce a list. Then a human picks what to fix.
5. **If a skill wants to write tests, a test framework, or a long plan — stop it.** We are in hackathon mode (see `CLAUDE.md`).
6. **Do not install anything that is listed under "Do not install" below**, and do not install the same thing twice (plugin + manual copy).

---

## 1. Idea and target (the most important part)

| Moment | Use | Why |
| --- | --- | --- |
| Right after the theme is announced | `/office-hours` (gstack) | Six forcing questions; reframes the idea around a real user and pain; writes a design doc every later step reads. Do it all together on one laptop. |
| Straight after | `/plan-ceo-review` in **Reduction** or **Hold Scope** mode | Cuts the idea to what ships in 24 h. Never pick Expansion on Saturday. |
| Straight after | `/plan-eng-review` (Role A) | Architecture, data flow, edge cases → becomes the API contract in `CLAUDE.md`. |
| Short on time | `/autoplan` instead of the two reviews above | Same reviews in one command. |
| **Pivot checkpoint, Saturday ~18:00–20:00** (after the skeleton works) | `/plan-ceo-review` again, on the **working product** | The real target often appears while building. Ask: where did the "wow" actually happen? Who reacted? Keep the focus or shift it there. **After 20:00 no pivots** — only polish. |
| Before writing the pitch | `/office-hours` again, short | Re-states the problem and user in one sentence for the pitch. |

Do not use for ideation: Superpowers `brainstorming` (duplicates `/office-hours` and then pushes into a TDD planning chain), `design-sprint` (a 5-day process).

---

## 2. Visual design

### Default: Impeccable (auto)
Runs whenever you build or polish UI. It reads `DESIGN.md` and `PRODUCT.md` from the repo root.
- First time on a machine, it downloads its own small binary — allow it.
- After the idea is locked, Role B runs `/impeccable init` once to write `PRODUCT.md` (who the product is for).
- Useful sub-commands: `/impeccable critique` (what looks generated), `/impeccable polish` (final pass), `/impeccable document` (write `DESIGN.md` from existing code).

### Manual alternatives — use only in these situations

| Situation | Use | Notes |
| --- | --- | --- |
| Theme demands a different look than our white preset | Browse `docs/design-library/` (brutalist, cinematic, data-dense, editorial, glass, indie, playful, terminal, warm…), copy one into `DESIGN.md` | Team decision. Then Impeccable follows the new `DESIGN.md` automatically. |
| Need a full design system from a product description fast | `/ui-ux-pro-max` | 50+ styles, palettes, font pairings. Needs Python 3. Use it once to generate the system, write the result into `DESIGN.md`, then stop using it. |
| A public landing page / hero that must look "award-level" | `/design-taste-frontend` | Art direction for marketing pages. Not for app screens that already follow `DESIGN.md`. |
| A brand-new page from scratch, nothing exists yet | `/hallmark` | Varies structure, blocks default AI layouts. Do not run on an existing design. |
| Anthropic's baseline aesthetic guidance | `/frontend-design` | Only if Impeccable is unavailable (e.g., its binary fails). |
| See 4–6 layout options and pick one | `/design-shotgun` (gstack) → `/design-html` | Needs `OPENAI_API_KEY` for images. Best first step for Role B. |
| Flip between real coded variants of one component | `/prototype` | Renders versions behind a picker. Good for the main demo widget. |
| Emil Kowalski's polish philosophy for a component | `/emil-design-eng` | Use on the single most important component, not the whole app. |
| Gestures, sheets, springs, Apple-like feel | `/apple-design` | Only if the demo is touch / mobile-first. |
| Which library for charts / toasts / command menu / DnD | `/pick-ui-library` | Ask once, then build. |
| A theme for slides or a poster for the pitch | `/theme-factory`, `/canvas-design` | Pitch material only (Role C). |
| Generative art background or visual wow | `/algorithmic-art` | Only if it serves the demo story. |
| Self-contained React artifact for claude.ai | `/web-artifacts-builder` | Rarely needed here — we build a real Next.js app. |

**Never combine** in one session on the same screen: impeccable + taste, impeccable + hallmark, taste + hallmark, ui-ux-pro-max + taste. Each imposes its own art direction.

---

## 3. Motion and the "wow" moment (auto unless marked)

| Situation | Skill |
| --- | --- |
| "Animate this", build a transition | `animate` (auto) |
| "What could be animated here?" | `find-animation-opportunities` (auto, read-only) |
| Audit all motion in the app | `improve-animations` (auto, read-only, writes a plan) |
| Animation is janky / drops frames | `animation-performance` (auto) |
| Strict review of motion code | `/review-animations` (manual) |

Rule: motion only on the demo path. One great transition in the 90-second demo beats ten small ones.

---

## 4. Making the demo not break

| Moment | Use |
| --- | --- |
| Something broke and nobody knows why | `/investigate` (gstack) |
| Every timeline gate (14:00 Sat, evening, Sunday morning) | `/qa` (gstack) on the exact demo script |
| Testing a local page programmatically | `webapp-testing` (auto, Playwright) |
| Main demo screen with worst-case data | `break-ui` (auto when asked "try to break this") |
| Demo will be shown on a phone | `mobile-native` (auto) |
| Before feature freeze (~03:00 Sun) | `/review` and `/design-review` (gstack) |
| Agent keeps touching other people's files | `/freeze <your-folder>/` (gstack), `/unfreeze` to lift |
| Running risky commands late at night | `/careful` (gstack) |

---

## 5. Building blocks for the agent / backend (Role A)

- `mcp-builder` (auto) — if our agent needs to talk to external services through MCP.
- `skill-creator` (auto) — if we want to package a repeated workflow as our own skill mid-event.

---

## 6. Optional extras — install only if you personally need them

| Tool | Who | Install (inside Claude Code) | Use for |
| --- | --- | --- | --- |
| ECC (Everything Claude Code) | Role A only | `/plugin marketplace add https://github.com/affaan-m/ECC` then `/plugin install ecc@ecc` | `/ecc:build-fix` when the build is broken, `/ecc:save-session` / `/ecc:resume-session` to hand work across laptops, `/ecc:context-budget`. Do not use its TDD workflow. Install once, never also via its `install.sh`. |
| Vercel web-design-guidelines | Role B, optional | `npx skills add vercel-labs/agent-skills --skill web-design-guidelines` | Accessibility / UX audit of finished UI. Overlaps `/design-review`, so pick one. |

## Do not install during the hackathon
- **Superpowers** (`obra/superpowers`) — its brainstorming duplicates `/office-hours` and it forces a TDD plan → execute chain.
- **Any second copy** of a skill already in `.claude/skills/` (plugin + local copy = duplicate triggers).
- **Random skills from awesome-lists** — every new auto skill is another voice competing for the same task.

---

## Per-role cheat sheet

**Role A — backend & agent:** `/office-hours` → `/plan-ceo-review` → `/plan-eng-review` → build → `/investigate` when stuck → pivot checkpoint `/plan-ceo-review` → `/review` before freeze. Optional: ECC `/ecc:build-fix`.

**Role B — frontend:** `/freeze frontend/` → `/impeccable init` (once, after idea locked) → `/design-shotgun` → `/design-html` → build (Impeccable auto) → one `animate` wow transition → `/design-review` + `/impeccable polish` before freeze.

**Role C — integrations, then pitch:** `/freeze integrations/` → sponsor API wrappers → `/qa` at every gate → `break-ui` on the main screen → evening: `/theme-factory` / `/canvas-design` for pitch visuals, Devpost, backup video.

---

## Credits
All skills in `.claude/skills/` keep their original licence file. Sources:
anthropics/skills (Apache 2.0), pbakaus/impeccable (Apache 2.0), nextlevelbuilder/ui-ux-pro-max-skill (MIT),
Leonxlnx/taste-skill (MIT), nutlope/hallmark (MIT), emilkowalski/skill (MIT), rohitg00/awesome-claude-design (MIT, in `docs/design-library/`).
Local changes: `disable-model-invocation: true` added to manual skills; ui-ux-pro-max script paths changed to `${CLAUDE_SKILL_DIR}`.
