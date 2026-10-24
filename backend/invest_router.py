"""Invest dashboard API: plans (create / pause / resume / stop), the bets feed, real vs backtest profit.

Writes need the X-Dashboard-Pin header (DASHBOARD_PIN in .env.local). The trading loop runs only
where TRADER_ENABLED=1 — an always-on host, never the serverless deploy.
"""
import asyncio
import hmac
import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from invest.rules import plan_value
from invest.store import Store, now_iso

HERE = Path(__file__).parent
router = APIRouter()
store = Store()
PIN = os.environ.get("DASHBOARD_PIN")
_fails = {"n": 0, "until": 0.0}


def _broker_meta():
    try:
        from invest.broker import Broker
        return Broker.mode, float(Broker.ceiling)
    except Exception:  # integrations deps missing on this host: reads still work
        return "paper", float(os.environ.get("POLYMARKET_MAX_BET_USD") or 10)


def require_pin(pin):
    if not PIN:
        raise HTTPException(503, "DASHBOARD_PIN is not set on the server")
    if time.time() < _fails["until"]:
        raise HTTPException(429, "Too many wrong PINs; try again in 5 minutes")
    if not hmac.compare_digest(pin or "", PIN):
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
    budget: float = Field(gt=0, le=1_000_000)
    max_bet: float = Field(gt=0)
    daily_loss_stop: float = Field(gt=0)


@router.get("/api/plans")
def list_plans():
    mode, ceiling = _broker_meta()
    return {"mode": mode, "interval_min": 10, "max_bet_ceiling": ceiling,
            "plans": [summary(p) for p in sorted(store.plans(), key=lambda p: p["created_at"], reverse=True)]}


@router.post("/api/plans")
def create_plan(body: PlanIn, x_dashboard_pin: str | None = Header(default=None)):
    require_pin(x_dashboard_pin)
    _, ceiling = _broker_meta()
    if body.max_bet > ceiling:
        raise HTTPException(400, f"Max per bet can be at most ${ceiling:g} on this server")
    now = now_iso()
    plan = store.new_plan(body.budget, body.max_bet, body.daily_loss_stop, now)
    store.log(plan["id"], "start", now, budget=body.budget, max_bet=body.max_bet)
    return summary(plan)


@router.post("/api/plans/{plan_id}/{action}")
def control_plan(plan_id: str, action: str, x_dashboard_pin: str | None = Header(default=None)):
    require_pin(x_dashboard_pin)
    plan = store.plan(plan_id)
    if plan is None:
        raise HTTPException(404, "No such plan")
    if action not in ("pause", "resume", "stop"):
        raise HTTPException(404, "Unknown action")
    if plan["status"] == "stopped":
        raise HTTPException(400, "This plan is stopped; start a new one")
    if action == "resume":  # a person chose to carry on: today's loss stop counts from now
        plan.update(status="running", pause_reason=None, errors=0)
        plan["day"]["start_value"] = plan_value(plan)
    else:
        plan.update(status="paused" if action == "pause" else "stopped", pause_reason="by_person" if action == "pause" else None)
    store.save_plan(plan)
    store.log(plan_id, action, now_iso())
    return summary(plan)


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


def start_trader(app):
    """Run the 10-minute loop inside this process when TRADER_ENABLED=1."""
    if os.environ.get("TRADER_ENABLED") != "1":
        return

    async def _start():
        from invest.broker import Broker
        from invest.trader import loop
        asyncio.get_running_loop().create_task(loop(store, Broker()))

    app.add_event_handler("startup", _start)
