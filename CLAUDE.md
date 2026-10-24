# OxHack '26 — team brain

Every Claude Code session on this team reads this file. Keep it short and current.
Update it whenever a decision changes; it is how our three agents stay in sync.

## Event
- OxHack '26, Mathematical Institute, Oxford. **Hacking: Sat 12:00 → Sun 12:00 (hard stop).** Clocks go back at 02:00 Sunday, so we get 25 real hours.
- **Devpost submission must be done by Sun 12:00.** Devpost workshop Sun 09:00–10:00 (C1). Judging Sun 13:00–15:45, closing 16:00.
- Schedule: lunch Sat 13:00, Citadel bubble tea 14:00, HRT talk (Matt Godbolt, compilers) 15:00–16:00 L1, dinner 18:00, HRT midnight pizza 00:00, breakfast Sun 08:00.
- **Platinum sponsor challenge — HRT (Hudson River Trading): "Best use of Data for Predictions & Decision Making".** Prize: £1,000 per team member of the winning team (per track vs overall: TBA).
- **Silver sponsor challenge — Zed: "Built with Delta".** Show how we worked together in Delta (teammates + agents, from ideation through building to testing); share Delta threads as evidence. Extra points for solving real problems.
- Only HRT and Zed have challenges; the other sponsors (Citadel, Jane Street, Oxford Asset Management, Entangl) are recruiting only.
- **Strategy: one project for both.** Build the HRT data/prediction/decision project, and do the work inside Delta so the Zed track comes for free. MLH prizes (Gemini, ElevenLabs, Tiger Data) only if they fit naturally.

## Working in Delta (for the Zed track)
- Run Claude Code sessions linked to Delta threads; Delta works on top of this git repo, so branches and `CLAUDE.md` stay as they are.
- Keep ideation (`/office-hours`), key build steps and testing (`/qa`) in Delta threads. Role C collects the best thread links for Devpost as we go.
- If Delta access or setup takes more than 15 minutes, drop it and keep working in git — HRT is the priority.

## What HRT judges will look for (design every feature around this)
HRT is a quant trading firm. A pretty chart is not enough. Our project must show:
1. **Real data → a prediction**, evaluated honestly on held-out data. Show the actual accuracy / error, including where it fails.
2. **Probabilities, not yes/no.** Calibrated where possible ("72% likely"), with uncertainty shown in the UI.
3. **A decision made from the prediction** — "therefore do X", with the expected value or trade-off spelled out. This is the step most teams skip.
4. A baseline to beat (naive / last-value / majority class), so the model's lift is visible.
Never fake data or accuracy numbers; judges will ask how they were measured.

## What we are building
TBA — one paragraph, written after the idea is locked (after /office-hours).

## Stack (default, change only by team decision)
- Frontend: Next.js + Tailwind + shadcn/ui, deployed on Vercel. Visual style: our minimalist white preset (see `DESIGN.md`).
- Backend / agent: TBA (FastAPI or Next.js API routes). AI: Gemini API. Voice: ElevenLabs.
- Secrets live in `.env.local` (never committed). Template: `.env.example`.

## Roles — who you are
At the start of every session, ask the human which role they have (if not obvious from the branch name), then act only as that role.

### Role A — Tech lead: agent & backend (Gleb)
- Folder: `backend/` (or `app/api/` if we go full Next.js). Branches: `gleb/<feature>`.
- Owns: architecture, agent logic on Gemini, API endpoints, wiring everything together, cut/keep decisions, merging PRs.
- Writes and keeps the **API contract** section below up to date — other roles build against it.
- gstack flow: `/office-hours` → `/plan-ceo-review` (Reduction / Hold Scope) → `/plan-eng-review` at the start; `/investigate` when something breaks; `/review` on the whole repo before feature freeze.

### Role B — Frontend & demo screen
- Folder: `frontend/`. Branches: `front/<feature>`. First command in a session: `/freeze frontend/`.
- Owns: the one main demo screen, styled strictly by `DESIGN.md`, calling the API exactly as the contract says.
- gstack flow: `/design-shotgun` → pick one → `/design-html`; `/design-review` in the evening. Impeccable applies to every screen automatically.
- Until the backend exists, use the contract's example responses — but replace them with real calls before the 16:30 gate.

### Role C — Integrations, demo data, then pitch
- Folder: `integrations/`. Branches: `int/<feature>`. First command in a session: `/freeze integrations/`.
- Owns: thin wrappers around sponsor APIs (ElevenLabs voice, Presage, others as needed), real demo data, and running the demo as a user.
- gstack flow: `/qa` at every gate, walking the exact demo script.
- From Saturday evening: Devpost page, backup demo video, pitch script (see "Pitch" in TASKS.md).

## API contract (Role A maintains this)
TBA after `/plan-eng-review` — list each endpoint: method, path, request body, example response.

## Order of work (real schedule)
1. **12:00–13:00 — idea.** All together, one laptop: `/office-hours` → `/plan-ceo-review` → `/plan-eng-review` (or `/autoplan`). Write "What we are building" + API contract here. Everyone `git pull`. Eat lunch while building, not instead of planning.
2. **13:00–16:30 — skeleton.** Parallel build in own folders. **Gate 16:30:** one scenario works end-to-end on a public URL with real data (`/qa`). Optional: one person at the HRT talk 15:00–16:00 — it is the challenge sponsor, worth a question to their engineers afterwards.
3. **18:00–20:00 — pivot checkpoint** (over dinner): `/plan-ceo-review` on the working product. Where did the "wow" happen? Keep or shift focus. **No pivots after 20:00.**
4. **20:00–02:00 — model quality + wow moment + polish.** Honest evaluation on held-out data, baseline, calibrated probabilities, the decision screen. `/design-review` around midnight.
5. **~02:00 (before clocks go back) — `/review`, then feature freeze.** Then sleep in shifts.
6. **Sun 07:00–10:00 — bugs only, backup demo video, final `/qa` on the exact demo script.** Devpost workshop 09:00.
7. **Sun 10:00–11:30 — Devpost written and submitted by 11:30** (30 min buffer before the 12:00 hard stop). Pitch rehearsal 5x.

## Rules for agents and humans
1. Work only inside your own role's folder unless the task in `TASKS.md` says otherwise. Never edit another role's folder — ask instead.
2. Before starting: `git pull`, read `TASKS.md`, claim a task by putting your name on it.
3. One branch per person/feature → pull request → someone else glances at it → merge. (Judges score "best practices".)
4. Small commits, often. Never commit secrets. `git pull` at least every hour.
5. Only build what appears in the demo. If it is not in the 90-second demo script, it does not get built.
6. Feature freeze ~02:00 Sunday. After that: bugs, backup video, Devpost, pitch only. Submission by 11:30 Sunday.

## Hackathon mindset (applies to every task)
- The demo is the product. Optimise for what judges see in the 90-second demo, not for code quality.
- No tests, refactors or abstractions unless they directly unblock the demo.
- Get the simplest working path end-to-end first, then polish.
- No mocks or fake data where judges will click; real calls to Gemini / ElevenLabs / Presage.
- Any UI follows `DESIGN.md` (repo root). Impeccable is the one auto UI skill; never stack a second visual-direction skill on the same screen.
- Before each gate in the timeline, offer to run `/qa`; before feature freeze, offer `/review`.
- If a task looks like more than 30 minutes, stop and propose a smaller cut first.

## Skills — read `docs/SKILLS.md` before invoking any skill
That file is the playbook: which skill for which moment, per-role sequence, what never to combine, what not to install.
- **Auto** (load themselves): impeccable (the only auto UI skill), animate, find-animation-opportunities, improve-animations, animation-performance, break-ui, mobile-native, webapp-testing, mcp-builder, skill-creator.
- **Manual only** (`/name`, only in the situations listed in SKILLS.md): frontend-design, design-taste-frontend, ui-ux-pro-max, hallmark, emil-design-eng, apple-design, prototype, pick-ui-library, review-animations, theme-factory, canvas-design, algorithmic-art, web-artifacts-builder.
- **gstack** (installed per machine by `scripts/setup.sh`): /office-hours, /plan-ceo-review, /plan-eng-review, /autoplan, /design-shotgun, /design-html, /design-review, /investigate, /qa, /review, /freeze, /careful.
- Style library for other looks: `docs/design-library/`.
- Do not install other skills or plugins during the event without asking Role A.
