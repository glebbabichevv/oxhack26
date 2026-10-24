# backend/invest/trader.py
"""The auto-buyer: every 10 minutes, settle and mark each plan's bets, check its safety stops,
then buy the best live edges inside its limits. Paper or live is the broker's business."""
import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .rules import MAX_ERRORS, event_of, p_win, pause_reason, plan_value, side_of, size_bet

INTERVAL_S = 600


def _iso(now):
    return now.isoformat(timespec="seconds")


def settle_and_mark(store, broker, plan, now):
    for p in plan["positions"]:
        if p["status"] != "open":
            continue
        mark, outcome = broker.mark(broker.market(p["market_id"]), p["side"])
        if outcome is None:
            p["mark"] = mark if mark is not None else p["mark"]
            continue
        payout = round(p["shares"] * outcome, 4)
        plan["cash"] = round(plan["cash"] + payout, 4)
        p.update(status="won" if outcome else "lost", payout=payout, mark=float(outcome))
        store.log(plan["id"], "settle", _iso(now), question=p["question"], side=p["side"], outcome=outcome,
                  cost=p["cost"], payout=payout, pnl=round(payout - p["cost"], 4), url=p["url"])


def buy_round(store, broker, plan, live, now, value, room):
    """Returns the stake spent, so the caller can shrink the shared exposure room."""
    spent = 0.0
    picks = sorted((i for i in live["markets"] if i["action"] != "NO_TRADE" and i["net_edge"] > 0),
                   key=lambda i: -i["net_edge"])
    for item in picks:
        if plan["errors"] >= MAX_ERRORS:
            break
        stake, _ = size_bet(item, plan, value, min(broker.ceiling, room - spent))
        if not stake:
            continue
        side = side_of(item)
        base = dict(question=item["question"], side=side, url=item["url"])
        try:
            m = broker.market(item["market_id"])
            q = broker.quote(m, side, stake)
            if not q["shares"]:
                store.log(plan["id"], "skip", _iso(now), reason="no_liquidity", **base)
                continue
            if q.get("min_order_size") and q["shares"] < float(q["min_order_size"]):
                store.log(plan["id"], "skip", _iso(now), reason="below_minimum", **base)
                continue
            if p_win(item, side) - q["avg_price"] - (item.get("fee") or 0) <= 0:
                store.log(plan["id"], "skip", _iso(now), reason="edge_vanished", price=q["avg_price"], **base)
                continue
            fill = broker.buy(m, side, q["fillable_usd"], q["worst_price"], note=f"plan {plan['id']}")
        except Exception as e:  # network / order errors count towards the auto-pause
            plan["errors"] += 1
            store.log(plan["id"], "error", _iso(now), text=str(e)[:300], **base)
            continue
        plan["errors"] = 0
        plan["cash"] = round(plan["cash"] - fill["cost"], 4)
        spent += fill["cost"]
        p_model = item["q_yes"] if side == "YES" else 1 - item["q_yes"]
        plan["positions"].append(dict(
            market_id=item["market_id"], event=event_of(item["url"]), question=item["question"], side=side,
            shares=fill["shares"], cost=fill["cost"], avg_price=fill["avg_price"], p_model=round(p_model, 4),
            bought_at=_iso(now), end_hours=item["hours_to_resolution"], url=item["url"],
            status="open", mark=fill["avg_price"], payout=None))
        store.log(plan["id"], "buy", _iso(now), cost=fill["cost"], shares=fill["shares"], price=fill["avg_price"],
                  p_model=round(p_model, 4), hours_to_resolution=item["hours_to_resolution"], **base)
    return spent


def run_cycle(store, broker, live, now, total_cap):
    plans = store.plans()
    open_stake = sum(p["cost"] for pl in plans for p in pl["positions"] if p["status"] == "open")
    room = max(total_cap - open_stake, 0.0)
    for plan in plans:
        try:
            settle_and_mark(store, broker, plan, now)
        except Exception as e:
            plan["errors"] += 1
            store.log(plan["id"], "error", _iso(now), text=f"settling: {str(e)[:300]}")
        value = plan_value(plan)
        today = now.date().isoformat()
        if plan["day"]["date"] != today:
            plan["day"] = {"date": today, "start_value": value}
        if plan["status"] == "running":
            reason = pause_reason(plan, value, live.get("updated_at"), now)
            if reason:
                plan.update(status="paused", pause_reason=reason)
                store.log(plan["id"], "pause", _iso(now), reason=reason)
            else:
                room -= buy_round(store, broker, plan, live, now, value, room)
                if plan["errors"] >= MAX_ERRORS:
                    plan.update(status="paused", pause_reason="polymarket_errors")
                    store.log(plan["id"], "pause", _iso(now), reason="polymarket_errors")
        plan["last_check"] = _iso(now)
        store.save_plan(plan)
    plans = store.plans()
    store.add_equity(_iso(now), round(sum(p["budget"] for p in plans), 2), round(sum(plan_value(p) for p in plans), 2))


def acquire_lock(path, now, stale_s=1800):
    """One trader per data folder: take the lock if it is missing or its heartbeat is stale."""
    path = Path(path)
    if path.exists() and now - float(path.read_text().split()[1]) < stale_s:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{os.getpid()} {now}")
    return True


def run_once(store, broker):
    import live as live_feed  # backend/live.py: the same decisions /api/live serves
    total_cap = float(os.environ.get("MAX_TOTAL_EXPOSURE_USD") or 200)
    run_cycle(store, broker, live_feed.get_live(), datetime.now(timezone.utc), total_cap)


async def loop(store, broker, interval_s=INTERVAL_S):
    lock, me = store.dir / "trader.lock", str(os.getpid())
    while True:
        mine = lock.exists() and lock.read_text().split()[0] == me
        if mine or acquire_lock(lock, time.time()):
            lock.write_text(f"{me} {time.time()}")  # heartbeat: another process may take over after 30 min of silence
            try:
                await asyncio.to_thread(run_once, store, broker)
            except Exception as e:
                store.log(None, "error", _iso(datetime.now(timezone.utc)), text=f"cycle failed: {str(e)[:300]}")
        await asyncio.sleep(interval_s)
