"""Descriptive breakdowns on TEST (Gleb 00:40) — DESCRIPTIVE, NOT USED FOR SELECTION.

  python integrations/ensemble/breakdowns.py   # -> integrations/ensemble/summary.json (blocks domain, volume, price_bucket)

Shipped policy V3 (M0 fitted on all train, min edge 1c, entry within 24 h, fees on, "ours" exposure) and COH
(V3 + event coherence + one bet per event), on the embargoed test set, same code as ensemble.py. Per group:
trades, cents per $1 staked [90% event-bootstrap CI], hit rate, return in starting bankrolls.
Volume tiers use the market's LIFETIME volume (volume_usd): volume at the moment of entry is not in our
data, so a market's tier partly reflects trading after the entry. Price bucket = the price paid for the side
bought (YES: p, NO: 1 - p), before costs.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ensemble as E  # noqa: E402

VOL_BINS, VOL_LABELS = [0, 1e5, 1e6, np.inf], ["<$100k", "$100k-1M", ">$1M"]
PRICE_BINS, PRICE_LABELS = [0, 0.10, 0.25, 0.50, 1.0], ["<=10c", "10-25c", "25-50c", ">50c"]


def group_stats(t, col):
    out = []
    for g, x in t.groupby(col, observed=True):
        staked = x["stake"].sum()
        out.append({col: str(g), "n_trades": int(len(x)),
                    "per_dollar": round(float((x["stake"] * x["ret"]).sum() / staked), 4) if staked else None,
                    "per_dollar_ci": E.B.per_dollar_ci(x, x["stake"].to_numpy(), np.random.default_rng(0)),
                    "hit_rate": round(float((x["ret"] > 0).mean()), 4),
                    "return": round(float((x["stake"] * x["ret"]).sum()), 4)})
    return out


def main():
    df = E.B.load_horizons(E.ROOT / "data" / "horizons.csv")
    train, test, cutoff = E.B.split_by_time(df, E.P.CUTOFF)
    rows = E.scored_rows(test, cutoff).reset_index(drop=True)
    m0 = E.B.Calibrator(["other"]).fit(train, np.random.default_rng(0))
    q0, lo0, hi0 = m0.predict(rows["price_yes"].to_numpy(), rows["horizon_hours"], rows["domain"])
    qs = {"M0": q0, "BETA": q0}  # BETA unused here; trades_for builds its lookup table eagerly
    res = {"label": "descriptive - not used for selection", "protocol": __doc__.strip(), "test_from": str(cutoff.date())}
    for name in ("V3", "COH"):
        t, _ = E.trades_for(rows, name, qs, q0 - lo0, hi0 - q0)
        _, stake = E.B.exposure(t, t["kelly"].to_numpy())
        t = t.assign(stake=stake)
        t = t[t["stake"] > 0].copy()
        paid = np.where(t["action"] == "BUY_YES", t["price_yes"], 1 - t["price_yes"])
        t["volume_tier"] = pd.cut(t["volume_usd"].astype(float), VOL_BINS, labels=VOL_LABELS, right=False)
        t["price_bucket"] = pd.cut(paid, PRICE_BINS, labels=PRICE_LABELS, right=True)
        staked = t["stake"].sum()
        res[name] = {"overall": {"n_trades": int(len(t)), "per_dollar": round(float((t["stake"] * t["ret"]).sum() / staked), 4)},
                     "domain": group_stats(t, "domain"), "volume": group_stats(t, "volume_tier"),
                     "price_bucket": group_stats(t, "price_bucket")}
        print(name, res[name]["overall"], flush=True)
        for block in ("domain", "volume", "price_bucket"):
            for r in res[name][block]:
                print(f"  {block:12s} {list(r.values())[0]:14s} n={r['n_trades']:5d} {r['per_dollar'] * 100:+6.1f}c "
                      f"{[round(x * 100, 1) for x in r['per_dollar_ci']] if r['per_dollar_ci'] else None} hit {r['hit_rate']:.2f} "
                      f"ret {r['return']:+.2f}", flush=True)
    (HERE / "summary.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
