"""Policy playoff: one harness, identical costs / exposure / split, selection on VALIDATION only.

  .venv/bin/python playoff.py      # -> integrations/playoff/results.json (does not touch backend/results/)

Variants (same model M0 = model.py's simple calibrator, same decide(), same Polymarket taker fees):
  V0  current main policy: enter at the first (furthest) horizon whose net edge is > 0
  V1  V0 + minimum net edge 1¢  (Ayaz, PR #17)
  V2  V0 + do not enter earlier than 24 h before the scheduled end  (Mark, PR #13)
  V3  V1 + V2

Validation = model.select_model's split: the last 20% of TRAIN markets by resolution time; the model is
fitted on the first 80% (seed 0). Test = model.split_by_time at the shipped cutoff; the model is fitted on
all of train (exactly backend/results/model.json). Embargo (Ayaz) on both: a trade counts only if its entry
time (scheduled end - horizon) is at or after the start of the scored period.

Exposure rule sets, applied identically to every variant:
  "ours"  (primary)     ¼ Kelly capped 5%/trade; total open stake <= 1 starting bankroll; trades entering
                         at the same moment share the remaining room pro rata (model.exposure)
  "ayaz"  (sensitivity)  ¼ Kelly capped 5%/trade; <= 10% of the starting bankroll per event; total open stake
                         <= current equity (1 + P&L realised so far); same pro-rata tie rule
Returns are additive, in starting bankrolls. CIs: 90%, event bootstrap (1,000 resamples, seed 0).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "integrations"))

from model import (Calibrator, decide, equity_stats, event_key, exposure, fee_per_share, load_horizons,  # noqa: E402
                   payoff, per_dollar_ci, return_ci, select_model, split_by_time, trade_cost)

OUT = ROOT / "integrations" / "playoff"
CUTOFF = "2026-05-18"  # the shipped split (backend/results/backtest.json)
VARIANTS = {"V0": dict(min_edge=0.0, enter_from=None), "V1": dict(min_edge=0.01, enter_from=None),
            "V2": dict(min_edge=0.0, enter_from=24), "V3": dict(min_edge=0.01, enter_from=24)}
LABEL = {"V0": "current main", "V1": "+ min edge 1¢", "V2": "+ enter from 24h", "V3": "+ both"}
EVENT_CAP = 0.10


def entry_time(df):
    return (pd.to_datetime(df["end_date"], utc=True, format="ISO8601")
            - pd.to_timedelta(df["horizon_hours"], unit="h"))


def candidates(rows, model):
    """Every (market, horizon) row with Horizon's decision and cost (fees on)."""
    p = rows["price_yes"].to_numpy()
    q, lo, hi = model.predict(p, rows["horizon_hours"], rows["domain"])
    cost = trade_cost(rows["spread"].to_numpy(dtype=float), fee_per_share(rows), 0.01)
    action, kelly, edge = decide(p, q, cost, lo, hi)
    return rows.assign(q=q, cost=cost, action=action, kelly=kelly, edge=edge)


def policy(c, min_edge, enter_from):
    """One trade per market: the furthest horizon that passes the variant's filters, held to resolution."""
    t = c[(c["action"] != "NO_TRADE") & (c["edge"] > 0) & (c["edge"] >= min_edge)]
    if enter_from is not None:
        t = t[t["horizon_hours"] <= enter_from]
    t = t.sort_values("horizon_hours", ascending=False).groupby("market_id").head(1).copy()
    t["ret"] = payoff(t["action"].to_numpy(), t["price_yes"].to_numpy(), t["cost"].to_numpy(), t["outcome"].to_numpy())
    return t.sort_values("resolved_at")


def ayaz_caps(trades):
    """5%/trade (already in kelly), <= 10%/event (pro rata), open stake <= current equity (pro rata at ties)."""
    stake = trades["kelly"].to_numpy(float).copy()
    ev = trades[event_key(trades)].to_numpy()
    tot = pd.Series(stake).groupby(ev).transform("sum").to_numpy()
    stake = np.where(tot > EVENT_CAP, stake * EVENT_CAP / np.where(tot > 0, tot, 1), stake)
    entry = entry_time(trades).dt.tz_convert(None).to_numpy("datetime64[ns]")
    exit_ = pd.to_datetime(trades["resolved_at"], utc=True).dt.tz_convert(None).to_numpy("datetime64[ns]")
    ret = trades["ret"].to_numpy(float)
    out, open_, realised = np.zeros(len(stake)), [], 0.0  # open_: (exit, stake, pnl)
    order = np.argsort(entry, kind="stable")
    groups = np.split(order, np.flatnonzero(np.diff(entry[order]) != np.timedelta64(0, "ns")) + 1) if len(order) else []
    for g in groups:
        t0 = entry[g[0]]
        still = []
        for e, s, pnl in open_:
            if e <= t0:
                realised += pnl
            else:
                still.append((e, s, pnl))
        open_ = still
        room = max(0.0, 1.0 + realised - sum(s for _, s, _ in open_))
        want = float(stake[g].sum())
        scale = 1.0 if want <= room else (room / want if want > 0 else 0.0)
        for i in g:
            out[i] = stake[i] * scale
            if out[i] > 0:
                open_.append((exit_[i], out[i], out[i] * ret[i]))
    return out


def stats(trades, stake):
    rng = np.random.default_rng(0)
    keep = stake > 0
    t = trades[keep].assign(kelly=stake[keep])
    if not len(t):
        return {"n_trades": 0}
    s = equity_stats(t, t["kelly"].to_numpy())
    peak, _ = exposure(t, t["kelly"].to_numpy())
    staked = float(t["kelly"].sum())
    by_h = []
    for h, g in t.groupby("horizon_hours"):
        by_h.append({"horizon_hours": int(h), "n_trades": int(len(g)),
                     "return": round(float((g["kelly"] * g["ret"]).sum()), 4),
                     "per_dollar": round(float((g["kelly"] * g["ret"]).sum() / g["kelly"].sum()), 4)})
    return {"n_trades": int(len(t)), "return": s["return"], "return_ci": return_ci(t, rng),
            "per_dollar": round(float((t["kelly"] * t["ret"]).sum()) / staked, 4),
            "per_dollar_ci": per_dollar_ci(t, t["kelly"].to_numpy(), np.random.default_rng(0)),
            "hit_rate": s["hit_rate"], "max_drawdown": s["max_drawdown"], "peak_open_stake": round(peak, 3),
            "staked": round(staked, 3), "by_horizon": sorted(by_h, key=lambda x: -x["horizon_hours"])}


def run(rows, model, start):
    """All variants x both rule sets on one scored period (rows already restricted to it)."""
    rows = rows[entry_time(rows) >= start]  # embargo: no position opened before the period starts
    c = candidates(rows, model)
    out = {}
    for v, kw in VARIANTS.items():
        t = policy(c, **kw)
        _, ours = exposure(t, t["kelly"].to_numpy())
        out[v] = {"ours": stats(t, ours), "ayaz": stats(t, ayaz_caps(t)),
                  "uncapped": {k: stats(t, t["kelly"].to_numpy())[k] for k in ("n_trades", "return", "per_dollar", "peak_open_stake")}}
    return out


def main():
    df = load_horizons(ROOT / "data" / "horizons.csv")
    train, test, cutoff = split_by_time(df, CUTOFF)

    # Validation: select_model's split (last 20% of train markets by resolution time).
    order = train.groupby("market_id")["resolved_at"].first().sort_values()
    val_ids = set(order.index[int(len(order) * 0.8):])
    fit, val = train[~train["market_id"].isin(val_ids)], train[train["market_id"].isin(val_ids)]
    val_start = val["resolved_at"].min()
    m_val = Calibrator(["other"]).fit(fit, np.random.default_rng(0))
    m_test, sel = select_model(train, np.random.default_rng(0))  # exactly the shipped model (results/model.json)
    assert sel["chosen"] == "simple", sel
    # Validation picks; test is computed once per variant afterwards, for reporting only.
    validation = run(val, m_val, val_start)
    pick = max(VARIANTS, key=lambda v: validation[v]["ours"]["per_dollar"])
    pick_ayaz = max(VARIANTS, key=lambda v: validation[v]["ayaz"]["per_dollar"])
    testing = run(test, m_test, cutoff)

    OUT.mkdir(parents=True, exist_ok=True)
    res = {
        "protocol": __doc__.strip(),
        "cutoff": str(cutoff.date()), "validation_start": val_start.isoformat(),
        "n_validation_markets": len(val_ids), "n_test_markets": int(test["market_id"].nunique()),
        "variants": {v: {"label": LABEL[v], **kw} for v, kw in VARIANTS.items()},
        "selected_by_validation": {"rule": "highest validation per-$ return, 'ours' exposure rules", "winner": pick,
                                   "winner_under_ayaz_caps": pick_ayaz},
        "validation": validation, "test": testing,
    }
    (OUT / "results.json").write_text(json.dumps(res, indent=1))

    def line(v, part, rules):
        s = res[part][v][rules]
        return (f"| {v} {LABEL[v]} | {s['per_dollar'] * 100:+.1f}¢ [{s['per_dollar_ci'][0] * 100:+.1f}, {s['per_dollar_ci'][1] * 100:+.1f}] "
                f"| {s['return']:+.2f} [{s['return_ci'][0]:+.2f}, {s['return_ci'][1]:+.2f}] | {s['n_trades']:,} | "
                f"{s['max_drawdown']:.2f} | {s['peak_open_stake']:.2f} |")

    hdr = "| Variant | per $1 staked [90% CI] | bankrolls [90% CI] | trades | max DD | peak open |\n|---|---|---|---|---|---|"
    md = [f"# Policy playoff (generated by backend/playoff.py)\n",
          f"Validation picks **{pick}** ({LABEL[pick]}) on per-$ return under our exposure rules "
          f"(under Ayaz's caps it picks {pick_ayaz}). Test is shown for every variant but was not used to choose.\n"]
    for part, title in (("validation", f"Validation ({len(val_ids):,} markets, last 20% of train)"),
                        ("test", f"Test ({res['n_test_markets']:,} markets, after {res['cutoff']}, embargoed)")):
        for rules, rt in (("ours", "our caps (open stake <= 1 bankroll)"), ("ayaz", "Ayaz's caps (10%/event, open <= equity)")):
            md += [f"## {title}, {rt}\n", hdr] + [line(v, part, rules) for v in VARIANTS] + [""]
    md += ["## Test per-$ by entry horizon, our caps\n", "| Variant | " + " | ".join(f"{h}h" for h in (720, 168, 72, 24, 12)) + " |",
           "|---|---|---|---|---|---|"]
    for v in VARIANTS:
        bh = {b["horizon_hours"]: b for b in testing[v]["ours"]["by_horizon"]}
        md.append(f"| {v} | " + " | ".join(f"{bh[h]['per_dollar'] * 100:+.1f}¢ (n={bh[h]['n_trades']})" if h in bh else "–"
                                         for h in (720, 168, 72, 24, 12)) + " |")
    md += ["", "Fees: each market's Gamma feeSchedule (fees on). Same model for all variants. "
           "Returns additive, starting bankrolls. See results.json for hit rates, staked totals, uncapped numbers."]
    (OUT / "README.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
