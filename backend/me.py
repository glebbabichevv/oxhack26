"""My results: "am I making or losing money with Horizon?"

  GET /api/me?install_id=<id>&wallet=<0x… optional>

journal  from the Decision Journal for this install: counts by status; the bets the user marked as placed
         (self-reported in the extension) scored after Polymarket's taker fee; a counterfactual "if you had
         followed every Horizon pick shown to you" (every BUY decision, first per market x side, at its suggested
         stake); and how the skipped picks did.
wallet   optional public address (read only, 0x + 40 hex; never a key): real positions from Polymarket's public
         data API, marked to the current price, tagged "followed Horizon" when the same conditionId + side is in
         this install's journal as set_up or placed. The address is not stored; responses are cached 60 s in memory.
"""
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

import journal
import track

DATA_API = "https://data-api.polymarket.com"
WALLET_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
RANK = {"placed": 3, "set_up": 2, "skipped": 1, "shown": 0}
router = APIRouter()
_wallet_cache, _wlock = {}, threading.Lock()


def _score(rec, info, stake):
    """$ P&L of `stake` dollars on the record's side at its logged price + the market's taker fee."""
    y = info.get("outcome")
    if y is None or rec.get("side") not in ("YES", "NO"):
        return None
    p = rec["price"]
    fee = info["fee_rate"] * (p * (1 - p)) ** info["fee_exp"] if info.get("fees_enabled") else 0.0
    shares = stake / min(p + fee, 1.0)
    won = (y == 1) == (rec["side"] == "YES")
    return round(shares * won - stake, 4)


def _book(recs, infos, stake_of):
    rows, pts = [], []
    for r in recs:
        info = infos.get(r["market_id"]) or {}
        stake = stake_of(r)
        pnl = _score(r, info, stake) if stake else None
        status = "open" if info.get("outcome") is None else ("won" if pnl and pnl > 0 else "lost")
        rows.append({"market_id": r["market_id"], "slug": r.get("slug"), "question": r.get("question"), "side": r.get("side"),
                     "price": r.get("price"), "q": r.get("q"), "stake_usd": stake, "status": r.get("status"),
                     "result": status, "pnl_usd": pnl, "ts": r.get("ts"), "closed_at": info.get("closed_at"),
                     "source": r.get("source")})
        if pnl is not None and info.get("closed_at"):
            pts.append({"t": info["closed_at"], "pnl": pnl})
    done = [x for x in rows if x["pnl_usd"] is not None]
    staked = sum(x["stake_usd"] for x in done)
    pnl = sum(x["pnl_usd"] for x in done)
    cum, curve = 0.0, []
    for p in sorted(pts, key=lambda p: p["t"]):
        cum += p["pnl"]
        curve.append({"t": p["t"], "cum_usd": round(cum, 4)})
    return {"n": len(rows), "n_open": len(rows) - len(done), "n_resolved": len(done),
            "n_won": sum(x["result"] == "won" for x in done),
            "hit_rate": round(sum(x["result"] == "won" for x in done) / len(done), 4) if done else None,
            "staked_usd": round(staked, 2), "pnl_usd": round(pnl, 2),
            "per_dollar": round(pnl / staked, 4) if staked else None, "roi": round(pnl / staked, 4) if staked else None,
            "curve": curve, "bets": sorted(rows, key=lambda x: x["ts"] or "", reverse=True)}


def journal_part(install_id):
    recs = [r for r in journal.STORE.all() if isinstance(r, dict) and r.get("install_id") == install_id and r.get("market_id")]
    counts = {s: sum(r.get("status") == s for r in recs) for s in RANK}
    buys = sorted([r for r in recs if r.get("action") in ("BUY_YES", "BUY_NO") and r.get("side")], key=lambda r: r.get("ts") or "")

    def first(rs, key=lambda r: (r["market_id"], r["side"])):
        out = {}
        for r in rs:
            out.setdefault(key(r), r)
        return list(out.values())

    placed = first([r for r in buys if r.get("status") == "placed" and (r.get("stake_usd") or 0) > 0])
    picks = first(buys)  # every Horizon pick shown, first time it was shown
    skipped = first([r for r in buys if r.get("status") == "skipped"])
    infos = track.market_info(list({r["market_id"] for r in buys}))
    suggested = lambda r: float(r.get("stake_usd") or 1.0)  # noqa: E731
    # status of each market x side = the furthest the user went with it
    best = {}
    for r in buys:
        k = (r["market_id"], r["side"])
        if k not in best or RANK.get(r.get("status"), 0) > RANK.get(best[k], 0):
            best[k] = r.get("status")
    followed = {k for k, s in best.items() if s in ("set_up", "placed")}
    pick_book = _book(picks, infos, suggested)
    for b in pick_book["bets"]:
        b["status"] = best.get((b["market_id"], b["side"]), b["status"])
    return {
        "counts": counts,
        "placed": _book(placed, infos, lambda r: float(r["stake_usd"])),
        "if_followed_all": pick_book,
        "skipped": _book(skipped, infos, suggested),
        "followed_keys": followed,
        "note": "Placed bets are self-reported in the extension. P&L after Polymarket's taker fee for that market, "
                "at the logged price. 'If followed' = every BUY pick shown, first per market and side, at its suggested stake.",
    }


def _get(path, params):
    url = f"{DATA_API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "horizon-me/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())


MAX_ROWS = 1000


def _paged(path, user):
    """All pages (the data API caps a page, e.g. 50 closed positions), up to MAX_ROWS rows."""
    rows, offset = [], 0
    while len(rows) < MAX_ROWS:
        page = _get(path, {"user": user, "limit": 500, "offset": offset, **({"sizeThreshold": 0} if path == "/positions" else {})})
        rows += page
        offset += len(page)
        if not page or len(page) < 50:
            break
    return rows


def wallet_part(wallet, followed):
    key = wallet.lower()
    with _wlock:
        hit = _wallet_cache.get(key)
        if hit and time.time() - hit[0] < 60:
            raw = hit[1]
        else:
            raw = {"open": _paged("/positions", key), "closed": _paged("/closed-positions", key)}
            _wallet_cache[key] = (time.time(), raw)
            for k in [k for k, v in _wallet_cache.items() if time.time() - v[0] > 60]:
                _wallet_cache.pop(k, None)

    def side(p):
        return "YES" if p.get("outcomeIndex") == 0 else "NO" if p.get("outcomeIndex") == 1 else None

    def row(p, open_):
        tag = "followed" if (p.get("conditionId"), side(p)) in followed else "own"
        out = {"title": p.get("title"), "slug": p.get("eventSlug") or p.get("slug"), "outcome": p.get("outcome"),
               "side": side(p), "avg_price": p.get("avgPrice"), "cur_price": p.get("curPrice"), "tag": tag,
               "open": open_, "realized_usd": round(float(p.get("realizedPnl") or 0), 2)}
        if open_:
            out.update(size=p.get("size"), initial_usd=round(float(p.get("initialValue") or 0), 2),
                       value_usd=round(float(p.get("currentValue") or 0), 2),
                       unrealized_usd=round(float(p.get("cashPnl") or 0), 2))
        else:
            out.update(bought_usd=round(float(p.get("totalBought") or 0) * float(p.get("avgPrice") or 0), 2))
        return out

    rows = [row(p, True) for p in raw["open"]] + [row(p, False) for p in raw["closed"]]

    def totals(rs):
        return {"n_open": sum(r["open"] for r in rs), "n_closed": sum(not r["open"] for r in rs),
                "value_usd": round(sum(r.get("value_usd", 0) for r in rs), 2),
                "unrealized_usd": round(sum(r.get("unrealized_usd", 0) for r in rs), 2),
                "realized_usd": round(sum(r["realized_usd"] for r in rs), 2),
                "total_usd": round(sum(r.get("unrealized_usd", 0) + r["realized_usd"] for r in rs), 2)}

    return {"totals": totals(rows), "followed": totals([r for r in rows if r["tag"] == "followed"]),
            "own": totals([r for r in rows if r["tag"] == "own"]),
            "truncated": len(raw["open"]) >= MAX_ROWS or len(raw["closed"]) >= MAX_ROWS,
            "positions": sorted(rows, key=lambda r: (r["tag"] != "followed", not r["open"],
                                                     -abs(r.get("unrealized_usd", 0) + r["realized_usd"])))[:200],
            "note": "Real positions from Polymarket's public data API, marked to the current price. Read only; the address is not stored."}


@router.get("/api/me")
def me(install_id: Optional[str] = None, wallet: Optional[str] = None):
    if not install_id and not wallet:
        raise HTTPException(422, "pass install_id and/or wallet")
    if install_id and not ID_RE.match(install_id):
        raise HTTPException(422, "install_id must be 8-64 of [A-Za-z0-9_-]")
    if wallet and not WALLET_RE.match(wallet):
        raise HTTPException(422, "wallet must be a public address: 0x followed by 40 hex characters")
    try:
        j = journal_part(install_id) if install_id else None
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"journal unavailable ({type(e).__name__})")
    followed = j.pop("followed_keys") if j else set()
    w, w_err = None, None
    if wallet:
        try:
            w = wallet_part(wallet, followed)
        except Exception as e:  # noqa: BLE001 - data API down: say so, keep the journal part
            w_err = f"Polymarket data API unavailable ({type(e).__name__})"
    return {"install_id": install_id, "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "journal": j, "wallet": w, "wallet_error": w_err}
