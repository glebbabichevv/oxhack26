"""Horizon as an MCP server: two tools for a browser agent (Argos), stateless JSON-RPC over POST.

Same math as extension-module/horizon.ts and backend/model.py, in pure Python from
results/model.json (no sklearn at runtime). Parity: `python3 backend/horizon_mcp.py parity capsule/seal-<ts>.json` (or a fee fixture from parity_fees.py).

Transport: MCP Streamable HTTP without sessions. POST /mcp takes a JSON-RPC message (or batch) and
answers application/json; notifications get 202; GET /mcp is 405 (no server-initiated stream).
"""
import json
import math
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

MODEL_PATH = Path(__file__).parent / "results" / "model.json"
GAMMA = "https://gamma-api.polymarket.com"
SERVER_INFO = {"name": "horizon", "version": "1.0.0"}
FALLBACK_PROTOCOL = "2025-06-18"


# ---------- model (mirror of horizon.ts) ----------

def _clip(x, a, b):
    return min(max(x, a), b)


# A model file names its features; each is a product (" * ") of these factors. The default model is
# ["logit(p)", "log(clip(hours, 12, 720) / 24)", "logit(p) * log(clip(hours, 12, 720) / 24)"];
# "domain=<name>" (1 if the market's domain is <name>, else 0) lets a per-domain model drop in.
LOGIT_P = "logit(p)"
LOG_H = "log(clip(hours, 12, 720) / 24)"
DEFAULT_FEATURES = [LOGIT_P, LOG_H, f"{LOGIT_P} * {LOG_H}"]


def parse_features(names):
    """Feature names -> list of factor tuples; raises ValueError on anything this code can't compute."""
    parsed = []
    for name in names or DEFAULT_FEATURES:
        factors = tuple(f.strip() for f in name.split(" * "))
        for f in factors:
            if f not in (LOGIT_P, LOG_H) and not (f.startswith("domain=") and len(f) > 7):
                raise ValueError(f"unknown feature factor {f!r} in {name!r}")
        parsed.append(factors)
    return parsed


def load_model(path=MODEL_PATH):
    """Read and validate a model file (same format as results/model.json)."""
    m = json.loads(Path(path).read_text()) if not isinstance(path, dict) else path
    m["_features"] = parse_features(m.get("features"))
    for fit in [m["main"], *m["boot"]]:
        if len(fit["coef"]) != len(m["_features"]):
            raise ValueError(f"{len(fit['coef'])} coefficients for {len(m['_features'])} features")
    return m


MODEL = load_model()


def model_version(m=None):
    return (m or MODEL).get("version") or "unversioned"


def _features(price, hours, domain=None, m=None):
    m = m or MODEL
    p = _clip(price, m["eps"], 1 - m["eps"])
    val = {LOGIT_P: math.log(p / (1 - p)), LOG_H: math.log(_clip(hours, 12, 720) / 24)}  # inside the trained range
    out = []
    for factors in m["_features"]:
        x = 1.0
        for f in factors:
            x *= val[f] if f in val else float(domain == f[7:])
        out.append(x)
    return out


def _prob(fit, x):
    z = fit["intercept"] + sum(c * xi for c, xi in zip(fit["coef"], x))
    return 1 / (1 + math.exp(-z))


def _percentile(values, pct):
    """numpy.percentile with the default linear interpolation."""
    s = sorted(values)
    k = (len(s) - 1) * (pct / 100)
    f, c = math.floor(k), math.ceil(k)
    return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)


def domain_of(tag_slugs):
    slugs = set(tag_slugs)
    for domain, keys in MODEL["domain_tags"]:
        if any(k in slugs for k in keys):
            return domain
    return "other"


def _pct(x):
    return f"{round(x * 100)}%"


def _horizon_label(h):
    return f"{round(h / 24)}d" if h >= 48 else f"{max(1, round(h))}h"


def fee_of(mk, domain, m=None):
    """(rate, exponent) of a Gamma market's taker fee: its own feeSchedule, else the model's domain table; 0 if off."""
    m = m or MODEL
    if not mk.get("feesEnabled"):
        return 0.0, 1.0
    sched = mk.get("feeSchedule") or {}
    rate = sched.get("rate")
    if rate is None:
        rate = (m.get("fee_rates") or {}).get(domain, (m.get("fee_rates") or {}).get("other", 0.0))
    return float(rate), float(sched.get("exponent") or 1)


WAIT_REASON = "Wait: best time is within 24h of the end"


def decide(price, hours, domain, spread=None, m=None, fee_rate=None, fee_exponent=1.0, policy=None):
    """price = order-book mid, spread = ask - bid (None if unknown), hours = to the scheduled end.
    Taker fee per share = fee_rate * (p(1-p))**fee_exponent (fee_of(market)); fee_rate None = the domain's rate.
    policy: None = the model file's `policy` (V3: min net edge, enter only within enter_from_hours of the end);
    False = no policy filter (the pre-V3 rule, used to check old seals)."""
    m = m or MODEL
    pol = (m.get("policy") or {}) if policy is None else (policy or {})
    has_spread = spread is not None and math.isfinite(spread)
    if fee_rate is None:
        fee_rate = (m.get("fee_rates") or {}).get(domain, (m.get("fee_rates") or {}).get("other", 0.0))
    fee = fee_rate * (price * (1 - price)) ** fee_exponent
    cost = (max(spread / 2, m["min_half_spread"]) if has_spread else m["min_half_spread"]) + fee
    base = {"price": price, "hours": hours, "domain": domain, "cost": cost,
            "wait": False, "would_be": None, "check_back_in_hours": None}
    if not (m["tradable"][0] <= price <= m["tradable"][1]):
        return {**base, "q": price, "lo": price, "hi": price, "action": "NO_TRADE", "kelly": 0.0, "net_edge": 0.0,
                "reason": f"Market at {price * 100:.1f}%: too close to certain, a {round(cost * 100)}¢ cost exceeds any edge"}
    x = _features(price, hours, domain, m)
    q = _prob(m["main"], x)
    qs = [_prob(f, x) for f in m["boot"]]
    lo = _percentile(qs, m["interval_percentiles"][0])
    hi = _percentile(qs, m["interval_percentiles"][1])

    buy_yes = lo - (price + cost)
    buy_no = (price - cost) - hi
    action = "BUY_YES" if buy_yes > 0 else "BUY_NO" if buy_no > 0 else "NO_TRADE"
    qc = lo if action == "BUY_YES" else hi if action == "BUY_NO" else q
    py = _clip(price + cost, m["eps"], 1 - m["eps"])
    pn = _clip(1 - price + cost, m["eps"], 1 - m["eps"])
    raw = (qc - py) / (1 - py) if action == "BUY_YES" else ((1 - qc) - pn) / (1 - pn) if action == "BUY_NO" else 0.0
    kelly = _clip(raw * m["kelly_scale"], 0, m["kelly_cap"])
    net_edge = buy_no if action == "BUY_NO" else buy_yes
    gap = abs(q - price) * 100
    if action == "NO_TRADE":
        reason = (f"Model {_pct(q)} (range {_pct(lo)}–{_pct(hi)}) vs market {_pct(price)}: the {gap:.1f}¢ gap is "
                  f"inside the model's uncertainty plus {round(cost * 100)}¢ cost")
    else:
        reason = (f"{_horizon_label(hours)} out, {domain}: model {_pct(q)} vs market {_pct(price)}, "
                  f"net edge {net_edge * 100:.1f}¢")
    out = {**base, "q": q, "lo": lo, "hi": hi, "action": action, "kelly": kelly, "net_edge": net_edge, "reason": reason}
    if action != "NO_TRADE" and net_edge < pol.get("min_edge", 0.0):
        out.update(action="NO_TRADE", kelly=0.0,
                   reason=f"Net edge {net_edge * 100:.1f}¢ is under the {pol['min_edge'] * 100:.0f}¢ minimum: not worth the risk")
    elif action != "NO_TRADE" and pol.get("enter_from_hours") is not None and hours > pol["enter_from_hours"]:
        out.update(action="NO_TRADE", kelly=0.0, wait=True, would_be=action, reason=WAIT_REASON,
                   check_back_in_hours=round(hours - pol["enter_from_hours"], 1))
    return out


def _best_window_note():
    h = MODEL.get("headline") or {}
    pol = MODEL.get("policy") or {}
    n_test = (MODEL.get("metrics") or {}).get("n_test_markets", 10579)
    if not h:
        return "Out-of-time results are in /api/backtest."
    ci = h.get("per_dollar_ci") or [None, None]
    return (f"Horizon only enters within {pol.get('enter_from_hours', 24)}h of the scheduled end and only with a net edge of at "
            f"least {pol.get('min_edge', 0.01) * 100:.0f}¢ (rule chosen on validation, test opened once). Out of time "
            f"({n_test:,} markets after {MODEL['train_cutoff']}) that earned {h['per_dollar'] * 100:+.1f}¢ per $1 staked after "
            f"fees (90% CI {ci[0] * 100:+.1f}¢ to {ci[1] * 100:+.1f}¢) over {h['n_trades']:,} trades. An average over many "
            "markets, not a forecast for this one; the edge is solid mainly in sports.")


# ---------- Gamma ----------

def _get(path, params):
    url = f"{GAMMA}{path}?{urllib.parse.urlencode(params, doseq=True)}"
    req = urllib.request.Request(url, headers={"User-Agent": "horizon-mcp/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as res:
        return json.loads(res.read())


def _slug_from(text):
    """Accept a bare event slug or any polymarket.com URL."""
    s = text.strip()
    if "://" in s or s.startswith("polymarket.com"):
        parts = [p for p in urllib.parse.urlparse(s if "://" in s else "https://" + s).path.split("/") if p]
        if "event" in parts and parts.index("event") + 1 < len(parts):
            return parts[parts.index("event") + 1]
        return parts[-1] if parts else s
    return s.strip("/")


def _leg(mk, event, now):
    """Horizon's view of one market of an event: a decision dict, or {'skip': why}."""
    question = mk.get("question") or event.get("title")
    try:
        outcomes = [o.lower() for o in json.loads(mk.get("outcomes") or "[]")]
    except (ValueError, TypeError, AttributeError):
        outcomes = []
    if outcomes != ["yes", "no"]:
        return {"question": question, "skip": "not a yes/no market"}
    if mk.get("closed") or not mk.get("acceptingOrders"):
        return {"question": question, "skip": "closed"}
    try:
        bid, ask = float(mk.get("bestBid")), float(mk.get("bestAsk"))
    except (TypeError, ValueError):
        return {"question": question, "skip": "no two-sided order book"}
    if not (0 < bid < ask < 1):
        return {"question": question, "skip": "no two-sided order book"}
    end_s = mk.get("endDate") or event.get("endDate")
    try:
        end = datetime.fromisoformat(end_s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return {"question": question, "skip": "no end date"}
    hours = (end - now).total_seconds() / 3600
    if not hours > 0:
        return {"question": question, "skip": "past its end date"}
    tags = [t.get("slug") for t in (mk.get("tags") or []) + (event.get("tags") or []) if t.get("slug")]
    domain = domain_of(tags)
    rate, exp = fee_of(mk, domain)
    d = decide((bid + ask) / 2, hours, domain, ask - bid, fee_rate=rate, fee_exponent=exp)
    return {
        "question": question,
        "event": event.get("slug"),
        "url": f"https://polymarket.com/event/{event.get('slug')}",
        "domain": d["domain"],
        "market_price_yes": round(d["price"], 4),
        "bid": bid, "ask": ask,
        "horizon_q_yes": round(d["q"], 4),
        "q_interval_10_90": [round(d["lo"], 4), round(d["hi"], 4)],
        "action": d["action"],
        "net_edge_after_spread": round(d["net_edge"], 4),
        "cost_per_share": round(d["cost"], 4),
        "quarter_kelly_stake_of_bankroll": round(d["kelly"], 4),
        "wait": d["wait"], "would_be": d["would_be"], "check_back_in_hours": d["check_back_in_hours"],
        "hours_to_end": round(hours, 1),
        "reason": d["reason"],
    }


def horizon_check(slug):
    now = datetime.now(timezone.utc)
    slug = _slug_from(slug)
    events = _get("/events", {"slug": slug})
    if not events:
        return {"error": f"No Polymarket event with slug '{slug}'. Pass the slug from the URL polymarket.com/event/<slug>."}
    event = events[0]
    legs = [_leg(mk, event, now) for mk in event.get("markets") or []]
    priced = [l for l in legs if "skip" not in l]
    priced.sort(key=lambda l: (l["action"] == "NO_TRADE", -l["net_edge_after_spread"]))
    skipped = {}
    for l in legs:
        if "skip" in l:
            skipped[l["skip"]] = skipped.get(l["skip"], 0) + 1
    return {
        "event": event.get("title"),
        "slug": slug,
        "n_markets": len(legs),
        "n_priced": len(priced),
        "skipped": skipped,
        "trades": sum(l["action"] != "NO_TRADE" for l in priced),
        "legs": priced[:25],
        "legs_truncated": max(0, len(priced) - 25),
        "best_window": _best_window_note(),
        "method": ("Horizon recalibrates the order-book mid with a 4-coefficient logistic model fitted on 23,838 resolved "
                   "Polymarket markets; it trades only if the model's 10–90% bootstrap interval clears price ± cost "
                   "(cost = max(spread/2, 1¢) + Polymarket's taker fee for that market), sizes by quarter-Kelly capped at 5%, and skips prices outside 3–97%. Policy V3: only a net edge of at least 1¢, "
                   "and only within 24h of the scheduled end (earlier = WAIT)."),
    }


def horizon_scan(tag="sports", within_hours=24.0, top=5):
    now = datetime.now(timezone.utc)
    within_hours = _clip(float(within_hours), 0.5, 24 * 30)
    top = int(_clip(int(top), 1, 25))
    tag = (tag or "sports").strip().lower()
    try:
        tag_id = _get(f"/tags/slug/{urllib.parse.quote(tag)}", {})["id"]
    except Exception:
        return {"error": f"Unknown Polymarket tag '{tag}'. Try sports, nba, nfl, soccer, nhl, crypto, politics."}
    end_max = now + timedelta(hours=within_hours)
    # /markets, not /events: an event page embeds every leg (tens of MB for sports), a market page is ~0.6 MB.
    base = {"tag_id": tag_id, "related_tags": "true", "closed": "false", "include_tag": "true", "limit": 100,
            "order": "volume24hr", "ascending": "false",
            "end_date_min": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "end_date_max": end_max.strftime("%Y-%m-%dT%H:%M:%SZ")}

    def page(offset):
        try:
            return _get("/markets", {**base, "offset": offset})
        except Exception:  # one bad page should not kill the scan
            return []

    markets = []
    with ThreadPoolExecutor(max_workers=11) as pool:  # Gamma's offset cap is 2100: the 2,100 most-traded markets
        for b in pool.map(page, range(0, 2100, 100)):
            markets.extend(b)
    seen, legs = set(), []
    for mk in markets:
        if mk.get("id") in seen:
            continue
        seen.add(mk.get("id"))
        event = (mk.get("events") or [{}])[0]
        event = {**event, "slug": event.get("slug") or mk.get("slug")}
        l = _leg(mk, event, now)
        if "skip" not in l and l["hours_to_end"] <= within_hours and 0.03 <= l["market_price_yes"] <= 0.97:
            legs.append(l)
    legs.sort(key=lambda l: -l["net_edge_after_spread"])
    trades = [l for l in legs if l["action"] != "NO_TRADE"]
    return {
        "tag": tag,
        "within_hours": within_hours,
        "n_markets_scanned": len(seen),
        "n_markets_priced": len(legs),
        "n_trades": len(trades),
        "top": trades[:top] if trades else legs[:top],
        "note": (None if trades else "No market clears the cost and uncertainty bar right now; closest ones shown, all NO_TRADE.")
                if legs else "No open yes/no market with a two-sided book in this window.",
        "best_window": _best_window_note(),
    }


# ---------- MCP (JSON-RPC 2.0) ----------

TOOLS = [
    {
        "name": "horizon_check",
        "description": ("Horizon calibration verdict for one Polymarket event page. For each yes/no market: market price, "
                        "Horizon's recalibrated probability with 10-90% interval, BUY_YES/BUY_NO/NO_TRADE, net edge after "
                        "the spread, quarter-Kelly stake, hours to end, reason. Use when the user asks whether to buy or "
                        "bet on a polymarket.com/event/<slug> page."),
        "inputSchema": {
            "type": "object",
            "properties": {"slug": {"type": "string", "description": "Event slug from polymarket.com/event/<slug>, or the full page URL"}},
            "required": ["slug"],
        },
    },
    {
        "name": "horizon_scan",
        "description": ("Find where Horizon sees edge now: open Polymarket yes/no markets with a tag, ending within a window, "
                        "two-sided book, priced 3-97%, ranked by net edge after costs. Use for 'where else is there edge "
                        "tonight?'. Defaults: tag sports, within_hours 24, top 5."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tag": {"type": "string", "description": "Polymarket tag slug, e.g. sports, nba, nfl, soccer, nhl, crypto, politics (default sports)"},
                "within_hours": {"type": "number", "description": "Only markets ending within this many hours (default 24)"},
                "top": {"type": "integer", "description": "How many markets to return, 1-25 (default 5)"},
            },
        },
    },
]


def _call_tool(name, args):
    if name == "horizon_check":
        if not args.get("slug"):
            raise ValueError("slug is required")
        return horizon_check(str(args["slug"]))
    if name == "horizon_scan":
        return horizon_scan(args.get("tag") or "sports", args.get("within_hours") or 24, args.get("top") or 5)
    raise KeyError(name)


def handle_message(msg):
    """One JSON-RPC message → response dict, or None for notifications."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or "method" not in msg:
        return {"jsonrpc": "2.0", "id": msg.get("id") if isinstance(msg, dict) else None,
                "error": {"code": -32600, "message": "Invalid Request"}}
    if "id" not in msg:  # notification (notifications/initialized, cancelled, ...)
        return None
    mid, method, params = msg["id"], msg["method"], msg.get("params") or {}

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    if method == "initialize":
        return ok({
            "protocolVersion": params.get("protocolVersion") or FALLBACK_PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": ("Horizon: calibrated probabilities and trade/no-trade decisions for Polymarket. Call "
                             "horizon_check with the event slug of the page the user is on; horizon_scan to find edge elsewhere."),
        })
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments") or {}
        try:
            data = _call_tool(name, args)
        except KeyError:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Unknown tool: {name}"}}
        except Exception as e:  # report as a tool error so the agent can explain it
            return ok({"content": [{"type": "text", "text": f"Horizon error: {e}"}], "isError": True})
        is_err = isinstance(data, dict) and "error" in data
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return ok({"content": [{"type": "text", "text": text}], "isError": is_err})
    if method in ("resources/list", "prompts/list"):
        return ok({method.split("/")[0]: []})
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}


def handle_body(body):
    """Whole POST body (message or batch) → (status, payload or None)."""
    if isinstance(body, list):
        out = [r for r in (handle_message(m) for m in body) if r is not None]
        return (200, out) if out else (202, None)
    r = handle_message(body)
    return (200, r) if r is not None else (202, None)


# ---------- parity check ----------

if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "parity":
    seal = json.loads(Path(sys.argv[2]).read_text())
    worst, mismatched = 0.0, 0
    for r in seal["markets"]:
        # Seals predate fees and V3: no fee, no policy. Fee fixtures carry fee_rate and their policy.
        d = decide(r["price_yes"], r["hours_to_resolution"], r["domain"], r.get("spread"),
                   fee_rate=r.get("fee_rate", 0.0), fee_exponent=r.get("fee_exponent", 1.0), policy=r.get("policy", False))
        worst = max(worst, abs(d["q"] - r["q_yes"]), abs(d["lo"] - r["q_low"]), abs(d["hi"] - r["q_high"]),
                    abs(d["net_edge"] - r["net_edge"]))
        mismatched += d["action"] != r["action"]
    print(f"{len(seal['markets'])} markets · max |diff| {worst:.2e} · action mismatches {mismatched}")
    sys.exit(0 if worst < 1e-4 and mismatched == 0 else 1)
