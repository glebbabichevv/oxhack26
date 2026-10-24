"""Reconcile 2026 papers a judge may cite (A's 01:20) -> integrations/robustness/literature.json

  python integrations/robustness/literature.py

Descriptive, TRAIN only (test untouched). A "buy" = taking the cheap side of a (market, horizon) row at its price:
YES if price < 50¢, else NO at 1 - price. Return per $1 = payout / price - 1, before fees and spread (the papers'
headline is gross), and after our cost model (max(spread/2, 1¢) + the market's taker fee) as a second column.
  equal-weight   mean over buys
  event-grouped  mean over parent events of each event's mean (Cardozo & Rivero-Wildemauwe's grouping)
CIs: 90%, event bootstrap (1,000 draws, seed 0).
(1) Cardozo & Rivero-Wildemauwe, arXiv 2609.12878: buys < 10¢ lose 6.3¢/$ equal-weighted, gain +4.1¢/$ event-grouped,
    absent in sports. Reproduced with their definition (all < 10¢ buys, no horizon filter), then conditioned on
    <= 24 h and the 10–35¢ band we trade.
(2) Qiu & Qiu, arXiv 2610.13593 (Polymarket weather): favourites overpriced most 1–12 h before the end, longshots
    slightly underpriced 3–9 h: cited only (we don't model weather separately).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import model as M  # noqa: E402
import playoff as P  # noqa: E402


def stats(g, col):
    ev = g["event"].to_numpy()
    r = g[col].to_numpy()
    per_ev = pd.Series(r).groupby(ev).agg(["sum", "count", "mean"])
    s, n, mu = per_ev["sum"].to_numpy(), per_ev["count"].to_numpy(), per_ev["mean"].to_numpy()
    rng = np.random.default_rng(0)
    idx = rng.integers(0, len(s), (1000, len(s)))
    eq = s[idx].sum(1) / n[idx].sum(1)
    grp = mu[idx].mean(1)
    f = lambda x: [round(float(v) * 100, 1) for v in np.percentile(x, [5, 95])]  # noqa: E731
    return {"n_buys": int(len(g)), "n_events": int(len(s)),
            "equal_weight_c_per_dollar": round(float(r.mean()) * 100, 1), "equal_weight_ci": f(eq),
            "event_grouped_c_per_dollar": round(float(mu.mean()) * 100, 1), "event_grouped_ci": f(grp)}


def main():
    df = M.load_horizons(ROOT / "data" / "horizons.csv")
    train, _, _ = M.split_by_time(df, P.CUTOFF)
    d = train.copy()
    p = d["price_yes"].to_numpy()
    cheap_yes = p < 0.5
    d["c"] = np.where(cheap_yes, p, 1 - p)
    d["won"] = np.where(cheap_yes, d["outcome"], 1 - d["outcome"])
    cost = M.trade_cost(d["spread"].to_numpy(dtype=float), M.fee_per_share(d), 0.01)
    d["gross"] = d["won"] / d["c"] - 1
    d["net"] = d["won"] / (d["c"] + cost) - 1
    d["event"] = d[M.event_key(d)].fillna(d["market_id"])
    d = d[d["c"] > 0.005]  # sub-half-cent prices are not tradable buys
    cells = {
        "their definition: all buys < 10¢, any horizon": d["c"] < 0.10,
        "< 10¢, within 24 h": (d["c"] < 0.10) & (d["horizon_hours"] <= 24),
        "10–35¢, any horizon": d["c"].between(0.10, 0.35),
        "10–35¢, within 24 h (what we trade)": d["c"].between(0.10, 0.35) & (d["horizon_hours"] <= 24),
    }
    out = {"note": __doc__.strip(), "split": "train only (events ended before the 2026-05-18 cutoff)", "cells": []}
    for name, mask in cells.items():
        for dom, dm in (("all", np.ones(len(d), bool)), ("sports", (d["domain"] == "sports").to_numpy()),
                        ("non-sports", (d["domain"] != "sports").to_numpy())):
            g = d[mask.to_numpy() & dm]
            if len(g) < 50:
                continue
            row = {"cell": name, "domain": dom, "gross": stats(g, "gross"), "after_our_costs": stats(g, "net")}
            out["cells"].append(row)
            gg = row["gross"]
            print(f"{name:42s} {dom:10s} n={gg['n_buys']:6,} eq {gg['equal_weight_c_per_dollar']:+6.1f}¢ {gg['equal_weight_ci']} "
                  f"grp {gg['event_grouped_c_per_dollar']:+6.1f}¢ {gg['event_grouped_ci']} | net eq "
                  f"{row['after_our_costs']['equal_weight_c_per_dollar']:+.1f}¢", flush=True)
    out["cited"] = [
        {"paper": "Cardozo & Rivero-Wildemauwe, arXiv 2609.12878 (Sep 2026)", "claim": "Polymarket buys < 10¢ lose 6.3¢/$ "
         "equal-weighted, gain +4.1¢/$ grouped by parent event; absent in sports", "status": "reproduced above"},
        {"paper": "Qiu & Qiu, arXiv 2610.13593 (Oct 2026)", "claim": "Polymarket weather: favourites overpriced most in the "
         "final 1–12 h (−11 pp at 6 h), longshots slightly underpriced at 3–9 h", "status": "cited: independent replication "
         "of near-resolution overconfidence in a domain we don't trade"},
        {"paper": "hrishi-tailor/prediction-market-calibration (GitHub, 2026)", "claim": "Polymarket slope 0.91–0.93 near "
         "resolution; Kalshi the opposite", "status": "cited; our slope ≈ 0.85 near resolution, same direction"}]
    (HERE / "literature.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
