"""Horizon agent: Gemini function-calling for the extension's plain-language command box.

Stateless. The panel owns the conversation (Gemini `contents`), executes every tool itself
(Gamma prices, the user's Horizon bets, page actions) and posts the results back; this endpoint
only adds the system rules + tool schemas and asks Gemini for the next step. No key -> 503, and
the panel falls back to its deterministic command parser.

Bet/sell tools only build a plan list. The panel sets up Polymarket's order ticket in the user's
tab for the top few and stops; the human presses Trade. Nothing here places an order.
"""
import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Current stable Flash per ai.google.dev/gemini-api/docs/models (Oct 2026); 2.5 kept as a fallback.
MODELS = [m for m in (os.environ.get("GEMINI_MODEL"), "gemini-3.8-flash", "gemini-2.5-flash") if m]

SYSTEM = """You are Horizon's agent inside a Chrome side panel next to Polymarket. You turn the user's request into a
plan of bets by calling tools; the panel executes them. Rules:
- place_bet, adjust_stake, close_position and close_all only ADD TO THE PLAN LIST. The panel then sets up
  Polymarket's order ticket (outcome + amount) in the user's tab for the top 2-3 items and stops: the user
  presses Trade. Never say a bet is placed; say it is set up or in the plan.
- Every bet goes through Horizon's model: place_bet refuses sides the model does not back and caps the
  amount at Horizon's suggested bet (a quarter of the Kelly stake, max 5% of the user's budget, at least $1).
  If the user names an amount, pass it as amount (up to their budget). Only pass override=true if the user
  explicitly asked to bet against the model.
- For several bets: call scan_markets, then place_bet for each pick, best first. Never invent prices or
  probabilities.
- End with ONE short plain sentence for a non-expert (say "good bet" or "price too low", not "edge" or
  "Kelly"). Never promise profit. Never use the word gamble."""

S, N, B = {"type": "string"}, {"type": "number"}, {"type": "boolean"}
SIDE = {"type": "string", "enum": ["YES", "NO"]}


def _fn(name, description, props=None, required=None):
    params = {"type": "object", "properties": props or {}}
    if required:
        params["required"] = required
    return {"name": name, "description": description, "parameters": params}


TOOLS = [{"functionDeclarations": [
    _fn("scan_markets", "Open yes/no Polymarket markets ending soon, ranked by Horizon's advantage after costs.",
        {"tag": {**S, "description": "Gamma tag slug: all, sports, politics, crypto, soccer, nba, nfl, tennis, esports..."},
         "within_hours": {**N, "description": "Only markets ending within this many hours (default 24)."},
         "top": {**N, "description": "How many to return (default 10, max 40)."}}),
    _fn("get_decision", "Horizon's call on one market (by market slug) or all legs of an event (by event slug).",
        {"slug": S}, ["slug"]),
    _fn("place_bet", "Add a bet to the plan: Horizon sets up the ticket on Polymarket and the human presses Trade. amount in dollars; omit to use the suggested bet.",
        {"market": {**S, "description": "market slug from scan_markets/get_decision"}, "side": SIDE, "amount": N,
         "override": {**B, "description": "true only if the user explicitly asked to exceed the suggestion"}},
        ["market", "side"]),
    _fn("adjust_stake", "Plan raising or lowering a bet placed through Horizon: new_amount in dollars, or factor (0.5 halves, 2 doubles). Lowering = selling part on Polymarket.",
        {"position": {**S, "description": "position id or market slug"}, "new_amount": N, "factor": N}, ["position"]),
    _fn("close_position", "Plan selling a whole bet placed through Horizon.", {"position": S}, ["position"]),
    _fn("close_all", "Plan selling several bets placed through Horizon.",
        {"filter": {"type": "string", "enum": ["all", "losing", "winning", "no_edge"],
                    "description": "no_edge = Horizon no longer backs the side"}}),
    _fn("open_market_in_tab", "Open a Polymarket event page in the user's tab.", {"slug": {**S, "description": "event slug"}}, ["slug"]),
    _fn("prepare_ticket_on_page", "Fill Polymarket's ticket in the user's tab (outcome + amount) without pressing Trade.",
        {"market": S, "side": SIDE, "amount": N}, ["market", "side"]),
    _fn("open_my_results", "Open the user's personal results page (decisions made with Horizon and how they turned out) in a new tab; returns a one-line summary if available. Use for 'show my stats', 'my results', 'how am I doing', 'am I up'."),
    _fn("set_bankroll", "Set the user's budget, which sizes suggested bets.", {"amount": N}, ["amount"]),
    _fn("summarize_portfolio", "Budget, bets the user placed after Horizon set them up, money in those bets, result so far."),
]}]


def _call(model: str, key: str, body: dict) -> dict:
    req = urllib.request.Request(API.format(model=model), data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read())


@router.get("/api/agent")
def agent_status():
    return {"llm": bool(os.environ.get("GEMINI_API_KEY")), "model": MODELS[0], "tools": [f["name"] for f in TOOLS[0]["functionDeclarations"]]}


@router.post("/api/agent")
async def agent_step(request: Request):
    """Body {contents: Gemini Content[], context?: str} -> {content: Content, finish: str, model: str}."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY not set; use the built-in command parser")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON body required")
    contents = payload.get("contents")
    if not isinstance(contents, list) or not contents or len(contents) > 120:
        raise HTTPException(status_code=400, detail="contents must be a non-empty list (max 120)")
    system = SYSTEM + (f"\nCurrent state: {str(payload['context'])[:2000]}" if payload.get("context") else "")
    body = {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents, "tools": TOOLS,
            "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}}, "generationConfig": {"temperature": 0.2}}
    last = ""
    for model in MODELS:
        try:
            out = _call(model, key, body)
        except urllib.error.HTTPError as e:
            last = f"{model}: HTTP {e.code} {e.read()[:300].decode(errors='replace')}"
            if e.code == 404:  # model name not served to this key: try the next one
                continue
            raise HTTPException(status_code=502, detail=last)
        except Exception as e:  # network / timeout
            raise HTTPException(status_code=502, detail=f"{model}: {e}")
        cand = (out.get("candidates") or [{}])[0]
        content = cand.get("content") or {"role": "model", "parts": [{"text": "(no answer)"}]}
        content.setdefault("role", "model")
        return {"content": content, "finish": cand.get("finishReason", ""), "model": model}
    raise HTTPException(status_code=502, detail=last or "no model available")
