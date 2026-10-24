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
    """Never raises: each position's failure is counted and logged on its own."""
    failed = False
    for p in plan["positions"]:
        if p["status"] != "open":
            continue
        try:
            mark, outcome = broker.mark(broker.market(p["market_id"]), p["side"])
            if outcome is None:
                p["mark"] = mark if mark is not None else p["mark"]
                continue
            payout = round(p["shares"] * outcome, 4)
            plan["cash"] = round(plan["cash"] + payout, 4)
            p.update(status="won" if outcome else "lost", payout=payout, mark=float(outcome))
            store.log(plan["id"], "settle", _iso(now), question=p["question"], side=p["side"], outcome=outcome,
                      cost=p["cost"], payout=payout, pnl=round(payout - p["cost"], 4), url=p["url"])
        except Exception as e:
            failed = True
            plan["errors"] += 1
            store.log(plan["id"], "error", _iso(now), text=f"settling: {str(e)[:300]}",
                      question=p["question"], side=p["side"], url=p["url"])
    if not failed:  # a clean settle pass ends any run of errors
        plan["errors"] = 0


def buy_round(store, broker, plan, live, now, value, room):
    """Returns the stake spent, so the caller can shrink the shared exposure room."""
    spent = 0.0
    picks = sorted((i for i in live["markets"] if i["action"] != "NO_TRADE" and i["net_edge"] > 0),
                   key=lambda i: -i["net_edge"])
    for item in picks:
        if plan["errors"] >= MAX_ERRORS:
            break
        current = store.plan(plan["id"])  # a Stop or Pause from the person wins over this round
        if current is None or current["status"] != "running":
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
        except Exception as e:  # quote/network errors count towards the auto-pause
            plan["errors"] += 1
            store.log(plan["id"], "error", _iso(now), text=str(e)[:300], **base)
            continue
        try:
            fill = broker.buy(m, side, q["fillable_usd"], q["worst_price"], note=f"plan {plan['id']}")
        except Exception as e:  # money may already have left: stop and check by hand
            plan["errors"] += 1
            plan.update(status="paused", pause_reason="check_fill")
            store.log(plan["id"], "error", _iso(now), text=str(e)[:300], possible_fill=True, **base)
            store.log(plan["id"], "pause", _iso(now), reason="check_fill")
            break
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
        status_at_start = plan["status"]
        settle_and_mark(store, broker, plan, now)
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

        def merge(stored):
            # the person changed status mid-cycle: their status and pause reason win; everything else is ours
            if stored["status"] != status_at_start:
                status = {"status": stored["status"], "pause_reason": stored.get("pause_reason")}
            else:
                status = {"status": plan["status"], "pause_reason": plan.get("pause_reason")}
            stored.update({k: v for k, v in plan.items() if k not in ("status", "pause_reason")})
            stored.update(status)

        store.update_plan(plan["id"], merge)
    plans = store.plans()
    store.add_equity(_iso(now), round(sum(p["budget"] for p in plans), 2), round(sum(plan_value(p) for p in plans), 2))


def _read_lock(path):
    """(pid, timestamp) from a lock file, or None if it is missing or malformed."""
    try:
        pid, ts = Path(path).read_text().split()[:2]
        return int(pid), float(ts)
    except (OSError, ValueError):
        return None


def acquire_lock(path, now, stale_s=1800):
    """One trader per data folder. Creating the file is atomic (O_EXCL); a missing, malformed or
    stale lock may be taken over."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        held = _read_lock(path)
        if held is not None and now - held[1] < stale_s:
            return False
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(f"{os.getpid()} {now}")
        os.replace(tmp, path)
        return True
    with os.fdopen(fd, "w") as f:
        f.write(f"{os.getpid()} {now}")
    return True


def release_lock(path):
    """Remove the lock only if this process holds it."""
    held = _read_lock(path)
    if held and held[0] == os.getpid():
        try:
            Path(path).unlink()
        except OSError:
            pass


def run_once(store, broker):
    import live as live_feed  # backend/live.py: the same decisions /api/live serves
    total_cap = float(os.environ.get("MAX_TOTAL_EXPOSURE_USD") or 200)
    run_cycle(store, broker, live_feed.get_live(), datetime.now(timezone.utc), total_cap)


async def loop(store, broker, interval_s=INTERVAL_S):
    lock, me = store.dir / "trader.lock", os.getpid()
    try:
        while True:
            held = _read_lock(lock)
            if (held and held[0] == me) or acquire_lock(lock, time.time()):
                lock.write_text(f"{me} {time.time()}")  # heartbeat: another process may take over after 30 min of silence
                try:
                    await asyncio.to_thread(run_once, store, broker)
                except Exception as e:
                    store.log(None, "error", _iso(datetime.now(timezone.utc)), text=f"cycle failed: {str(e)[:300]}")
            await asyncio.sleep(interval_s)
    finally:
        release_lock(lock)
