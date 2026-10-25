"""Ayaz's results -> flat rows in integrations/methods/summary.json (A's 23:55 format), merge-safe.

  python integrations/methods/add_ayaz_rows.py

Rows: {block, name, value, lo, hi, n, split, note, source}. Rewrites only rows whose `source` is "C-Ayaz";
everyone else's rows are kept. Reads integrations/ensemble/{results, paired, coh_check, exit, summary}.json.
Values are cents-per-$1 as fractions (0.171 = 17.1c) unless the note says otherwise.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENS = ROOT / "integrations" / "ensemble"
OUT = ROOT / "integrations" / "methods" / "summary.json"
SRC = "C-Ayaz"

LABELS = {"V3": "V3 (shipped before)", "COH": "Event coherence", "BETA": "Beta calibration", "ENS": "Mean of 8 models",
          "AGREE": "Models agree", "POOL": "Log pool", "shin": "Shin 1993", "power": "Power method",
          "isotonic": "Isotonic", "hier": "Hierarchical"}


def row(block, name, value, lo=None, hi=None, n=None, split="", note=""):
    r = lambda x: None if x is None else round(float(x), 6)  # noqa: E731
    return {"block": block, "name": name, "value": r(value), "lo": r(lo), "hi": r(hi), "n": n, "split": split,
            "note": note, "source": SRC}


def load(name):
    return json.loads((ENS / name).read_text(encoding="utf-8"))


def ci(x, key="per_dollar_ci"):
    return (x.get(key) or [None, None])


def main():
    res, paired, coh, ex, desc = (load(f) for f in ("results.json", "paired.json", "coh_check.json", "exit.json", "summary.json"))
    rows = []
    n_var = res["n_candidates_compared"] + 2  # + FIX* exit and DYNAMIC exit
    for c, v in res["validation_second_half"].items():
        lo, hi = ci(v)
        rows.append(row("tournament", LABELS.get(c, c), v.get("per_dollar"), lo, hi, v.get("n_trades"), "val2",
                        f"¢/$ after fees, V3 rules on this q; Brier {v['brier']}, log loss {v['logloss']}; "
                        f"winner {res['winner']}; {n_var} variants compared in total"))
    fx = ex["fixed_pair_chosen_on_val1"]
    for name, v in (("Sell early " + fx.replace("FIX", "").replace(",", "h→").replace(")", "h)"), ex["val2"].get(fx, {})),
                    ("Sell when market catches up", ex["val2"]["DYNAMIC"])):
        lo, hi = ci(v)
        rows.append(row("tournament", name, v.get("per_dollar"), lo, hi, v.get("n_trades"), "val2",
                        "¢/$ after fees on both legs; pair chosen on VAL1"))
    m = res["error_correlation"]
    keys = m["members"]
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            rows.append(row("errcorr", f"{keys[i]}~{keys[j]}", m["matrix"][i][j], split="val2" if False else "val",
                            note="correlation of (q - outcome) on validation, in-band rows"))
    d, c95 = paired["delta_coh_minus_v3"], paired["delta_ci90"]
    for k, note in (("per_dollar", "Δ ¢/$ COH − V3"), ("return", "Δ total return, starting bankrolls"),
                    ("brier", "Δ Brier (negative = better)"), ("max_dd", "Δ max drawdown")):
        rows.append(row("paired", f"COH − V3 {k}", d[k], c95[k][0], c95[k][1], paired["n_val2_events"], "val2",
                        f"{note}; paired event bootstrap, {paired['n_boot']} draws; before test"))
    rows.append(row("paired", "COH on Gamma-complete books only", coh["COH_complete_books_only"]["COH"]["per_dollar"],
                    n=coh["COH_complete_books_only"]["n_trades"]["COH"], split="val2",
                    note=f"look-ahead check: {coh['n_complete']} of {coh['n_coherence_events']} events complete; "
                         f"all books {coh['COH_all_books']['COH']['per_dollar']}"))
    for c, v in res["test"].items():
        lo, hi = ci(v)
        rows.append(row("test", LABELS.get(c, c), v.get("per_dollar"), lo, hi, v.get("n_trades"), "test",
                        f"¢/$ after fees; return {v['return']} {v['return_ci']} bankrolls; maxDD {v['max_drawdown']}; "
                        f"Brier {v['brier']}; opened once after the freeze"))
    for k in ["HOLD(72)", "HOLD(48)", "HOLD(24)", ex["fixed_pair_chosen_on_val1"], "V3", "DYNAMIC", "COH", "COH+DYNAMIC"]:
        v = ex["val2"].get(k)
        if v:
            lo, hi = ci(v)
            rows.append(row("exit", k, v.get("per_dollar"), lo, hi, v.get("n_trades"), "val2",
                            f"return/maxDD {v.get('ret_per_dd')}; hit {v.get('hit_rate')}; P&L std/trade "
                            f"{v.get('pnl_std_per_trade')}; sold before end {v.get('share_sold_before_end')}; "
                            f"test opened: {ex['test_opened']}"))
    for k in ("COH", "COH+DYNAMIC", "V3", "DYNAMIC", ex["fixed_pair_chosen_on_val1"]):
        v = (ex.get("test") or {}).get(k)
        if v:
            lo, hi = ci(v)
            rows.append(row("exit", f"{k} (test)", v.get("per_dollar"), lo, hi, v.get("n_trades"), "test",
                            f"return/maxDD {v.get('ret_per_dd')}; maxDD {v.get('max_drawdown')}; SECOND test look (after V3 vs COH), "
                            f"gated on COH+DYNAMIC beating COH on VAL2 return/maxDD; descriptive, not a fresh out-of-sample read"))
    for policy in ("V3", "COH"):
        for block, col in (("domain", "domain"), ("volume", "volume_tier"), ("price_bucket", "price_bucket")):
            for g in desc[policy][block]:
                lo, hi = g["per_dollar_ci"] or [None, None]
                rows.append(row(block, f"{policy}: {g[col]}", g["per_dollar"], lo, hi, g["n_trades"], "test",
                                f"descriptive - not used for selection; hit {g['hit_rate']}; return {g['return']}"
                                + ("; LIFETIME volume (no volume-at-entry in data)" if block == "volume" else "")))
    if (ENS / "coh_robust.json").exists():
        rb = load("coh_robust.json")
        for r in rb["monthly"]:
            for pol in ("V3", "COH"):
                v = r[pol]
                if v["per_dollar"] is None:
                    continue
                lo, hi = v["per_dollar_ci"] or [None, None]
                rows.append(row("monthly_coh", f"{r['month']} {pol}", v["per_dollar"], lo, hi, v["n_trades"], "walkforward",
                                "¢/$ after fees; M0 refitted on events ended before the month"))
        ms = rb["monthly_summary"]
        rows.append(row("monthly_coh_summary", "COH months positive", ms["COH"]["positive"], n=ms["COH"]["months"], split="walkforward",
                        note=f"COH positive in {ms['COH']['positive']} of {ms['COH']['months']} months (V3 {ms['V3']['positive']} of "
                             f"{ms['V3']['months']}); CI below 0 in {ms['COH']['ci_below_0']} (a 1-trade month)"))
        pl = rb["placebo_coh"]
        rows.append(row("placebo_coh", "COH real", pl["real_per_dollar"], n=pl["n_trades"], split="placebo",
                        note=f"Bernoulli 'prices are right' null, {pl['draws']} draws: p-value {pl['p_value']}"))
        rows.append(row("placebo_coh", "COH null", pl["null_p50"], pl["null_p5"], pl["null_p95"], pl["n_trades"], "placebo",
                        f"null median [p5, p95]; mean {pl['null_mean']}"))
        d = rb["dsr_coh"]
        rows.append(row("dsr_coh", "COH deflated Sharpe", d["dsr"], n=d["n_trades"], split="test",
                        note=f"per-trade SR {d['sharpe_per_trade']}, PSR {d['psr_true_sharpe_gt_0']}, {d['n_trials']} trials, "
                             f"SR0 {d['sr0_expected_max_under_null']}"))
        lc = rb["leg_choice"]
        rows.append(row("leg_choice", "largest-edge leg (COH)", lc["largest_edge_leg"]["per_dollar"], n=lc["largest_edge_leg"]["n_trades"],
                        split="test", note="descriptive - not used for selection"))
        rows.append(row("leg_choice", "random eligible leg", lc["random_leg"]["mean"], lc["random_leg"]["p5"], lc["random_leg"]["p95"],
                        split="test", note=f"descriptive; {lc['random_leg']['draws']} draws, mean [p5, p95]"))
        rows.append(row("leg_choice", "all eligible legs, no event cap", lc["all_eligible_legs_no_event_cap"]["per_dollar"],
                        n=lc["all_eligible_legs_no_event_cap"]["n_trades"], split="test",
                        note="descriptive; the gain comes from one bet per event, not from which leg"))
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    keep = [r for r in old if r.get("source") != SRC]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(keep + rows, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"kept {len(keep)} rows from others, wrote {len(rows)} {SRC} rows -> {OUT}")


if __name__ == "__main__":
    main()
