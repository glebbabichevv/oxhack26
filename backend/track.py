"""Live track record: cumulative result per $1 of real, resolved decisions (nothing here is backtest).

  GET /api/track  -> {"journal": {...}, "seal": {...}, "note"}
  python track.py build-seal   # capsule/seal-<ts>.json (read only) -> results/seal1_calls.json

Two lines, each point = one resolved decision at its resolution time, $1 on the side taken:
  journal  Decision Journal entries from the extension / agent with status set_up or placed and a BUY action
           (first entry per install x market x side), result per $1 at the logged price, before fees.
  seal     Capsule Seal 1: every sealed BUY_* call, scored at the sealed mid + max(spread/2, 1¢) + the market's
           taker fee, side taken (capsule Amendment 1: only markets resolved after the hash was posted).
"""
import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter

import journal

HERE = Path(__file__).resolve().parent
SEAL_CALLS = HERE / "results" / "seal1_calls.json"
TTL = 300
router = APIRouter()
_info, _lock = {}, threading.Lock()  # market_id -> (checked_at, info)
_cache = {"at": 0.0, "payload": None}


def market_info(ids):
    """conditionId -> {outcome, closed_at, fees_enabled, fee_rate, fee_exp}; open markets re-checked every 10 min."""
    now = time.time()
    due = [m for m in set(ids) if m.startswith("0x") and
           (m not in _info or (_info[m][1].get("outcome") is None and now - _info[m][0] > journal.OUTCOME_TTL))]
    try:
        for i in range(0, len(due), 50):
            for mk in journal._gamma([("condition_ids", c) for c in due[i:i + 50]] + [("closed", "true"), ("limit", 50)]):
                sched = mk.get("feeSchedule") or {}
                _info[mk["conditionId"]] = (now, {
                    "outcome": journal._resolution(mk), "closed_at": mk.get("closedTime"),
                    "fees_enabled": bool(mk.get("feesEnabled")), "fee_rate": float(sched.get("rate") or 0),
                    "fee_exp": float(sched.get("exponent") or 1)})
        for m in due:
            _info.setdefault(m, (now, {"outcome": None}))
            if _info[m][1].get("outcome") is None:
                _info[m] = (now, _info[m][1])
    except Exception:  # noqa: BLE001 - Gamma down: serve what we know
        pass
    return {m: _info.get(m, (0, {"outcome": None}))[1] for m in ids}


def _ts(s):
    try:
        return datetime.fromisoformat(str(s).replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        return None


def curve(points, n_open):
    points = sorted(points, key=lambda p: p["t"])
    cum, out = 0.0, []
    for i, p in enumerate(points, 1):
        cum += p["r"]
        out.append({"t": p["t"], "cum": round(cum, 4), "mean": round(cum / i, 4), "n": i})
    return {"n_resolved": len(points), "n_open": n_open, "total": round(cum, 4),
            "mean": round(cum / len(points), 4) if points else None,
            "n_right": sum(p["r"] > 0 for p in points), "points": out}


def journal_line():
    recs = [r for r in journal.STORE.all() if isinstance(r, dict) and r.get("action") in ("BUY_YES", "BUY_NO")
            and r.get("status") in ("set_up", "placed") and r.get("side") in ("YES", "NO") and r.get("market_id")]
    first = {}
    for r in sorted(recs, key=lambda r: r.get("ts") or ""):
        first.setdefault((r.get("install_id"), r["market_id"], r["side"]), r)
    recs = list(first.values())
    info = market_info([r["market_id"] for r in recs])
    pts, n_open = [], 0
    for r in recs:
        i = info.get(r["market_id"]) or {}
        s = journal.scored(r, i.get("outcome"))
        if s["result_per_dollar"] is None or not i.get("closed_at"):
            n_open += 1
            continue
        pts.append({"t": _ts(i["closed_at"]).isoformat(timespec="seconds"), "r": s["result_per_dollar"]})
    return curve(pts, n_open)


def seal_line():
    if not SEAL_CALLS.exists():
        return None
    seal = json.loads(SEAL_CALLS.read_text())
    posted = _ts(seal.get("posted_at")) if seal.get("posted_at") else None
    info = market_info([c["market_id"] for c in seal["calls"]])
    pts, n_open, n_excluded = [], 0, 0
    for c in seal["calls"]:
        i = info.get(c["market_id"]) or {}
        y, closed = i.get("outcome"), _ts(i.get("closed_at")) if i.get("closed_at") else None
        if y is None or closed is None:
            n_open += 1
            continue
        if posted and closed <= posted:
            n_excluded += 1  # Amendment 1: resolved before the hash was public
            continue
        p = c["price_yes"]
        fee = i["fee_rate"] * (p * (1 - p)) ** i["fee_exp"] if i.get("fees_enabled") else 0.0
        cost = max((c.get("spread") or 0) / 2, 0.01) + fee
        r = y / min(p + cost, 1) - 1 if c["action"] == "BUY_YES" else (1 - y) / min(1 - p + cost, 1) - 1
        pts.append({"t": closed.isoformat(timespec="seconds"), "r": round(r, 4)})
    out = curve(pts, n_open)
    out.update(name=seal["name"], sealed_at=seal["sealed_at"], posted_at=seal.get("posted_at"),
               n_calls=len(seal["calls"]), n_excluded_before_post=n_excluded)
    return out


@router.get("/api/track")
def track():
    with _lock:
        if _cache["payload"] is not None and time.time() - _cache["at"] < 120:
            return _cache["payload"]
        payload = {"journal": journal_line(), "seal": seal_line(),
                   "note": "Live: markets resolve overnight; nothing here is backtest. Each point is $1 on the side "
                           "taken. Journal: logged price, before fees. Seal 1: sealed mid + half-spread (min 1¢) + taker fee."}
        _cache.update(at=time.time(), payload=payload)
        return payload


if __name__ == "__main__" and sys.argv[1:] == ["build-seal"]:
    root = HERE.parent / "capsule"
    name = "seal-20261024T153130Z.json"
    s = json.loads((root / name).read_text())
    posts = json.loads((root / "posts.json").read_text()) if (root / "posts.json").exists() else {}
    calls = [{k: m[k] for k in ("market_id", "question", "price_yes", "spread", "action", "q_yes")}
             for m in s["markets"] if m["action"] in ("BUY_YES", "BUY_NO")]
    SEAL_CALLS.write_text(json.dumps({"name": name, "sealed_at": s["sealed_at"], "posted_at": posts.get(name),
                                      "calls": calls}, indent=0))
    print(f"{len(calls)} sealed BUY calls -> {SEAL_CALLS.relative_to(HERE.parent)} (posted {posts.get(name)})")
