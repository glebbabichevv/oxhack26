"""Polymarket fetcher -> data/horizons.csv and data/live.csv (see Data contract in CLAUDE.md).

Usage (from repo root):
    python integrations/polymarket.py horizons [--max-markets 4000] [--min-volume 10000]
    python integrations/polymarket.py live [--max-markets 300]

Horizons are measured back from the market's scheduled endDate. A (market, horizon)
row is dropped if the market had already closed at that time, or if there is no
price point within MAX_GAP_HOURS before it. Only prices at or before the target
timestamp are used, so there is no future leakage.
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw" / "polymarket"

HORIZONS_H = [720, 168, 72, 24, 12]
CHUNK_S = 15 * 86400
MAX_GAP_HOURS = 12

# First match wins; checked against lowercased event tag labels and title.
DOMAINS = [
    ("Sports", ["sports", "nfl", "nba", "mlb", "nhl", "soccer", "football", "tennis", "f1", "ufc",
                "boxing", "golf", "cricket", "esports", "olympics", "premier league", "champions league"]),
    ("Crypto", ["crypto", "bitcoin", "ethereum", "solana", "btc", "eth", "xrp", "doge", "memecoin", "airdrop"]),
    ("Politics", ["politics", "election", "elections", "us election", "trump", "congress", "senate",
                  "primaries", "president", "democratic", "republican", "governor", "parliament"]),
    ("Geopolitics", ["geopolitics", "world", "ukraine", "russia", "israel", "gaza", "iran", "china",
                     "middle east", "war", "nato", "foreign policy"]),
    ("Economics", ["economy", "economics", "fed", "interest rates", "inflation", "finance", "business",
                   "stocks", "earnings", "gdp", "recession", "commodities", "ipo"]),
    ("Culture", ["pop culture", "culture", "entertainment", "movies", "music", "awards", "oscars",
                 "grammys", "celebrities", "tv", "youtube", "twitter", "elon musk"]),
    ("Tech", ["tech", "ai", "science", "space", "openai", "apple", "spacex"]),
]

session = requests.Session()


def get(url, params=None, tries=5):
    for i in range(tries):
        try:
            r = session.get(url, params=params, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2 ** i)
                continue
            return r
        except requests.RequestException:
            time.sleep(2 ** i)
    raise RuntimeError(f"GET failed: {url} {params}")


def parse_ts(s):
    if not s:
        return None
    s = s.replace(" ", "T").replace("Z", "+00:00")
    if s.endswith("+00"):
        s += ":00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def domain_of(event):
    words = [t.get("label", "").lower() for t in event.get("tags") or []]
    title = (event.get("title") or "").lower()
    for name, keys in DOMAINS:
        if any(k in words for k in keys):
            return name
    for name, keys in DOMAINS:
        if any(f" {k} " in f" {title} " for k in keys if len(k) > 3):
            return name
    return "Other"


def fetch_events(closed, max_events):
    events, offset = [], 0
    params = {"closed": str(closed).lower(), "limit": 100, "order": "volume", "ascending": "false"}
    if not closed:
        params["active"] = "true"
    while len(events) < max_events:
        r = get(f"{GAMMA}/events", {**params, "offset": offset})
        if r.status_code != 200:
            print(f"  events pagination stopped at offset {offset}: {r.text[:100]}", file=sys.stderr)
            break
        page = r.json()
        if not page:
            break
        events += page
        offset += len(page)
        print(f"  events: {len(events)}", file=sys.stderr)
    return events


def binary_yes_token(m):
    try:
        outcomes = json.loads(m.get("outcomes") or "[]")
        tokens = json.loads(m.get("clobTokenIds") or "[]")
    except json.JSONDecodeError:
        return None
    if [o.lower() for o in outcomes] != ["yes", "no"] or len(tokens) != 2:
        return None
    return tokens[0]


def resolved_outcome(m):
    """1/0 for a clean YES/NO resolution, None for cancelled / 50-50 / MKT."""
    if m.get("umaResolutionStatus") not in (None, "resolved"):
        return None
    try:
        p = [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
    except (json.JSONDecodeError, ValueError):
        return None
    if p == [1.0, 0.0]:
        return 1
    if p == [0.0, 1.0]:
        return 0
    return None


def price_history(token, start, end):
    cache = RAW / "prices" / f"{token}_{start}_{end}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    points = []
    s = start
    while s < end:
        e = min(s + CHUNK_S, end)
        r = get(f"{CLOB}/prices-history", {"market": token, "startTs": s, "endTs": e, "fidelity": 60})
        if r.status_code == 200:
            points += r.json().get("history", [])
        s = e
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(points))
    return points


def horizon_rows(m, event):
    token = binary_yes_token(m)
    outcome = resolved_outcome(m)
    end_dt = parse_ts(m.get("endDate"))
    closed_dt = parse_ts(m.get("closedTime"))
    if token is None or outcome is None or end_dt is None or closed_dt is None:
        return []
    end_ts, closed_ts = int(end_dt.timestamp()), int(closed_dt.timestamp())
    targets = {h: end_ts - h * 3600 for h in HORIZONS_H}
    targets = {h: t for h, t in targets.items() if t < closed_ts}  # market still open then
    if not targets:
        return []
    start = min(targets.values()) - MAX_GAP_HOURS * 3600
    stop = max(targets.values())
    hist = sorted(price_history(token, start, stop), key=lambda p: p["t"])
    rows = []
    for h, t in targets.items():
        before = [p for p in hist if p["t"] <= t]
        if not before or t - before[-1]["t"] > MAX_GAP_HOURS * 3600:
            continue
        rows.append({
            "market_id": m["id"],
            "question": m.get("question"),
            "domain": domain_of(event),
            "horizon_hours": h,
            "price_yes": before[-1]["p"],
            "outcome": outcome,
            "resolved_at": closed_dt.isoformat(),
            "end_date": end_dt.isoformat(),
            "volume_usd": m.get("volumeNum"),
            "spread": None,
            "event_id": event.get("id"),
        })
    return rows


def cmd_horizons(args):
    events = fetch_events(closed=True, max_events=args.max_events)
    pairs, seen = [], set()
    for e in events:
        for m in e.get("markets") or []:
            if m["id"] in seen or (m.get("volumeNum") or 0) < args.min_volume:
                continue
            if binary_yes_token(m) and resolved_outcome(m) is not None:
                seen.add(m["id"])
                pairs.append((m, e))
    pairs.sort(key=lambda x: -(x[0].get("volumeNum") or 0))
    pairs = pairs[: args.max_markets]
    print(f"candidate markets: {len(pairs)}", file=sys.stderr)

    rows, done = [], 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(horizon_rows, m, e) for m, e in pairs]
        for f in as_completed(futs):
            try:
                rows += f.result()
            except Exception as ex:  # one bad market should not kill the run
                print(f"  skip: {ex}", file=sys.stderr)
            done += 1
            if done % 200 == 0:
                print(f"  prices: {done}/{len(pairs)} markets, {len(rows)} rows", file=sys.stderr)

    df = pd.DataFrame(rows).sort_values(["resolved_at", "market_id", "horizon_hours"])
    out = DATA / "horizons.csv"
    df.to_csv(out, index=False)
    print(f"wrote {out} ({len(df)} rows, {df.market_id.nunique()} markets)")


def cmd_live(args):
    events = fetch_events(closed=False, max_events=args.max_events)
    now = datetime.now(timezone.utc)
    rows = []
    for e in events:
        for m in e.get("markets") or []:
            end_dt = parse_ts(m.get("endDate"))
            if m.get("closed") or not m.get("active") or not binary_yes_token(m) or end_dt is None:
                continue
            hours = (end_dt - now).total_seconds() / 3600
            bid, ask = m.get("bestBid"), m.get("bestAsk")
            if hours <= 0 or bid is None or ask is None or not 0 < bid <= ask < 1:
                continue
            rows.append({
                "market_id": m["id"],
                "question": m.get("question"),
                "domain": domain_of(e),
                "price_yes": round((bid + ask) / 2, 4),
                "hours_to_resolution": round(hours, 1),
                "volume_usd": m.get("volumeNum"),
                "spread": round(ask - bid, 4),
                "url": f"https://polymarket.com/event/{e.get('slug')}",
                "end_date": end_dt.isoformat(),
            })
    df = pd.DataFrame(rows).drop_duplicates("market_id")
    df = df.sort_values("volume_usd", ascending=False).head(args.max_markets)
    out = DATA / "live.csv"
    df.to_csv(out, index=False)
    print(f"wrote {out} ({len(df)} markets)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("horizons")
    h.add_argument("--max-events", type=int, default=3000)
    h.add_argument("--max-markets", type=int, default=4000)
    h.add_argument("--min-volume", type=float, default=10000)
    h.add_argument("--workers", type=int, default=8)
    lv = sub.add_parser("live")
    lv.add_argument("--max-events", type=int, default=500)
    lv.add_argument("--max-markets", type=int, default=300)
    args = ap.parse_args()
    {"horizons": cmd_horizons, "live": cmd_live}[args.cmd](args)


if __name__ == "__main__":
    main()
