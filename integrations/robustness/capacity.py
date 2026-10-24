"""Capacity from LIVE order books (A's 00:40 item 1) -> integrations/robustness/capacity.json

  python integrations/robustness/capacity.py [--api https://oxhack26-production.up.railway.app]

Live snapshot, not historical. Markets: every row of the shipped /api/live with a trade now (V3: BUY_YES / BUY_NO),
plus the WAIT rows' would-be side, reported separately (their book will be different by the time they enter).
For each, walk Polymarket's CLOB book of the side bought (YES token asks for BUY_YES, NO token asks for BUY_NO) to
fill $10 / $100 / $1k / $10k, and recompute the net edge per share exactly as decide() does, with the fill's
average price instead of the quoted one:  net = conservative value (q_low for YES, 1 - q_high for NO)
- avg fill price - taker fee per share (rate x p(1-p) at each level, rate from the market's live fee).
"""
import argparse
import json
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
SIZES = (10, 100, 1000, 10000)


def tokens(condition_id):
    r = requests.get(f"{GAMMA}/markets", params={"condition_ids": condition_id, "limit": 5}, timeout=20).json()
    if not r:
        return None
    m = r[0]
    outs = json.loads(m.get("outcomes") or "[]")
    ids = json.loads(m.get("clobTokenIds") or "[]")
    return dict(zip([o.lower() for o in outs], ids))


def asks(token_id):
    book = requests.get(f"{CLOB}/book", params={"token_id": token_id}, timeout=20).json()
    return sorted(((float(a["price"]), float(a["size"])) for a in book.get("asks") or []), key=lambda x: x[0])


def fill(levels, usd, fee_rate):
    """Spend `usd` (price + fee) walking the asks: shares bought, avg price, avg fee per share; None if too thin."""
    left, shares, paid, fees = usd, 0.0, 0.0, 0.0
    for price, size in levels:
        fee = fee_rate * price * (1 - price)
        take = min(size, left / (price + fee))
        shares += take
        paid += take * price
        fees += take * fee
        left -= take * (price + fee)
        if left <= 1e-9:
            return shares, paid / shares, fees / shares
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="https://oxhack26-production.up.railway.app")
    a = ap.parse_args()
    live = requests.get(f"{a.api}/api/live", timeout=60).json()
    out = {"note": __doc__.strip(), "snapshot_utc": live.get("updated_at"), "model_version": live.get("model_version"),
           "n_markets_scanned": live.get("n_markets_scanned"), "markets": []}
    for m in live["markets"]:
        side = m["action"] if m["action"] != "NO_TRADE" else m.get("would_be")
        if side not in ("BUY_YES", "BUY_NO"):
            continue
        tk = tokens(m["market_id"])
        if not tk or "yes" not in tk:
            continue
        p = m["price_yes"]
        fee_rate = m.get("fee", 0) / (p * (1 - p)) if 0 < p < 1 else 0
        tok, value = (tk["yes"], m["q_low"]) if side == "BUY_YES" else (tk["no"], 1 - m["q_high"])
        lv = asks(tok)
        row = {"question": m["question"], "domain": m["domain"], "hours_to_resolution": m["hours_to_resolution"],
               "status": "trade now" if m["action"] != "NO_TRADE" else "wait (would-be side)", "side": side,
               "value_per_share": round(value, 4), "best_ask": lv[0][0] if lv else None,
               "ask_depth_usd": round(sum(pr * s for pr, s in lv), 2), "volume_usd": m.get("volume_usd"), "by_size": []}
        for usd in SIZES:
            f = fill(lv, usd, fee_rate)
            if f is None:
                row["by_size"].append({"usd": usd, "fills": False})
                continue
            shares, avg, fee = f
            net = value - avg - fee
            row["by_size"].append({"usd": usd, "fills": True, "avg_price": round(avg, 4), "fee_per_share": round(fee, 4),
                                   "net_edge_per_share": round(net, 4), "net_edge_per_dollar": round(net / (avg + fee), 4)})
        row["max_size_with_positive_edge"] = max([s["usd"] for s in row["by_size"] if s.get("fills") and s["net_edge_per_share"] > 0], default=0)
        out["markets"].append(row)
        print(f"{row['status']:22s} {side} {m['question'][:60]:60s} " + " ".join(
            f"${s['usd']}:{s['net_edge_per_share'] * 100:+.1f}¢" if s.get("fills") else f"${s['usd']}:thin" for s in row["by_size"]), flush=True)
    now = [r for r in out["markets"] if r["status"] == "trade now"]
    allm = out["markets"]
    for label, rows in (("trade_now", now), ("trade_now_and_waits", allm)):
        out[label] = {"n_markets": len(rows),
                      "per_market_median_max_size": sorted(r["max_size_with_positive_edge"] for r in rows)[len(rows) // 2] if rows else 0,
                      "sum_max_size_usd": sum(r["max_size_with_positive_edge"] for r in rows)}
    (HERE / "capacity.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("snapshot_utc", "trade_now", "trade_now_and_waits")}, indent=1))


if __name__ == "__main__":
    main()
