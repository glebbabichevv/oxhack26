# OxHack '26 — team brain

Every Claude Code session on this team reads this file. Keep it short and current.
Update it whenever a decision changes; it is how our three agents stay in sync.

## Event
- OxHack '26, Mathematical Institute, Oxford. Sat 24 Oct 09:00 → Sun 25 Oct ~16:30.
- Clocks go back 1 hour on Sunday night (02:00 → 01:00).
- Submission deadline: TBA (fill in after opening ceremony).
- Theme / tracks / main prize: TBA (fill in after opening ceremony).
- MLH sponsor prizes we target: Best Use of Gemini, ElevenLabs, Presage (+ Tiger Data / Vultr if natural).

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
- gstack flow: `/design-shotgun` → pick one → `/design-html`; `/design-review` in the evening. The frontend-design skill applies to every screen.
- Until the backend exists, use the contract's example responses — but replace them with real calls before the 14:00 gate.

### Role C — Integrations, demo data, then pitch
- Folder: `integrations/`. Branches: `int/<feature>`. First command in a session: `/freeze integrations/`.
- Owns: thin wrappers around sponsor APIs (ElevenLabs voice, Presage, others as needed), real demo data, and running the demo as a user.
- gstack flow: `/qa` at every gate, walking the exact demo script.
- From Saturday evening: Devpost page, backup demo video, pitch script (see "Pitch" in TASKS.md).

## API contract (Role A maintains this)
TBA after `/plan-eng-review` — list each endpoint: method, path, request body, example response.

## Order of work after the task is announced
1. Opening → fill Event section above (theme, tracks, deadline).
2. All together, one laptop: `/office-hours` → `/plan-ceo-review` → `/plan-eng-review` (or `/autoplan`). Write "What we are building" and the API contract here. Everyone `git pull`.
3. Parallel build in own folders. Gate ~14:00 Sat: skeleton works end-to-end on a public URL (`/qa`).
4. **Pivot checkpoint, Sat ~18:00–20:00:** all together, `/plan-ceo-review` on the working product. Where did the "wow" actually happen? Keep the focus or shift it there, update "What we are building". No pivots after 20:00.
5. Evening: polish + wow moment, `/design-review`. ~03:00 Sun: `/review`, then feature freeze.
6. Sunday morning: final `/qa` on the exact demo script, backup video, Devpost, pitch rehearsal.

## Rules for agents and humans
1. Work only inside your own role's folder unless the task in `TASKS.md` says otherwise. Never edit another role's folder — ask instead.
2. Before starting: `git pull`, read `TASKS.md`, claim a task by putting your name on it.
3. One branch per person/feature → pull request → someone else glances at it → merge. (Judges score "best practices".)
4. Small commits, often. Never commit secrets. `git pull` at least every hour.
5. Only build what appears in the demo. If it is not in the 90-second demo script, it does not get built.
6. Feature freeze ~03:00 Sunday. After that: bugs, backup video, Devpost, pitch only.

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
