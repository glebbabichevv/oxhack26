"""Invest dashboard API: plans (create / pause / resume / stop), the bets feed, real vs backtest profit.

Writes need the X-Dashboard-Pin header (DASHBOARD_PIN in .env.local). The trading loop runs only
where TRADER_ENABLED=1 — an always-on host, never the serverless deploy.
"""
import asyncio
import hmac
import json
import os
import sys
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from invest.rules import plan_value
from invest.store import Store, now_iso

try:  # local runs: DASHBOARD_PIN lives in the repo's .env.local, which polymarket_trading loads
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrations"))
    from polymarket_trading import load_env
    load_env()
except Exception:
    pass

HERE = Path(__file__).parent


class _StrictJSONRoute(APIRoute):
    """Validation errors echo the bad input back, and Infinity cannot be sent as strict JSON: drop the echo."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def wrapped(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                errors = [{k: v for k, v in e.items() if k not in ("input", "ctx")} for e in exc.errors()]
                return JSONResponse({"detail": errors}, status_code=422)

        return wrapped


router = APIRouter(route_class=_StrictJSONRoute)
store = Store()
_fails = {"n": 0, "until": 0.0}
_fails_lock = threading.Lock()


def _broker_meta():
    try:
        from invest.broker import Broker
        return Broker.mode, float(Broker.ceiling)
    except Exception:  # integrations deps missing on this host: reads still work
        return "paper", float(os.environ.get("POLYMARKET_MAX_BET_USD") or 10)


def require_trader_host():
    if os.environ.get("TRADER_ENABLED") != "1":
        raise HTTPException(503, "This server does not run the trader; use the trading host")


def require_pin(pin):
    expected = os.environ.get("DASHBOARD_PIN")
    if not expected:
        raise HTTPException(503, "DASHBOARD_PIN is not set on the server")
    with _fails_lock:
        if time.time() < _fails["until"]:
            raise HTTPException(429, "Too many wrong PINs; try again in 5 minutes")
        if not hmac.compare_digest((pin or "").encode(), expected.encode()):
            _fails["n"] += 1
            if _fails["n"] >= 3:
                _fails.update(n=0, until=time.time() + 300)
            raise HTTPException(401, "Wrong PIN")
        _fails["n"] = 0


def summary(plan):
    value = plan_value(plan)
    profit = round(value - plan["budget"], 2)
    keys = ("id", "status", "pause_reason", "budget", "max_bet", "daily_loss_stop", "cash", "last_check", "created_at")
    return {**{k: plan[k] for k in keys}, "value": value, "profit": profit,
            "profit_pct": round(profit / plan["budget"], 4),
            "open_bets": sum(p["status"] == "open" for p in plan["positions"])}


class PlanIn(BaseModel):
    budget: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    max_bet: float = Field(gt=0, allow_inf_nan=False)
    daily_loss_stop: float = Field(gt=0, allow_inf_nan=False)


@router.get("/api/plans")
def list_plans():
    mode, ceiling = _broker_meta()
    return {"mode": mode, "interval_min": 10, "max_bet_ceiling": ceiling,
            "plans": [summary(p) for p in sorted(store.plans(), key=lambda p: p["created_at"], reverse=True)]}


@router.post("/api/plans")
def create_plan(body: PlanIn, x_dashboard_pin: str | None = Header(default=None)):
    require_trader_host()
    require_pin(x_dashboard_pin)
    _, ceiling = _broker_meta()
    if body.max_bet > ceiling:
        raise HTTPException(400, f"Max per bet can be at most ${ceiling:g} on this server")
    if body.max_bet > body.budget:
        raise HTTPException(400, "Max per bet can't be more than the budget")
    if body.daily_loss_stop > body.budget:
        raise HTTPException(400, "The daily loss stop can't be more than the budget")
    now = now_iso()
    plan = store.new_plan(body.budget, body.max_bet, body.daily_loss_stop, now)
    store.log(plan["id"], "start", now, budget=body.budget, max_bet=body.max_bet)
    return summary(plan)


@router.post("/api/plans/{plan_id}/{action}")
def control_plan(plan_id: str, action: str, x_dashboard_pin: str | None = Header(default=None)):
    require_trader_host()
    require_pin(x_dashboard_pin)
    if action not in ("pause", "resume", "stop"):
        raise HTTPException(404, "Unknown action")
    logged = {}

    def change(plan):
        if plan["status"] == "stopped":
            raise HTTPException(400, "This plan is stopped; start a new one")
        if action == "resume":  # only a paused plan; a person chose to carry on, so today's loss stop counts from now
            if plan["status"] != "paused":
                raise HTTPException(400, "Only a paused plan can be resumed")
            logged["prev_reason"] = plan.get("pause_reason")
            plan.update(status="running", pause_reason=None, errors=0)
            plan["day"]["start_value"] = plan_value(plan)
        elif action == "pause":  # never overwrites an auto-pause reason such as check_fill
            if plan["status"] != "running":
                raise HTTPException(400, "This plan is not running")
            plan.update(status="paused", pause_reason="by_person")
            logged["reason"] = "by_person"
        else:
            plan.update(status="stopped", pause_reason=None)

    updated = store.update_plan(plan_id, change)
    if updated is None:
        raise HTTPException(404, "No such plan")
    store.log(plan_id, action, now_iso(), **logged)
    return summary(updated)


@router.get("/api/orders")
def orders(plan: str | None = None, limit: int = 50):
    return store.events(plan, min(limit, 500))


def _backtest_equity():
    for folder in (HERE / "results", HERE / "examples"):
        path = folder / "backtest.json"
        if path.exists():
            return json.loads(path.read_text())["with_costs"]["equity"]
    return []


@router.get("/api/pnl")
def pnl():
    budget = sum(p["budget"] for p in store.plans()) or 1000.0
    real = [{"t": e["t"], "value": round(e["value"] - e["invested"], 2)} for e in store.equity()]
    # Backtest equity is in starting-bankroll units from 1.0; show it as $ profit on the same budget.
    backtest = [{"t": e["t"], "value": round((e["value"] - 1) * budget, 2)} for e in _backtest_equity()]
    return {"real": real, "backtest": backtest, "backtest_budget": budget}


def _on_trader_done(task):
    if task.cancelled():
        why = "cancelled"
    elif task.exception() is not None:
        why = str(task.exception()) or type(task.exception()).__name__
    else:
        why = "ended"
    store.log(None, "error", now_iso(), text=f"trader loop stopped: {why}"[:300])


def start_trader(app):
    """Run the 10-minute loop inside this process when TRADER_ENABLED=1."""
    if os.environ.get("TRADER_ENABLED") != "1":
        return

    async def _start():
        from invest.broker import Broker
        from invest.trader import loop
        task = asyncio.get_running_loop().create_task(loop(store, Broker()))
        app.state.trader_task = task  # keep a reference; the done callback records how it ended
        task.add_done_callback(_on_trader_done)

    app.add_event_handler("startup", _start)
