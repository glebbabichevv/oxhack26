"""Robustness evidence for the SHIPPED policy (M0 + V3, fees, caps). No new model variants.
-> integrations/robustness/results.json + by_month.png + placebo.png + deflated_sharpe.png

  python integrations/robustness/robustness.py [--draws 1000]

(1) Monthly walk-forward over the whole history: for each calendar month m, M0 is refitted on every event that
    ended before m starts (model.split_by_time at m's first day), and V3 trades month m's markets only (embargo:
    entry on/after the 1st). Per month: markets, trades, ¢ per $1 with event-bootstrap CI, Brier market vs model.
    Months that fall in the test period use models refitted on data the shipped model never saw: this is the
    shipped SPEC re-run, not the shipped coefficients.
(2) Placebo on the test set, shipped model (fit on all of train): the trades do not depend on outcomes, so each
    draw keeps the same trades and stakes and only re-draws outcomes. Two nulls:
      a. A's: outcomes shuffled within (5¢ price bin × horizon × domain) cells. This keeps each cell's win rate,
         i.e. it KEEPS the cell-level favourite/longshot bias and only destroys within-cell information.
      b. "prices are right": every outcome redrawn as Bernoulli(price at that row). The market is calibrated by
         construction, so any profit is luck.
    p-value = share of draws with ¢ per $1 >= the real one.
(3) Deflated Sharpe (Bailey & López de Prado 2014) for the shipped test trades: per-trade Sharpe of stake × return,
    probabilistic Sharpe (P[true SR > 0]) and DSR given N trials. Trials = V0–V3 (playoff) + the 18 members/mixes
    scored on validation in integrations/model_eval (V3 trades each); their validation Sharpes give the variance
    across trials.
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import kurtosis, norm, skew  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import playoff as P  # noqa: E402
from model import (Calibrator, brier, event_key, exposure, in_band, load_horizons, per_dollar_ci,  # noqa: E402
                   select_model, split_by_time)

V3 = P.VARIANTS["V3"]
INK, MUTED, BLUE, GRID = "#1f2328", "#6e7781", "#2f6fdb", "#d0d7de"


def v3_trades(rows, model, start):
    rows = rows[P.entry_time(rows) >= start]
    c = P.candidates(rows, model)
    t = P.policy(c, **V3)
    if len(t):
        _, capped = exposure(t, t["kelly"].to_numpy())
        t = t.assign(kelly=capped)[capped > 0]
    return t, c


def by_month(df):
    end = df.groupby(event_key(df))["resolved_at"].transform("max")
    months = pd.date_range(df["resolved_at"].min().normalize().replace(day=1), df["resolved_at"].max(), freq="MS")
    out = []
    for m0, m1 in zip(months[:-1], months[1:]):
        fit, rows, start = split_by_time(df[end < m1], str(m0.date()))
        if fit["market_id"].nunique() < 2000 or not len(rows):
            continue  # too little history to fit on
        model = Calibrator(["other"]).fit(fit, np.random.default_rng(0))
        t, c = v3_trades(rows, model, start)
        b = in_band(c["price_yes"])
        row = {"month": str(m0.date())[:7], "n_fit_markets": int(fit["market_id"].nunique()),
               "n_markets": int(c["market_id"].nunique()), "n_trades": int(len(t)),
               "brier_market": round(brier(c["price_yes"][b], c["outcome"][b]), 5),
               "brier_model": round(brier(c["q"][b], c["outcome"][b]), 5)}
        if len(t):
            st = t["kelly"].to_numpy()
            row["per_dollar"] = round(float((st * t["ret"]).sum() / st.sum()), 4)
            row["per_dollar_ci"] = per_dollar_ci(t, st, np.random.default_rng(0))
            row["return"] = round(float((st * t["ret"]).sum()), 4)
        out.append(row)
        print(f"  {row['month']}: {row['n_markets']:,} markets, {row['n_trades']:,} trades, "
              f"{row.get('per_dollar', float('nan')) * 100:+.1f}¢/$", flush=True)
    return out


def placebo(test, model, cutoff, draws):
    t, c = v3_trades(test, model, cutoff)
    st, p, cost, act = (t["kelly"].to_numpy(), t["price_yes"].to_numpy(), t["cost"].to_numpy(), t["action"].to_numpy())

    def per_dollar(y):
        ret = np.where(act == "BUY_YES", y / (p + cost) - 1, (1 - y) / (1 - p + cost) - 1)
        return float((st * ret).sum() / st.sum())

    real = per_dollar(t["outcome"].to_numpy())
    # Cells over ALL in-band test rows (not just traded ones), so a traded row's outcome is drawn from its whole cell.
    c = c[in_band(c["price_yes"])].copy()
    c["cell"] = (np.floor(c["price_yes"] * 20).astype(int).astype(str) + "|" + c["horizon_hours"].astype(str)
                 + "|" + c["domain"])
    cells = c.groupby("cell")["outcome"].apply(lambda s: s.to_numpy()).to_dict()
    tcell = (np.floor(t["price_yes"] * 20).astype(int).astype(str) + "|" + t["horizon_hours"].astype(str)
             + "|" + t["domain"]).to_numpy()
    rng = np.random.default_rng(0)
    idx = {k: np.flatnonzero(tcell == k) for k in np.unique(tcell)}
    shuffled, bern = [], []
    for _ in range(draws):
        y = np.empty(len(t))
        for k, ii in idx.items():
            y[ii] = rng.choice(cells[k], len(ii), replace=False) if len(cells[k]) >= len(ii) else rng.choice(cells[k], len(ii))
        shuffled.append(per_dollar(y))
        bern.append(per_dollar((rng.random(len(t)) < p).astype(float)))
    shuffled, bern = np.array(shuffled), np.array(bern)

    def summ(x):
        return {"mean": round(float(x.mean()), 4), "p5": round(float(np.percentile(x, 5)), 4),
                "p95": round(float(np.percentile(x, 95)), 4), "p_value": round(float((x >= real).mean()), 4)}

    return {"real_per_dollar": round(real, 4), "n_trades": int(len(t)), "draws": draws,
            "shuffle_within_cells": summ(shuffled), "prices_are_right": summ(bern)}, shuffled, bern, t


def sharpe_stats(x):
    x = np.asarray(x, float)
    return float(x.mean() / x.std(ddof=1)), float(skew(x)), float(kurtosis(x, fisher=False))


def deflated_sharpe(x, trial_srs):
    x = np.asarray(x, float)  # per-trade P&L in starting bankrolls
    sr, g3, g4 = sharpe_stats(x)
    T = len(x)
    denom = np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr * sr)
    psr = norm.cdf(sr * np.sqrt(T - 1) / denom)
    n = len(trial_srs)
    v = float(np.var(trial_srs, ddof=1))
    gamma = 0.5772156649
    sr0 = np.sqrt(v) * ((1 - gamma) * norm.ppf(1 - 1 / n) + gamma * norm.ppf(1 - 1 / (n * np.e)))
    dsr = norm.cdf((sr - sr0) * np.sqrt(T - 1) / denom)
    return {"n_trades": T, "sharpe_per_trade": round(sr, 4), "skew": round(g3, 3), "kurtosis": round(g4, 3),
            "psr_true_sharpe_gt_0": round(float(psr), 6), "n_trials": n, "var_trial_sharpe": round(v, 6),
            "expected_max_sharpe_under_null_sr0": round(float(sr0), 4), "dsr": round(float(dsr), 6)}


def trial_sharpes(val_fit, val, val_start):
    """Validation per-trade Sharpe of every trial compared tonight: V0–V3 (M0) + model_eval members under V3."""
    srs, xs = {}, {}
    m = Calibrator(["other"]).fit(val_fit, np.random.default_rng(0))
    c = P.candidates(val[P.entry_time(val) >= val_start], m)
    for v, kw in P.VARIANTS.items():
        t = P.policy(c, **kw)
        _, capped = exposure(t, t["kelly"].to_numpy())
        xs[f"playoff_{v}"] = capped[capped > 0] * t["ret"].to_numpy()[capped > 0]
        srs[f"playoff_{v}"] = sharpe_stats(xs[f"playoff_{v}"])[0]
    sys.path.insert(0, str(ROOT / "integrations" / "model_eval"))
    import evaluate_all as E
    qf = pd.read_csv(ROOT / "integrations" / "model_eval" / "q_validation.csv.gz")
    rows = E.prepare(val)
    rows = rows[P.entry_time(rows) >= val_start].reset_index(drop=True)
    assert len(rows) == len(qf) and (rows["market_id"].to_numpy() == qf["market_id"].to_numpy()).all()
    for k in [c[2:] for c in qf if c.startswith("q_")]:
        if k in ("market", "M0"):
            continue
        cc = E.candidates(rows, qf[f"q_{k}"].to_numpy(), qf[f"lo_{k}"].to_numpy(), qf[f"hi_{k}"].to_numpy())
        t = P.policy(cc, **V3)
        if len(t) < 30:
            continue
        _, capped = exposure(t, t["kelly"].to_numpy())
        srs[f"member_{k}"] = sharpe_stats(capped[capped > 0] * t["ret"].to_numpy()[capped > 0])[0]
    return srs, xs


def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED)
    ax.yaxis.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", type=int, default=1000)
    a = ap.parse_args()
    df = load_horizons(ROOT / "data" / "horizons.csv")
    train, test, cutoff = split_by_time(df, P.CUTOFF)
    HERE.mkdir(exist_ok=True)
    res = {"protocol": __doc__.strip(), "cutoff": str(cutoff.date())}

    print("(1) monthly walk-forward", flush=True)
    months = by_month(df)
    traded = [m for m in months if m.get("n_trades", 0) >= 30]
    res["by_month"] = months
    res["by_month_summary"] = {
        "months_with_30_plus_trades": len(traded),
        "months_positive": sum(m["per_dollar"] > 0 for m in traded),
        "months_ci_above_0": sum(m["per_dollar_ci"][0] > 0 for m in traded),
        "months_ci_below_0": sum(m["per_dollar_ci"][1] < 0 for m in traded),
        "months_model_brier_better": sum(m["brier_model"] < m["brier_market"] for m in months)}

    print("(2) placebo", flush=True)
    model, _ = select_model(train, np.random.default_rng(0))  # exactly the shipped model
    res["placebo"], shuffled, bern, t = placebo(test, model, cutoff, a.draws)

    print("(3) deflated Sharpe", flush=True)
    order = train.groupby("market_id")["resolved_at"].first().sort_values()
    val_ids = set(order.index[int(len(order) * 0.8):])
    vfit, val = train[~train["market_id"].isin(val_ids)], train[train["market_id"].isin(val_ids)]
    srs, xs = trial_sharpes(vfit, val, val["resolved_at"].min())
    playoff_only = [v for k, v in srs.items() if k.startswith("playoff_")]
    # DSR is defined for the strategy SELECTED among the trials, on the data it was selected on (validation).
    # The test Sharpe is out of sample: it was not used to choose, so its PSR needs no deflation.
    res["deflated_sharpe"] = {
        "selected_on_validation_all_trials": deflated_sharpe(xs["playoff_V3"], list(srs.values())),
        "selected_on_validation_playoff_trials_only": deflated_sharpe(xs["playoff_V3"], playoff_only),
        "test_out_of_sample": {k: v for k, v in deflated_sharpe((t["kelly"] * t["ret"]).to_numpy(), list(srs.values())).items()
                               if k in ("n_trades", "sharpe_per_trade", "skew", "kurtosis", "psr_true_sharpe_gt_0")},
        "note": "Trials are highly correlated (every model reads the same price; error correlations 0.99), so N=15 "
                "independent trials overstates the luck threshold; the playoff-only row (N=4) is the other end.",
        "trial_sharpes_validation": {k: round(v, 4) for k, v in srs.items()}}
    (HERE / "results.json").write_text(json.dumps(res, indent=1), encoding="utf-8")

    # --- charts ---
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=160)
    style(ax)
    ms = [m for m in months if m.get("n_trades", 0) >= 30]
    x = np.arange(len(ms))
    y = np.array([m["per_dollar"] * 100 for m in ms])
    lo = y - np.array([m["per_dollar_ci"][0] * 100 for m in ms])
    hi = np.array([m["per_dollar_ci"][1] * 100 for m in ms]) - y
    test_start = next((i for i, m in enumerate(ms) if m["month"] >= str(cutoff.date())[:7]), None)
    if test_start is not None:
        ax.axvspan(test_start - 0.5, len(ms) - 0.5, color="#eef3fc", zorder=0)
        ax.text(test_start - 0.35, 0.98, "test period", color=MUTED, va="top", fontsize=9, transform=ax.get_xaxis_transform())
    ax.axhline(0, color=INK, lw=0.8)
    ax.errorbar(x, y, yerr=[lo, hi], fmt="o", color=BLUE, ms=5, elinewidth=1.4, capsize=0)
    ax.set_xticks(x, [f"{m['month']}\n{m['n_trades']:,} tr." for m in ms], fontsize=7)
    ax.set_ylabel("¢ per $1 staked after fees (90% CI)", color=INK)
    s = res["by_month_summary"]
    ax.set_title(f"Edge by month (M0 refitted monthly, policy V3): positive in {s['months_positive']} of "
                 f"{s['months_with_30_plus_trades']} months", loc="left", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(HERE / "by_month.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 3.8), dpi=160)
    style(ax)
    real = res["placebo"]["real_per_dollar"] * 100
    bins = np.linspace(min(bern.min(), shuffled.min()) * 100, max(real + 2, shuffled.max() * 100), 60)
    ax.hist(bern * 100, bins=bins, color="#9aa4ae", alpha=0.8, label="null: prices are right (Bernoulli(price))")
    ax.hist(shuffled * 100, bins=bins, color="#7fa7ec", alpha=0.8, label="null: outcomes shuffled within price×horizon×domain cells")
    ax.axvline(real, color=INK, lw=1.6)
    ax.text(real, ax.get_ylim()[1] * 0.95, f"  real: {real:+.1f}¢", color=INK, va="top")
    ax.set_xlabel("¢ per $1 staked after fees, same 3,6xx test trades".replace("3,6xx", f"{res['placebo']['n_trades']:,}"))
    ax.set_ylabel(f"draws (of {a.draws:,})")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    ax.set_title("Placebo: the shipped V3 trades with re-drawn outcomes", loc="left", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(HERE / "placebo.png")
    plt.close(fig)

    d = {**res["deflated_sharpe"]["selected_on_validation_all_trials"],
         "test_sr": res["deflated_sharpe"]["test_out_of_sample"]["sharpe_per_trade"]}
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=160)
    style(ax)
    names = sorted(srs, key=srs.get)
    ax.barh(range(len(names)), [srs[k] for k in names], color="#9aa4ae", height=0.6)
    ax.axvline(d["expected_max_sharpe_under_null_sr0"], color=MUTED, ls="--", lw=1)
    ax.axvline(d["sharpe_per_trade"], color=BLUE, lw=2)
    ax.axvline(d["test_sr"], color=INK, lw=1.2, ls=":")
    ax.set_yticks(range(len(names)), [k.replace("member_", "").replace("playoff_", "playoff ") for k in names], fontsize=7)
    ax.set_xlabel("per-trade Sharpe · bars: trials (validation) · blue: V3 val · dotted: V3 test · dashed: luck threshold")
    ax.set_title(f"Deflated Sharpe of the selected rule (V3, validation): {d['n_trials']} trials, DSR = {d['dsr']:.2f}",
                 loc="left", color=INK, fontsize=11)
    fig.tight_layout()
    fig.savefig(HERE / "deflated_sharpe.png")
    plt.close(fig)
    print(json.dumps({k: res[k] for k in ("by_month_summary", "placebo")}, indent=1))
    print(json.dumps({k: v for k, v in res["deflated_sharpe"].items() if k != "trial_sharpes_validation"}, indent=1))


if __name__ == "__main__":
    main()
