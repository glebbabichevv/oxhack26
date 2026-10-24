"""Sanity checks on data/horizons_full.csv and data/live_full.csv (or the files given). Exits non-zero if a hard check fails.

Run from the repo root:  python integrations/check_data.py [horizons.csv] [live.csv]
"""
import sys

import pandas as pd

from common import DATA

HORIZONS = sys.argv[1] if len(sys.argv) > 1 else DATA / "horizons_full.csv"
LIVE = sys.argv[2] if len(sys.argv) > 2 else DATA / "live_full.csv"
h = pd.read_csv(HORIZONS)
for col in ("resolved_at", "end_date", "price_ts"):
    h[col] = pd.to_datetime(h[col], format="ISO8601", utc=True)
live = pd.read_csv(LIVE)
fails = []


def check(ok, msg):
    print(("ok    " if ok else "FAIL  ") + msg)
    if not ok:
        fails.append(msg)


print(f"horizons.csv: {len(h)} rows, {h.market_id.nunique()} markets, "
      f"resolved {h.resolved_at.min():%Y-%m-%d} -> {h.resolved_at.max():%Y-%m-%d}\n")
check(h.outcome.isin([0, 1]).all(), "outcomes are 0/1 only (no 50-50 / cancelled)")
check(h.price_yes.between(0, 1).all(), "prices in [0, 1]")
check(not h.duplicated(["market_id", "horizon_hours"]).any(), "one row per (market, horizon)")
target = h.end_date - pd.to_timedelta(h.horizon_hours, unit="h")
check((h.price_ts <= target).all(), "no look-ahead: every price is at or before end_date - horizon")
check((h.price_ts < h.resolved_at).all(), "every price is before the market resolved")
check(h.question.notna().all() and h.domain.notna().all(), "question and domain always present")

print("\nrows / YES rate / mean |price - outcome| / Brier of the market price, by horizon:")
by_h = h.groupby("horizon_hours").apply(lambda g: pd.Series({
    "rows": len(g), "yes_rate": g.outcome.mean(), "mae": (g.price_yes - g.outcome).abs().mean(),
    "brier_market": ((g.price_yes - g.outcome) ** 2).mean()}), include_groups=False)
print(by_h.round(4).to_string())
print("\nrows by domain x horizon:")
print(pd.crosstab(h.domain, h.horizon_hours, margins=True).to_string())
print("\nmarkets resolved per quarter (for choosing the out-of-time cutoff):")
print(h.drop_duplicates("market_id").resolved_at.dt.tz_localize(None).dt.to_period("Q").value_counts().sort_index().to_string())

print(f"\nlive.csv: {len(live)} open markets")
check(live.price_yes.between(0, 1).all(), "live prices in [0, 1]")
check((live.hours_to_resolution > 0).all(), "live markets all resolve in the future")
check(live.spread.ge(0).all(), "live spreads non-negative")
check(not live.market_id.duplicated().any(), "live market ids unique")

sys.exit(1 if fails else 0)
