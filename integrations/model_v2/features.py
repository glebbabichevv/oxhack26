"""Feature table for model v2: data/horizons.csv + hourly paths + raw Gamma dump -> one DataFrame.

Every feature uses only information available at that row's horizon. volume_usd is lifetime volume
(includes trading after the horizon) and is deliberately not a feature.
"""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

FEATURES = ["price_yes", "horizon_hours", "domain", "by_date", "n_legs", "book_share", "mom24", "mom72", "vol72"]
BY_DATE = re.compile(r"\b(by|before)\b\s+(the\s+end\s+of\s+)?"
                     r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d|q[1-4]|end|202)", re.I)


def load_id_map(raw_dir):
    cache = raw_dir / "id_map.csv"
    if cache.exists():
        return pd.read_csv(cache, dtype={"gamma_id": str, "market_id": str})
    dump = sorted(raw_dir.glob("markets_*.json"))[-1]
    rows = [{"gamma_id": str(m["id"]), "market_id": m["conditionId"],
             "fees_on": str(m.get("feesEnabled")) == "True"} for m in json.loads(dump.read_text())]
    out = pd.DataFrame(rows)
    out.to_csv(cache, index=False)
    return out


def by_date(questions):
    return questions.fillna("").str.contains(BY_DATE).to_numpy()


def book_features(df):
    g = df.groupby(["event_slug", "horizon_hours"])["price_yes"]
    n = g.transform("size")
    return pd.DataFrame({"n_legs": n.astype(int),
                         "book_share": np.where(n > 1, df["price_yes"] / g.transform("sum"), 1.0)}, index=df.index)


def path_stats(t, p, at):
    keep = t <= at
    t, p = t[keep], p[keep]
    if len(t) == 0:
        return 0.0, 0.0, 0.0
    now = p[-1]

    def back(hours):
        i = np.searchsorted(t, at - hours * 3600, side="right") - 1
        return float(now - p[i]) if i >= 0 else 0.0

    w = p[t >= at - 72 * 3600]
    vol = float(np.std(np.diff(w))) if len(w) >= 12 else 0.0
    return back(24), back(72), vol


def build_table(data_dir, raw_dir):
    df = pd.read_csv(data_dir / "horizons.csv")
    df = df[df["outcome"].isin([0, 1]) & df["price_yes"].between(0, 1, inclusive="neither")].reset_index(drop=True)
    for c in ("resolved_at", "end_date", "price_ts"):
        df[c] = pd.to_datetime(df[c], utc=True, format="mixed")
    df["domain"] = df["domain"].fillna("other").str.lower()
    df["spread"] = pd.to_numeric(df["spread"], errors="coerce")
    df["by_date"] = by_date(df["question"])
    df = df.join(book_features(df))
    ids = load_id_map(raw_dir)
    df["fees_on"] = df["market_id"].map(ids.set_index("market_id")["fees_on"]).fillna(False).astype(bool)
    gamma = ids.set_index("market_id")["gamma_id"]
    stats = np.zeros((len(df), 3))
    for mid, rows in df.groupby("market_id").indices.items():
        f = raw_dir / "hist" / f"{gamma.get(mid)}.json"
        if not f.exists():
            continue
        pts = json.loads(f.read_text())
        t = np.array([x["t"] for x in pts], float)
        p = np.array([x["p"] for x in pts], float)
        order = np.argsort(t)
        t, p = t[order], p[order]
        for r in rows:
            stats[r] = path_stats(t, p, df.at[r, "price_ts"].timestamp())
    df[["mom24", "mom72", "vol72"]] = stats
    return df
