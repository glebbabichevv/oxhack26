"""Horizon agent: Gemini function-calling for the extension's plain-language command box.

Stateless. The panel owns the conversation (Gemini `contents`), executes every tool itself
(demo account, Gamma prices, page actions) and posts the results back; this endpoint only adds
the system rules + tool schemas and asks Gemini for the next step. No key -> 503, and the panel
falls back to its deterministic command parser.

Money is simulated (demo account on live Polymarket prices). The tools never place a real order.
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

SYSTEM = """You are Horizon's agent inside a Chrome side panel. You manage a DEMO account (simulated money)
priced on live Polymarket prices. You act only by calling tools; the panel executes them and shows each
step to the user. Rules:
- Every bet goes through Horizon's model: place_bet refuses sides the model does not back and caps the
  amount at Horizon's suggested bet (quarter Kelly, max 5% of balance). Only pass override=true if the
  user explicitly asked to exceed the suggestion or bet against the model in their own words.
- Respect the daily loss limit; if a tool says it is reached, stop placing bets and say so.
- For plans with several bets, call scan_markets first, then place_bet for each pick, then
  summarize_portfolio and report the expected profit and the chance of ending down it returns.
  Never promise profit. Never invent prices or probabilities: quote tool results only.
- prepare_ticket_on_page only fills Polymarket's order ticket for show; it never confirms a trade.
- Keep the final answer to 1-3 short plain sentences for a non-expert (say "advantage", not "edge";
  "suggested bet", not "Kelly"). This is play money; never use the word gamble."""

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
    _fn("place_bet", "Open a demo position at the live ask. amount in dollars; omit to use the suggested bet.",
        {"market": {**S, "description": "market slug from scan_markets/get_decision"}, "side": SIDE, "amount": N,
         "override": {**B, "description": "true only if the user explicitly asked to exceed the suggestion"}},
        ["market", "side"]),
    _fn("adjust_stake", "Raise or lower an open position: new_amount in dollars, or factor (0.5 halves, 2 doubles).",
        {"position": {**S, "description": "position id or market slug"}, "new_amount": N, "factor": N}, ["position"]),
    _fn("close_position", "Sell an open demo position at the live bid.", {"position": S}, ["position"]),
    _fn("close_all", "Close several positions.",
        {"filter": {"type": "string", "enum": ["all", "losing", "winning", "no_edge"],
                    "description": "no_edge = Horizon no longer backs the side"}}),
    _fn("open_market_in_tab", "Open a Polymarket event page in the user's tab.", {"slug": {**S, "description": "event slug"}}, ["slug"]),
    _fn("prepare_ticket_on_page", "Show the bet on Polymarket: select the leg and outcome, type the amount. Never confirms.",
        {"market": S, "side": SIDE, "amount": N}, ["market", "side"]),
    _fn("set_bankroll", "Reset the demo account to a new starting balance (closes everything).", {"amount": N}, ["amount"]),
    _fn("summarize_portfolio", "Balance, open bets, P&L, and for open bets the expected profit and chance of ending down."),
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
