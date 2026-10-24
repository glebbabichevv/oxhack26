"""One command reproduces every headline number.

  python integrations/reproduce.py

Re-runs the shipped pipeline (backend/model.py evaluate(): time split at the shipped cutoff, model chosen on
train, Polymarket taker fees, open stake <= 1 bankroll, embargo, policy COH) from data/horizons.csv with the
fixed seed, in memory (nothing is written), and diffs the headline against backend/results/backtest.json:
COH and V3 cents per $1 with CI, return, trades, max drawdown. Exit code 0 = every number matches.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import model as M  # noqa: E402

TOL = 1e-4


def pick(bt):
    """The numbers the site and pitch quote."""
    h = bt["headline"]
    rows = {r["variant"]: r["test"] for r in bt["policy_comparison"]["rows"]}
    out = {f"{h['policy']} per_dollar": h["per_dollar"], f"{h['policy']} per_dollar_ci": h["per_dollar_ci"],
           f"{h['policy']} return": h["return"], f"{h['policy']} return_ci": h["return_ci"],
           f"{h['policy']} n_trades": h["n_trades"], f"{h['policy']} max_drawdown": h["max_drawdown"]}
    for v in ("V3", "COH"):
        if v in rows and v != h["policy"]:
            for k in ("per_dollar", "per_dollar_ci", "return", "n_trades", "max_drawdown"):
                out[f"{v} {k}"] = rows[v].get(k)
    out["Brier market"], out["Brier model"] = bt["overall"]["brier_market"], bt["overall"]["brier_model"]
    return out


def same(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= TOL * max(1, abs(b))
    return a == b


def main():
    shipped = json.loads((ROOT / "backend" / "results" / "backtest.json").read_text(encoding="utf-8"))
    df = M.load_horizons(ROOT / "data" / "horizons.csv")
    _, _, bt = M.evaluate(df, cutoff=shipped["cutoff"], seed=0)
    want, got = pick(shipped), pick(bt)
    bad = 0
    print(f"{'number':32s} {'shipped':>22s} {'reproduced':>22s}")
    for k, w in want.items():
        g = got.get(k)
        ok = same(g, w)
        bad += not ok
        print(f"{k:32s} {str(w):>22s} {str(g):>22s}  {'ok' if ok else 'DIFF'}")
    print(f"\n{len(want) - bad} of {len(want)} headline numbers reproduced exactly"
          + ("" if not bad else f"; {bad} differ (shipped file is older than the code or the data)"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
