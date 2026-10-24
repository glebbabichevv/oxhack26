"""Walk-forward over ALL of train: more out-of-sample markets per model, and paired comparisons vs M0.
-> integrations/model_eval/walk_forward.json + WALK_FORWARD.md

  python integrations/model_eval/walk_forward.py

Test is never touched. Train events (split_by_time at the shipped cutoff) are ordered by when they end and cut
into blocks at date boundaries: the first FIRST_FIT share is only ever fitted on, then each of N_BLOCKS blocks is
predicted by every member of evaluate_all.py fitted on everything that ended before the block started. Per block
the split is model.split_by_time (events stay whole, legs resolved before the block start are dropped) and the
playoff embargo (entry time >= block start). Predictions of all blocks are concatenated in time and scored once.

Why: validation alone is 4,768 markets (~1,300 V3 trades). V3 takes at most one trade per market, and only ~28%
of markets get one, so even all of train cannot give 10,000 V3 trades per model; walk-forward roughly quadruples
the scored markets. V0 (any horizon, any positive net edge) is reported too: it trades more markets.
Paired: every member vs M0 on the SAME resampled events (1,000 event-bootstrap draws, seed 0): Δ log loss and
Δ ¢ per $1. A pair CI that excludes 0 is a real difference; two separate CIs overlapping says little.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import evaluate_all as E  # noqa: E402
from evaluate_all import P, candidates, event_key, exposure, in_band, load_horizons, split_by_time  # noqa: E402

FIRST_FIT = 0.3
N_BLOCKS = 7
N_DRAWS = 1000
POLICIES = {"V3": dict(min_edge=0.01, enter_from=24), "V0": dict(min_edge=0.0, enter_from=None)}


def blocks(train):
    ends = train.groupby(event_key(train))["resolved_at"].max().sort_values()
    qs = np.linspace(FIRST_FIT, 1, N_BLOCKS + 1)
    return [ends.iloc[min(int(len(ends) * q), len(ends) - 1)].normalize() for q in qs]


def predictions(train):
    cuts = blocks(train)
    end = train.groupby(event_key(train))["resolved_at"].transform("max")
    out, info = [], []
    for i, (a, b) in enumerate(zip(cuts[:-1], cuts[1:])):
        last = i == len(cuts) - 2
        upto = train if last else train[end < b]
        fit, rows, start = split_by_time(upto, str(a.date()))
        print(f"block {i + 1}/{N_BLOCKS}: {a.date()} → {b.date()}  fit {fit.market_id.nunique():,} markets, "
              f"predict {rows.market_id.nunique():,}", flush=True)
        _, _, qf = E.period(fit, rows, start, score=False)
        qf["block"] = i + 1
        out.append(qf)
        info.append({"block": i + 1, "start": str(a.date()), "end": str(b.date()),
                     "n_fit_markets": int(fit.market_id.nunique()), "n_markets": int(qf.market_id.nunique())})
    return pd.concat(out, ignore_index=True).sort_values("resolved_at").reset_index(drop=True), info


def trades_for(d, name, policy):
    c = candidates(d, d[f"q_{name}"].to_numpy(), d[f"lo_{name}"].to_numpy(), d[f"hi_{name}"].to_numpy())
    if name == "mix_4_agree":
        c.loc[~d["agree"].to_numpy(), "action"] = "NO_TRADE"
    t = P.policy(c, **policy)
    if name == "M0_coherent" and len(t):
        t = t.sort_values("edge", ascending=False).groupby(event_key(t)).head(1).sort_values("resolved_at")
    if len(t):
        _, capped = exposure(t, t["kelly"].to_numpy())
        t = t.assign(stake=capped)[capped > 0]
    return t


def per_event(t, ev_index):
    """Per-event P&L and stake, aligned to ev_index (zeros where the model did not trade)."""
    if not len(t):
        return np.zeros(len(ev_index)), np.zeros(len(ev_index))
    g = pd.DataFrame({"pnl": t["stake"] * t["ret"], "st": t["stake"], "ev": t[event_key(t)]}).groupby("ev").sum()
    g = g.reindex(ev_index, fill_value=0.0)
    return g["pnl"].to_numpy(), g["st"].to_numpy()


def main():
    df = load_horizons(E.ROOT / "data" / "horizons.csv")
    train, _, cutoff = split_by_time(df, P.CUTOFF)
    d, info = predictions(train)
    q_names = [c[2:] for c in d if c.startswith("q_")]
    mix = ["M0", "M1_lite", "M2_lite", "beta_h"]
    qs = np.stack([d[f"q_{k}"].to_numpy() for k in mix])
    p = d["price_yes"].to_numpy()
    d["agree"] = (np.all(qs > p, 0) | np.all(qs < p, 0)) & (qs.max(0) - qs.min(0) < E.AGREE_SPREAD)
    for c in ("q", "lo", "hi"):
        d[f"{c}_mix_4_agree"] = d[f"{c}_mix_4"]
    names = q_names + ["mix_4_agree"]

    band = in_band(d["price_yes"])
    ev = d[event_key(d)].to_numpy()
    ev_index = pd.Index(pd.unique(ev))
    ev_code = ev_index.get_indexer(ev)
    y = d["outcome"].to_numpy()
    rng = np.random.default_rng(0)
    draws = rng.integers(0, len(ev_index), (N_DRAWS, len(ev_index)))
    counts = np.stack([np.bincount(r, minlength=len(ev_index)) for r in draws])  # times each event is drawn

    def ll_by_event(q):
        q = np.clip(q, E.EPS, 1 - E.EPS)
        l = -(y * np.log(q) + (1 - y) * np.log(1 - q))
        return np.bincount(ev_code[band], l[band], len(ev_index)), np.bincount(ev_code[band], minlength=len(ev_index))

    n_rows_ev = ll_by_event(p)[1]
    ll_ev = {k: ll_by_event(d[f"q_{k}"].to_numpy())[0] for k in names}
    res = {"protocol": __doc__.strip(), "cutoff": str(cutoff.date()), "blocks": info,
           "n_markets_scored": int(d.market_id.nunique()), "n_events_scored": int(len(ev_index)),
           "n_rows_scored": int(band.sum()), "models": {}}
    money = {pol: {k: per_event(trades_for(d, k, kw), ev_index) for k in names} for pol, kw in POLICIES.items()}
    ntr = {pol: {k: int(len(trades_for(d, k, kw))) for k in names} for pol, kw in POLICIES.items()}
    for k in names:
        s = E.scores(d, d[f"q_{k}"].to_numpy())
        ll_boot = counts @ ll_ev[k] / (counts @ n_rows_ev)
        ll_boot0 = counts @ ll_ev["M0"] / (counts @ n_rows_ev)
        row = {**s, "logloss_ci": [round(float(x), 5) for x in np.percentile(ll_boot, [5, 95])],
               "d_logloss_vs_M0": round(s["logloss"] - float(ll_ev["M0"].sum() / n_rows_ev.sum()), 5),
               "d_logloss_vs_M0_ci": [round(float(x), 5) for x in np.percentile(ll_boot - ll_boot0, [5, 95])]}
        # Only the rows this model actually moves off the price: is it better than the price THERE?
        moved = band & (np.abs(d[f"q_{k}"].to_numpy() - p) > 1e-6)
        if moved.any():
            qm = np.clip(d[f"q_{k}"].to_numpy(), E.EPS, 1 - E.EPS)
            pm = np.clip(p, E.EPS, 1 - E.EPS)
            diff = -(y * np.log(qm) + (1 - y) * np.log(1 - qm)) + (y * np.log(pm) + (1 - y) * np.log(1 - pm))
            dsum = np.bincount(ev_code[moved], diff[moved], len(ev_index))
            dn = np.bincount(ev_code[moved], minlength=len(ev_index))
            with np.errstate(invalid="ignore", divide="ignore"):
                boot = (counts @ dsum) / (counts @ dn)
            row["moved_rows"] = {"n_rows": int(moved.sum()), "n_events": int((dn > 0).sum()),
                                 "d_logloss_vs_market": round(float(diff[moved].mean()), 5),
                                 "ci": [round(float(x), 5) for x in np.nanpercentile(boot, [5, 95])]}
        else:
            row["moved_rows"] = {"n_rows": 0}
        for pol in POLICIES:
            pnl, st = money[pol][k]
            pnl0, st0 = money[pol]["M0"]
            if st.sum() == 0:
                row[pol] = {"n_trades": 0}
                continue
            with np.errstate(invalid="ignore", divide="ignore"):
                pd_boot = (counts @ pnl) / (counts @ st)
                pd_boot0 = (counts @ pnl0) / (counts @ st0)
            row[pol] = {"n_trades": ntr[pol][k], "per_dollar": round(float(pnl.sum() / st.sum()), 4),
                        "per_dollar_ci": [round(float(x), 4) for x in np.nanpercentile(pd_boot, [5, 95])],
                        "return": round(float(pnl.sum()), 3),
                        "d_per_dollar_vs_M0": round(float(pnl.sum() / st.sum() - pnl0.sum() / st0.sum()), 4),
                        "d_per_dollar_vs_M0_ci": [round(float(x), 4) for x in np.nanpercentile(pd_boot - pd_boot0, [5, 95])]}
        res["models"][k] = row
    (HERE / "walk_forward.json").write_text(json.dumps(res, indent=1), encoding="utf-8")

    def c(x):
        return f"{x * 100:+.1f}"

    md = ["# Walk-forward over all of train (generated by walk_forward.py)\n",
          f"{res['n_markets_scored']:,} markets / {res['n_events_scored']:,} events / {res['n_rows_scored']:,} "
          f"in-band rows scored out of sample, in {N_BLOCKS} time blocks (each fitted only on earlier events). "
          "Test not touched. Δ = model − M0 on the same resampled events (90% CI); "
          "for log loss lower is better, for ¢/$ higher is better.\n",
          "| model | log loss | Δ log loss vs M0 [90% CI] | V3 ¢/$ [90% CI] | V3 trades | Δ V3 ¢/$ vs M0 [CI] | V0 ¢/$ [CI] | V0 trades | Δ V0 ¢/$ vs M0 [CI] |",
          "|---|---|---|---|---|---|---|---|---|"]
    for k, r in res["models"].items():
        cells = [f"{r['logloss']:.4f}", f"{r['d_logloss_vs_M0'] * 1000:+.2f}e-3 [{r['d_logloss_vs_M0_ci'][0] * 1000:+.2f}, {r['d_logloss_vs_M0_ci'][1] * 1000:+.2f}]"]
        for pol in POLICIES:
            m = r[pol]
            if not m["n_trades"]:
                cells += ["–", "0", "–"]
                continue
            cells += [f"{c(m['per_dollar'])}¢ [{c(m['per_dollar_ci'][0])}, {c(m['per_dollar_ci'][1])}]", f"{m['n_trades']:,}",
                      f"{c(m['d_per_dollar_vs_M0'])}¢ [{c(m['d_per_dollar_vs_M0_ci'][0])}, {c(m['d_per_dollar_vs_M0_ci'][1])}]"]
        md.append(f"| {k} | " + " | ".join(cells) + " |")
    md += ["", "## Only the rows each model moves off the price (vs the market price on those rows)\n",
           "| model | rows moved | events | Δ log loss vs market [90% CI] |", "|---|---|---|---|"]
    for k, r in res["models"].items():
        mr = r["moved_rows"]
        md.append(f"| {k} | {mr['n_rows']:,} | {mr.get('n_events', 0):,} | " + (
            f"{mr['d_logloss_vs_market'] * 1000:+.2f}e-3 [{mr['ci'][0] * 1000:+.2f}, {mr['ci'][1] * 1000:+.2f}] |" if mr["n_rows"] else "– |"))
    md += ["", "Blocks: " + "; ".join(f"{b['start']}→{b['end']} ({b['n_markets']:,} markets, fit on {b['n_fit_markets']:,})" for b in info)]
    (HERE / "WALK_FORWARD.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote", HERE / "WALK_FORWARD.md")


if __name__ == "__main__":
    main()
