"""Horizon API (see CLAUDE.md, API contract).

/api/live is computed on request from live Polymarket prices with results/model.json (live.py,
cached ~5 min per instance; the saved snapshot results/live.json only if Gamma fails). The other
endpoints serve backend/results/<name>.json, written by model.py / refit.py, stamped with
generated_at + model_version; backend/examples/<name>.json before the pipeline has run.
"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import horizon_mcp
import live as live_feed

HERE = Path(__file__).parent
RESULTS = HERE / "results"
EXAMPLES = HERE / "examples"

app = FastAPI(title="Horizon API", version="1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


def load(name: str):
    for folder in (RESULTS, EXAMPLES):
        path = folder / f"{name}.json"
        if path.exists():
            return json.loads(path.read_text()), folder.name
    raise HTTPException(status_code=503, detail=f"{name} not available yet")


@app.get("/api/health")
def health():
    out = {name: load(name)[1] for name in ("calibration", "backtest")}
    return {**out, "live": "computed on request", "model_version": horizon_mcp.model_version()}


@app.get("/api/live")
def live(response: Response):
    payload = live_feed.get_live()
    # Let Vercel's CDN share one fetch across visitors for a minute; each instance also caches ~5 min.
    response.headers["Cache-Control"] = "public, s-maxage=60, stale-while-revalidate=240"
    return payload


@app.get("/api/calibration")
def calibration(domain: str = "all"):
    data, _ = load("calibration")
    # Real results are keyed by domain; the example is a single "all" payload.
    if "by_domain" in data:
        if domain not in data["by_domain"]:
            raise HTTPException(status_code=404, detail=f"unknown domain {domain}")
        meta = {k: data.get(k) for k in ("generated_at", "model_version", "cutoff")}
        return {**meta, **data["by_domain"][domain]}
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


# MCP server for browser agents (Argos): stateless Streamable HTTP, JSON responses, no sessions.
@app.post("/mcp")
@app.post("/api/mcp")
async def mcp(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, status_code=400)
    status, payload = horizon_mcp.handle_body(body)
    if payload is None:
        return Response(status_code=status)
    return JSONResponse(payload, status_code=status)


@app.get("/mcp")
@app.get("/api/mcp")
@app.delete("/mcp")
@app.delete("/api/mcp")
def mcp_no_stream():
    """No server-initiated SSE stream and no sessions; the MCP client treats 405 as 'not offered'."""
    return Response(status_code=405, headers={"Allow": "POST"})


# Agent for the extension command box (Gemini function-calling; 503 without GEMINI_API_KEY).
from agent_router import router as agent_router; app.include_router(agent_router)  # noqa: E402

# Decision Journal: POST/GET /api/journal (journal.py; Vercel Blob when BLOB_READ_WRITE_TOKEN is set).
from journal import router as journal_router; app.include_router(journal_router)  # noqa: E402
