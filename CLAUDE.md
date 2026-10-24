# OxHack '26 — team brain

Every Claude Code session on this team reads this file. Keep it short and current.
Update it whenever a decision changes; it is how our four agents stay in sync.

## Event
- OxHack '26, Mathematical Institute, Oxford. Sat 24 Oct 09:00 → Sun 25 Oct ~16:30.
- Clocks go back 1 hour on Sunday night (02:00 → 01:00).
- Submission deadline: TBA (fill in after opening ceremony).
- Theme / tracks / main prize: TBA (fill in after opening ceremony).
- MLH sponsor prizes we target: Best Use of Gemini, ElevenLabs, Presage (+ Tiger Data / Vultr if natural).

## What we are building
TBA — one paragraph, written after the idea is locked (after /office-hours).

## Stack (default, change only by team decision)
- Frontend: Next.js + Tailwind + shadcn/ui, deployed on Vercel. Visual style: our minimalist white preset (see `docs/DESIGN.md`).
- Backend / agent: TBA (FastAPI or Next.js API routes). AI: Gemini API. Voice: ElevenLabs.
- Secrets live in `.env.local` (never committed). Template: `.env.example`.

## Roles (who owns what)
| Role | Person | Owns |
| --- | --- | --- |
| Tech lead / agent & backend | Gleb | architecture, agent logic, API, cut/keep decisions |
| Frontend / demo UI | TBA | the one demo screen, design preset |
| Integrations & data | TBA | ElevenLabs, Presage, Tiger Data/Vultr, demo data |
| Product & pitch | TBA | testing as a user, Devpost, sponsors, pitch |

## Rules for agents and humans
1. Work only inside your own area (folder) unless the task in `TASKS.md` says otherwise.
2. Before starting: `git pull`, read `TASKS.md`, claim a task by putting your name on it.
3. One branch per person/feature → pull request → someone else glances at it → merge. (Judges score "best practices".)
4. Small commits, often. Never commit secrets.
5. Only build what appears in the demo. If it is not in the 90-second demo script, it does not get built.
6. Feature freeze ~03:00 Sunday. After that: bugs, backup video, Devpost, pitch only.

## Skills available
- Project skills in `.claude/skills/` (auto-loaded): frontend-design, canvas-design, theme-factory, web-artifacts-builder, webapp-testing, mcp-builder, skill-creator, algorithmic-art.
- gstack (installed per machine by `scripts/setup.sh`): /office-hours, /plan-eng-review, /design-shotgun, /design-html, /design-review, /review, /qa, /ship.
