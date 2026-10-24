"""A's 00:40 items (2) and (3) -> integrations/robustness/costs.json, costs.png, shin_time.json, shin_time.png

  python integrations/robustness/costs_and_time.py

(2) COST SENSITIVITY on test, descriptive (NOT used for selection): the shipped model and V3 rule, re-run with
    taker fee × {1, 1.5, 2}, half-spread floor {1¢, 2¢, 3¢} and Kelly multiplier {⅛, ¼, ½} (cap 5% per trade and
    open stake <= 1 bankroll unchanged). Higher costs also change WHICH trades pass the edge filter, as they would live.
(3) SHIN'S z BY HORIZON: Shin's insider share fitted freely per horizon by maximum likelihood on all of train
    (z < 0 = longshots UNDER-priced, the opposite of Shin's assumption), 90% CI from 200 event-bootstrap refits.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "integrations" / "model_eval"))
import model as M  # noqa: E402
import playoff as P  # noqa: E402
import evaluate_all as E  # noqa: E402

FEE_X = (1.0, 1.5, 2.0)
FLOOR = (0.01, 0.02, 0.03)
KELLY = (0.125, 0.25, 0.5)
INK, MUTED, BLUE, GRID = "#1f2328", "#6e7781", "#2f6fdb", "#d0d7de"


def cost_grid(test, model, cutoff):
    rows = test[P.entry_time(test) >= cutoff]
    p = rows["price_yes"].to_numpy()
    q, lo, hi = model.predict(p, rows["horizon_hours"], rows["domain"])
    fee = M.fee_per_share(rows)
    out = []
    for fx in FEE_X:
        for fl in FLOOR:
            cost = M.trade_cost(rows["spread"].to_numpy(dtype=float), fee * fx, fl)
            for k in KELLY:
                M.KELLY_SCALE = k
                action, kelly, edge = M.decide(p, q, cost, lo, hi)
                c = rows.assign(q=q, cost=cost, action=action, kelly=kelly, edge=edge)
                t = P.policy(c, **P.VARIANTS["V3"])
                cell = {"fee_x": fx, "half_spread_floor": fl, "kelly": k, "n_trades": int(len(t))}
                if len(t):
                    _, capped = M.exposure(t, t["kelly"].to_numpy())
                    s = P.stats(t, capped)
                    cell.update(per_dollar=s["per_dollar"], per_dollar_ci=s["per_dollar_ci"], ret=s["return"],
                                max_drawdown=s["max_drawdown"], n_trades=s["n_trades"])
                out.append(cell)
                print(f"  fee×{fx} floor {fl * 100:.0f}¢ kelly {k}: {cell.get('per_dollar', float('nan')) * 100:+.1f}¢ "
                      f"({cell['n_trades']} trades)", flush=True)
    M.KELLY_SCALE = 0.25
    return out


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED)


def main():
    df = M.load_horizons(ROOT / "data" / "horizons.csv")
    train, test, cutoff = M.split_by_time(df, P.CUTOFF)
    model, _ = M.select_model(train, np.random.default_rng(0))  # the shipped model

    print("(2) cost grid", flush=True)
    grid = cost_grid(test, model, cutoff)
    base = next(c for c in grid if c["fee_x"] == 1 and c["half_spread_floor"] == 0.01 and c["kelly"] == 0.25)
    worst_ok = [c for c in grid if c["kelly"] == 0.25 and c.get("per_dollar_ci", [-1])[0] > 0]
    (HERE / "costs.json").write_text(json.dumps({"note": __doc__.strip().split("(3)")[0], "base": base, "grid": grid,
                                                 "all_quarter_kelly_cells_ci_above_0": len(worst_ok) == 9}, indent=1),
                                     encoding="utf-8")

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.8), dpi=160, sharey=True)
    for ax, k in zip(axes, KELLY):
        z = np.array([[next(c for c in grid if c["fee_x"] == fx and c["half_spread_floor"] == fl and c["kelly"] == k)
                       .get("per_dollar", np.nan) * 100 for fl in FLOOR] for fx in FEE_X])
        ax.imshow(z, cmap="Blues", vmin=0, vmax=max(30, np.nanmax(z)), aspect="auto")
        for i, fx in enumerate(FEE_X):
            for j, fl in enumerate(FLOOR):
                c = next(c for c in grid if c["fee_x"] == fx and c["half_spread_floor"] == fl and c["kelly"] == k)
                lo, hi = c.get("per_dollar_ci", [np.nan, np.nan])
                ax.text(j, i, f"{z[i, j]:+.1f}¢\n[{lo * 100:+.0f}, {hi * 100:+.0f}]\nDD {c.get('max_drawdown', np.nan):.2f}",
                        ha="center", va="center", fontsize=7.5, color=INK if z[i, j] < 22 else "white")
        ax.set_xticks(range(3), [f"{f * 100:.0f}¢" for f in FLOOR])
        ax.set_yticks(range(3), [f"fee ×{f:g}" for f in FEE_X])
        ax.set_xlabel("half-spread floor", color=MUTED)
        ax.set_title(f"Kelly ×{k:g}" + (" (shipped)" if k == 0.25 else ""), color=INK, fontsize=10, loc="left")
        style(ax)
    fig.suptitle("Cost sensitivity on test (descriptive): ¢ per $1 staked after costs [90% CI], max drawdown",
                 x=0.01, ha="left", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(HERE / "costs.png")
    plt.close(fig)

    print("(3) Shin z by horizon", flush=True)
    E.N_BOOT = 200
    m = E.ScalarFit("shin_fit", E.shin_binary, (-0.5, 0.5)).fit(train, np.random.default_rng(0))
    hs = sorted(m.main, reverse=True)
    rows = []
    for h in hs:
        b = np.array([bb[h] for bb in m.boot])
        rows.append({"horizon_hours": int(h), "z": round(float(m.main[h]), 4),
                     "ci": [round(float(x), 4) for x in np.percentile(b, [5, 95])]})
    (HERE / "shin_time.json").write_text(json.dumps({"note": __doc__.strip().split("(3)")[1].strip(),
                                                     "n_train_markets": int(train["market_id"].nunique()),
                                                     "by_horizon": rows}, indent=1), encoding="utf-8")
    fig, ax = plt.subplots(figsize=(7.5, 3.8), dpi=160)
    style(ax)
    ax.yaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    lab = {720: "30 days", 168: "7 days", 72: "3 days", 24: "1 day", 12: "12 hours"}
    x = np.arange(len(rows))
    z = np.array([r["z"] for r in rows])
    ax.axhline(0, color=INK, lw=0.9)
    ax.text(len(rows) - 0.6, 0.002, "Shin's assumption: z > 0 (longshots overpriced)", color=MUTED, fontsize=8, ha="right", va="bottom")
    ax.errorbar(x, z, yerr=[z - [r["ci"][0] for r in rows], [r["ci"][1] for r in rows] - z], fmt="o-", color=BLUE,
                ms=6, lw=1.6, elinewidth=1.4, capsize=0)
    for i, r in enumerate(rows):
        ax.text(i, r["z"] - 0.006, f"{r['z']:+.3f}", ha="center", va="top", fontsize=8, color=INK)
    ax.set_xticks(x, [lab[r["horizon_hours"]] for r in rows])
    ax.set_xlabel("time before the scheduled end", color=MUTED)
    ax.set_ylabel("Shin's insider share z (fitted)", color=INK)
    ax.set_ylim(min(-0.095, z.min() - 0.02), 0.02)
    ax.set_title("Polymarket gets Shin backwards, and more so as the end nears", loc="left", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(HERE / "shin_time.png")
    plt.close(fig)
    print(json.dumps(rows))


if __name__ == "__main__":
    main()
