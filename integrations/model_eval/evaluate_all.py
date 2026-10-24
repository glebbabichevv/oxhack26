"""Every candidate model scored on its own, same harness -> integrations/model_eval/results.json + VALIDATION.md

  python integrations/model_eval/evaluate_all.py [--test-q]

Evaluation only: nothing here changes backend/, the site or the shipped model.
Split, costs, policy and exposure are exactly backend/playoff.py's:
  validation = last 20% of TRAIN markets by resolution time, models fitted on the first 80% (seed 0);
  test       = model.split_by_time at the shipped cutoff, models fitted on all of train (predictions only);
  embargo    = a trade counts only if its entry time is at or after the start of the scored period;
  policy V3  = min net edge 1¢, enter only within 24 h of the scheduled end, one trade per market;
  costs      = max(spread/2, 1¢) + each market's Polymarket taker fee; ¼ Kelly capped 5%, open stake <= 1 bankroll.
Every member gets its own 10–90% band from refits on events resampled with replacement (Shin has no fit: band = q).
VALIDATION ONLY (A, 23:08): every member is scored on validation; the test set is not scored here.
`--test-q` also writes unscored test predictions for whoever opens the test once. No member is promoted from here.
A's 23:08 list for C: shin, power, isotonic, hierarchical. The rest are reference rows in the same harness.

Members (all predict only inside the 3–97¢ band; outside it q = price):
  market      q = price (the baseline)
  M0          shipped model: logistic on logit(p), log h, logit(p)·log h
  M0_domain   M0 + per-domain intercept and slopes (backend's "full")
  beta        Kull et al. 2017 beta calibration: logistic on ln p, ln(1−p)  (asymmetric favourite/longshot)
  beta_h      beta + log h and both log-price terms × log h
  isotonic    monotone price → frequency map, one per horizon (non-parametric)
  M1_lite     logistic on M0 terms + by-date question flag, legs in the event, leg's share of the book, domain
  M2_lite     gradient boosting on the M1_lite features, anchored to the market (log-odds shift <= 0.7)
  shin        Shin (1993) fair probabilities from all legs of a neg-risk event at the same horizon
              (books summing 0.9–1.15 only; z = 0 when the book is not overround; elsewhere q = price)
  power       power method: q_i = p_i^k, k solved so the same near-complete book sums to 1
  shin_spread / power_spread  Shin / power on every binary row, overround = the two asks (p + h, 1 - p + h)
  shin_fit    Shin's insider share z fitted per horizon by maximum likelihood (z < 0 allowed: the data may say
              longshots are UNDER-priced, the opposite of Shin's assumption)
  power_fit   power exponent k fitted per horizon (q = p^k / (p^k + (1-p)^k), i.e. logit q = k·logit p)
  hierarchical M0 + per-domain intercept and logit(p) slope, L2-shrunk toward the pooled fit (partial pooling)
  M0_coherent M0, then q normalised to sum 1 over the same near-complete books, max one bet per event
Mixes (reported as extra rows, same harness): mean of M0, M1_lite, M2_lite, beta_h (+ shin), and the
agreement filter (trade only if every member's q is on the same side of the price and their spread < 3¢).
M1_lite / M2_lite drop model_v2's momentum and volatility features: the hourly paths for all 34,677 markets
are not on this machine. model_v2's full M1 / M2 lost to M0 on validation log loss (its README).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import playoff as P  # noqa: E402  (also puts backend's model on the path)
from model import (brier, decide, event_key, exposure, fee_per_share, in_band, load_horizons, log_loss,  # noqa: E402
                   pick_domains, split_by_time, trade_cost)

N_BOOT = 20
MIN_EDGE, ENTER_FROM = 0.01, 24  # policy V3, as shipped
BOOK = (0.9, 1.15)  # a neg-risk book counts as near-complete when its legs' prices sum to this range
AGREE_SPREAD = 0.03
BY_DATE = r"\b(?:by|before)\b\s+(?:the\s+end\s+of\s+)?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d|q[1-4]|end|202)"
EPS = 1e-4


def lg(p):
    p = np.clip(np.asarray(p, float), 0.01, 0.99)
    return np.log(p / (1 - p))


def prepare(df):
    df = df.copy()
    df["lp"] = lg(df["price_yes"])
    df["lh"] = np.log(np.clip(df["horizon_hours"].to_numpy(float), 12, 720) / 24)
    df["by_date"] = df["question"].fillna("").str.contains(BY_DATE, case=False, regex=True).astype(float)
    g = df.groupby(["event_slug", "horizon_hours"])["price_yes"]
    df["n_legs"] = g.transform("size")
    df["book_sum"] = g.transform("sum")
    df["book_share"] = np.where(df["n_legs"] > 1, df["price_yes"] / df["book_sum"], 1.0)
    df["book"] = (df["neg_risk"].astype(str).str.lower().eq("true") & (df["n_legs"] > 1)
                  & df["book_sum"].between(*BOOK)).to_numpy()
    return df


DOMAINS = ["sports", "crypto", "politics", "economics", "culture", "science_tech", "geopolitics"]


def x_m0(d):
    return np.column_stack([d.lp, d.lh, d.lp * d.lh])


def x_beta(d):
    p = np.clip(d["price_yes"].to_numpy(float), 0.01, 0.99)
    return np.column_stack([np.log(p), -np.log(1 - p)])


def x_beta_h(d):
    b = x_beta(d)
    return np.column_stack([b, d.lh, b[:, 0] * d.lh, b[:, 1] * d.lh])


def x_lite(d):
    cols = [d.lp, d.lh, d.lp * d.lh, d.by_date, d.lp * d.by_date, np.log(d.n_legs), d.book_share]
    return np.column_stack(cols + [(d["domain"] == k).to_numpy(float) for k in DOMAINS])


class Fitted:
    """Main fit + event-bootstrap refits for the 10–90% band. Predicts only inside the tradable band."""

    def __init__(self, name, xf, est, anchor=False):
        self.name, self.xf, self.est, self.anchor = name, xf, est, anchor

    def _q(self, m, d):
        q = m.predict_proba(self.xf(d))[:, 1]
        if self.anchor:
            q = 1 / (1 + np.exp(-(d.lp.to_numpy() + np.clip(lg(q) - d.lp.to_numpy(), -0.7, 0.7))))
        return q

    def fit(self, df, rng):
        d = df[in_band(df["price_yes"])].reset_index(drop=True)
        X, y = self.xf(d), d["outcome"].to_numpy()
        self.main = self.est().fit(X, y)
        rows = d.groupby(event_key(d)).indices
        ids = np.array(list(rows))
        self.boot = []
        for _ in range(N_BOOT):
            pick = np.concatenate([rows[i] for i in rng.choice(ids, len(ids))])
            self.boot.append(self.est().fit(X[pick], y[pick]))
        return self

    def predict(self, d):
        p = d["price_yes"].to_numpy(float)
        q = self._q(self.main, d)
        qs = np.stack([self._q(m, d) for m in self.boot])
        lo, hi = np.percentile(qs, 10, axis=0), np.percentile(qs, 90, axis=0)
        b = in_band(p)
        return np.where(b, q, p), np.where(b, lo, p), np.where(b, hi, p)


class Isotonic:
    name = "isotonic"

    def _fit1(self, d):
        return {h: IsotonicRegression(y_min=EPS, y_max=1 - EPS, out_of_bounds="clip").fit(g["price_yes"], g["outcome"])
                for h, g in d.groupby("horizon_hours")}

    def fit(self, df, rng):
        d = df[in_band(df["price_yes"])].reset_index(drop=True)
        self.main = self._fit1(d)
        rows = d.groupby(event_key(d)).indices
        ids = np.array(list(rows))
        self.boot = [self._fit1(d.iloc[np.concatenate([rows[i] for i in rng.choice(ids, len(ids))])])
                     for _ in range(N_BOOT)]
        return self

    @staticmethod
    def _q(maps, d):
        q = d["price_yes"].to_numpy(float).copy()
        for h, idx in d.groupby("horizon_hours").indices.items():
            if h in maps:
                q[idx] = maps[h].predict(q[idx])
        return q

    def predict(self, d):
        p = d["price_yes"].to_numpy(float)
        q = self._q(self.main, d)
        qs = np.stack([self._q(m, d) for m in self.boot])
        lo, hi = np.percentile(qs, 10, axis=0), np.percentile(qs, 90, axis=0)
        b = in_band(p)
        return np.where(b, q, p), np.where(b, lo, p), np.where(b, hi, p)


def shin_probs(pi):
    """Shin (1993): solve for the insider share z so the fair probabilities sum to 1. Needs an overround book."""
    s = pi.sum()
    if s <= 1:
        return pi / s, 0.0  # no overround: Shin's z is 0, the fair probabilities are the normalised prices

    def fair(z):
        return (np.sqrt(z * z + 4 * (1 - z) * pi * pi / s) - z) / (2 * (1 - z))

    lo, hi = 0.0, 0.999
    for _ in range(60):
        z = (lo + hi) / 2
        lo, hi = (z, hi) if fair(z).sum() > 1 else (lo, z)
    z = (lo + hi) / 2
    return fair(z), z


def coherent(d, q):
    """Normalise q to sum 1 within each near-complete neg-risk book (same event, same horizon)."""
    q = q.copy()
    for _, idx in d[d["book"]].groupby(["event_slug", "horizon_hours"]).indices.items():
        rows = d.index.get_indexer(d[d["book"]].index[idx])
        q[rows] = q[rows] / q[rows].sum()
    return q


class Shin:
    name = "shin"

    def fit(self, df, rng):
        return self

    def predict(self, d):
        p = d["price_yes"].to_numpy(float)
        q = p.copy()
        self.z = []
        sub = d[d["book"]]
        for _, idx in sub.groupby(["event_slug", "horizon_hours"]).indices.items():
            rows = d.index.get_indexer(sub.index[idx])
            q[rows], z = shin_probs(p[rows])
            self.z.append(z)
        q = np.where(in_band(p), np.clip(q, EPS, 1 - EPS), p)
        return q, q, q


class Power:
    """Power method: q_i = p_i^k with k solved so the near-complete book sums to 1 (elsewhere q = price)."""
    name = "power"

    def fit(self, df, rng):
        return self

    def predict(self, d):
        p = d["price_yes"].to_numpy(float)
        q = p.copy()
        self.k = []
        sub = d[d["book"]]
        for _, idx in sub.groupby(["event_slug", "horizon_hours"]).indices.items():
            rows = d.index.get_indexer(sub.index[idx])
            pi = np.clip(p[rows], EPS, 1 - EPS)
            lo, hi = 0.05, 20.0  # sum(pi^k) falls as k rises
            for _ in range(60):
                k = (lo + hi) / 2
                lo, hi = (k, hi) if (pi ** k).sum() > 1 else (lo, k)
            q[rows] = pi ** ((lo + hi) / 2)
            self.k.append((lo + hi) / 2)
        q = np.where(in_band(p), np.clip(q, EPS, 1 - EPS), p)
        return q, q, q


def half_spread(d):
    sp = d["spread"].to_numpy(dtype=float)
    return np.where(np.isnan(sp), 0.01, np.maximum(np.nan_to_num(sp) / 2, 0.01))


class SpreadBook:
    """Shin / power on EVERY binary row: the book is the two asks, YES at p + h and NO at 1 - p + h
    (h = max(quoted half-spread, 1¢), the same floor as the cost), so the overround is 2h on every market."""

    def __init__(self, kind):
        self.kind, self.name = kind, f"{kind}_spread"

    def fit(self, df, rng):
        return self

    def predict(self, d):
        p = d["price_yes"].to_numpy(float)
        h = half_spread(d)
        a, b = np.clip(p + h, EPS, 1 - EPS), np.clip(1 - p + h, EPS, 1 - EPS)
        s = a + b
        if self.kind == "shin":
            def fair(z, x):
                return (np.sqrt(z * z + 4 * (1 - z) * x * x / s) - z) / (2 * (1 - z))
            lo, hi = np.zeros_like(p), np.full_like(p, 0.999)
            for _ in range(60):  # sum of fair probabilities falls as z rises
                z = (lo + hi) / 2
                big = fair(z, a) + fair(z, b) > 1
                lo, hi = np.where(big, z, lo), np.where(big, hi, z)
            z = (lo + hi) / 2
            q = fair(z, a) / (fair(z, a) + fair(z, b))
        else:
            lo, hi = np.ones_like(p), np.full_like(p, 20.0)
            for _ in range(60):  # a^k + b^k falls as k rises
                k = (lo + hi) / 2
                big = a ** k + b ** k > 1
                lo, hi = np.where(big, k, lo), np.where(big, hi, k)
            k = (lo + hi) / 2
            q = a ** k / (a ** k + b ** k)
        q = np.where(in_band(p), np.clip(q, EPS, 1 - EPS), p)
        return q, q, q


def shin_binary(p, z):
    """Shin's fair YES probability for a two-outcome book with no overround and insider share z
    (z > 0 shaves longshots as Shin assumes; z < 0 is allowed so the data can say the opposite)."""
    p = np.clip(p, EPS, 1 - EPS)
    fy = np.sqrt(z * z + 4 * (1 - z) * p * p) - z
    fn = np.sqrt(z * z + 4 * (1 - z) * (1 - p) ** 2) - z
    return fy / (fy + fn)


def power_binary(p, k):
    """Power method with a free exponent: q = p^k / (p^k + (1-p)^k), i.e. logit q = k * logit p."""
    p = np.clip(p, EPS, 1 - EPS)
    return p ** k / (p ** k + (1 - p) ** k)


class ScalarFit:
    """One parameter per horizon, fitted by maximum likelihood on the fitting rows; event-bootstrap band."""

    def __init__(self, name, f, bounds):
        self.name, self.f, self.bounds = name, f, bounds

    def _fit1(self, d):
        from scipy.optimize import minimize_scalar
        out = {}
        for h, g in d.groupby("horizon_hours"):
            p, y = g["price_yes"].to_numpy(float), g["outcome"].to_numpy()
            out[h] = minimize_scalar(lambda t: log_loss(np.clip(self.f(p, t), EPS, 1 - EPS), y),
                                     bounds=self.bounds, method="bounded").x
        return out

    def fit(self, df, rng):
        d = df[in_band(df["price_yes"])].reset_index(drop=True)
        self.main = self._fit1(d)
        rows = d.groupby(event_key(d)).indices
        ids = np.array(list(rows))
        self.boot = [self._fit1(d.iloc[np.concatenate([rows[i] for i in rng.choice(ids, len(ids))])])
                     for _ in range(N_BOOT)]
        self.info = {int(h): round(float(v), 4) for h, v in self.main.items()}
        return self

    def _q(self, par, d):
        p = d["price_yes"].to_numpy(float)
        t = d["horizon_hours"].map(lambda h: par.get(h, np.nan)).to_numpy(float)
        return np.where(np.isnan(t), p, self.f(p, np.nan_to_num(t, nan=1.0)))

    def predict(self, d):
        p = d["price_yes"].to_numpy(float)
        q = self._q(self.main, d)
        qs = np.stack([self._q(m, d) for m in self.boot])
        lo, hi = np.percentile(qs, 10, axis=0), np.percentile(qs, 90, axis=0)
        b = in_band(p)
        return np.where(b, q, p), np.where(b, lo, p), np.where(b, hi, p)


SCALE = 10.0  # pooled terms are scaled up so the L2 penalty effectively falls on the per-domain deviations only
SHRINK_GRID = (0.003, 0.01, 0.03, 0.1, 1.0)


def hierarchical(train):
    """Partial pooling: pooled M0 terms + per-domain intercept and logit(p) slope deviations, L2-shrunk toward 0
    (i.e. toward the pooled slope). Shrinkage C picked on an inner time split of the fitting rows only."""
    doms = [k for k in DOMAINS if (train["domain"] == k).sum() >= 200]

    def xf(d):
        cols = [SCALE * d.lp, SCALE * d.lh, SCALE * d.lp * d.lh]
        for k in doms:
            ind = (d["domain"] == k).to_numpy(float)
            cols += [ind, ind * d.lp]
        return np.column_stack(cols)

    d = prepare(train) if "lp" not in train else train
    d = d[in_band(d["price_yes"])]
    order = d.groupby("market_id")["resolved_at"].first().sort_values()
    inner = set(order.index[int(len(order) * 0.8):])
    a, b = d[~d["market_id"].isin(inner)], d[d["market_id"].isin(inner)]
    ll = {C: log_loss(np.clip(LogisticRegression(C=C, max_iter=3000).fit(xf(a), a["outcome"]).predict_proba(xf(b))[:, 1],
                              EPS, 1 - EPS), b["outcome"].to_numpy()) for C in SHRINK_GRID}
    C = min(ll, key=ll.get)
    m = Fitted("hierarchical", xf, lambda: LogisticRegression(C=C, max_iter=3000))
    m.info = {"C": C, "domains": doms, "inner_logloss": {str(k): round(v, 5) for k, v in ll.items()}}
    return m


def members(train):
    lr = lambda: LogisticRegression(C=1.0, max_iter=3000)  # noqa: E731
    doms = [k for k in pick_domains(train) if k != "other"]

    def x_dom(d):
        cols = [d.lp, d.lh, d.lp * d.lh]
        for k in doms:
            ind = (d["domain"] == k).to_numpy(float)
            cols += [ind, ind * d.lp, ind * d.lp * d.lh]
        return np.column_stack(cols)

    return [Fitted("M0", x_m0, lr), Fitted("M0_domain", x_dom, lr), Fitted("beta", x_beta, lr),
            Fitted("beta_h", x_beta_h, lr), Isotonic(),
            Fitted("M1_lite", x_lite, lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=3000))),
            Fitted("M2_lite", x_lite, lambda: HistGradientBoostingClassifier(
                max_depth=3, learning_rate=0.05, max_iter=300, min_samples_leaf=200, early_stopping=True,
                validation_fraction=0.15, random_state=0), anchor=True),
            Shin(), Power(), SpreadBook("shin"), SpreadBook("power"),
            ScalarFit("shin_fit", shin_binary, (-0.5, 0.5)), ScalarFit("power_fit", power_binary, (0.3, 3.0)),
            hierarchical(train)]


def candidates(d, q, lo, hi):
    p = d["price_yes"].to_numpy(float)
    cost = trade_cost(d["spread"].to_numpy(dtype=float), fee_per_share(d), 0.01)
    action, kelly, edge = decide(p, q, cost, lo, hi)
    return d.assign(q=q, cost=cost, action=action, kelly=kelly, edge=edge)


def money(c, one_per_event=False):
    t = P.policy(c, MIN_EDGE, ENTER_FROM)
    if one_per_event and len(t):
        t = t.sort_values("edge", ascending=False).groupby(event_key(t)).head(1).sort_values("resolved_at")
    if not len(t):
        return {"n_trades": 0}
    _, capped = exposure(t, t["kelly"].to_numpy())
    s = P.stats(t, capped)
    return {k: s[k] for k in ("n_trades", "per_dollar", "per_dollar_ci", "return", "return_ci", "hit_rate", "max_drawdown")}


def scores(d, q):
    b = in_band(d["price_yes"])
    near = b & (d["horizon_hours"] <= ENTER_FROM).to_numpy()
    y = d["outcome"].to_numpy()
    qc = np.clip(q, EPS, 1 - EPS)
    return {"brier": round(brier(qc[b], y[b]), 5), "logloss": round(log_loss(qc[b], y[b]), 5),
            "brier_le24h": round(brier(qc[near], y[near]), 5), "logloss_le24h": round(log_loss(qc[near], y[near]), 5),
            "n_rows": int(b.sum()), "n_rows_le24h": int(near.sum())}


def period(fit_rows, rows, start, seed=0, score=True):
    """Fit every member on fit_rows and predict rows (embargoed from start); score them only if score=True."""
    fit_rows, rows = prepare(fit_rows), prepare(rows)
    rows = rows[P.entry_time(rows) >= start].reset_index(drop=True)
    preds, out, extra = {}, {}, {}
    p = rows["price_yes"].to_numpy(float)
    preds["market"] = (p, p, p)
    for m in members(fit_rows):
        print("  fit", m.name, flush=True)
        preds[m.name] = m.fit(fit_rows, np.random.default_rng(seed)).predict(rows)
        if m.name == "shin":
            z = np.array(m.z)
            extra["shin"] = {"books": int(len(z)), "books_overround": int((z > 0).sum()),
                             "median_z_overround": round(float(np.median(z[z > 0])), 4) if (z > 0).any() else None,
                             "rows_changed": int((np.abs(preds["shin"][0] - p) > 1e-9).sum())}
        if m.name == "power":
            extra["power"] = {"books": len(m.k), "median_k": round(float(np.median(m.k)), 4) if m.k else None,
                              "rows_changed": int((np.abs(preds["power"][0] - p) > 1e-9).sum())}
        if m.name in ("shin_fit", "power_fit"):
            extra[m.name] = {"param_by_horizon": m.info}
        if m.name == "hierarchical":
            extra["hierarchical"] = m.info
    q0, lo0, hi0 = preds["M0"]
    preds["M0_coherent"] = tuple(coherent(rows, a) for a in (q0, lo0, hi0))
    mix = ["M0", "M1_lite", "M2_lite", "beta_h"]
    for name, ms in (("mix_4", mix), ("mix_4+shin", mix + ["shin"])):
        preds[name] = tuple(np.mean([preds[k][i] for k in ms], axis=0) for i in range(3))
    qframe = rows.copy()
    for name, (q, lo, hi) in preds.items():
        qframe[f"q_{name}"], qframe[f"lo_{name}"], qframe[f"hi_{name}"] = q, lo, hi
    if not score:
        return None, extra, qframe
    for name, (q, lo, hi) in preds.items():
        c = candidates(rows, q, lo, hi)
        out[name] = {**scores(rows, q), "money_V3": money(c, one_per_event=(name == "M0_coherent"))}
    # agreement filter on the 4-member mix
    qs = np.stack([preds[k][0] for k in mix])
    agree = (np.all(qs > p, axis=0) | np.all(qs < p, axis=0)) & (qs.max(0) - qs.min(0) < AGREE_SPREAD)
    c = candidates(rows, *preds["mix_4"])
    c.loc[~agree, "action"] = "NO_TRADE"
    out["mix_4_agree"] = {**scores(rows, preds["mix_4"][0]), "money_V3": money(c),
                          "rows_agreeing": round(float(agree[in_band(p)].mean()), 4)}
    return out, extra, qframe


KEEP = ["market_id", "event_slug", "horizon_hours", "price_yes", "outcome", "resolved_at"]


def qcols(qf):
    return qf[KEEP + [c for c in qf if c.startswith(("q_", "lo_", "hi_"))]]


def main():
    df = load_horizons(ROOT / "data" / "horizons.csv")
    train, test, cutoff = split_by_time(df, P.CUTOFF)
    order = train.groupby("market_id")["resolved_at"].first().sort_values()
    val_ids = set(order.index[int(len(order) * 0.8):])
    fit, val = train[~train["market_id"].isin(val_ids)], train[train["market_id"].isin(val_ids)]
    print("validation", flush=True)
    v, vx, vq = period(fit, val, val["resolved_at"].min())
    HERE.mkdir(exist_ok=True)
    qcols(vq).to_csv(HERE / "q_validation.csv.gz", index=False)
    if "--test-q" in sys.argv:  # predictions only, NOT scored here: the test is opened once, by whoever picks the winner
        print("test predictions (unscored)", flush=True)
        _, _, tq = period(train, test, cutoff, score=False)
        qcols(tq).drop(columns=["outcome"]).to_csv(HERE / "q_test_unscored.csv.gz", index=False)
    res = {"protocol": __doc__.strip(), "cutoff": str(cutoff.date()), "n_validation_markets": len(val_ids),
           "validation": v, "details": vx}
    (HERE / "results.json").write_text(json.dumps(res, indent=1), encoding="utf-8")

    def cell(s):
        m = s["money_V3"]
        if not m.get("n_trades"):
            return f"{s['brier']:.4f} | {s['logloss']:.4f} | {s['logloss_le24h']:.4f} | – | 0"
        lo, hi = m["per_dollar_ci"]
        return (f"{s['brier']:.4f} | {s['logloss']:.4f} | {s['logloss_le24h']:.4f} | "
                f"{m['per_dollar'] * 100:+.1f}¢ [{lo * 100:+.1f}, {hi * 100:+.1f}] | {m['n_trades']:,}")

    hdr = ("| model | Brier | log loss | log loss ≤24h | ¢ per $1 after fees, V3 [90% CI] | trades |\n"
           "|---|---|---|---|---|---|")
    md = ["# Every model, scored separately (generated by evaluate_all.py)\n",
          "Same split, fees, V3 policy and exposure cap as `backend/playoff.py`. Lower Brier / log loss is better. "
          "VALIDATION ONLY: the test set is not scored here (it is opened once, for the winner). "
          "Per-row q / lo / hi for every member: `q_validation.csv.gz`.\n"]
    md += [f"## Validation ({len(val_ids):,} markets, last 20% of train)\n", hdr]
    md += [f"| {k} | {cell(s)} |" for k, s in v.items()] + [""]
    md += [f"Near-complete neg-risk books = legs of one event at one horizon summing {BOOK[0]}–{BOOK[1]}. "
           f"Details (Shin z, power k, hierarchical shrinkage): `{json.dumps(vx)}`"]
    (HERE / "VALIDATION.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("wrote", HERE / "VALIDATION.md")


if __name__ == "__main__":
    main()
