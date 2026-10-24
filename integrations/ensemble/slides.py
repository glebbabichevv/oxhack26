"""Three static slides for the pitch (Gleb 23:30 #3), from results already computed — no new numbers.

  python integrations/ensemble/slides.py   # -> integrations/ensemble/slides/{errcorr,tournament,pool}.png

Light surface, one hue for magnitude (blue ramp), text in ink tokens, recessive grid.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "slides"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, BLUE_DARK, MUTED = "#2a78d6", "#184f95", "#b8b7b0"
RAMP = LinearSegmentedColormap.from_list("blue", ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
NAMES = {"M0": "M0 (shipped)", "M1": "M1 logistic+feat.", "M2": "M2 boosting", "BETA": "beta", "shin": "Shin",
         "power": "power", "isotonic": "isotonic", "hier": "hierarchical", "SHIN": "Shin (built-in)"}
LABELS = {"V3": "V3 shipped", "COH": "Event coherence", "BETA": "Beta calibration", "ENS": "Mean ensemble",
          "AGREE": "Agreement filter", "POOL": "Time-weighted log pool", "shin": "Shin 1993", "power": "Power method",
          "isotonic": "Isotonic", "hier": "Hierarchical domain"}

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.color": INK, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.edgecolor": GRID, "figure.facecolor": SURFACE,
                     "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE})


def title(fig, head, sub):
    fig.text(0.03, 0.95, head, fontsize=16, fontweight="bold", color=INK, va="top")
    fig.text(0.03, 0.885, sub, fontsize=11, color=INK2, va="top")


def errcorr(res):
    m = res["error_correlation"]
    keys, mat = m["members"], np.array(m["matrix"])
    fig, ax = plt.subplots(figsize=(9, 7.2))
    fig.subplots_adjust(top=0.8, left=0.2, right=0.9, bottom=0.18)
    im = ax.imshow(mat, cmap=RAMP, vmin=0.95, vmax=1.0)
    lab = [NAMES.get(k, k) for k in keys]
    ax.set_xticks(range(len(keys)), lab, rotation=40, ha="right")
    ax.set_yticks(range(len(keys)), lab)
    for i in range(len(keys)):
        for j in range(len(keys)):
            v = mat[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=9, color="white" if v > 0.985 else INK)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.03)
    cb.outline.set_visible(False)
    cb.set_label("correlation of errors (q − outcome)", color=INK2)
    lo = mat[np.triu_indices(len(keys), 1)].min()
    title(fig, "The ensemble voted unanimously",
          f"Every model reads the same price: errors correlate {lo:.3f}–1.00 on validation, so averaging adds nothing")
    fig.savefig(OUT / "errcorr.png", dpi=160)


def tournament(res, ex):
    v2 = res["validation_second_half"]
    items = [(LABELS.get(c, c), v["per_dollar"], v["per_dollar_ci"], v["n_trades"], c == res["winner"])
             for c, v in v2.items() if v.get("per_dollar") is not None]
    fx = ex["fixed_pair_chosen_on_val1"]
    for name, v in ((f"Exit early {fx.replace('FIX', '')}", ex["val2"][fx]), ("Exit when market catches up", ex["val2"]["DYNAMIC"])):
        items.append((name, v["per_dollar"], v["per_dollar_ci"], v["n_trades"], False))
    items.sort(key=lambda x: x[1])
    fig, ax = plt.subplots(figsize=(10, 7.2))
    fig.subplots_adjust(top=0.8, left=0.27, right=0.95, bottom=0.1)
    for y, (name, v, (lo, hi), n, win) in enumerate(items):
        col = BLUE_DARK if win else (BLUE if v > 0 else MUTED)
        ax.plot([lo * 100, hi * 100], [y, y], color=col, lw=2, solid_capstyle="round")
        ax.scatter([v * 100], [y], s=70, color=col, zorder=3, edgecolor=SURFACE, linewidth=2)
        ax.text(max(hi * 100, v * 100) + 3, y, f"{v * 100:+.0f}¢  (n={n:,})", va="center", fontsize=9, color=INK2)
    ax.set_yticks(range(len(items)), [i[0] for i in items])
    ax.axvline(0, color=INK2, lw=1)
    v3 = v2["V3"]["per_dollar"] * 100
    ax.axvline(v3, color=MUTED, lw=1, ls="--")
    ax.text(v3, len(items) - 0.4, " V3 shipped", color=INK2, fontsize=9, va="bottom")
    ax.set_xlim(min(i[2][0] for i in items) * 100 - 8, max(i[2][1] for i in items) * 100 + 30)
    ax.set_xlabel("¢ per \$1 staked after fees, later half of validation (90% event-bootstrap CI)")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    n_var = res["n_candidates_compared"] + 2
    title(fig, f"{n_var} variants, chosen on validation: one bet per event wins",
          "Classic de-vig models (Shin, power) call Polymarket fair and barely trade; time-aware calibration doesn't")
    fig.savefig(OUT / "tournament.png", dpi=160)


def pool(res):
    keys, w = res["pool_weights"]["keys"], res["pool_weights"]["w"]
    a = np.array(w[1::2])  # per-member base weights a_i (b_i are the horizon slopes)
    fig, ax = plt.subplots(figsize=(9, 6))
    fig.subplots_adjust(top=0.78, left=0.22, right=0.95, bottom=0.12)
    y = np.arange(len(keys))
    ax.barh(y, a, color=[BLUE if x >= 0 else MUTED for x in a], height=0.6)
    for yi, x in zip(y, a):
        ax.text(x + (0.15 if x >= 0 else -0.15), yi, f"{x:+.2f}", va="center", ha="left" if x >= 0 else "right",
                fontsize=9, color=INK2)
    ax.set_yticks(y, [NAMES.get(k, k) for k in keys])
    ax.axvline(0, color=INK2, lw=1)
    ax.axvline(1 / len(keys), color=MUTED, lw=1, ls="--")
    ax.text(1 / len(keys), len(keys) - 0.45, " plain average", color=INK2, fontsize=9)
    ax.set_xlabel("log-pool weight a_i fitted on the first half of validation")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    p = res["validation_second_half"]["POOL"]["per_dollar"] * 100
    v3 = res["validation_second_half"]["V3"]["per_dollar"] * 100
    lim = np.abs(a).max() * 1.35
    ax.set_xlim(-lim, lim)
    title(fig, "Stacking near-identical models overfits",
          f"Collinear members get huge opposite weights; on held-out data the pool earns {p:+.0f}¢ per \$1 vs V3 {v3:+.0f}¢")
    fig.savefig(OUT / "pool.png", dpi=160)


def main():
    OUT.mkdir(exist_ok=True)
    res = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
    ex = json.loads((HERE / "exit.json").read_text(encoding="utf-8"))
    errcorr(res)
    tournament(res, ex)
    pool(res)
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))


if __name__ == "__main__":
    main()
