"""Open binary Polymarket markets -> data/live_full.csv.

Run from the repo root:  python integrations/fetch_live.py

price_yes is the order-book midpoint and spread is best ask - best bid, both live
from gamma. hours_to_resolution is measured to the scheduled end date, the same
clock fetch_horizons.py uses, so the model sees live markets on its training axis.
"""
import argparse
from datetime import datetime, timedelta, timezone

import pandas as pd

from common import DATA, GAMMA, domain_of, get, is_yes_no, parse_ts, tag_slugs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-volume", type=float, default=50000)
    ap.add_argument("--max-days", type=float, default=45)
    ap.add_argument("--out", default=str(DATA / "live_full.csv"))
    a = ap.parse_args()

    now = datetime.now(timezone.utc)
    markets, offset = {}, 0
    while True:
        page = get(f"{GAMMA}/markets", dict(
            closed="false", active="true", limit=100, offset=offset, volume_num_min=a.min_volume,
            end_date_min=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_date_max=(now + timedelta(days=a.max_days)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            order="endDate", ascending="true", include_tag="true"))
        for m in page:
            markets[m["id"]] = m
        offset += 100
        if len(page) < 100 or offset >= 2000:
            break

    rows = []
    for m in markets.values():
        bid, ask, end = m.get("bestBid"), m.get("bestAsk"), parse_ts(m.get("endDate"))
        if not is_yes_no(m) or not m.get("acceptingOrders") or bid is None or ask is None or not end:
            continue
        bid, ask = float(bid), float(ask)
        if not 0 < bid < ask < 1:
            continue  # empty or crossed book: no tradable price
        event = (m.get("events") or [{}])[0]
        rows.append(dict(
            market_id=m["conditionId"], question=m["question"], domain=domain_of(tag_slugs(m)),
            price_yes=round((bid + ask) / 2, 4), hours_to_resolution=round((end - now).total_seconds() / 3600, 1),
            volume_usd=round(float(m.get("volumeNum") or 0), 2), spread=round(ask - bid, 4),
            url=f"https://polymarket.com/event/{event.get('slug') or m.get('slug')}",
            best_bid=bid, best_ask=ask, end_date=end.isoformat(),
            liquidity_usd=round(float(m.get("liquidityNum") or 0), 2), neg_risk=bool(m.get("negRisk")),
            fetched_at=now.isoformat(timespec="seconds"),
        ))

    df = pd.DataFrame(rows).sort_values("volume_usd", ascending=False)
    df.to_csv(a.out, index=False)
    print(f"wrote {len(df)} open markets to {a.out}")
    print(df.domain.value_counts().to_string())


if __name__ == "__main__":
    main()
