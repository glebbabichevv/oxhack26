"""Exit before resolution (Gleb 23:35 + 23:50): sell at a later horizon instead of holding to the outcome.

  python integrations/ensemble/exit.py [--raw data/raw] [--test]   # -> integrations/ensemble/exit.json

Same model (M0, backend Calibrator), same entry rule as V3 (net edge >= 1c after costs, conservative band,
1/4 Kelly capped 5%), same split as ensemble.py (validation = last 20% of train markets; VAL1 / VAL2 = earlier /
later half by resolution time), same "ours" exposure (open stake <= 1 bankroll), with a position's exit time
replacing its resolution time while it is open.

Prices come from the hourly paths: the last print at or before the target time and at most 1 h before it
(prior-only). We have no historical order books, so selling "at the bid" = last print minus the cost; costs
on EVERY leg = max(quoted half-spread, 1c) + the market's taker fee at that price (Gamma fee schedule).

  HOLD(h)      enter at h hours before the scheduled end, hold to the outcome           (baseline per entry h)
  FIX(h, x)    enter at h, sell at x < h hours before the end; if the market resolved by then, or there is no
               print within 1 h of the exit time, the position is settled at the outcome
               pairs: (72,24) (72,12) (48,24) (48,12) (24,12)
  DYNAMIC      the V3 positions (horizons.csv rows, entry within 24 h); at every later hourly print recompute
               M0's q at that time-to-end and sell as soon as the sale value after costs >= q
               (YES: p - c >= q; NO: (1 - p) - c >= 1 - q): the market has caught up with Horizon. Else hold.
  V3           the shipped policy, held to resolution (reference)

Selection: the FIX pair with the best return / max drawdown on VAL1; then FIX*, DYNAMIC and V3 are compared on
VAL2. The test is opened (--test, once) only if FIX* or DYNAMIC beats V3 on VAL2 return / max drawdown.
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

B = E.B
PAIRS = [(72, 24), (72, 12), (48, 24), (48, 12), (24, 12)]
ENTRIES = sorted({h for h, _ in PAIRS}, reverse=True)
MAX_AGE = 3600.0


def load_paths(market_ids, raw):
    ids = pd.read_csv(raw / "id_map.csv", dtype={"gamma_id": str, "market_id": str}).set_index("market_id")["gamma_id"]
    out = {}
    for m in market_ids:
        f = raw / "hist" / f"{ids.get(m)}.json"
        if f.exists():
            pts = json.loads(f.read_text())
            if pts:
                a = np.array([[x["t"], x["p"]] for x in pts], float)
                a = a[np.argsort(a[:, 0])]
                out[m] = (a[:, 0], a[:, 1])
    return out


def price_at(paths, m, ts):
    if m not in paths:
        return np.nan
    t, p = paths[m]
    i = np.searchsorted(t, ts, side="right") - 1
    return p[i] if i >= 0 and ts - t[i] <= MAX_AGE else np.nan


def cost_at(meta, price):
    d = meta.assign(price_yes=price)
    return B.trade_cost(d["spread"].to_numpy(float), B.fee_per_share(d), 0.01)


def market_meta(rows):
    m = rows.sort_values("horizon_hours").drop_duplicates("market_id").copy()
    epoch = pd.Timestamp(0, tz="UTC")
    m["end_ts"] = (pd.to_datetime(m["end_date"], utc=True, format="ISO8601") - epoch).dt.total_seconds()
    m["res_ts"] = (pd.to_datetime(m["resolved_at"], utc=True) - epoch).dt.total_seconds()
    return m.reset_index(drop=True)


def enter(meta, paths, model, h):
    """V3's entry decision at h hours before the end, from the hourly path."""
    ts = meta["end_ts"].to_numpy() - h * 3600
    p = np.array([price_at(paths, m, t) for m, t in zip(meta["market_id"], ts)])
    open_ = meta["res_ts"].to_numpy() > ts
    ok = open_ & ~np.isnan(p)
    d = meta[ok].copy()
    d["price_yes"], d["entry_ts"], d["entry_h"] = p[ok], ts[ok], h
    q, lo, hi = model.predict(d["price_yes"].to_numpy(), np.full(len(d), h), d["domain"])
    d["cost"] = cost_at(d, d["price_yes"].to_numpy())
    d["action"], d["kelly"], d["edge"] = B.decide(d["price_yes"].to_numpy(), q, d["cost"].to_numpy(), lo, hi,
                                                   None, E.MIN_EDGE, None)
    return d[d["action"] != "NO_TRADE"].copy()


def settle(d):
    y = d["outcome"].to_numpy(float)
    return B.payoff(d["action"].to_numpy(), d["price_yes"].to_numpy(), d["cost"].to_numpy(), y)


def sell_return(d, px, cx):
    yes = (d["action"] == "BUY_YES").to_numpy()
    paid = np.where(yes, d["price_yes"] + d["cost"], 1 - d["price_yes"] + d["cost"])
    got = np.where(yes, px - cx, (1 - px) - cx)
    return got / paid - 1


def finish(d, ret, exit_ts, sold):
    d = d.assign(ret=ret, exit_ts=exit_ts, sold=sold)
    # exposure / equity use the exit time as the "resolution" while the position is open
    d["resolved_at"] = pd.to_datetime(d["exit_ts"], unit="s", utc=True)
    d["horizon_hours"] = (d["end_ts"] - d["entry_ts"]) / 3600
    return d


def hold(d):
    return finish(d, settle(d), d["res_ts"].to_numpy(), np.zeros(len(d), bool))


def fixed_exit(d, paths, x):
    ts = d["end_ts"].to_numpy() - x * 3600
    px = np.array([price_at(paths, m, t) for m, t in zip(d["market_id"], ts)])
    sellable = (d["res_ts"].to_numpy() > ts) & ~np.isnan(px)
    cx = cost_at(d, np.nan_to_num(px, nan=0.5))
    ret = np.where(sellable, sell_return(d, px, cx), settle(d))
    return finish(d, ret, np.where(sellable, ts, d["res_ts"].to_numpy()), sellable)


def dynamic_exit(d, paths, model):
    ret, ex_ts, sold = settle(d), d["res_ts"].to_numpy().copy(), np.zeros(len(d), bool)
    for i, r in enumerate(d.itertuples()):
        if r.market_id not in paths:
            continue
        t, p = paths[r.market_id]
        k = (t > r.entry_ts) & (t < r.res_ts) & (t < r.end_ts)
        if not k.any():
            continue
        t, p = t[k], p[k]
        hrs = np.maximum((r.end_ts - t) / 3600, 0.5)
        q = model.predict(p, hrs, np.full(len(p), r.domain))[0]
        c = cost_at(pd.DataFrame({"spread": np.full(len(p), r.spread), "domain": r.domain,
                                  **{k2: getattr(r, k2) for k2 in ("fees_enabled", "fee_rate", "fee_exponent")
                                     if hasattr(r, k2)}}), p)
        hit = (p - c >= q) if r.action == "BUY_YES" else ((1 - p) - c >= 1 - q)
        if hit.any():
            j = int(np.argmax(hit))
            paid = r.price_yes + r.cost if r.action == "BUY_YES" else 1 - r.price_yes + r.cost
            got = p[j] - c[j] if r.action == "BUY_YES" else (1 - p[j]) - c[j]
            ret[i], ex_ts[i], sold[i] = got / paid - 1, t[j], True
    return finish(d, ret, ex_ts, sold)


def stats(t):
    if not len(t):
        return {"n_trades": 0}
    _, stake = B.exposure(t, t["kelly"].to_numpy())
    t = t.assign(stake=stake)
    t = t[t["stake"] > 0].sort_values("resolved_at")
    pnl = (t["stake"] * t["ret"]).to_numpy()
    eq = 1 + np.cumsum(pnl)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[1.0], eq])) - np.concatenate([[1.0], eq])))
    staked = float(t["stake"].sum())
    ret = float(pnl.sum())
    return {"n_trades": int(len(t)), "per_dollar": round(ret / staked, 4) if staked else None,
            "per_dollar_ci": B.per_dollar_ci(t, t["stake"].to_numpy(), np.random.default_rng(0)),
            "return": round(ret, 4), "max_drawdown": round(dd, 4),
            "ret_per_dd": round(ret / dd, 3) if dd > 0 else None,
            "hit_rate": round(float((t["ret"] > 0).mean()), 4),
            "pnl_std_per_trade": round(float(np.std(t["ret"])), 4),
            "share_sold_before_end": round(float(t["sold"].mean()), 4)}


def run_all(sc, model, paths, which):
    rows, q0, dlo, dhi = sc
    meta = market_meta(rows)
    out, entries = {}, {h: enter(meta, paths, model, h) for h in ENTRIES}
    for h in ENTRIES:
        out[f"HOLD({h})"] = stats(hold(entries[h]))
    for h, x in PAIRS:
        if which is None or f"FIX({h},{x})" in which:
            out[f"FIX({h},{x})"] = stats(fixed_exit(entries[h], paths, x))
    v3, _ = E.trades_for(rows, "V3", {"M0": q0, "BETA": q0}, dlo, dhi)
    v3 = v3.merge(meta[["market_id", "end_ts", "res_ts"]], on="market_id")
    v3["entry_ts"] = v3["end_ts"] - v3["horizon_hours"] * 3600
    out["V3"] = stats(hold(v3))
    out["DYNAMIC"] = stats(dynamic_exit(v3, paths, model))
    coh, _ = E.trades_for(rows, "COH", {"M0": q0, "BETA": q0}, dlo, dhi)  # Gleb 01:05: exit on top of COH
    coh = coh.merge(meta[["market_id", "end_ts", "res_ts"]], on="market_id")
    coh["entry_ts"] = coh["end_ts"] - coh["horizon_hours"] * 3600
    out["COH"] = stats(hold(coh))
    out["COH+DYNAMIC"] = stats(dynamic_exit(coh, paths, model))
    return out


def with_q(rows, model):
    q0, lo0, hi0 = model.predict(rows["price_yes"].to_numpy(), rows["horizon_hours"], rows["domain"])
    return rows.reset_index(drop=True), q0, q0 - lo0, hi0 - q0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(E.ROOT / "data" / "raw"))
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    raw = Path(a.raw)
    df = B.load_horizons(E.ROOT / "data" / "horizons.csv")
    train, test, cutoff = B.split_by_time(df, E.P.CUTOFF)
    order = train.groupby("market_id")["resolved_at"].first().sort_values()
    val_ids = set(order.index[int(len(order) * 0.8):])
    fit, val = train[~train["market_id"].isin(val_ids)], train[train["market_id"].isin(val_ids)]
    val = E.scored_rows(val, val["resolved_at"].min())
    m_fit = B.Calibrator(["other"]).fit(fit, np.random.default_rng(0))
    paths = load_paths(set(val["market_id"]), raw)
    print(f"paths for {len(paths)} of {val['market_id'].nunique()} validation markets", flush=True)
    half = val["resolved_at"] >= val["resolved_at"].quantile(0.5)
    val1, val2 = with_q(val[~half], m_fit), with_q(val[half], m_fit)

    r1 = run_all(val1, m_fit, paths, None)
    best = max((k for k in r1 if k.startswith("FIX")), key=lambda k: r1[k].get("ret_per_dd") or -9)
    r2 = run_all(val2, m_fit, paths, {best})
    for part, r in (("VAL1", r1), ("VAL2", r2)):
        for k, v in r.items():
            print(f"{part} {k:10s} n={v.get('n_trades')} per$ {v.get('per_dollar')} {v.get('per_dollar_ci')} ret {v.get('return')} "
                  f"maxDD {v.get('max_drawdown')} ret/DD {v.get('ret_per_dd')} hit {v.get('hit_rate')} std {v.get('pnl_std_per_trade')} "
                  f"sold {v.get('share_sold_before_end')}", flush=True)
    base = r2["V3"].get("ret_per_dd") or 0
    beats = {k: (r2[k].get("ret_per_dd") or -9) > base for k in (best, "DYNAMIC")}
    coh_base = r2["COH"].get("ret_per_dd") or 0
    beats["COH+DYNAMIC vs COH"] = (r2["COH+DYNAMIC"].get("ret_per_dd") or -9) > coh_base
    res = {"protocol": __doc__.strip(), "fixed_pair_chosen_on_val1": best, "val1": r1, "val2": r2,
           "beats_v3_on_val2_ret_per_dd": beats, "test_opened": False}
    if a.test and any(beats.values()):
        m_all = B.Calibrator(["other"]).fit(train, np.random.default_rng(0))
        tpaths = load_paths(set(test["market_id"]), raw)
        rows_t = with_q(E.scored_rows(test, cutoff), m_all)
        res["test"] = run_all(rows_t, m_all, tpaths, {best})
        res["test_opened"] = True
        for k, v in res["test"].items():
            print(f"TEST {k:10s} n={v.get('n_trades')} per$ {v.get('per_dollar')} {v.get('per_dollar_ci')} ret {v.get('return')} "
                  f"maxDD {v.get('max_drawdown')} ret/DD {v.get('ret_per_dd')} hit {v.get('hit_rate')}", flush=True)
    elif a.test:
        print("no exit variant beats V3 on VAL2 risk-adjusted: test NOT opened", flush=True)
    (HERE / "exit.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
