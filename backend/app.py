"""Horizon API. Serves the 3 contract endpoints (see CLAUDE.md, API contract v1).

Each endpoint returns backend/results/<name>.json when the model pipeline has
written it, otherwise the contract example from backend/examples/<name>.json,
so the frontend works before the model does.
"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

HERE = Path(__file__).parent
RESULTS = HERE / "results"
EXAMPLES = HERE / "examples"

app = FastAPI(title="Horizon API", version="1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


def load(name: str):
    for folder in (RESULTS, EXAMPLES):
        path = folder / f"{name}.json"
        if path.exists():
            return json.loads(path.read_text()), folder.name
    raise HTTPException(status_code=503, detail=f"{name} not available yet")


@app.get("/api/health")
def health():
    return {name: load(name)[1] for name in ("live", "calibration", "backtest")}


@app.get("/api/live")
def live():
    return load("live")[0]


@app.get("/api/calibration")
def calibration(domain: str = "all"):
    data, _ = load("calibration")
    # Real results are keyed by domain; the example is a single "all" payload.
    if "by_domain" in data:
        if domain not in data["by_domain"]:
            raise HTTPException(status_code=404, detail=f"unknown domain {domain}")
        return data["by_domain"][domain]
    return data


@app.get("/api/backtest")
def backtest():
    return load("backtest")[0]


@app.get("/api/model")
def model():
    """Fitted coefficients + bootstrap sets + decision constants, for computing q in the browser."""
    return load("model")[0]


@app.get("/api/capsule")
def capsule():
    """Sealed predictions: each seal's hash and counts, its opening once scored, and C's forward test."""
    return load("capsule")[0]
