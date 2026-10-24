"""Model v2: playoff on validation, minimum edge tuned on validation (Kelly fixed at x0.25), one out-of-time test.

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

from decision import apply_caps, decide, earliest_trades, trade_cost  # noqa: E402
from features import book_features, build_table, by_date, path_stats  # noqa: E402
from models import in_band, make  # noqa: E402

CUTOFF = "2026-05-18"
KELLY_MULT = 0.25  # house rule: quarter Kelly (additive P&L rises with stake, so it is not tuned)
HALF_KELLY = 0.5  # reported as a variant only
EDGE_GRID = (0.0, 0.01, 0.02, 0.03)
TIE = 0.0005
MIN_HORIZON_H = 12  # shortest trained horizon; live cards closer than this get no call


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
    """Returns ((name, kwargs), scores); M1's C is picked here too; earliest candidate within TIE of the lowest validation log loss."""
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
    """Minimum edge chosen on validation P&L after caps; Kelly fixed at KELLY_MULT."""
    q, lo, hi = model.predict(val)
    c = costs(val)
    grid = []
    for e in EDGE_GRID:
        t = apply_caps(earliest_trades(val, q, lo, hi, c, e, KELLY_MULT))
        grid.append({"kelly_mult": KELLY_MULT, "min_edge": e, "n_trades": int(len(t)),
                     "pnl": round(float((t["stake"] * t["ret"]).sum()), 4)})
    best = max(grid, key=lambda g: (g["pnl"], g["min_edge"]))
    return KELLY_MULT, best["min_edge"], grid


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


def embargo(t, cutoff):
    """Test trades must enter on or after the cutoff: nothing opened before it is scored."""
    return t[t["entry_at"] >= pd.Timestamp(cutoff, tz="UTC")]


def policy(model, df, kelly_mult, min_edge, cost, cutoff=None, caps=True):
    q, lo, hi = model.predict(df)
    t = earliest_trades(df, q, lo, hi, cost, min_edge, kelly_mult)
    if cutoff is not None:
        t = embargo(t, cutoff)
    t = apply_caps(t) if caps else t.assign(stake=t["kelly"])
    return t.sort_values("resolved_at"), q


def ladder_row(label, t):
    pnl, staked = float((t["stake"] * t["ret"]).sum()), float(t["stake"].sum())
    return {"label": label, "n_trades": int(len(t)), "return": round(pnl, 4),
            "return_per_dollar": round(pnl / staked, 4) if staked else None}


def decomposition(model, test, min_edge, trades, half):
    """Test-set ladder from the old backend rules to the headline policy, one change at a time."""
    no_fees = trade_cost(test["price_yes"], test["spread"], np.zeros(len(test), bool), test["domain"])
    a, _ = policy(model, test, KELLY_MULT, 0.0, no_fees, CUTOFF, caps=False)
    b, _ = policy(model, test, KELLY_MULT, 0.0, costs(test), CUTOFF, caps=False)
    c, _ = policy(model, test, KELLY_MULT, 0.0, costs(test), CUTOFF)
    return [ladder_row("old rules: 1c cost, x0.25 Kelly, no min edge, no caps", a),
            ladder_row("+ Polymarket fees", b),
            ladder_row("+ caps (5%/trade, 10%/event, equity-capped bankroll)", c),
            ladder_row(f"+ min edge {min_edge * 100:.0f}c (chosen on validation)", trades),
            ladder_row("+ half Kelly (variant)", half)]


def summary(t, rng):
    s = backend.equity_stats(t, t["stake"].to_numpy())
    s["return_ci"] = backend.return_ci(t, rng)
    s["peak_exposure"] = peak_exposure(t)
    staked = float(t["stake"].sum())
    s["return_per_dollar"] = round(float((t["stake"] * t["ret"]).sum()) / staked, 4) if staked else None
    return s


def live_table(data_dir, raw_dir):
    live = pd.read_csv(data_dir / "live.csv")
    live = live[live["price_yes"].between(0, 1, inclusive="neither")].reset_index(drop=True)
    live["domain"] = live["domain"].fillna("other").str.lower()
    live["horizon_hours"] = live["hours_to_resolution"]
    live["by_date"] = by_date(live["question"])
    live = live.join(book_features(live))
    now = pd.to_datetime(live["fetched_at"], utc=True, format="mixed")
    stats = []
    for r, ts in zip(live.itertuples(), now):
        f = raw_dir / "live_hist" / f"{r.market_id}.json"
        pts = json.loads(f.read_text()) if f.exists() else []
        t = np.array([x["t"] for x in pts], float)
        p = np.array([x["p"] for x in pts], float)
        stats.append(path_stats(t, p, ts.timestamp()))
    live[["mom24", "mom72", "vol72"]] = np.array(stats) if stats else np.zeros((0, 3))
    live["fees_on"] = live["fees_enabled"].astype(bool)
    return live


def live_report(model, live, kelly_mult, min_edge, n_trades=30, n_no_trade=15):
    p = live["price_yes"].to_numpy()
    q, lo, hi = model.predict(live)
    c = costs(live)
    action, kelly, edge = decide(p, q, lo, hi, c, min_edge, kelly_mult)
    short = live["hours_to_resolution"].to_numpy(float) < MIN_HORIZON_H
    action = np.where(short, "NO_TRADE", action)
    kelly = np.where(short, 0.0, kelly)
    out = []
    for i, r in enumerate(live.itertuples()):
        if short[i]:
            reason = "Outside the trained horizon range (12h-30d): no call"
        elif not in_band(p[i]):
            reason = f"Market at {p[i]:.1%}: too close to certain, costs exceed any edge"
        elif action[i] == "NO_TRADE":
            reason = (f"Model {q[i]:.0%} (range {lo[i]:.0%}-{hi[i]:.0%}) vs market {p[i]:.0%}: "
                      f"gap is inside the model's uncertainty plus {c[i] * 100:.1f}c cost incl. fees")
        else:
            reason = (f"{backend.horizon_label(r.hours_to_resolution)} out, {r.domain}: model {q[i]:.0%} vs market "
                      f"{p[i]:.0%}, net edge {edge[i] * 100:.1f}c after fees")
        out.append({"market_id": str(r.market_id), "question": r.question, "domain": r.domain,
                    "price_yes": round(float(p[i]), 4), "hours_to_resolution": float(r.hours_to_resolution),
                    "q_yes": round(float(q[i]), 4), "q_low": round(float(lo[i]), 4), "q_high": round(float(hi[i]), 4),
                    "edge": round(float(q[i] - p[i]), 4), "net_edge": round(float(edge[i]), 4), "cost": round(float(c[i]), 4),
                    "action": str(action[i]), "kelly_fraction": round(float(kelly[i]), 4), "reason": reason,
                    "url": r.url, "volume_usd": float(r.volume_usd)})
    trades = sorted((x for x in out if x["action"] != "NO_TRADE"), key=lambda x: -x["net_edge"])[:n_trades]
    no_trade = sorted((x for x in out if x["action"] == "NO_TRADE" and in_band(x["price_yes"])),
                      key=lambda x: -x["volume_usd"])[:n_no_trade]
    return trades + no_trade


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
    trades, q = policy(model, test, kelly_mult, min_edge, c, CUTOFF)
    zero, _ = policy(model, test, kelly_mult, min_edge, np.zeros(len(test)), CUTOFF)
    half, _ = policy(model, test, HALF_KELLY, min_edge, c, CUTOFF)
    m0 = model if best == "M0" else make("M0").fit(train)
    m0_trades, q0 = (trades, q) if best == "M0" else policy(m0, test, kelly_mult, min_edge, c, CUTOFF)
    cut = pd.Timestamp(CUTOFF, tz="UTC")
    assert all((t["entry_at"] >= cut).all() for t in (trades, zero, half, m0_trades)), "test embargo violated"
    y = test["outcome"].to_numpy()

    cal = backend.calibration_report(test, q)
    (out / "calibration.json").write_text(json.dumps({"cutoff": CUTOFF, "by_domain": cal}, indent=1))
    fails, worst = backend.failures(test, q, cal, trades)
    fails += [{"kind": "null_strategy", "domain": "all", "horizon_hours": None, "n": None, "text": s} for s in NULL_STRATEGIES]
    _, lo_t, hi_t = model.predict(test)
    by_h = backend.by_horizon(test, q, c, lo_t, hi_t)  # descriptive: backend's decide() per fixed horizon, with our fee-aware costs
    with_costs = summary(trades, rng)
    dom_rows = backend.by_domain(trades, rng)
    for r in dom_rows:
        g = trades[trades["domain"] == r["domain"]]
        st = float(g["stake"].sum())
        r["return_per_dollar"] = round(float((g["stake"] * g["ret"]).sum()) / st, 4) if st else None
    without_costs = summary(zero, rng)
    m0_scores = {"logloss": round(backend.log_loss(q0, y), 4), "brier": round(backend.brier(q0, y), 4)}
    baseline_m0 = {**m0_scores, **(with_costs if best == "M0" else summary(m0_trades, rng))}
    half_kelly = summary(half, rng)
    backtest = {
        "cutoff": CUTOFF, "model": "v2",
        "n_train_markets": int(train.market_id.nunique()), "n_test_markets": int(test.market_id.nunique()),
        "n_trades": int(len(trades)),
        "model_selection": {"chosen": best, "params": best_kw, "val_logloss": scores, "val_markets": int(val.market_id.nunique()),
                            "kelly_mult": kelly_mult, "min_edge": min_edge, "grid": grid},
        "with_costs": with_costs,
        "return_ci": with_costs["return_ci"],
        "by_domain": dom_rows,
        "without_costs": without_costs,
        "variants": {"half_kelly": half_kelly},
        "decomposition": decomposition(model, test, min_edge, trades, half),
        "naive_favourite": backend.naive_favourite(test, c),
        "baseline_m0": baseline_m0,
        "overall": {"brier_market": round(backend.brier(test["price_yes"], y), 4), "brier_model": round(backend.brier(q, y), 4),
                    "logloss_market": round(backend.log_loss(test["price_yes"], y), 4), "logloss_model": round(backend.log_loss(q, y), 4)},
        "by_horizon": by_h,
        "failures": fails, "worst_trades": worst,
        "assumptions": [
            f"Split by time at {CUTOFF}: train on events that ended before it; test on markets of the remaining events that resolved after it.",
            "Model and minimum edge chosen on the last 20% of train events; the test set is scored once.",
            f"Test trades must enter on or after the cutoff (no position opened before {CUTOFF} is scored).",
            "Cost per contract = max(spread/2, 1c) + Polymarket taker fee rate x p x (1-p) on markets with fees enabled (today's rates, whole period).",
            "One trade per market at the earliest qualifying horizon, held to resolution; fills at the historical price.",
            "Stakes capped at 5% per trade, 10% per event, and open stakes of at most min(1.0, 1 + realised P&L) bankrolls; P&L additive.",
            f"Validation chose a {min_edge*100:.0f}c minimum edge.",
            "Kelly is fixed at the house x0.25; additive P&L rises with stake size, so tuning the multiplier on P&L would just pick the largest one. Half Kelly is shown in variants.half_kelly.",
            "without_costs is a separate policy run with zero costs (different trades), not the same trades without fees.",
            "Max drawdown is measured on resolved P&L in resolution order, not mark-to-market.",
            "Live kelly_fraction is per card; it does not apply the per-event or bankroll caps.",
            "by_horizon is descriptive: each horizon traded on its own with the backend's quarter-Kelly rule, no minimum edge and no caps - it is not the headline policy.",
            "naive_favourite uses flat 2% stakes with no caps, so compare its sign, not its size.",
            "volume_usd is not a feature (lifetime volume would leak trading after the horizon).",
        ],
    }
    (out / "backtest.json").write_text(json.dumps(backtest, indent=1, default=str))
    w = backtest["with_costs"]
    if (Path(a.data) / "live.csv").exists():
        live = live_report(model, live_table(Path(a.data), Path(a.raw)), kelly_mult, min_edge)
        (out / "live.json").write_text(json.dumps(live, indent=1))
        print(f"live: {sum(x['action'] != 'NO_TRADE' for x in live)} trades of {len(live)} cards")
    print(f"TEST  logloss market {backtest['overall']['logloss_market']}  {best} {backtest['overall']['logloss_model']}  M0 {backtest['baseline_m0']['logloss']}")
    print(f"TEST  {len(trades)} trades  return {w['return']:+.3f} CI {w['return_ci']}  peak exposure {w['peak_exposure']}  "
          f"per $ {w['return_per_dollar']}  maxDD {w['max_drawdown']}")
    print(f"      M0 same rules: return {backtest['baseline_m0']['return']:+.3f} CI {backtest['baseline_m0']['return_ci']}")
    print(f"      half Kelly variant: return {half_kelly['return']:+.3f} CI {half_kelly['return_ci']}  "
          f"maxDD {half_kelly['max_drawdown']}  peak exposure {half_kelly['peak_exposure']}")
    for r in backtest["decomposition"]:
        print(f"      ladder: {r['label']}: {r['n_trades']} trades, return {r['return']:+.3f}, per $ {r['return_per_dollar']}")


if __name__ == "__main__":
    main()
