"""Resolved binary Kalshi markets -> data/kalshi_horizons.csv (same layout as data/horizons.csv).

Run from the repo root:  python integrations/fetch_kalshi.py [--since 2026-05-18] [--min-volume 20000]

Kalshi is a CFTC-regulated US exchange with the same yes/no contracts. Used as a second venue the model has never
seen. Same rules as fetch_horizons.py:
- Clock = the scheduled end (`expected_expiration_time`, known in advance), not the actual close.
- A (market, horizon) row exists only if the market was open at that moment.
- Price = midpoint of the hourly candle's closing yes bid/ask at or before the horizon moment (≤ 6 h stale);
  `spread` = ask − bid from the same candle. Unlike Polymarket, Kalshi keeps historical quotes, so the cost is real.
- Fee: Kalshi's taker fee 0.07 × p × (1 − p) per contract (fees_enabled/fee_rate columns, as backend fee_per_share reads).
Multivariate "combo" markets (KXMVE*) are not listed by /events, so they never enter.
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pandas as pd

from common import DATA, RAW, get, parse_ts

API = "https://api.elections.kalshi.com/trade-api/v2"
HORIZONS = [720, 168, 72, 24, 12]
MAX_STALE_H = 6
CACHE = RAW / "kalshi"
DOMAINS = {"Sports": "sports", "Elections": "politics", "Politics": "politics", "Economics": "economics",
           "Financials": "economics", "Companies": "economics", "Commodities": "economics", "Crypto": "crypto",
           "Entertainment": "culture", "Mentions": "culture", "Social": "culture", "World": "geopolitics",
           "Science and Technology": "science_tech", "AI": "science_tech", "Health": "science_tech",
           "Climate and Weather": "science_tech", "Transportation": "other"}


def list_markets(since, min_volume):
    out, cursor = [], None
    while True:
        params = {"status": "settled", "limit": 200, "with_nested_markets": "true",
                  "min_close_ts": int(since.timestamp())}
        if cursor:
            params["cursor"] = cursor
        page = get(f"{API}/events", params)
        for e in page.get("events") or []:
            for m in e.get("markets") or []:
                if (m.get("market_type") == "binary" and m.get("result") in ("yes", "no")
                        and float(m.get("volume_fp") or m.get("volume") or 0) >= min_volume):
                    out.append(dict(m, series_ticker=e["series_ticker"], category=e.get("category"),
                                    event_title=e.get("title")))
        cursor = page.get("cursor")
        if not cursor or not page.get("events"):
            return out


def candles(m, start, end):
    path = CACHE / f"{m['ticker']}.json"
    if path.exists():
        return json.loads(path.read_text())
    data = get(f"{API}/series/{m['series_ticker']}/markets/{m['ticker']}/candlesticks",
               {"start_ts": start, "end_ts": end, "period_interval": 60}).get("candlesticks") or []
    path.write_text(json.dumps(data))
    return data


def rows_for(m):
    anchor = parse_ts(m.get("expected_expiration_time") or m.get("close_time"))
    close, open_ = parse_ts(m["close_time"]), parse_ts(m.get("open_time"))
    if not anchor or not close:
        return []
    start = int((anchor.timestamp() - (max(HORIZONS) + MAX_STALE_H) * 3600))
    end = int(min(close, anchor).timestamp())
    if end <= start:
        return []
    cs = candles(m, start, end)
    out = []
    for h in HORIZONS:
        t = anchor.timestamp() - h * 3600
        if t >= close.timestamp() or (open_ and t <= open_.timestamp()):
            continue  # market not open at that moment
        best = None
        for c in cs:
            if t - MAX_STALE_H * 3600 <= c["end_period_ts"] <= t:
                best = c  # candles are in time order: keep the last one at or before t
        if best is None:
            continue
        bid = float((best.get("yes_bid") or {}).get("close_dollars") or 0)
        ask = float((best.get("yes_ask") or {}).get("close_dollars") or 0)
        if not 0 < bid < ask < 1:
            continue  # no two-sided quote: no tradable price
        out.append(dict(
            market_id=m["ticker"], question=m.get("title") or m.get("event_title"),
            domain=DOMAINS.get(m.get("category"), "other"), horizon_hours=h, price_yes=round((bid + ask) / 2, 4),
            outcome=int(m["result"] == "yes"), resolved_at=close.isoformat(),
            volume_usd=round(float(m.get("volume_fp") or 0), 2), spread=round(ask - bid, 4), end_date=anchor.isoformat(),
            price_ts=datetime.fromtimestamp(best["end_period_ts"], timezone.utc).isoformat(), neg_risk=False,
            event_slug=m.get("event_ticker"), tags=m.get("category") or "", fees_enabled=True, fee_rate=0.07,
            fee_exponent=1.0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-05-18", help="markets closing on/after this date")
    ap.add_argument("--min-volume", type=float, default=20000, help="contracts traded")
    ap.add_argument("--out", default=str(DATA / "kalshi_horizons.csv"))
    a = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    markets = list_markets(datetime.fromisoformat(a.since).replace(tzinfo=timezone.utc), a.min_volume)
    print(f"{len(markets)} settled binary markets with volume >= {a.min_volume:,.0f} contracts")
    with ThreadPoolExecutor(8) as pool:
        rows = [r for rs in pool.map(rows_for, markets) for r in rs]
    df = pd.DataFrame(rows)
    df.to_csv(a.out, index=False)
    print(f"wrote {len(df)} rows, {df.market_id.nunique()} markets to {a.out}")
    print(pd.crosstab(df.domain, df.horizon_hours, margins=True))


if __name__ == "__main__":
    main()
