"""Quick data check: is there a calibration bias in data/horizons.csv, and which way?

Fits outcome ~ logit(a + b * logit(price)) per horizon. b > 1: prices compressed toward 50%
(the paper's claim); b < 1: prices too extreme (favourite-longshot bias). 95% CI by bootstrapping
whole events, because markets inside one event are correlated.
Run: python integrations/calibration_check.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"


def fit(x, y):
    a, b = 0.0, 1.0
    for _ in range(30):
        p = 1 / (1 + np.exp(-(a + b * x)))
        w = p * (1 - p) + 1e-9
        X = np.c_[np.ones_like(x), x]
        a, b = np.array([a, b]) + np.linalg.solve(X.T @ (X * w[:, None]), X.T @ (y - p))
    return a, b


def main(n_boot=300):
    rng = np.random.default_rng(0)
    d = pd.read_csv(DATA / "horizons.csv")
    d = d[(d.price_yes > 0.02) & (d.price_yes < 0.98)]  # pinned prices carry no tradable edge
    d = d.assign(x=np.log(d.price_yes / (1 - d.price_yes)))
    for h, g in d.groupby("horizon_hours"):
        groups = {e: gg for e, gg in g.groupby("event_id")}
        events = list(groups)
        boot = []
        for _ in range(n_boot):
            s = pd.concat([groups[e] for e in rng.choice(events, len(events))])
            boot.append(fit(s.x.values, s.outcome.values)[1])
        a, b = fit(g.x.values, g.outcome.values)
        lo, hi = np.percentile(boot, [2.5, 97.5])
        brier = np.mean((g.price_yes - g.outcome) ** 2)
        print(f"h={h:4d}h rows={len(g):5d} events={len(events):4d} "
              f"slope={b:.2f} 95%CI[{lo:.2f},{hi:.2f}] intercept={a:+.2f} brier_market={brier:.4f}")


if __name__ == "__main__":
    main()
