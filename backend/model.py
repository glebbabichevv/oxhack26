"""Horizon model pipeline.

data/horizons.csv + data/live.csv  ->  backend/results/{calibration,backtest,live}.json

  .venv/bin/python model.py [--data ../data] [--cutoff YYYY-MM-DD] [--fee 0] [--min-half-spread 0.01]

Model: logistic regression of the outcome on logit(market price), log(horizon), domain and
their interactions. Baseline: the market price itself. Split by time: markets resolved before
the cutoff train, markets resolved on/after it test. Every number written here is computed on
the test set only.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

HERE = Path(__file__).parent
EPS = 0.01
# Outside this price band a 1¢ cost swamps any edge and tiny prices make logit features unstable:
# the model is neither trained nor traded there (q = market price, NO_TRADE).
TRADABLE = (0.03, 0.97)
KELLY_SCALE = 0.25
KELLY_CAP = 0.05
N_BOOT = 40
MIN_DOMAIN_ROWS = 50


def logit(p):
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


# ---------- data ----------

def load_horizons(path):
    df = pd.read_csv(path)
    df = df[df["outcome"].isin([0, 1]) & df["price_yes"].between(0, 1, inclusive="neither") & (df["horizon_hours"] > 0)]
    df["resolved_at"] = pd.to_datetime(df["resolved_at"], utc=True, format="ISO8601")
    df["domain"] = df["domain"].fillna("other").str.lower()
    df["spread"] = pd.to_numeric(df.get("spread"), errors="coerce")
    return df.reset_index(drop=True)


def event_key(df):
    """Column grouping correlated markets (legs of one event); falls back to the market itself."""
    for col in ("event_id", "event_slug"):
        if col in df and df[col].notna().any():
            return col
    return "market_id"


def split_by_time(df, cutoff):
    """Train on events whose last market resolved before the cutoff, test on the rest:
    all legs of one event stay on the same side."""
    key = event_key(df)
    event_end = df.groupby(key)["resolved_at"].transform("max")
    if cutoff is None:
        per_event = df.groupby(key)["resolved_at"].max().sort_values()
        cutoff = per_event.iloc[int(len(per_event) * 0.7)].normalize()
    else:
        cutoff = pd.Timestamp(cutoff, tz="UTC")
    return df[event_end < cutoff], df[event_end >= cutoff], cutoff


# ---------- model ----------

class Calibrator:
    def __init__(self, domains):
        self.domains = domains

    def features(self, price, hours, domain):
        lp = logit(np.asarray(price, float))
        lh = np.log(np.clip(np.asarray(hours, float), 12, 720) / 24)  # stay inside the trained range
        dom = np.asarray([d if d in self.domains else "other" for d in domain])
        cols = [lp, lh, lp * lh]
        for d in self.domains[1:]:  # first domain is the reference level
            ind = (dom == d).astype(float)
            cols += [ind, ind * lp, ind * lp * lh]
        return np.column_stack(cols)

    def fit(self, df, rng):
        df = df[in_band(df["price_yes"])].reset_index(drop=True)
        X = self.features(df["price_yes"], df["horizon_hours"], df["domain"])
        y = df["outcome"].to_numpy()
        self.main = LogisticRegression(C=1.0, max_iter=2000).fit(X, y)
        # Bootstrap over events (rows of one market, and markets of one event, are correlated).
        cluster = event_key(df)
        ids = df[cluster].unique()
        rows = df.groupby(cluster).indices
        self.boot = []
        for _ in range(N_BOOT):
            pick = np.concatenate([rows[i] for i in rng.choice(ids, len(ids))])
            self.boot.append(LogisticRegression(C=1.0, max_iter=2000).fit(X[pick], y[pick]))
        return self

    def predict(self, price, hours, domain):
        p = np.asarray(price, float)
        X = self.features(p, hours, domain)
        q = self.main.predict_proba(X)[:, 1]
        qs = np.stack([m.predict_proba(X)[:, 1] for m in self.boot])
        lo, hi = np.percentile(qs, 10, axis=0), np.percentile(qs, 90, axis=0)
        band = in_band(p)
        return np.where(band, q, p), np.where(band, lo, p), np.where(band, hi, p)


def in_band(price):
    p = np.asarray(price, float)
    return (p >= TRADABLE[0]) & (p <= TRADABLE[1])


class MarketBaseline:
    """q = market price. Chosen when no model beats the market on validation, so every decision is NO_TRADE."""

    def predict(self, price, hours, domain):
        p = np.asarray(price, float)
        return p, p, p


def select_model(train, rng):
    """Pick market / simple / full by log loss on the last 20% of train (by resolution time). Test is untouched."""
    order = train.groupby("market_id")["resolved_at"].first().sort_values()
    val_ids = set(order.index[int(len(order) * 0.8):])
    fit, val = train[~train["market_id"].isin(val_ids)], train[train["market_id"].isin(val_ids)]
    val = val[in_band(val["price_yes"])]
    y = val["outcome"].to_numpy()
    scores = {"market": log_loss(val["price_yes"], y)}
    candidates = {"simple": ["other"], "full": pick_domains(fit)}
    for name, domains in candidates.items():
        q, _, _ = Calibrator(domains).fit(fit, rng).predict(val["price_yes"], val["horizon_hours"], val["domain"])
        scores[name] = log_loss(q, y)
    best = min(scores, key=scores.get)
    model = MarketBaseline() if best == "market" else Calibrator(
        ["other"] if best == "simple" else pick_domains(train)).fit(train, rng)
    return model, {"chosen": best, "val_markets": len(val_ids),
                   "val_logloss": {k: round(v, 4) for k, v in scores.items()}}


def pick_domains(train):
    counts = train["domain"].value_counts()
    keep = [d for d in counts.index if counts[d] >= MIN_DOMAIN_ROWS and d != "other"]
    return ["other"] + sorted(keep)


# ---------- metrics ----------

def brier(p, y):
    return float(np.mean((np.asarray(p) - y) ** 2))


def log_loss(p, y):
    p = np.clip(np.asarray(p), 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def reliability(price, q, y, n_bins=10):
    edges = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(price, edges) - 1, 0, n_bins - 1)
    bins = []
    for b in range(n_bins):
        m = idx == b
        if m.sum() == 0:
            continue
        bins.append({"price_mid": round((edges[b] + edges[b + 1]) / 2, 2), "observed": round(float(y[m].mean()), 4),
                     "model": round(float(q[m].mean()), 4), "n": int(m.sum())})
    return bins


def calibration_report(test, q):
    out = {}
    for dom in ["all"] + sorted(test["domain"].unique()):
        mask = np.ones(len(test), bool) if dom == "all" else (test["domain"] == dom).to_numpy()
        horizons = []
        for h in sorted(test.loc[mask, "horizon_hours"].unique(), reverse=True):
            m = mask & (test["horizon_hours"] == h).to_numpy()
            p, y = test["price_yes"].to_numpy()[m], test["outcome"].to_numpy()[m]
            horizons.append({"horizon_hours": int(h), "n": int(m.sum()),
                             "bins": reliability(p, q[m], y),
                             "brier_market": round(brier(p, y), 4), "brier_model": round(brier(q[m], y), 4),
                             "logloss_market": round(log_loss(p, y), 4), "logloss_model": round(log_loss(q[m], y), 4)})
        out[dom] = {"horizons": horizons}
    return out


# ---------- decision ----------

def trade_cost(spread, fee, min_half_spread):
    half = np.where(np.isnan(spread), min_half_spread, np.maximum(np.nan_to_num(spread) / 2, min_half_spread))
    return half + fee


def decide(p, q, cost, lo=None, hi=None):
    """Net edge per $1 contract, required to survive the model's own uncertainty: buy YES only if the
    low end of the q interval beats price + cost, buy NO only if the high end is below price - cost.
    Quarter Kelly on the conservative q. Outside the tradable band: NO_TRADE."""
    lo = q if lo is None else lo
    hi = q if hi is None else hi
    buy_yes = lo - (p + cost)         # pay p + cost for a contract worth at least lo
    buy_no = (p - cost) - hi          # pay (1 - p) + cost for a contract worth at least 1 - hi
    band = in_band(p)
    action = np.where(band & (buy_yes > 0), "BUY_YES", np.where(band & (buy_no > 0), "BUY_NO", "NO_TRADE"))
    q = np.where(action == "BUY_YES", lo, np.where(action == "BUY_NO", hi, q))
    py, pn = np.clip(p + cost, EPS, 1 - EPS), np.clip(1 - p + cost, EPS, 1 - EPS)
    kelly = np.where(action == "BUY_YES", (q - py) / (1 - py),
                     np.where(action == "BUY_NO", ((1 - q) - pn) / (1 - pn), 0.0))
    kelly = np.clip(kelly * KELLY_SCALE, 0, KELLY_CAP)
    edge = np.where(action == "BUY_NO", buy_no, buy_yes)
    return action, kelly, edge


def payoff(action, p, cost, y):
    """Return per $1 staked, held to resolution."""
    return np.where(action == "BUY_YES", y / np.clip(p + cost, EPS, 1) - 1,
                    np.where(action == "BUY_NO", (1 - y) / np.clip(1 - p + cost, EPS, 1) - 1, 0.0))


def run_policy(test, q, cost, lo, hi):
    """One trade per market: the earliest horizon (furthest from resolution) where the net edge is positive."""
    t = test.assign(q=q, cost=cost)
    t["action"], t["kelly"], t["edge"] = decide(t["price_yes"].to_numpy(), q, cost, lo, hi)
    t = t[t["action"] != "NO_TRADE"].sort_values("horizon_hours", ascending=False)
    trades = t.groupby("market_id").head(1).copy()
    trades["ret"] = payoff(trades["action"].to_numpy(), trades["price_yes"].to_numpy(),
                           trades["cost"].to_numpy(), trades["outcome"].to_numpy())
    return trades.sort_values("resolved_at")


def equity_stats(trades, stake):
    # stake: fraction of the starting bankroll per trade (scalar or per-trade array). Additive P&L in
    # resolution order, no compounding: positions overlap in time, so compounding would overstate.
    pnl = np.asarray(stake) * trades["ret"].to_numpy()
    equity = 1 + np.cumsum(pnl) if len(pnl) else np.array([])
    peak = np.maximum.accumulate(equity) if len(equity) else equity
    dd = float(np.max(peak - equity)) if len(equity) else 0.0  # in units of starting bankroll
    step = max(1, len(equity) // 200)
    curve = [{"t": ts.strftime("%Y-%m-%d"), "value": round(float(v), 4)}
             for ts, v in list(zip(trades["resolved_at"], equity))[::step]]
    return {"n_trades": int(len(trades)), "return": round(float(equity[-1] - 1), 4) if len(equity) else 0.0,
            "hit_rate": round(float((trades["ret"] > 0).mean()), 4) if len(trades) else None,
            "max_drawdown": round(dd, 4), "avg_edge": round(float(trades["edge"].mean()), 4) if len(trades) and "edge" in trades else None,
            "equity": curve}


def return_ci(trades, rng, n=1000, level=90):
    """CI on the with-costs return (additive P&L), resampling whole events: legs of one event move together."""
    if not len(trades):
        return None
    pnl = (trades["kelly"] * trades["ret"]).groupby(trades[event_key(trades)]).sum().to_numpy()
    sums = [pnl[rng.integers(0, len(pnl), len(pnl))].sum() for _ in range(n)]
    tail = (100 - level) / 2
    return [round(float(np.percentile(sums, tail)), 2), round(float(np.percentile(sums, 100 - tail)), 2)]


def by_horizon(test, q, cost, lo, hi):
    """If you could only act at one fixed horizon: is the edge tradable there?"""
    rows = []
    for h in sorted(test["horizon_hours"].unique(), reverse=True):
        m = (test["horizon_hours"] == h).to_numpy()
        p, y = test["price_yes"].to_numpy()[m], test["outcome"].to_numpy()[m]
        out = {"horizon_hours": int(h), "n_markets": int(m.sum())}
        for name, c in (("with_costs", cost[m]), ("without_costs", np.zeros(m.sum()))):
            action, kelly, edge = decide(p, q[m], c, lo[m], hi[m])
            traded = action != "NO_TRADE"
            r = payoff(action, p, c, y)[traded]
            out[name] = {"n_trades": int(traded.sum()),
                         "mean_return_per_trade": round(float(r.mean()), 4) if traded.any() else None,
                         "hit_rate": round(float((r > 0).mean()), 4) if traded.any() else None}
        rows.append(out)
    return rows


def naive_favourite(test, cost, stake=0.02):
    t = test.assign(cost=cost)[in_band(test["price_yes"])].sort_values("horizon_hours", ascending=False).groupby("market_id").head(1)
    action = np.where(t["price_yes"] >= 0.5, "BUY_YES", "BUY_NO")
    t = t.assign(ret=payoff(action, t["price_yes"].to_numpy(), t["cost"].to_numpy(), t["outcome"].to_numpy()))
    s = equity_stats(t.sort_values("resolved_at"), stake)
    return {"return": s["return"], "n_trades": s["n_trades"], "hit_rate": s["hit_rate"], "stake": stake}


def failures(test, q, cal, trades):
    out = []
    for dom, rep in cal.items():
        for h in rep["horizons"]:
            if h["n"] >= 30 and h["brier_model"] >= h["brier_market"]:
                out.append({"kind": "no_lift", "domain": dom, "horizon_hours": h["horizon_hours"], "n": h["n"],
                            "text": f"{dom}, {h['horizon_hours']}h: model Brier {h['brier_model']} vs market {h['brier_market']} — no lift"})
            elif h["n"] < 30:
                out.append({"kind": "thin_data", "domain": dom, "horizon_hours": h["horizon_hours"], "n": h["n"],
                            "text": f"{dom}, {h['horizon_hours']}h: only {h['n']} test markets — too few to trust"})
    t = trades.assign(pnl=trades["kelly"] * trades["ret"])
    for dom, g in t.groupby("domain"):
        if len(g) >= 20 and g["pnl"].sum() < 0:
            out.append({"kind": "losing_domain", "domain": dom, "horizon_hours": None, "n": int(len(g)),
                        "text": f"{dom}: {len(g)} trades lost {abs(g['pnl'].sum()):.2f} bankroll units — the market is better calibrated here than the model assumes"})
    rank = {"losing_domain": 0, "no_lift": 1, "thin_data": 2}
    out.sort(key=lambda f: rank[f["kind"]])
    worst = trades.sort_values("ret").head(5)
    worst_trades = [{"question": r.question, "action": r.action, "price_yes": round(r.price_yes, 3), "q_yes": round(r.q, 3),
                     "outcome": int(r.outcome), "horizon_hours": int(r.horizon_hours), "ret": round(r.ret, 3)}
                    for r in worst.itertuples()]
    return out, worst_trades


# ---------- live ----------

def horizon_label(h):
    return f"{h / 24:.0f}d" if h >= 48 else f"{h:.0f}h"


def live_report(model, live, fee, min_half_spread, n_trades=30, n_no_trade=15):
    live = live[live["price_yes"].between(0, 1, inclusive="neither")].copy()
    live["domain"] = live["domain"].fillna("other").str.lower()
    p = live["price_yes"].to_numpy()
    q, lo, hi = model.predict(p, live["hours_to_resolution"], live["domain"])
    cost = trade_cost(pd.to_numeric(live["spread"], errors="coerce").to_numpy(), fee, min_half_spread)
    action, kelly, edge = decide(p, q, cost, lo, hi)
    out = []
    for i, r in enumerate(live.itertuples()):
        gap = (q[i] - p[i]) * 100
        if not in_band(p[i]):
            reason = f"Market at {p[i]:.1%}: too close to certain, a {cost[i] * 100:.0f}¢ cost exceeds any edge"
        elif action[i] == "NO_TRADE":
            reason = (f"Model {q[i]:.0%} (range {lo[i]:.0%}–{hi[i]:.0%}) vs market {p[i]:.0%}: "
                      f"the {abs(gap):.1f}¢ gap is inside the model's uncertainty plus {cost[i] * 100:.0f}¢ cost")
        else:
            reason = f"{horizon_label(r.hours_to_resolution)} out, {r.domain}: model {q[i]:.0%} vs market {p[i]:.0%}, net edge {edge[i] * 100:.1f}¢"
        out.append({"market_id": str(r.market_id), "question": r.question, "domain": r.domain,
                    "price_yes": round(float(p[i]), 4), "hours_to_resolution": float(r.hours_to_resolution),
                    "q_yes": round(float(q[i]), 4), "q_low": round(float(lo[i]), 4), "q_high": round(float(hi[i]), 4),
                    "edge": round(float(q[i] - p[i]), 4), "net_edge": round(float(edge[i]), 4), "cost": round(float(cost[i]), 4),
                    "action": str(action[i]), "kelly_fraction": round(float(kelly[i]), 4), "reason": reason,
                    "url": getattr(r, "url", "") or "", "volume_usd": float(r.volume_usd)})
    trades = sorted((x for x in out if x["action"] != "NO_TRADE"), key=lambda x: -x["net_edge"])[:n_trades]
    # Biggest markets where the honest answer is "don't trade".
    no_trade = sorted((x for x in out if x["action"] == "NO_TRADE" and in_band(x["price_yes"])),
                      key=lambda x: -x["volume_usd"])[:n_no_trade]
    return trades + no_trade


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(HERE.parent / "data"))
    ap.add_argument("--out", default=str(HERE / "results"))
    ap.add_argument("--cutoff", default=None, help="markets resolved before this date train (default: 70th percentile)")
    ap.add_argument("--fee", type=float, default=0.0, help="fee per $1 contract")
    ap.add_argument("--min-half-spread", type=float, default=0.01, help="cost floor per contract when spread is unknown/tiny")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    df = load_horizons(Path(a.data) / "horizons.csv")
    train, test, cutoff = split_by_time(df, a.cutoff)
    model, selection = select_model(train, rng)
    q, lo, hi = model.predict(test["price_yes"], test["horizon_hours"], test["domain"])
    y = test["outcome"].to_numpy()
    cost = trade_cost(test["spread"].to_numpy(dtype=float), a.fee, a.min_half_spread)

    cal = calibration_report(test, q)
    (out / "calibration.json").write_text(json.dumps({"cutoff": str(cutoff.date()), "by_domain": cal}, indent=1))

    with_c = run_policy(test, q, cost, lo, hi)
    without_c = run_policy(test, q, np.zeros(len(test)), lo, hi)
    fails, worst = failures(test, q, cal, with_c)
    backtest = {
        "cutoff": str(cutoff.date()),
        "n_train_markets": int(train["market_id"].nunique()), "n_test_markets": int(test["market_id"].nunique()),
        "n_trades": int(len(with_c)),
        "model_selection": selection,
        "with_costs": equity_stats(with_c, with_c["kelly"].to_numpy()),
        "return_ci": return_ci(with_c, rng),
        "without_costs": equity_stats(without_c, without_c["kelly"].to_numpy()),
        "naive_favourite": naive_favourite(test, cost),
        "overall": {"brier_market": round(brier(test["price_yes"], y), 4), "brier_model": round(brier(q, y), 4),
                    "logloss_market": round(log_loss(test["price_yes"], y), 4), "logloss_model": round(log_loss(q, y), 4)},
        "by_horizon": by_horizon(test, q, cost, lo, hi),
        "failures": fails, "worst_trades": worst,
        "assumptions": [
            "Split by time: train on markets resolved before the cutoff, test on markets resolved after it.",
            f"Cost per contract = max(spread / 2, {a.min_half_spread}) + fee {a.fee}; spread is the market's quoted spread, not the historical one.",
            "One trade per market, at the earliest horizon with positive net edge, held to resolution.",
            f"Only prices in {TRADABLE[0]:.0%}–{TRADABLE[1]:.0%} are modelled or traded; edge must survive the model's 10–90% bootstrap interval (resampled by event).",
            f"Stake = {KELLY_SCALE} Kelly on the conservative q, capped at {KELLY_CAP:.0%} of the starting bankroll; P&L is additive (no compounding) because positions overlap.",
            "Prices are Polymarket price history at each horizon; fills at that price are assumed.",
        ],
    }
    (out / "backtest.json").write_text(json.dumps(backtest, indent=1, default=str))

    live_path = Path(a.data) / "live.csv"
    if live_path.exists():
        live = live_report(model, pd.read_csv(live_path), a.fee, a.min_half_spread)
        (out / "live.json").write_text(json.dumps(live, indent=1))

    o = backtest["overall"]
    print(f"model selection: {selection}")
    print(f"cutoff {cutoff.date()}  train {backtest['n_train_markets']}  test {backtest['n_test_markets']} markets")
    print(f"Brier market {o['brier_market']}  model {o['brier_model']}   logloss market {o['logloss_market']}  model {o['logloss_model']}")
    for k in ("with_costs", "without_costs"):
        s = backtest[k]
        print(f"{k:14s} trades {s['n_trades']:4d}  return {s['return']:+.3f}  hit {s['hit_rate']}  maxDD {s['max_drawdown']}")
    print(f"naive favourite return {backtest['naive_favourite']['return']:+.3f}")
    for h in backtest["by_horizon"]:
        print(f"  {h['horizon_hours']:4d}h  n {h['n_markets']:4d}  with costs {h['with_costs']}")


if __name__ == "__main__":
    main()
