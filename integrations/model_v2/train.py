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
sys.path.insert(0, str(HERE.parents[1] / "backend"))
sys.path.insert(0, str(HERE))  # last insert wins: local modules beat backend/ and site-packages
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
    keyed = [((name, kw), scores[name + "".join(f"_C{v}" for v in kw.values())]) for name, kw in CANDIDATES]
    lowest = min(sc for _, sc in keyed)
    best = next(c for c, sc in keyed if sc <= lowest + TIE)  # earliest (simplest) within TIE of the minimum
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


NULL_STRATEGIES = [
    "Sell before resolution: from 7d on, the model's edge does not predict the price move (slope ~0); selling early loses 11-16% per $1 vs +6-14% held to resolution.",
    "Fade/follow hourly shocks: prices revert 1-2c over 72h after jumps of 8c+, less than the 2c round trip; 0 of 24 rules profitable on train.",
    "Neg-risk overround: books summing >105% look like +8.9% arbitrage at snapshot prices, but on live bids only 1 of 91 events has sum(bid) > 1.",
    "'Nothing Ever Happens' (buy NO on by-date markets): reversed near the deadline (+5.5pp more YES than priced at 12h).",
]


def peak_exposure(t):
    ev = pd.concat([pd.DataFrame({"ts": t["entry_at"], "d": t["stake"]}),
                    pd.DataFrame({"ts": t["resolved_at"], "d": -t["stake"]})]).sort_values(["ts", "d"])
    return round(float(ev["d"].cumsum().max()), 4) if len(ev) else 0.0


def policy(model, df, kelly_mult, min_edge, cost):
    q, lo, hi = model.predict(df)
    t = apply_caps(earliest_trades(df, q, lo, hi, cost, min_edge, kelly_mult))
    return t.sort_values("resolved_at"), q


def summary(t, rng):
    s = backend.equity_stats(t, t["stake"].to_numpy())
    s["return_ci"] = backend.return_ci(t, rng)
    s["peak_exposure"] = peak_exposure(t)
    staked = float(t["stake"].sum())
    s["return_per_dollar"] = round(float((t["stake"] * t["ret"]).sum()) / staked, 4) if staked else None
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default=str(HERE / "results"))
    a = ap.parse_args()
    rng = np.random.default_rng(0)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    df = build_table(Path(a.data), Path(a.raw))
    train, test = split_time(df, CUTOFF)
    fit, val = split_validation(train)
    print(f"train {train.market_id.nunique()} markets (fit {fit.market_id.nunique()}, val {val.market_id.nunique()}), "
          f"test {test.market_id.nunique()}", flush=True)

    (best, best_kw), scores = playoff(fit, val)
    kelly_mult, min_edge, grid = tune(make(best, **best_kw).fit(fit), val)
    print(f"chosen {best} {best_kw}, kelly x{kelly_mult}, min edge {min_edge}", flush=True)

    # ---- frozen: refit on all train, score the test once ----
    model = make(best, **best_kw).fit(train)
    c = costs(test)
    trades, q = policy(model, test, kelly_mult, min_edge, c)
    zero, _ = policy(model, test, kelly_mult, min_edge, np.zeros(len(test)))
    m0 = model if best == "M0" else make("M0").fit(train)
    m0_trades, q0 = policy(m0, test, kelly_mult, min_edge, c)
    y = test["outcome"].to_numpy()

    cal = backend.calibration_report(test, q)
    (out / "calibration.json").write_text(json.dumps({"cutoff": CUTOFF, "by_domain": cal}, indent=1))
    fails, worst = backend.failures(test, q, cal, trades)
    fails += [{"kind": "null_strategy", "domain": "all", "horizon_hours": None, "n": None, "text": s} for s in NULL_STRATEGIES]
    _, lo_t, hi_t = model.predict(test)
    by_h = backend.by_horizon(test, q, c, lo_t, hi_t)  # descriptive: backend's decide() per fixed horizon, with our fee-aware costs
    backtest = {
        "cutoff": CUTOFF, "model": "v2",
        "n_train_markets": int(train.market_id.nunique()), "n_test_markets": int(test.market_id.nunique()),
        "n_trades": int(len(trades)),
        "model_selection": {"chosen": best, "params": best_kw, "val_logloss": scores, "val_markets": int(val.market_id.nunique()),
                            "kelly_mult": kelly_mult, "min_edge": min_edge, "grid": grid},
        "with_costs": summary(trades, rng),
        "return_ci": backend.return_ci(trades, rng),
        "by_domain": backend.by_domain(trades, rng),
        "without_costs": summary(zero, rng),
        "naive_favourite": backend.naive_favourite(test, c),
        "baseline_m0": {"logloss": round(backend.log_loss(q0, y), 4), **summary(m0_trades, rng)},
        "overall": {"brier_market": round(backend.brier(test["price_yes"], y), 4), "brier_model": round(backend.brier(q, y), 4),
                    "logloss_market": round(backend.log_loss(test["price_yes"], y), 4), "logloss_model": round(backend.log_loss(q, y), 4)},
        "by_horizon": by_h,
        "failures": fails, "worst_trades": worst,
        "assumptions": [
            f"Split by time at {CUTOFF}: train on events that ended before it; test on markets of the remaining events that resolved after it.",
            "Model, Kelly multiplier and minimum edge chosen on the last 20% of train events; the test set is scored once.",
            "Cost per contract = max(spread/2, 1c) + Polymarket taker fee rate x p x (1-p) on markets with fees enabled (today's rates, whole period).",
            "One trade per market at the earliest qualifying horizon, held to resolution; fills at the historical price.",
            "Stakes capped at 5% per trade, 10% per event, and 1.0 starting bankroll open at any time; P&L additive.",
            f"Validation chose Kelly x{kelly_mult} and a {min_edge*100:.0f}c minimum edge; x0.5 Kelly doubles stake size versus the backend's x0.25, so return and drawdown scale with it - compare return_per_dollar across rules.",
            "volume_usd is not a feature (lifetime volume would leak trading after the horizon).",
        ],
    }
    (out / "backtest.json").write_text(json.dumps(backtest, indent=1, default=str))
    w = backtest["with_costs"]
    print(f"TEST  logloss market {backtest['overall']['logloss_market']}  {best} {backtest['overall']['logloss_model']}  M0 {backtest['baseline_m0']['logloss']}")
    print(f"TEST  {len(trades)} trades  return {w['return']:+.3f} CI {w['return_ci']}  peak exposure {w['peak_exposure']}  "
          f"per $ {w['return_per_dollar']}  maxDD {w['max_drawdown']}")
    print(f"      M0 same rules: return {backtest['baseline_m0']['return']:+.3f} CI {backtest['baseline_m0']['return_ci']}")


if __name__ == "__main__":
    main()
