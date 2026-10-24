"""Static charts for Devpost gallery / backup slide, from backend/results. Run: python integrations/pitch/make_charts.py"""
import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
INK, MUTED, FAINT, HAIR = "#111113", "#676e7e", "#a1a1aa", "#e4e4e7"
LABEL = {720: "30 days", 168: "7 days", 72: "3 days", 24: "1 day", 12: "12 hours"}


def when_to_trade():
    bt = json.loads((ROOT / "backend/results/backtest.json").read_text())
    rows = sorted(bt["by_horizon"], key=lambda r: -r["horizon_hours"])
    names = [LABEL[r["horizon_hours"]] for r in rows]
    ret = [r["with_costs"]["mean_return_per_trade"] * 100 for r in rows]
    n = [r["with_costs"]["n_trades"] for r in rows]

    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=200)
    fig.patch.set_facecolor("white")
    colors = [FAINT if v <= 0.5 else INK for v in ret]
    bars = ax.bar(names, ret, color=colors, width=0.56, zorder=3)
    for b, v, k in zip(bars, ret, n):
        y = max(v, 0) + 0.5
        ax.text(b.get_x() + b.get_width() / 2, y, f"{v:+.1f}%", ha="center", va="bottom",
                fontsize=15, color=INK, fontweight="bold")
        ax.text(b.get_x() + b.get_width() / 2, -1.6, f"{k:,} trades", ha="center", va="top",
                fontsize=10, color=FAINT)
    ax.axhline(0, color=MUTED, linewidth=1, zorder=4)
    ax.set_ylim(-3.2, max(ret) * 1.25)
    ax.yaxis.grid(True, color=HAIR, linewidth=0.8, zorder=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(axis="x", length=0, labelsize=13, labelcolor=INK, pad=22)
    ax.tick_params(axis="y", length=0, labelsize=10, labelcolor=FAINT)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.set_xlabel("time to resolution when you enter", fontsize=11, color=MUTED, labelpad=10)

    fig.text(0.06, 0.95, "When to trade: the edge appears in the last week",
             fontsize=19, color=INK, fontweight="bold", va="top")
    fig.text(0.06, 0.885,
             f"Mean return per trade after a 1¢ cost, out-of-time test on {bt['n_test_markets']:,} Polymarket markets "
             f"(resolved after {bt['cutoff']})",
             fontsize=11, color=MUTED, va="top")
    fig.text(0.06, 0.03, "Each horizon backtested on its own: one trade per market at that horizon, ¼ Kelly, held to "
             "resolution. Source: backend/results/backtest.json", fontsize=8.5, color=FAINT)
    fig.subplots_adjust(left=0.08, right=0.97, top=0.8, bottom=0.2)
    out = OUT / "when_to_trade.png"
    fig.savefig(out, facecolor="white")
    print("wrote", out, dict(zip(names, [round(v, 2) for v in ret])))


if __name__ == "__main__":
    when_to_trade()
