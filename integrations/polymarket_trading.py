"""Betting tools for the Polymarket MCP server: quote, place, list positions, cancel.

Two modes, chosen by env (.env.local at the repo root):
- paper (default): fills are simulated against the *live* order book (walk the asks, pay the
  spread and slippage) and logged to data/raw/paper_bets.json. Positions are marked to the live
  bid and settled at the real outcome, so the ledger is an honest forward test.
- live: POLYMARKET_LIVE=1 plus POLYMARKET_PRIVATE_KEY. Orders are signed with py-clob-client and
  sent to the Polymarket CLOB as fill-and-kill orders capped at the quoted worst price.
  Every live order is capped at POLYMARKET_MAX_BET_USD (default 10).

Every bet is two calls: place_bet without confirm returns a quote; the same call with
confirm=true executes it, never above the quoted worst price.
"""
import json
import os
import uuid
from datetime import datetime, timezone

from common import CLOB, DATA, ROOT, get, parse_ts

LEDGER = DATA / "raw" / "paper_bets.json"


def load_env():
    path = ROOT / ".env.local"
    if path.exists():
        for line in path.read_text().splitlines():
            k, sep, v = line.partition("=")
            if sep and not line.lstrip().startswith("#"):
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


load_env()
LIVE = os.environ.get("POLYMARKET_LIVE") == "1"
MAX_BET_USD = float(os.environ.get("POLYMARKET_MAX_BET_USD") or 10)
_client = None


def mode():
    return "live" if LIVE else "paper"


def client():
    """Authenticated CLOB client, created once. Only needed in live mode."""
    global _client
    if _client is None:
        from py_clob_client.client import ClobClient
        key = os.environ.get("POLYMARKET_PRIVATE_KEY")
        if not key:
            raise RuntimeError("live mode needs POLYMARKET_PRIVATE_KEY in .env.local")
        sig = int(os.environ.get("POLYMARKET_SIGNATURE_TYPE") or 0)
        funder = os.environ.get("POLYMARKET_FUNDER") or None
        c = ClobClient(CLOB, chain_id=137, key=key, signature_type=sig, funder=funder)
        c.set_api_creds(c.create_or_derive_api_creds())
        _client = c
    return _client


def now():
    return datetime.now(timezone.utc)


def side_token(m, side):
    side = side.upper()
    if side not in ("YES", "NO"):
        raise ValueError("side must be YES or NO")
    if not m["binary_yes_no"]:
        raise ValueError("only binary YES/NO markets can be bet on")
    if m["closed"] or not m["accepting_orders"]:
        raise ValueError("market is closed or not accepting orders")
    return side, m["token_ids"]["Yes" if side == "YES" else "No"]


def quote(m, side, amount_usd, limit_price=None):
    """Walk the live asks for `side` and price a buy of amount_usd, never above limit_price."""
    side, token = side_token(m, side)
    book = get(f"{CLOB}/book", {"token_id": token}, tries=3)
    asks = sorted(((float(a["price"]), float(a["size"])) for a in book.get("asks") or []), key=lambda a: a[0])
    left, shares, worst = amount_usd, 0.0, None
    for price, size in asks:
        if left <= 1e-9 or (limit_price is not None and price > limit_price):
            break
        take = min(size, left / price)
        shares += take
        left -= take * price
        worst = price
    spent = amount_usd - left
    bids = [float(b["price"]) for b in book.get("bids") or []]
    best_bid, best_ask = (max(bids) if bids else None), (asks[0][0] if asks else None)
    mid = (best_bid + best_ask) / 2 if best_bid is not None and best_ask is not None else None
    return dict(
        mode=mode(), market_id=m["market_id"], question=m["question"], side=side, token_id=token,
        amount_usd=round(amount_usd, 2), fillable_usd=round(spent, 4), unfilled_usd=round(max(left, 0), 4),
        shares=round(shares, 4), avg_price=round(spent / shares, 4) if shares else None, worst_price=worst,
        best_bid=best_bid, best_ask=best_ask, mid=mid,
        slippage_vs_mid=round(spent / shares - mid, 4) if shares and mid is not None else None,
        payout_if_win=round(shares, 4), profit_if_win=round(shares - spent, 4),
        tick_size=book.get("tick_size"), min_order_size=book.get("min_order_size"),
        hours_to_resolution=m["hours_to_resolution"], url=m["url"],
    )


def place_bet(m, side, amount_usd, limit_price=None, confirm=False, note=""):
    if amount_usd <= 0:
        raise ValueError("amount_usd must be positive")
    if LIVE and amount_usd > MAX_BET_USD:
        raise ValueError(f"live bets are capped at ${MAX_BET_USD} (POLYMARKET_MAX_BET_USD)")
    q = quote(m, side, amount_usd, limit_price)
    if not q["shares"]:
        raise ValueError("nothing fillable at or below the limit price")
    if not confirm:
        return {"status": "quote_only", "next": "call place_bet again with confirm=true to execute "
                "(fills never above worst_price)", **q}
    if LIVE:
        return {"status": "sent", **q, "order": live_buy(q)}
    bet = dict(id=uuid.uuid4().hex[:8], placed_at=now().isoformat(timespec="seconds"), note=note,
               **{k: q[k] for k in ("market_id", "question", "side", "token_id", "shares", "avg_price",
                                    "worst_price", "mid", "url")}, cost_usd=q["fillable_usd"])
    bets = read_ledger()
    bets.append(bet)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(bets, indent=1))
    return {"status": "paper_filled", **bet, "unfilled_usd": q["unfilled_usd"]}


def live_buy(q):
    from py_clob_client.clob_types import MarketOrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY
    c = client()
    args = MarketOrderArgs(token_id=q["token_id"], amount=q["fillable_usd"], side=BUY,
                           price=q["worst_price"], order_type=OrderType.FAK)
    return c.post_order(c.create_market_order(args), OrderType.FAK)


def read_ledger():
    return json.loads(LEDGER.read_text()) if LEDGER.exists() else []


def resolution(m, side):
    """1 if `side` won, 0 if it lost, None while unresolved (closed markets settle to outcome prices 1/0)."""
    if not m["closed"]:
        return None
    price = m["outcomes"].get("Yes" if side == "YES" else "No")
    if price is None or 0.02 < price < 0.98:
        return None
    return 1 if price >= 0.98 else 0


def exit_mark(m, side):
    """What selling one share now would fetch: the YES bid, or 1 - YES ask for a NO share."""
    if side == "YES":
        return float(m["best_bid"]) if m.get("best_bid") is not None else None
    return 1 - float(m["best_ask"]) if m.get("best_ask") is not None else None


def positions(summarise_market):
    """Paper: every bet marked to the live bid (exit price), or settled if resolved. Live: balance, open orders, trades."""
    if LIVE:
        from py_clob_client.clob_types import AssetType, BalanceAllowanceParams
        c = client()
        bal = c.get_balance_allowance(BalanceAllowanceParams(asset_type=AssetType.COLLATERAL,
                                                             signature_type=c.builder.sig_type))
        return dict(mode="live", usdc_balance=int(bal.get("balance", 0)) / 1e6,
                    open_orders=c.get_orders(), recent_trades=c.get_trades()[:50])
    rows, cost, value = [], 0.0, 0.0
    for b in read_ledger():
        m = summarise_market(b["market_id"])
        outcome_price = m["outcomes"].get("Yes" if b["side"] == "YES" else "No")
        if m["closed"]:
            price, status = outcome_price, "settled"
        else:  # mark at what selling now would get: YES bid, or 1 - YES ask for a NO share
            bid = m["best_bid"] if b["side"] == "YES" else (1 - float(m["best_ask"]) if m["best_ask"] else None)
            price, status = float(bid) if bid is not None else outcome_price, "open"
        worth = b["shares"] * (price or 0)
        cost += b["cost_usd"]
        value += worth
        rows.append({**b, "status": status, "mark_price": price, "value_usd": round(worth, 4),
                     "pnl_usd": round(worth - b["cost_usd"], 4)})
    return dict(mode="paper", n_bets=len(rows), cost_usd=round(cost, 2), value_usd=round(value, 2),
                pnl_usd=round(value - cost, 2), bets=rows)


def cancel_order(order_id=None, all_orders=False):
    if not LIVE:
        return {"mode": "paper", "status": "nothing to cancel: paper bets fill instantly"}
    c = client()
    return c.cancel_all() if all_orders else c.cancel(order_id)
