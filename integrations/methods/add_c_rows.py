"""C's results -> flat rows in integrations/methods/summary.json (A's 23:55 format), merge-safe.

  python integrations/methods/add_c_rows.py

Rows: {block, name, value, lo, hi, n, split, note}. Rewrites only rows whose `source` is "C"; rows from
anyone else in the file are kept as they are. Reads integrations/robustness/results.json and
integrations/model_eval/walk_forward.json (both from PR #18).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "integrations" / "methods" / "summary.json"


def row(block, name, value, lo=None, hi=None, n=None, split="", note=""):
    r = lambda x: None if x is None else round(float(x), 6)  # noqa: E731
    return {"block": block, "name": name, "value": r(value), "lo": r(lo), "hi": r(hi), "n": n, "split": split,
            "note": note, "source": "C"}


def main():
    rob = json.loads((ROOT / "integrations/robustness/results.json").read_text(encoding="utf-8"))
    wf = json.loads((ROOT / "integrations/model_eval/walk_forward.json").read_text(encoding="utf-8"))
    rows = []
    for m in rob["by_month"]:
        if m.get("n_trades", 0):
            lo, hi = m["per_dollar_ci"]
            rows.append(row("monthly", m["month"], m["per_dollar"], lo, hi, m["n_trades"], "walkforward",
                            f"¢/$ after fees, V3, M0 refitted on events ended before the month; "
                            f"Brier market {m['brier_market']} vs model {m['brier_model']}"))
    s = rob["by_month_summary"]
    rows.append(row("monthly", "months_positive", s["months_positive"], n=s["months_with_30_plus_trades"],
                    split="walkforward", note=f"of months with >=30 trades; CI>0 in {s['months_ci_above_0']}, "
                                              f"CI<0 in {s['months_ci_below_0']}"))
    p = rob["placebo"]
    rows.append(row("placebo", "real", p["real_per_dollar"], n=p["n_trades"], split="test",
                    note="shipped M0+V3, ¢/$ after fees"))
    for key, label in (("prices_are_right", "null: outcome ~ Bernoulli(price)"),
                       ("shuffle_within_cells", "null: shuffled within 5¢ bin x horizon x domain (keeps the cell bias)")):
        q = p[key]
        rows.append(row("placebo", key, q["mean"], q["p5"], q["p95"], p["draws"], "placebo",
                        f"{label}; p-value {q['p_value']} (share of draws >= real)"))
    d = rob["deflated_sharpe"]
    for key, split in (("selected_on_validation_all_trials", "val"), ("selected_on_validation_playoff_trials_only", "val")):
        x = d[key]
        rows.append(row("dsr", f"dsr_{x['n_trials']}_trials", x["dsr"], n=x["n_trades"], split=split,
                        note=f"V3 Sharpe/trade {x['sharpe_per_trade']} vs luck threshold {x['expected_max_sharpe_under_null_sr0']}"))
    t = d["test_out_of_sample"]
    rows.append(row("dsr", "psr_test", t["psr_true_sharpe_gt_0"], n=t["n_trades"], split="test",
                    note=f"P(true Sharpe>0), Sharpe/trade {t['sharpe_per_trade']}; test not used to choose"))
    for k, m in wf["models"].items():
        if m["V3"].get("n_trades"):
            v = m["V3"]
            rows.append(row("walkforward_models", k, v["per_dollar"], *v["per_dollar_ci"], v["n_trades"], "walkforward",
                            f"V3 ¢/$; Δ vs M0 {v['d_per_dollar_vs_M0']} [{v['d_per_dollar_vs_M0_ci'][0]}, "
                            f"{v['d_per_dollar_vs_M0_ci'][1]}]; log loss {m['logloss']} (Δ vs M0 {m['d_logloss_vs_M0']})"))
    rb = ROOT / "integrations/robustness"
    if (rb / "costs.json").exists():
        for c in json.loads((rb / "costs.json").read_text(encoding="utf-8"))["grid"]:
            if c.get("n_trades"):
                lo, hi = c["per_dollar_ci"]
                rows.append(row("costs", f"fee x{c['fee_x']:g} | floor {c['half_spread_floor'] * 100:.0f}c | kelly x{c['kelly']:g}",
                                c["per_dollar"], lo, hi, c["n_trades"], "test",
                                f"descriptive, not for selection; max drawdown {c['max_drawdown']}"))
    if (rb / "capacity.json").exists():
        cap = json.loads((rb / "capacity.json").read_text(encoding="utf-8"))
        for m in cap["markets"]:
            for b in m["by_size"]:
                if b.get("fills"):
                    rows.append(row("capacity", f"{m['question'][:70]} | ${b['usd']:,}", b["net_edge_per_share"], n=b["usd"],
                                    split="live", note=f"{m['status']}, {m['side']}, live snapshot {cap['snapshot_utc']}; "
                                                       f"net edge per share after fill price + fee"))
        for k in ("trade_now", "trade_now_and_waits"):
            rows.append(row("capacity", f"{k}: sum of max size with positive edge (USD, tested up to $10k)",
                            cap[k]["sum_max_size_usd"], n=cap[k]["n_markets"], split="live",
                            note=f"median per market ${cap[k]['per_market_median_max_size']:,}; live snapshot {cap['snapshot_utc']}"))
    if (rb / "shin_time.json").exists():
        for h in json.loads((rb / "shin_time.json").read_text(encoding="utf-8"))["by_horizon"]:
            rows.append(row("shin_time", f"{h['horizon_hours']}h", h["z"], *h["ci"], split="train",
                            note="Shin insider share z fitted per horizon (ML), 90% CI from 200 event-bootstrap refits; "
                                 "z<0 = longshots under-priced (opposite of Shin)"))
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    keep = [r for r in old if r.get("source") != "C"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(keep + rows, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(rows)} C rows (+{len(keep)} kept) to {OUT}")


if __name__ == "__main__":
    main()
