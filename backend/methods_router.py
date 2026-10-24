"""GET /api/methods: the "How we chose" evidence, read from integrations/methods/summary.json.

Flat rows {block, name, value, lo, hi, n, split, note}; blocks: tournament, errcorr, monthly,
placebo, exit, dsr. Missing or unreadable file -> {"rows": []} (the site then says results land later).
"""
import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()
HERE = Path(__file__).resolve().parent
# The repo copy, or a copy inside backend/ for deploys whose root is backend/ (Railway).
SUMMARY = [HERE.parent / "integrations" / "methods" / "summary.json", HERE / "results" / "methods.json"]


@router.get("/api/methods")
def methods():
    data = None
    for path in SUMMARY:
        try:
            data = json.loads(path.read_text())
            break
        except (OSError, ValueError):
            continue
    if data is None:
        return {"rows": []}
    rows = data.get("rows", data) if isinstance(data, dict) else data
    return {"rows": rows if isinstance(rows, list) else []}
