"""Sanity checks for data/horizons.csv and data/live.csv. Run: python integrations/sanity.py"""
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"


def check_horizons():
    df = pd.read_csv(DATA / "horizons.csv")
    for c in ["resolved_at", "end_date"]:
        df[c] = pd.to_datetime(df[c], utc=True, format="ISO8601")
    print(f"horizons.csv: {len(df)} rows, {df.market_id.nunique()} markets, {df.event_id.nunique()} events")
    print(f"resolved_at range: {df.resolved_at.min():%Y-%m-%d} -> {df.resolved_at.max():%Y-%m-%d}")
    print("\nrows per horizon x domain:")
    print(pd.crosstab(df.domain, df.horizon_hours, margins=True))
    print("\nYES rate and mean price per horizon (calibration gap at a glance):")
    print(df.groupby("horizon_hours").agg(n=("outcome", "size"), yes_rate=("outcome", "mean"),
                                          mean_price=("price_yes", "mean")).round(3))

    problems = []
    if df.duplicated(["market_id", "horizon_hours"]).any():
        problems.append("duplicate (market, horizon) rows")
    if not df.outcome.isin([0, 1]).all():
        problems.append("outcome not in {0,1}")
    if not df.price_yes.between(0, 1).all():
        problems.append("price_yes outside [0,1]")
    # Leakage: the horizon timestamp must be before the market closed.
    t = df.end_date - pd.to_timedelta(df.horizon_hours, unit="h")
    if (t >= df.resolved_at).any():
        problems.append(f"{(t >= df.resolved_at).sum()} rows priced after market close")
    # Price already pinned at 0/1 means the outcome was known: flag, don't silently keep.
    pinned = ((df.price_yes <= 0.005) | (df.price_yes >= 0.995)).mean()
    print(f"\nshare of rows with price pinned <=0.5% or >=99.5%: {pinned:.1%}")
    print("problems:", problems or "none")


def check_live():
    df = pd.read_csv(DATA / "live.csv")
    print(f"\nlive.csv: {len(df)} markets")
    print(df.domain.value_counts().to_string())
    print(f"median spread {df.spread.median():.3f}, hours_to_resolution median {df.hours_to_resolution.median():.0f}")


if __name__ == "__main__":
    check_horizons()
    check_live()
