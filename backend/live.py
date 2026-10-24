"""Live decisions for /api/live, computed on request from Polymarket's Gamma API with results/model.json.

Same market filter as integrations/fetch_live.py (open yes/no, accepting orders, two-sided book,
volume >= $100k (training floor), events not yet started, scheduled end within 45 days), same math as model.live_report via horizon_mcp.decide
(pure Python, no pandas at runtime), same selection: top 30 trades by net edge (policy V3: net edge >= 1¢,
within 24 h of the end), 15 WAIT rows (edge now, enter later; soonest first), 10 biggest in-band NO_TRADE. Cached in-process for CACHE_TTL seconds. If Gamma fails, serves results/live.json and says so.

  python backend/live.py      # refresh results/live.json (the fallback snapshot) from Gamma now
"""
import json
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import horizon_mcp
from horizon_mcp import GAMMA, decide, domain_of, model_version

HERE = Path(__file__).parent
SNAPSHOT = HERE / "results" / "live.json"
CACHE_TTL = 300  # seconds
MIN_VOLUME = 100_000  # the training floor: every one of the 34,677 markets had >= $100k lifetime volume
MAX_DAYS = 45
N_TRADES, N_WAIT, N_NO_TRADE = 30, 15, 10
PAGE, MAX_OFFSET = 100, 2000  # Gamma caps offset around 2,000

_lock = threading.Lock()
_cache = {"at": 0.0, "payload": None}


def _get(params, tries=2):
    url = f"{GAMMA}/markets?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "horizon-api/1.0", "Accept": "application/json"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=8) as res:
                return json.loads(res.read())
        except Exception:
            if attempt == tries - 1:
                raise


def fetch_open(now):
    base = dict(closed="false", active="true", limit=PAGE, volume_num_min=MIN_VOLUME,
                end_date_min=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                end_date_max=(now + timedelta(days=MAX_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                order="endDate", ascending="true", include_tag="true")
    markets, offset, batch = {}, 0, 8
    with ThreadPoolExecutor(max_workers=batch) as pool:
        while offset < MAX_OFFSET:
            offsets = range(offset, min(offset + batch * PAGE, MAX_OFFSET), PAGE)
            pages = list(pool.map(lambda o: _get({**base, "offset": o}), offsets))
            for page in pages:
                for m in page:
                    markets[m["id"]] = m
            offset += batch * PAGE
            if len(pages[-1]) < PAGE:
                break
    return list(markets.values())


def _ts(s):
    try:
        return datetime.fromisoformat(s.replace(" ", "T").replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def _row(m, now, model):
    try:
        if [o.lower() for o in json.loads(m.get("outcomes") or "[]")] != ["yes", "no"]:
            return None
        bid, ask = float(m["bestBid"]), float(m["bestAsk"])
    except (KeyError, TypeError, ValueError):
        return None
    end = _ts(m.get("endDate"))
    if not m.get("acceptingOrders") or not end or not 0 < bid < ask < 1:
        return None
    ev0 = (m.get("events") or [{}])[0]
    start = _ts((m.get("gameStartTime") or "").replace(" ", "T").replace("+00", "+00:00") or None) or _ts(ev0.get("startTime"))
    if start and start <= now < end:  # event under way: the price already reflects it; never advise
        return None
    hours = round((end - now).total_seconds() / 3600, 1)
    price, spread = round((bid + ask) / 2, 4), round(ask - bid, 4)
    tags = [t.get("slug") for t in m.get("tags") or [] if t.get("slug")]
    for ev in m.get("events") or []:
        tags += [t.get("slug") for t in ev.get("tags") or [] if t.get("slug")]
    domain = domain_of(tags)
    rate, exp = horizon_mcp.fee_of(m, domain, model)
    d = decide(price, hours, domain, spread, model, rate, exp)
    event = (m.get("events") or [{}])[0]
    return {"market_id": m.get("conditionId"), "question": m.get("question"), "domain": domain,
            "price_yes": price, "hours_to_resolution": hours,
            "q_yes": round(d["q"], 4), "q_low": round(d["lo"], 4), "q_high": round(d["hi"], 4),
            "edge": round(d["q"] - price, 4), "net_edge": round(d["net_edge"], 4), "cost": round(d["cost"], 4),
            "action": d["action"], "kelly_fraction": round(d["kelly"], 4), "reason": d["reason"],
            "url": f"https://polymarket.com/event/{event.get('slug') or m.get('slug')}",
            "volume_usd": round(float(m.get("volumeNum") or 0), 2), "spread": spread,
            "fee": round(rate * (price * (1 - price)) ** exp, 4),
            "wait": d["wait"], "would_be": d["would_be"], "check_back_in_hours": d["check_back_in_hours"]}


def snapshot(model=None):
    """Fetch Gamma now -> the /api/live payload with source 'live'. Raises if Gamma fails or is empty."""
    model = model or horizon_mcp.MODEL
    now = datetime.now(timezone.utc)
    markets = fetch_open(now)
    rows = [r for r in (_row(m, now, model) for m in markets) if r]
    if not rows:
        raise RuntimeError("Gamma returned no open yes/no markets with a two-sided book")
    lo, hi = model["tradable"]
    trades = sorted((r for r in rows if r["action"] != "NO_TRADE"), key=lambda r: -r["net_edge"])[:N_TRADES]
    # WAIT: an edge today, but the rule enters only within 24 h of the end; soonest first.
    waits = sorted((r for r in rows if r["wait"]), key=lambda r: r["check_back_in_hours"])[:N_WAIT]
    passes = sorted((r for r in rows if r["action"] == "NO_TRADE" and not r["wait"] and lo <= r["price_yes"] <= hi),
                    key=lambda r: -r["volume_usd"])[:N_NO_TRADE]
    return {"updated_at": now.isoformat(timespec="seconds"), "model_version": model_version(model),
            "source": "live", "cache_ttl_s": CACHE_TTL, "n_markets_scanned": len(markets),
            "n_markets_priced": len(rows), "n_trades": sum(r["action"] != "NO_TRADE" for r in rows),
            "n_wait": sum(r["wait"] for r in rows), "policy": model.get("policy"),
            "best_window": horizon_mcp._best_window_note(),
            "markets": trades + waits + passes}


def _fallback(error):
    data = json.loads(SNAPSHOT.read_text())
    if isinstance(data, list):  # legacy snapshot (a bare list, written by model.py before v1.3)
        data = {"updated_at": None, "model_version": None, "markets": data}
    return {**data, "source": "fallback", "error": f"live Polymarket fetch failed ({error}); showing the saved snapshot"}


def get_live():
    """Cached payload; one Gamma fetch per CACHE_TTL per instance, fallback snapshot on failure."""
    with _lock:
        if _cache["payload"] is not None and time.time() - _cache["at"] < CACHE_TTL:
            return _cache["payload"]
        try:
            payload = snapshot()
            _cache.update(at=time.time(), payload=payload)
        except Exception as e:  # noqa: BLE001 - any Gamma failure -> saved snapshot, retried after 60 s
            payload = _fallback(e)
            _cache.update(at=time.time() - CACHE_TTL + 60, payload=payload)
        return payload


def write_snapshot(model=None, path=SNAPSHOT):
    payload = snapshot(model)
    Path(path).write_text(json.dumps(payload, indent=1))
    return payload


if __name__ == "__main__":
    p = write_snapshot(horizon_mcp.load_model(sys.argv[1]) if len(sys.argv) > 1 else None)
    print(f"wrote {SNAPSHOT.relative_to(HERE.parent)}: {len(p['markets'])} markets "
          f"({p['n_markets_scanned']} scanned, {p['n_trades']} trades) model {p['model_version']}")
