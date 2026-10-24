#!/usr/bin/env bash
# One-time setup for each teammate. Run from the repo root:  bash scripts/setup.sh
set -e

echo "==> Checking tools"
for t in git node; do
  command -v "$t" >/dev/null || { echo "Missing: $t — install it first"; exit 1; }
done
if ! command -v bun >/dev/null; then
  echo "Bun not found (gstack needs it). Installing Bun..."
  curl -fsSL https://bun.sh/install | bash
  export PATH="$HOME/.bun/bin:$PATH"
fi
command -v claude >/dev/null || echo "WARNING: Claude Code CLI not found. Install it, then re-run."

echo "==> Installing gstack into ~/.claude/skills/gstack"
if [ -d "$HOME/.claude/skills/gstack/.git" ]; then
  git -C "$HOME/.claude/skills/gstack" pull --ff-only
else
  git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git "$HOME/.claude/skills/gstack"
fi
(cd "$HOME/.claude/skills/gstack" && ./setup)

echo "==> Env file"
[ -f .env.local ] || cp .env.example .env.local && echo "Fill your keys in .env.local"

echo
echo "Done. Project skills in .claude/skills load automatically when you run 'claude' in this repo."
echo "Try:  claude   then   /office-hours"
