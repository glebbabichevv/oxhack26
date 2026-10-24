"""Model v2: playoff on validation, betting knobs tuned on validation, one out-of-time test.

  python integrations/model_v2/train.py [--data data] [--raw data/raw] [--out integrations/model_v2/results]
"""
import os
os.environ.setdefault("OMP_NUM_THREADS", "4")

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "backend"))
import model as backend  # read-only: metric and report helpers  # noqa: E402

from decision import apply_caps, earliest_trades, trade_cost  # noqa: E402
from features import build_table  # noqa: E402
from models import in_band, make  # noqa: E402

CUTOFF = "2026-05-18"
KELLY_GRID = (0.125, 0.25, 0.5)
EDGE_GRID = (0.0, 0.01, 0.02, 0.03)
TIE = 0.0005


def split_time(df, cutoff):
    cut = pd.Timestamp(cutoff, tz="UTC")
    end = df.groupby("event_slug")["resolved_at"].transform("max")
    return df[end < cut], df[(end >= cut) & (df["resolved_at"] >= cut)]


def split_validation(train, frac=0.2):
    ends = train.groupby("event_slug")["resolved_at"].max().sort_values()
    val_events = set(ends.index[int(round(len(ends) * (1 - frac))):])
    v = train["event_slug"].isin(val_events)
    return train[~v], train[v]


def costs(df):
    return trade_cost(df["price_yes"], df["spread"], df["fees_on"], df["domain"])


CANDIDATES = [("M0", {}), ("M1", {"C": 0.1}), ("M1", {"C": 1.0}), ("M2", {})]


def playoff(fit, val):
    """Returns ((name, kwargs), scores); M1's C is picked here too; ties within TIE go to the simpler model."""
    vb = val[in_band(val["price_yes"])]
    y = vb["outcome"].to_numpy()
    scores = {"market": backend.log_loss(vb["price_yes"], y)}
    for name, kw in CANDIDATES:
        key = name + "".join(f"_C{v}" for v in kw.values())
        q, _, _ = make(name, **kw).fit(fit).predict(vb)
        scores[key] = backend.log_loss(q, y)
        print(f"  validation log loss {key}: {scores[key]:.4f} (market {scores['market']:.4f})", flush=True)
    best, best_score = CANDIDATES[0], scores["M0"]
    for name, kw in CANDIDATES[1:]:
        s = scores[name + "".join(f"_C{v}" for v in kw.values())]
        if s < best_score - TIE:
            best, best_score = (name, kw), s
    return best, {k: round(v, 5) for k, v in scores.items()}


def tune(model, val):
    q, lo, hi = model.predict(val)
    c = costs(val)
    grid = []
    for k in KELLY_GRID:
        for e in EDGE_GRID:
            t = apply_caps(earliest_trades(val, q, lo, hi, c, e, k))
            grid.append({"kelly_mult": k, "min_edge": e, "n_trades": int(len(t)),
                         "pnl": round(float((t["stake"] * t["ret"]).sum()), 4)})
    best = max(grid, key=lambda g: (g["pnl"], -g["kelly_mult"], g["min_edge"]))
    return best["kelly_mult"], best["min_edge"], grid
