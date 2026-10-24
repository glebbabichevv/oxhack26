#!/bin/bash
# Horizon scheduled refresh (run hourly by launchd or cron; see scripts/com.horizon.refresh.plist).
#   1. refit.py pulls newly resolved Polymarket markets into data/horizons.csv and refits;
#   2. the new model is promoted only if its out-of-time Brier is not worse (refit.py's gate);
#   3. on promotion (exit 10) the API is redeployed to Vercel with the owner's config.
# /api/live needs none of this: it recomputes from live prices on request (~5 min cache).
# HORIZON_AUTOCOMMIT=1 also commits the promoted model + data on the current branch (no push).
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LOCK="${TMPDIR:-/tmp}/horizon-refresh.lock"
mkdir "$LOCK" 2>/dev/null || { echo "$(date -u +%FT%TZ) refresh already running"; exit 0; }
trap 'rmdir "$LOCK"' EXIT

cd "$REPO/backend" || exit 1
echo "$(date -u +%FT%TZ) refit start"
.venv/bin/python refit.py
code=$?
if [ "$code" -eq 10 ]; then
  version=$(python3 -c "import json;print(json.load(open('results/model.json'))['version'])")
  echo "$(date -u +%FT%TZ) promoted $version, deploying API"
  vercel deploy --prod --yes -Q "$HOME/.vercel-gleb" || { echo "deploy failed"; exit 1; }
  if [ "${HORIZON_AUTOCOMMIT:-0}" = 1 ]; then
    cd "$REPO" && git add backend/results data/horizons.csv \
      && git commit -m "refit: promote model $version" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  fi
elif [ "$code" -ne 0 ]; then
  echo "$(date -u +%FT%TZ) refit failed ($code)"; exit "$code"
fi
echo "$(date -u +%FT%TZ) refit done"
