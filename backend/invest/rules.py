"""Pure sizing and safety rules for invest plans (no network, no files)."""
from datetime import datetime, timedelta

MIN_STAKE_USD = 1.0
MARKET_SHARE = 0.05  # max share of a plan's budget in one market
EVENT_SHARE = 0.10   # max share in one event (its legs are correlated)
STALE_HOURS = 2
MAX_ERRORS = 3


def event_of(url):
    return url.rstrip("/").split("/")[-1]


def side_of(item):
    return "YES" if item["action"] == "BUY_YES" else "NO"


def p_win(item, side):
    """Chance this side wins, taken at the cautious end of the model's interval."""
    return item["q_low"] if side == "YES" else 1 - item["q_high"]


def plan_value(plan):
    held = sum(p["shares"] * (p.get("mark") or 0) for p in plan["positions"] if p["status"] == "open")
    return round(plan["cash"] + held, 2)


def size_bet(item, plan, value, ceiling):
    """Dollar stake for one live decision: ¼-Kelly of plan value, clipped by every limit. (0, reason) to skip."""
    side = side_of(item)
    held = [p for p in plan["positions"] if p["status"] == "open"]
    if any(p["market_id"] == item["market_id"] and p["side"] != side for p in held):
        return 0.0, "opposite_side_held"
    in_market = sum(p["cost"] for p in held if p["market_id"] == item["market_id"])
    in_event = sum(p["cost"] for p in held if p["event"] == event_of(item["url"]))
    room = min(plan["max_bet"], ceiling, plan["cash"],
               MARKET_SHARE * plan["budget"] - in_market, EVENT_SHARE * plan["budget"] - in_event)
    if room < MIN_STAKE_USD:
        return 0.0, "limit_reached"
    stake = min(item["kelly_fraction"] * value, room)
    if stake < MIN_STAKE_USD:
        return 0.0, "too_small"
    return round(stake, 2), None


def pause_reason(plan, value, updated_at, now):
    if plan["errors"] >= MAX_ERRORS:
        return "polymarket_errors"
    if updated_at is None or now - datetime.fromisoformat(updated_at.replace("Z", "+00:00")) > timedelta(hours=STALE_HOURS):
        return "stale_data"
    if plan["day"]["start_value"] - value > plan["daily_loss_stop"]:
        return "daily_loss"
    return None
