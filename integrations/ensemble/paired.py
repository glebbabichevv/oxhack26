"""Paired event-bootstrap of COH - V3 on VAL2 (Gleb 23:30), BEFORE the test is opened.

  python integrations/ensemble/paired.py [--raw data/raw]   # -> integrations/ensemble/paired.json

Same members, split, fees, V3 rules and exposure as ensemble.py. Each bootstrap draw resamples VAL2 EVENTS
(the same draw for both candidates), then recomputes, on the trades and rows of the drawn events:
delta cents per $1 staked, delta total return (starting bankrolls), delta Brier (in-band rows), delta max
drawdown (resolved P&L in resolution order). Rule stated before the test (Gleb): if the 90% CI of delta
cents per $1 includes 0, COH is chosen on RISK grounds, not because it earns more.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ensemble as E  # noqa: E402

N_BOOT = 2000


def stake_trades(rows, name, qs, dlo, dhi):
    t, _ = E.trades_for(rows, name, qs, dlo, dhi)
    _, stake = E.B.exposure(t, t["kelly"].to_numpy())
    t = t.assign(stake=stake)
    return t[t["stake"] > 0]


def max_dd(t):
    if not len(t):
        return 0.0
    eq = 1 + np.cumsum((t["stake"] * t["ret"]).to_numpy())
    return float(np.max(np.maximum.accumulate(eq) - eq))


def metrics(t, rows, q):
    b = np.asarray(E.B.in_band(rows["price_yes"]), bool)
    y = rows["outcome"].to_numpy(float)
    staked = t["stake"].sum()
    return {"per_dollar": float((t["stake"] * t["ret"]).sum() / staked) if staked else np.nan,
            "return": float((t["stake"] * t["ret"]).sum()),
            "brier": float(np.mean((q[b] - y[b]) ** 2)),
            "max_dd": max_dd(t.sort_values("resolved_at"))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(E.ROOT / "data" / "raw"))
    a = ap.parse_args()
    df = E.B.load_horizons(E.ROOT / "data" / "horizons.csv")
    feats = E.build_table(E.ROOT / "data", Path(a.raw))
    train, _, _ = E.B.split_by_time(df, E.P.CUTOFF)
    order = train.groupby("market_id")["resolved_at"].first().sort_values()
    val_ids = set(order.index[int(len(order) * 0.8):])
    fit, val = train[~train["market_id"].isin(val_ids)], train[train["market_id"].isin(val_ids)]
    val = E.scored_rows(val, val["resolved_at"].min())
    qs, dlo, dhi = E.Members().fit(fit, feats).predict(val, feats)
    qs.update(E.load_mark(val, "val"))
    half = (val["resolved_at"] >= val["resolved_at"].quantile(0.5)).to_numpy()
    rows = val[half].reset_index(drop=True)
    q2 = E.sub(qs, half)
    lo2, hi2 = dlo[half], dhi[half]

    q_v3 = q2["M0"]
    q_coh = E.coherent(rows, q2["M0"])
    tv, tc = stake_trades(rows, "V3", q2, lo2, hi2), stake_trades(rows, "COH", q2, lo2, hi2)
    point = {"V3": metrics(tv, rows, q_v3), "COH": metrics(tc, rows, q_coh)}

    events = rows["event_slug"].unique()
    r_idx = rows.groupby("event_slug").indices
    tv_g, tc_g = tv.groupby("event_slug").indices, tc.groupby("event_slug").indices
    rng = np.random.default_rng(0)
    deltas = {k: [] for k in ("per_dollar", "return", "brier", "max_dd")}
    for _ in range(N_BOOT):
        draw = rng.choice(events, len(events))
        ri = np.concatenate([r_idx[e] for e in draw])
        vi = np.concatenate([tv_g[e] for e in draw if e in tv_g] or [np.array([], int)])
        ci = np.concatenate([tc_g[e] for e in draw if e in tc_g] or [np.array([], int)])
        mv = metrics(tv.iloc[vi], rows.iloc[ri], q_v3[ri])
        mc = metrics(tc.iloc[ci], rows.iloc[ri], q_coh[ri])
        for k in deltas:
            deltas[k].append(mc[k] - mv[k])
    ci90 = {k: [round(float(np.nanpercentile(v, 5)), 4), round(float(np.nanpercentile(v, 95)), 4)] for k, v in deltas.items()}
    delta = {k: round(point["COH"][k] - point["V3"][k], 4) for k in deltas}
    includes_zero = ci90["per_dollar"][0] <= 0 <= ci90["per_dollar"][1]
    res = {"protocol": __doc__.strip(), "n_boot": N_BOOT, "n_val2_events": int(len(events)),
           "n_trades": {"V3": int(len(tv)), "COH": int(len(tc))},
           "point": {c: {k: round(v, 4) for k, v in m.items()} for c, m in point.items()},
           "delta_coh_minus_v3": delta, "delta_ci90": ci90,
           "per_dollar_ci_includes_zero": bool(includes_zero),
           "verdict": ("COH chosen on RISK grounds (delta per $1 CI includes 0)" if includes_zero
                       else "COH earns more per $1 (delta CI excludes 0)")}
    (HERE / "paired.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("n_trades", "point", "delta_coh_minus_v3", "delta_ci90", "verdict")}, indent=1))


if __name__ == "__main__":
    main()
