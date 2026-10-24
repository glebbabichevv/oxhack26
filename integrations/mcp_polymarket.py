"""Polymarket MCP server: lets any agent (Claude Code, Delta) search, read and bet on Polymarket.

Market data uses public APIs, no keys. Betting is paper by default (see polymarket_trading.py). Zero extra dependencies (stdio JSON-RPC by hand, `requests`
for HTTP), so it runs on every teammate's machine without installing the MCP SDK.
Registered for this repo in .mcp.json; to run by hand:  python integrations/mcp_polymarket.py

Tools: search_markets, get_market, list_live_markets, get_order_book, get_price_history,
price_at_horizon. Prices are P(YES) in [0, 1]; times are UTC ISO; hours_to_resolution is
measured to the scheduled endDate, the same clock as data/horizons.csv and data/live.csv.
"""
import json
import sys
import traceback
from datetime import datetime, timedelta, timezone

import polymarket_trading as trading
from common import CLOB, GAMMA, domain_of, get, is_yes_no, parse_ts, tag_slugs

SERVER = {"name": "polymarket", "version": "1.0.0"}


def fetch(url, params=None):
    return get(url, params, tries=3)  # an agent is waiting: fail fast instead of 8 long retries


def now():
    return datetime.now(timezone.utc)


def summarise(m):
    """One Gamma market -> the fields an agent needs to reason about it."""
    end = parse_ts(m.get("endDate"))
    bid, ask = m.get("bestBid"), m.get("bestAsk")
    mid = round((float(bid) + float(ask)) / 2, 4) if bid is not None and ask is not None else None
    try:
        outcomes, prices = json.loads(m.get("outcomes") or "[]"), json.loads(m.get("outcomePrices") or "[]")
        tokens = json.loads(m.get("clobTokenIds") or "[]")
    except ValueError:
        outcomes, prices, tokens = [], [], []
    event = (m.get("events") or [{}])[0]
    return dict(
        market_id=m.get("conditionId"), gamma_id=m.get("id"), slug=m.get("slug"), question=m.get("question"),
        domain=domain_of(tag_slugs(m)), binary_yes_no=is_yes_no(m),
        outcomes=dict(zip(outcomes, [float(p) for p in prices])),
        price_yes=mid if mid is not None else (float(prices[0]) if prices else None),
        best_bid=bid, best_ask=ask, spread=round(float(ask) - float(bid), 4) if mid is not None else None,
        last_trade=m.get("lastTradePrice"), volume_usd=round(float(m.get("volumeNum") or 0), 2),
        liquidity_usd=round(float(m.get("liquidityNum") or 0), 2),
        end_date=end.isoformat() if end else None,
        hours_to_resolution=round((end - now()).total_seconds() / 3600, 1) if end else None,
        closed=m.get("closed"), accepting_orders=m.get("acceptingOrders"), neg_risk=m.get("negRisk"),
        token_ids=dict(zip(outcomes, tokens)),
        url=f"https://polymarket.com/event/{event.get('slug') or m.get('slug')}",
    )


def find_market(market):
    """Accepts a condition id (0x...), a numeric Gamma id, a slug, or a polymarket.com URL."""
    market = market.strip().rstrip("/")
    if "polymarket.com" in market:
        market = market.split("?")[0].split("/")[-1]
    if market.startswith("0x"):
        q = {"condition_ids": market, "include_tag": "true"}
        found = fetch(f"{GAMMA}/markets", q) or fetch(f"{GAMMA}/markets", {**q, "closed": "true"})
    elif market.isdigit():
        found = [fetch(f"{GAMMA}/markets/{market}", {"include_tag": "true"})]
    else:
        try:
            found = [fetch(f"{GAMMA}/markets/slug/{market}", {"include_tag": "true"})]
        except Exception:  # an event slug from a URL: return its first market
            events = fetch(f"{GAMMA}/events", {"slug": market})
            found = events[0]["markets"][:1] if events and events[0].get("markets") else []
    if not found:
        raise ValueError(f"no market found for {market!r}")
    return found[0]


def yes_token_of(market):
    m = summarise(find_market(market))
    token = next(iter(m["token_ids"].values()), None)
    if not token:
        raise ValueError("market has no CLOB token ids")
    return m, token


# ---- tools -------------------------------------------------------------------------------

def search_markets(query, include_closed=False, limit=10):
    res = fetch(f"{GAMMA}/public-search", {"q": query, "limit_per_type": 20,
                                           "events_status": "all" if include_closed else "active"})
    out = []
    for e in res.get("events") or []:
        for m in e.get("markets") or []:
            if not include_closed and m.get("closed"):
                continue
            m.setdefault("events", [{"slug": e.get("slug"), "tags": e.get("tags")}])
            s = summarise(m)
            s["event_title"] = e.get("title")
            out.append(s)
    out.sort(key=lambda s: -s["volume_usd"])
    return out[:limit]


def get_market(market):
    return summarise(find_market(market))


def list_live_markets(min_volume=50000, max_days=45, domain=None, limit=30):
    t = now()
    rows, offset = [], 0
    while offset < 2000:
        page = fetch(f"{GAMMA}/markets", dict(
            closed="false", active="true", limit=100, offset=offset, volume_num_min=min_volume,
            end_date_min=t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_date_max=(t + timedelta(days=max_days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            order="endDate", ascending="true", include_tag="true"))
        for m in page:
            s = summarise(m)
            if s["binary_yes_no"] and s["accepting_orders"] and s["spread"] is not None \
                    and (not domain or s["domain"] == domain):
                rows.append(s)
        offset += 100
        if len(page) < 100:
            break
    rows.sort(key=lambda s: -s["volume_usd"])
    return {"count": len(rows), "markets": rows[:limit]}


def get_order_book(market, depth=10):
    m, token = yes_token_of(market)
    b = fetch(f"{CLOB}/book", {"token_id": token})
    bids = sorted(b.get("bids") or [], key=lambda x: -float(x["price"]))[:depth]
    asks = sorted(b.get("asks") or [], key=lambda x: float(x["price"]))[:depth]
    return dict(market_id=m["market_id"], question=m["question"], side="YES", bids=bids, asks=asks,
                tick_size=b.get("tick_size"), min_order_size=b.get("min_order_size"),
                last_trade_price=b.get("last_trade_price"))


def get_price_history(market, days=7, fidelity_minutes=60, end=None):
    m, token = yes_token_of(market)
    stop = parse_ts(end) if end else now()
    start = stop - timedelta(days=days)
    pts, chunk = [], start
    while chunk < stop:  # closed markets return nothing for interval=max: ask in 15-day chunks
        nxt = min(chunk + timedelta(days=15), stop)
        h = fetch(f"{CLOB}/prices-history", {"market": token, "startTs": int(chunk.timestamp()),
                                             "endTs": int(nxt.timestamp()), "fidelity": fidelity_minutes})
        pts += h.get("history") or []
        chunk = nxt
    pts = sorted({p["t"]: p for p in pts}.values(), key=lambda p: p["t"])
    return dict(market_id=m["market_id"], question=m["question"], side="YES", n=len(pts),
                history=[{"t": datetime.fromtimestamp(p["t"], timezone.utc).isoformat(), "p": p["p"]} for p in pts])


def price_at_horizon(market, horizons_hours=(720, 168, 72, 24, 12), max_stale_hours=6):
    """YES price N hours before the scheduled endDate, using only prints at or before that time."""
    raw = find_market(market)
    m = summarise(raw)
    end = parse_ts(raw.get("endDate"))
    closed_at = parse_ts(raw.get("closedTime"))
    token = next(iter(m["token_ids"].values()), None)
    if not end or not token:
        raise ValueError("market has no end date or token")
    longest = max(horizons_hours)
    hist = get_price_history(market, days=longest / 24 + 1, fidelity_minutes=60, end=end.isoformat())["history"]
    pts = [(parse_ts(p["t"]), p["p"]) for p in hist]
    out = []
    for h in sorted(horizons_hours, reverse=True):
        target = end - timedelta(hours=h)
        before = [(t, p) for t, p in pts if t <= target]
        row = {"horizon_hours": h, "target_time": target.isoformat(), "price_yes": None}
        if closed_at and closed_at <= target:
            row["note"] = "market already closed at this horizon"
        elif target > now():
            row["note"] = "in the future"
        elif not before or (target - before[-1][0]) > timedelta(hours=max_stale_hours):
            row["note"] = f"no print within {max_stale_hours}h before target"
        else:
            row["price_yes"], row["price_time"] = before[-1][1], before[-1][0].isoformat()
        out.append(row)
    return dict(market_id=m["market_id"], question=m["question"], end_date=m["end_date"],
                closed=m["closed"], final_outcomes=m["outcomes"] if m["closed"] else None, horizons=out)


def place_bet(market, side, amount_usd, limit_price=None, confirm=False, note=""):
    return trading.place_bet(get_market(market), side, amount_usd, limit_price, confirm, note)


def get_positions():
    return trading.positions(get_market)


MARKET_ARG = {"type": "string", "description": "Condition id (0x...), Gamma id, market slug, or polymarket.com URL"}
TOOLS = {
    "search_markets": (search_markets, "Full-text search Polymarket. Returns markets with price, spread, volume, "
                       "domain, end date and hours to resolution, biggest volume first.", {
        "query": {"type": "string"},
        "include_closed": {"type": "boolean", "default": False},
        "limit": {"type": "integer", "default": 10}}, ["query"]),
    "get_market": (get_market, "Current snapshot of one market: midpoint P(YES), bid/ask/spread, volume, "
                   "liquidity, end date, hours to resolution, domain, token ids.", {"market": MARKET_ARG}, ["market"]),
    "list_live_markets": (list_live_markets, "Open binary YES/NO markets that are accepting orders and resolve "
                          "within max_days, filtered by min volume and optional domain "
                          "(sports, crypto, politics, economics, culture, science_tech, geopolitics, other).", {
        "min_volume": {"type": "number", "default": 50000},
        "max_days": {"type": "number", "default": 45},
        "domain": {"type": "string"},
        "limit": {"type": "integer", "default": 30}}, []),
    "get_order_book": (get_order_book, "Live CLOB order book for the YES token (best levels first).", {
        "market": MARKET_ARG, "depth": {"type": "integer", "default": 10}}, ["market"]),
    "get_price_history": (get_price_history, "YES price history from the CLOB, ending at `end` (ISO, default now).", {
        "market": MARKET_ARG, "days": {"type": "number", "default": 7},
        "fidelity_minutes": {"type": "integer", "default": 60},
        "end": {"type": "string", "description": "ISO timestamp, default now"}}, ["market"]),
    "price_at_horizon": (price_at_horizon, "YES price at fixed horizons before the scheduled end date, using only "
                         "prices at or before each target (no look-ahead) - the same rule as data/horizons.csv. "
                         "Includes the final outcome for closed markets.", {
        "market": MARKET_ARG,
        "horizons_hours": {"type": "array", "items": {"type": "number"}, "default": [720, 168, 72, 24, 12]},
        "max_stale_hours": {"type": "number", "default": 6}}, ["market"]),
    "place_bet": (place_bet, f"Buy YES or NO shares with amount_usd. Mode now: {trading.mode()} "
                  "(paper = simulated fill against the live order book, logged; live = real USDC order). "
                  "Without confirm it only returns a quote (avg price, slippage, payout); call again with "
                  "confirm=true to execute. Never fills above the quoted worst price or limit_price.", {
        "market": MARKET_ARG, "side": {"type": "string", "enum": ["YES", "NO"]},
        "amount_usd": {"type": "number"},
        "limit_price": {"type": "number", "description": "Max price per share (0-1) you will pay"},
        "confirm": {"type": "boolean", "default": False},
        "note": {"type": "string", "description": "Why: model q, edge, Kelly size"}}, ["market", "side", "amount_usd"]),
    "get_positions": (get_positions, "All bets with cost, mark-to-market value and P&L (paper: settled at the "
                      "real outcome once a market resolves; live: USDC balance, open orders, trades).", {}, []),
    "cancel_order": (trading.cancel_order, "Live mode only: cancel one open order by id, or all.", {
        "order_id": {"type": "string"}, "all_orders": {"type": "boolean", "default": False}}, []),
}


# ---- MCP over stdio (newline-delimited JSON-RPC 2.0) -------------------------------------

def handle(msg):
    method, params = msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {}}, "serverInfo": SERVER,
                "instructions": f"Live Polymarket data and betting (mode: {trading.mode()}). price_yes is "
                                "P(YES); costs = spread. Always quote a bet and show it to the user before "
                                "calling place_bet with confirm=true."}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": [{"name": n, "description": d,
                           "annotations": {"readOnlyHint": n not in ("place_bet", "cancel_order")},
                           "inputSchema": {"type": "object", "properties": p, "required": r}}
                          for n, (_, d, p, r) in TOOLS.items()]}
    if method == "tools/call":
        name = params.get("name")
        if name not in TOOLS:
            raise KeyError(f"unknown tool {name}")
        try:
            result = TOOLS[name][0](**(params.get("arguments") or {}))
            return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}
        except Exception as e:  # tool errors go back to the agent, not as protocol errors
            traceback.print_exc(file=sys.stderr)
            return {"content": [{"type": "text", "text": f"error: {e}"}], "isError": True}
    raise KeyError(f"method not found: {method}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    for line in sys.stdin:
        if not line.strip():
            continue
        msg = json.loads(line)
        if "id" not in msg:
            continue  # notifications (initialized, cancelled) need no reply
        try:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "result": handle(msg)}
        except KeyError as e:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": str(e)}}
        except Exception as e:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32603, "message": str(e)}}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
