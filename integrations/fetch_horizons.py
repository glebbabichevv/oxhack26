"""Resolved binary Polymarket markets -> data/horizons.csv (one row per market x horizon).

Run from the repo root:  python integrations/fetch_horizons.py --since 2024-01-01 --min-volume 50000

Time to resolution is measured from the market's *scheduled* end date (what a trader
sees at the time), never from the actual close time (that would leak the future).
A (market, horizon) row exists only if the market was still open and trading at
end_date - horizon, so markets that resolved early simply have no late-horizon rows.
Price histories are cached in data/raw/hist/ so reruns are cheap.
"""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import pandas as pd

from common import CLOB, DATA, GAMMA, RAW, domain_of, get, is_yes_no, parse_ts, tag_slugs, yes_token

HORIZONS_H = [720, 168, 72, 24, 12]
MAX_STALE_H = 6  # nearest trade print must be within 6h before the target time
HIST = RAW / "hist"


def list_window(start, end, min_volume):
    """All closed markets ending in [start, end). Gamma caps offset at 2000, so a full
    window is split in half and refetched rather than silently truncated."""
    found, offset = [], 0
    while True:
        page = get(f"{GAMMA}/markets", dict(
            closed="true", limit=100, offset=offset, volume_num_min=min_volume,
            end_date_min=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_date_max=end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            order="endDate", ascending="true", include_tag="true"))
        found += page
        offset += 100
        time.sleep(0.1)  # gamma rate-limits bursts of listing calls
        if len(page) < 100:
            return found
        if offset >= 2000:
            if end - start <= timedelta(hours=1):
                print(f"  warning: >2000 markets ending {start:%Y-%m-%d %H:%M}, truncated", flush=True)
                return found
            mid = start + (end - start) / 2
            return list_window(start, mid, min_volume) + list_window(mid, end, min_volume)


def list_markets(since, until, min_volume):
    out, start = {}, since
    while start < until:
        end = min(start + timedelta(days=7), until)
        for m in list_window(start, end, min_volume):
            out[m["id"]] = m
        print(f"  listed {start:%Y-%m-%d}: {len(out)} markets so far", flush=True)
        start = end
    return list(out.values())


def outcome_of(m):
    """1 / 0 for a clean YES / NO resolution; None for 50-50, cancelled or unresolved."""
    if (m.get("umaResolutionStatus") or "resolved") != "resolved":
        return None
    try:
        prices = [float(p) for p in json.loads(m.get("outcomePrices") or "[]")]
    except ValueError:
        return None
    if prices == [1.0, 0.0]:
        return 1
    if prices == [0.0, 1.0]:
        return 0
    return None


def history(m, end, closed):
    path = HIST / f"{m['id']}.json"
    if path.exists():
        return json.loads(path.read_text())
    token = yes_token(m)
    pts = get(f"{CLOB}/prices-history", dict(market=token, interval="max", fidelity=60)).get("history", [])
    if not pts:
        # interval=max is sometimes empty for closed markets: fall back to explicit 15-day chunks.
        lo = int((end - timedelta(hours=max(HORIZONS_H) + 24)).timestamp())
        hi = int(min(end, closed).timestamp())
        while lo < hi:
            step = min(lo + 15 * 86400, hi)
            pts += get(f"{CLOB}/prices-history", dict(market=token, startTs=lo, endTs=step, fidelity=60)).get("history", [])
            lo = step
    path.write_text(json.dumps(pts))
    return pts


def rows_for(m):
    outcome = outcome_of(m)
    end, closed = parse_ts(m.get("endDate")), parse_ts(m.get("closedTime"))
    if outcome is None or not is_yes_no(m) or not end or not closed or not m.get("clobTokenIds"):
        return []
    pts = sorted(history(m, end, closed), key=lambda p: p["t"])
    if not pts:
        return []
    tags = tag_slugs(m)
    rows = []
    for h in HORIZONS_H:
        target = (end - timedelta(hours=h)).timestamp()
        if target >= closed.timestamp() or target < pts[0]["t"]:
            continue  # market already resolved, or not yet trading, at that time
        prior = [p for p in pts if p["t"] <= target]
        if not prior or target - prior[-1]["t"] > MAX_STALE_H * 3600:
            continue
        rows.append(dict(
            market_id=m["conditionId"], question=m["question"], domain=domain_of(tags),
            horizon_hours=h, price_yes=round(float(prior[-1]["p"]), 4), outcome=outcome,
            resolved_at=closed.isoformat(), volume_usd=round(float(m.get("volumeNum") or 0), 2),
            spread="",  # historical spreads are not available from the API
            end_date=end.isoformat(), price_ts=datetime.fromtimestamp(prior[-1]["t"], timezone.utc).isoformat(),
            neg_risk=bool(m.get("negRisk")), event_slug=((m.get("events") or [{}])[0].get("slug") or ""),
            tags="|".join(dict.fromkeys(tags)),
        ))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2024-01-01")
    ap.add_argument("--until", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--min-volume", type=float, default=50000)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=str(DATA / "horizons.csv"))
    a = ap.parse_args()
    HIST.mkdir(parents=True, exist_ok=True)

    since = datetime.fromisoformat(a.since).replace(tzinfo=timezone.utc)
    until = datetime.fromisoformat(a.until).replace(tzinfo=timezone.utc)
    cache = RAW / f"markets_{a.since}_{a.until}_{int(a.min_volume)}.json"
    if cache.exists():
        listed = json.loads(cache.read_text())
    else:
        listed = list_markets(since, until, a.min_volume)
        cache.write_text(json.dumps(listed))
    markets = [m for m in listed if is_yes_no(m)]
    print(f"{len(markets)} closed yes/no markets; fetching price histories", flush=True)

    rows, failed = [], 0
    with ThreadPoolExecutor(a.workers) as pool:
        futures = [pool.submit(rows_for, m) for m in markets]
        for i, f in enumerate(as_completed(futures), 1):
            try:
                rows += f.result()
            except Exception as e:  # one bad market must not kill a 20-minute run
                failed += 1
                print(f"  failed: {e}", flush=True)
            if i % 250 == 0:
                print(f"  {i}/{len(markets)} markets, {len(rows)} rows", flush=True)

    df = pd.DataFrame(rows).sort_values(["resolved_at", "market_id", "horizon_hours"])
    df.to_csv(a.out, index=False)
    print(f"wrote {len(df)} rows ({df.market_id.nunique()} markets, {failed} failed) to {a.out}")


if __name__ == "__main__":
    main()
