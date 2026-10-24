"""Robustness for COH (Gleb 01:10), same methods and settings as TheMarkz3's integrations/robustness/robustness.py.

  python integrations/ensemble/coh_robust.py [--raw data/raw] [--draws 1000]   # -> integrations/ensemble/coh_robust.json

(1) monthly_coh  walk-forward over the whole history: for each month m, M0 refitted on every event that ended
                 before m (split_by_time at m's first day); V3 and COH trade month m's markets (entry on/after the 1st).
(2) placebo_coh  test set, shipped model (M0 on all train): "prices are right" Bernoulli null, outcomes redrawn as
                 Bernoulli(price) for COH's real trades and stakes; p = share of draws >= the real cents per $1.
(3) dsr_coh      deflated Sharpe (Bailey & Lopez de Prado 2014) of COH's per-trade test P&L, trials = the 10 VAL2
                 candidates of ensemble.py + V0-V3 of backend/playoff.py on validation (their per-trade Sharpes).
(4) leg_choice   descriptive, test: COH takes the leg with the largest net edge in each event; rerun with a RANDOM
                 eligible leg per event (200 draws) - is the gain from one-bet-per-event or from picking the leg?
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ensemble as E  # noqa: E402

B, P = E.B, E.P


def m0_qs(model, rows):
    q0, lo0, hi0 = model.predict(rows["price_yes"].to_numpy(), rows["horizon_hours"], rows["domain"])
    return {"M0": q0, "BETA": q0}, q0 - lo0, hi0 - q0


def placed(rows, name, qs, dlo, dhi):
    t, _ = E.trades_for(rows, name, qs, dlo, dhi)
    if not len(t):
        return t
    _, st = B.exposure(t, t["kelly"].to_numpy())
    t = t.assign(stake=st)
    return t[t["stake"] > 0]


def per_dollar(t):
    return float((t["stake"] * t["ret"]).sum() / t["stake"].sum()) if len(t) else None


def monthly(df):
    end = df.groupby(B.event_key(df))["resolved_at"].transform("max")
    months = pd.date_range(df["resolved_at"].min().normalize().replace(day=1), df["resolved_at"].max(), freq="MS")
    out = []
    for m0, m1 in zip(months[:-1], months[1:]):
        fit, rows, start = B.split_by_time(df[end < m1], str(m0.date()))
        if fit["market_id"].nunique() < 2000 or not len(rows):
            continue
        model = B.Calibrator(["other"]).fit(fit, np.random.default_rng(0))
        rows = E.scored_rows(rows, start).reset_index(drop=True)
        if not len(rows):
            continue
        qs, dlo, dhi = m0_qs(model, rows)
        r = {"month": str(m0.date())[:7], "n_markets": int(rows["market_id"].nunique())}
        for name in ("V3", "COH"):
            t = placed(rows, name, qs, dlo, dhi)
            r[name] = {"n_trades": int(len(t)), "per_dollar": None if not len(t) else round(per_dollar(t), 4),
                       "per_dollar_ci": B.per_dollar_ci(t, t["stake"].to_numpy(), np.random.default_rng(0)) if len(t) else None,
                       "return": round(float((t["stake"] * t["ret"]).sum()), 4) if len(t) else 0.0}
        out.append(r)
        print(f"  {r['month']}: V3 {r['V3']['per_dollar']} (n={r['V3']['n_trades']})  COH {r['COH']['per_dollar']} "
              f"(n={r['COH']['n_trades']})", flush=True)
    return out


def placebo(t, draws):
    st, p, cost, act = t["stake"].to_numpy(), t["price_yes"].to_numpy(), t["cost"].to_numpy(), t["action"].to_numpy()

    def pdol(y):
        ret = np.where(act == "BUY_YES", y / (p + cost) - 1, (1 - y) / (1 - p + cost) - 1)
        return float((st * ret).sum() / st.sum())

    real = pdol(t["outcome"].to_numpy())
    rng = np.random.default_rng(0)
    null = np.array([pdol((rng.random(len(t)) < p).astype(float)) for _ in range(draws)])
    return {"real_per_dollar": round(real, 4), "n_trades": int(len(t)), "draws": draws,
            "null_mean": round(float(null.mean()), 4), "null_p5": round(float(np.percentile(null, 5)), 4),
            "null_p50": round(float(np.percentile(null, 50)), 4), "null_p95": round(float(np.percentile(null, 95)), 4),
            "p_value": round(float((null >= real).mean()), 4)}


def sharpe(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1)), float(skew(x)), float(kurtosis(x, fisher=False))


def dsr(x, trial_srs):
    sr, g3, g4 = sharpe(x)
    T = len(x)
    den = np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr * sr)
    n, v, gamma = len(trial_srs), float(np.var(trial_srs, ddof=1)), 0.5772156649
    sr0 = np.sqrt(v) * ((1 - gamma) * norm.ppf(1 - 1 / n) + gamma * norm.ppf(1 - 1 / (n * np.e)))
    return {"n_trades": T, "sharpe_per_trade": round(sr, 4), "skew": round(g3, 3), "kurtosis": round(g4, 3),
            "psr_true_sharpe_gt_0": round(float(norm.cdf(sr * np.sqrt(T - 1) / den)), 6), "n_trials": n,
            "var_trial_sharpe": round(v, 6), "sr0_expected_max_under_null": round(float(sr0), 4),
            "dsr": round(float(norm.cdf((sr - sr0) * np.sqrt(T - 1) / den)), 6)}


def trial_sharpes(df, train, raw):
    """Per-trade Sharpe on validation of every trial: ensemble.py's 10 VAL2 candidates + playoff V0-V3."""
    srs = {}
    order = train.groupby("market_id")["resolved_at"].first().sort_values()
    val_ids = set(order.index[int(len(order) * 0.8):])
    fit, val = train[~train["market_id"].isin(val_ids)], train[train["market_id"].isin(val_ids)]
    vstart = val["resolved_at"].min()
    m = B.Calibrator(["other"]).fit(fit, np.random.default_rng(0))
    c = P.candidates(val[P.entry_time(val) >= vstart], m)
    for v, kw in P.VARIANTS.items():
        t = P.policy(c, **kw)
        _, cap = B.exposure(t, t["kelly"].to_numpy())
        srs[f"playoff_{v}"] = sharpe(cap[cap > 0] * t["ret"].to_numpy()[cap > 0])[0]
    feats = E.build_table(E.ROOT / "data", raw)
    val = E.scored_rows(val, vstart)
    qs, dlo, dhi = E.Members().fit(fit, feats).predict(val, feats)
    qs.update(E.load_mark(val, "val"))
    half = (val["resolved_at"] >= val["resolved_at"].quantile(0.5)).to_numpy()
    keys = E.ensemble_keys(qs)
    qs["POOL"] = E.LogPool(keys).fit(val[~half], E.sub(qs, ~half)).predict(val, qs)
    rows2, q2 = val[half].reset_index(drop=True), E.sub(qs, half)
    res = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    for name in res["candidates"]:
        thr = res["validation_second_half"][name].get("threshold")
        t, _ = E.trades_for(rows2, name, q2, dlo[half], dhi[half], thr)
        if len(t) < 30:
            continue
        _, cap = B.exposure(t, t["kelly"].to_numpy())
        srs[f"val2_{name}"] = sharpe(cap[cap > 0] * t["ret"].to_numpy()[cap > 0])[0]
    return srs


def leg_choice(rows, qs, dlo, dhi, draws=200):
    """COH's trades vs the same rule with a random eligible leg per event (descriptive)."""
    p = rows["price_yes"].to_numpy(float)
    q = E.coherent(rows, qs["M0"])
    lo, hi = np.clip(q - dlo, 0, 1), np.clip(q + dhi, 0, 1)
    cost = B.trade_cost(rows["spread"].to_numpy(float), B.fee_per_share(rows), 0.01)
    action, kelly, edge = B.decide(p, q, cost, lo, hi, rows["horizon_hours"].to_numpy(), E.MIN_EDGE, E.ENTER_FROM)
    c = rows.assign(q=q, cost=cost, action=action, kelly=kelly, edge=edge)
    elig = c[(c["action"] != "NO_TRADE") & (c["edge"] > 0)].sort_values("horizon_hours", ascending=False)
    elig = elig.groupby("market_id").head(1).copy()
    elig["ret"] = B.payoff(elig["action"].to_numpy(), elig["price_yes"].to_numpy(), elig["cost"].to_numpy(),
                           elig["outcome"].to_numpy())
    key = B.event_key(elig)

    def score(t):
        _, st = B.exposure(t, t["kelly"].to_numpy())
        t = t.assign(stake=st)
        t = t[t["stake"] > 0]
        return per_dollar(t), len(t)

    best = score(elig.sort_values("edge", ascending=False).groupby(key).head(1).sort_values("resolved_at"))
    every = score(elig.sort_values("resolved_at"))
    rng = np.random.default_rng(0)
    rand = []
    for _ in range(draws):
        pick = elig.assign(_r=rng.random(len(elig))).sort_values("_r").groupby(key).head(1).sort_values("resolved_at")
        rand.append(score(pick)[0])
    rand = np.array(rand)
    return {"largest_edge_leg": {"per_dollar": round(best[0], 4), "n_trades": best[1]},
            "random_leg": {"mean": round(float(rand.mean()), 4), "p5": round(float(np.percentile(rand, 5)), 4),
                           "p95": round(float(np.percentile(rand, 95)), 4), "draws": draws},
            "all_eligible_legs_no_event_cap": {"per_dollar": round(every[0], 4), "n_trades": every[1]}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(E.ROOT / "data" / "raw"))
    ap.add_argument("--draws", type=int, default=1000)
    a = ap.parse_args()
    df = B.load_horizons(E.ROOT / "data" / "horizons.csv")
    train, test, cutoff = B.split_by_time(df, P.CUTOFF)
    res = {"protocol": __doc__.strip()}

    print("(1) monthly walk-forward", flush=True)
    res["monthly"] = monthly(df)
    mon = [r for r in res["monthly"] if r["COH"]["per_dollar"] is not None]
    res["monthly_summary"] = {k: {"months": len(mon), "positive": sum(r[k]["per_dollar"] > 0 for r in mon if r[k]["per_dollar"] is not None),
                                  "ci_below_0": sum((r[k]["per_dollar_ci"] or [0, 0])[1] < 0 for r in mon)} for k in ("V3", "COH")}
    print(res["monthly_summary"], flush=True)

    m_all = B.Calibrator(["other"]).fit(train, np.random.default_rng(0))
    rows = E.scored_rows(test, cutoff).reset_index(drop=True)
    qs, dlo, dhi = m0_qs(m_all, rows)
    t_coh = placed(rows, "COH", qs, dlo, dhi)
    print(f"(2) placebo on {len(t_coh)} COH test trades", flush=True)
    res["placebo_coh"] = placebo(t_coh, a.draws)
    print(res["placebo_coh"], flush=True)

    print("(3) deflated Sharpe", flush=True)
    srs = trial_sharpes(df, train, Path(a.raw))
    res["dsr_coh"] = {**dsr((t_coh["stake"] * t_coh["ret"]).to_numpy(), list(srs.values())), "trials": srs}
    print({k: v for k, v in res["dsr_coh"].items() if k != "trials"}, flush=True)

    print("(4) leg choice", flush=True)
    res["leg_choice"] = leg_choice(rows, qs, dlo, dhi)
    print(res["leg_choice"], flush=True)
    (HERE / "coh_robust.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
