# How agents talk to each other

Each role has an inbox: `team/inbox/A.md`, `B.md`, `C.md`.

**Read your inbox** at the start of every task: `git pull origin main`, then open `team/inbox/<your role>.md`. Unhandled messages come before your next task.

**Write to someone's inbox** when you see a problem in their work or need something from them:
- append one line to `team/inbox/<their role>.md`
- `git add team/ && git commit -m "inbox: to <role>: <short>" && git push origin HEAD:main`
  (inbox files are the one exception allowed straight into `main`, no PR — they are append-only, one line each)

**Be blunt and specific.** "Your CSV breaks the data contract: `resolved_at` is a unix timestamp, contract says ISO — integrations/fetch.py" is good. "Looks off" is useless. Always say what is wrong, where, and what you expect instead.

What to check in each other's work (these are the usual failures):
- **A checks C:** CSV columns match the Data contract; no cancelled / MKT markets; prices really taken *before* the horizon (no future leakage); enough rows per horizon/domain.
- **B checks A:** endpoints return exactly the contract JSON shapes; numbers look sane (probabilities in 0–1, returns not absurd).
- **C checks B:** walk the demo as a user (`/qa`); anything confusing, slow or broken on screen.
- **Anyone checks anyone:** fake or hard-coded numbers shown as real; accuracy claimed without an out-of-time test.

**PR reviews:** every PR into `main` is reviewed by an agent of a *different* role before Role A merges: check out the branch, run `/review`, and post the verdict as a PR comment (`gh pr review <n> --comment -b "..."`) or, if `gh` is unavailable, in the author's inbox.
