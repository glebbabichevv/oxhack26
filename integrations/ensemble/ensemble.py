"""Ensemble playoff (Gleb's 23:05 task): which probability q should V3 trade on? VALIDATION ONLY, then one test.

  python integrations/ensemble/ensemble.py [--raw data/raw]          # VALIDATION only -> results.json
  python integrations/ensemble/ensemble.py [--raw data/raw] --test   # at 01:00: also scores the test ONCE

Candidate list (fixed; Gleb 23:08: no new variants after 00:00, ~9 in total). Ayaz's 5: V3, COH, BETA, ENS,
AGREE (below). TheMarkz3's 4 are read from members/<name>_val.csv and members/<name>_test.csv (columns
market_id, horizon_hours, q; validation q fitted on the fit slice, test q fitted on all of train, same split
as here): shin, power, isotonic, hier. Each is scored as its own candidate (V3 rules on that q) and joins the
ensemble. If Mark's shin is missing at 00:00, the built-in SHIN below is used as the ensemble's Shin member
(stated in results.json). Ayaz's candidates:
  (a) V3      M0 (backend Calibrator, the shipped model) — the baseline
  (b) COH     (a) + event coherence: in neg-risk events, q normalised across the legs priced at that horizon
              so they sum to 1 (only when the legs' prices sum to 0.95–1.25, i.e. the book looks complete),
              and at most ONE bet per event (the largest net edge)
  (c) BETA    beta calibration (Kull et al. 2017): logit q = a*ln p - b*ln(1-p) + c, per horizon bucket
              (log horizon as an extra term), fitted on the fit slice
  fallback SHIN (ensemble member only, not a candidate): Shin (1993) from all outcome prices of a neg-risk
              event (books summing to 1.0–1.25; otherwise q = p)
  (e) ENS     mean of M0, M1, M2 (integrations/model_v2), BETA and Mark's members (or the fallback SHIN)
  (f) AGREE   ENS, trading only when every member's edge has the same sign and the members' q spread is
              below a threshold chosen on validation from {2, 4, 6, 10}c

Everything else is exactly backend/playoff.py's V3: same split (validation = last 20% of train markets by
resolution, models fitted on the first 80%; test = shipped cutoff, models refitted on all of train), same
embargo, same fees (each market's Gamma fee schedule), same decide() with min edge 1c and entry only within
24 h of the end, same "ours" exposure (1/4 Kelly, 5%/trade, open stake <= 1 bankroll). The uncertainty band of
every non-M0 candidate is M0's band shifted to that candidate's q (same width), so decide() is not given
a narrower band just by switching models. Selection: highest validation per-$ return; ties within 0.5c go
to the earlier (simpler) candidate. The test set is scored once, for the winner and for V3 as reference.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "integrations" / "model_v2"))  # first, so its `models` beats any site-packages one

import model as B  # noqa: E402
import playoff as P  # noqa: E402
from features import build_table  # noqa: E402
from models import make  # noqa: E402

CANDIDATES = ["V3", "COH", "BETA", "ENS", "AGREE"]
MARK = ["shin", "power", "isotonic", "hier"]
MEMBERS_DIR = HERE / "members"
AGREE_GRID = (0.02, 0.04, 0.06, 0.10)
TIE = 0.005
MIN_EDGE, ENTER_FROM = 0.01, 24
BOOK_OK = (0.95, 1.25)


def logit(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


# ---------- members ----------

class Beta:
    """logit q = a*ln p - b*ln(1-p) + c + d*log(h/24): asymmetric in favourites vs longshots."""

    def fit(self, df):
        d = df[B.in_band(df["price_yes"])]
        X, y = self._x(d), d["outcome"].to_numpy(float)
        w = np.zeros(X.shape[1])
        for _ in range(50):  # Newton
            q = sigmoid(X @ w)
            w -= np.linalg.solve(X.T @ (X * (q * (1 - q))[:, None]) + 1e-6 * np.eye(len(w)), X.T @ (q - y))
        self.w = w
        return self

    def _x(self, d):
        p = np.clip(d["price_yes"].to_numpy(float), 1e-4, 1 - 1e-4)
        lh = np.log(np.clip(d["horizon_hours"].to_numpy(float), 12, 720) / 24)
        return np.column_stack([np.ones(len(p)), np.log(p), -np.log(1 - p), lh])

    def predict(self, d):
        p = d["price_yes"].to_numpy(float)
        return np.where(B.in_band(p), sigmoid(self._x(d) @ self.w), p)


def shin_probs(pi):
    """Shin (1993): solve for insider share z so the implied probabilities sum to 1."""
    s = pi.sum()

    def probs(z):
        return (np.sqrt(z * z + 4 * (1 - z) * pi * pi / s) - z) / (2 * (1 - z))

    lo, hi = 0.0, 0.99
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if probs(mid).sum() > 1 else (lo, mid)
    return probs((lo + hi) / 2)


def book_groups(d):
    """Neg-risk events with >= 2 legs priced at the same horizon and a plausible complete book."""
    g = d[d["neg_risk"].astype(str).str.lower().eq("true")].groupby(["event_slug", "horizon_hours"])["price_yes"]
    book, n = g.transform("sum"), g.transform("size")
    ok = (n >= 2) & book.between(*BOOK_OK)
    return ok.reindex(d.index, fill_value=False), book.reindex(d.index)


def shin(d):
    q = d["price_yes"].to_numpy(float).copy()
    ok, book = book_groups(d)
    sub = d[ok & (book >= 1.0)]
    pos = {ix: i for i, ix in enumerate(d.index)}
    for _, g in sub.groupby(["event_slug", "horizon_hours"]):
        q[[pos[ix] for ix in g.index]] = shin_probs(g["price_yes"].to_numpy(float))
    return q


def coherent(d, q):
    """Normalise q across the legs of a complete-looking neg-risk book so it sums to 1."""
    q = np.asarray(q, float).copy()
    ok, _ = book_groups(d)
    s = pd.Series(q, index=d.index)[ok].groupby([d.loc[ok, "event_slug"], d.loc[ok, "horizon_hours"]]).transform("sum")
    q[d.index.get_indexer(s.index)] = q[d.index.get_indexer(s.index)] / s.to_numpy()
    return np.clip(q, 1e-4, 1 - 1e-4)


class Members:
    def fit(self, fit_rows, feats):
        self.m0 = B.Calibrator(["other"]).fit(fit_rows, np.random.default_rng(0))
        self.beta = Beta().fit(fit_rows)
        f = feats[feats["market_id"].isin(set(fit_rows["market_id"]))]
        self.m1, self.m2 = make("M1", C=1.0), make("M2")
        self.m1.n_boot = self.m2.n_boot = 1  # only the point q is used; bands come from M0
        self.m1.fit(f), self.m2.fit(f)
        return self

    def predict(self, d, feats):
        p = d["price_yes"].to_numpy(float)
        q0, lo0, hi0 = self.m0.predict(p, d["horizon_hours"], d["domain"])
        cols = ["market_id", "horizon_hours", "by_date", "n_legs", "book_share", "mom24", "mom72", "vol72"]
        f = d[["market_id", "horizon_hours"]].merge(feats[cols], on=["market_id", "horizon_hours"], how="left")
        have = f["mom24"].notna().to_numpy()
        f = f.fillna({"by_date": False, "n_legs": 1, "book_share": 1.0, "mom24": 0, "mom72": 0, "vol72": 0})
        f["price_yes"], f["domain"] = p, d["domain"].to_numpy()
        q1 = np.where(have, self.m1.predict(f)[0], q0)
        q2 = np.where(have, self.m2.predict(f)[0], q0)
        qs = {"M0": q0, "M1": q1, "M2": q2, "BETA": self.beta.predict(d), "SHIN": shin(d)}
        return qs, q0 - lo0, hi0 - q0


# ---------- policy ----------

def trades_for(d, name, qs, dlo, dhi, agree=None):
    p = d["price_yes"].to_numpy(float)
    ens = ensemble_keys(qs)
    q = {"V3": qs["M0"], "COH": coherent(d, qs["M0"]), "BETA": qs["BETA"]}.get(name, qs.get(name))
    if q is None:  # ENS / AGREE
        q = np.mean([qs[k] for k in ens], axis=0)
    lo, hi = np.clip(q - dlo, 0, 1), np.clip(q + dhi, 0, 1)
    cost = B.trade_cost(d["spread"].to_numpy(float), B.fee_per_share(d), 0.01)
    action, kelly, edge = B.decide(p, q, cost, lo, hi, d["horizon_hours"].to_numpy(), MIN_EDGE, ENTER_FROM)
    if agree is not None:
        members = np.stack([qs[k] for k in ens])
        sign = np.sign(members - p)
        same = (np.abs(sign.sum(0)) == len(members)) & ((sign[0] > 0) == (action == "BUY_YES"))
        ok = same & ((members.max(0) - members.min(0)) < agree)
        action, kelly = np.where(ok, action, "NO_TRADE"), np.where(ok, kelly, 0.0)
    c = d.assign(q=q, cost=cost, action=action, kelly=kelly, edge=edge)
    t = c[(c["action"] != "NO_TRADE") & (c["edge"] > 0)].sort_values("horizon_hours", ascending=False)
    t = t.groupby("market_id").head(1).copy()
    if name == "COH":  # at most one bet per event: the largest net edge
        t = t.sort_values("edge", ascending=False).groupby(B.event_key(t)).head(1)
    t["ret"] = B.payoff(t["action"].to_numpy(), t["price_yes"].to_numpy(), t["cost"].to_numpy(), t["outcome"].to_numpy())
    return t.sort_values("resolved_at"), q


def ensemble_keys(qs):
    keys = ["M0", "M1", "M2", "BETA"] + [m for m in MARK if m in qs]
    return keys if "shin" in qs else keys + ["SHIN"]


def load_mark(d, part):
    """Mark's member q's for these rows; rows he did not price fall back to the market price."""
    out = {}
    for m in MARK:
        f = MEMBERS_DIR / f"{m}_{part}.csv"
        if f.exists():
            x = d[["market_id", "horizon_hours"]].merge(pd.read_csv(f), on=["market_id", "horizon_hours"], how="left")
            out[m] = np.where(x["q"].notna(), x["q"], d["price_yes"].to_numpy(float)).astype(float)
    return out


def score(d, name, qs, dlo, dhi, agree=None):
    t, q = trades_for(d, name, qs, dlo, dhi, agree)
    _, stake = B.exposure(t, t["kelly"].to_numpy())
    b = B.in_band(d["price_yes"])
    y = d["outcome"].to_numpy(float)[b]
    out = {"brier": round(B.brier(q[b], y), 5), "logloss": round(B.log_loss(q[b], y), 5)}
    out.update(P.stats(t, stake))
    return out


def scored_rows(rows, start):
    return rows[P.entry_time(rows) >= start]  # embargo, as in playoff.run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--test", action="store_true", help="score the test set once (01:00, after the list is frozen)")
    a = ap.parse_args()
    df = B.load_horizons(ROOT / "data" / "horizons.csv")
    feats = build_table(ROOT / "data", Path(a.raw))  # model_v2 feature table (M1/M2 train on it)
    train, test, cutoff = B.split_by_time(df, P.CUTOFF)
    order = train.groupby("market_id")["resolved_at"].first().sort_values()
    val_ids = set(order.index[int(len(order) * 0.8):])
    fit, val = train[~train["market_id"].isin(val_ids)], train[train["market_id"].isin(val_ids)]
    val = scored_rows(val, val["resolved_at"].min())

    # ---- validation ----
    mem = Members().fit(fit, feats)
    qs, dlo, dhi = mem.predict(val, feats)
    qs.update(load_mark(val, "val"))
    cands = CANDIDATES + [m for m in MARK if m in qs]
    print("candidates:", cands, "| ensemble members:", ensemble_keys(qs), flush=True)
    validation, agree_grid = {}, {}
    for c in cands:
        if c == "AGREE":
            for thr in AGREE_GRID:
                agree_grid[thr] = score(val, c, qs, dlo, dhi, thr)
                print(f"  val AGREE <{thr}: {agree_grid[thr].get('per_dollar')}  n={agree_grid[thr]['n_trades']}", flush=True)
            best_thr = max(AGREE_GRID, key=lambda t: agree_grid[t].get("per_dollar", -9))
            validation[c] = {**agree_grid[best_thr], "threshold": best_thr}
        else:
            validation[c] = score(val, c, qs, dlo, dhi)
        v = validation[c]
        print(f"val {c:5s} brier {v['brier']} logloss {v['logloss']} per$ {v.get('per_dollar')} "
              f"{v.get('per_dollar_ci')} n={v['n_trades']}", flush=True)
    winner, best = "V3", validation["V3"].get("per_dollar", -9)
    for c in cands[1:]:
        if validation[c].get("per_dollar", -9) > best + TIE:
            winner, best = c, validation[c]["per_dollar"]
    print("validation winner:", winner, flush=True)

    testing = {}
    if a.test:  # ---- test, once: winner + V3 reference ----
        mem_t = Members().fit(train, feats)
        test_rows = scored_rows(test, cutoff)
        qs_t, dlo_t, dhi_t = mem_t.predict(test_rows, feats)
        qs_t.update(load_mark(test_rows, "test"))
        testing = {c: score(test_rows, c, qs_t, dlo_t, dhi_t, validation[c].get("threshold"))
                   for c in dict.fromkeys(["V3", winner])}
    for c, v in testing.items():
        print(f"TEST {c:5s} brier {v['brier']} logloss {v['logloss']} per$ {v.get('per_dollar')} {v.get('per_dollar_ci')} "
              f"bankrolls {v.get('return')} {v.get('return_ci')} n={v['n_trades']} maxDD {v.get('max_drawdown')}", flush=True)

    res = {"protocol": __doc__.strip(), "candidates": cands, "n_candidates_compared": len(cands),
           "ensemble_members": ensemble_keys(qs), "test_opened": bool(a.test), "agree_thresholds_tried": list(AGREE_GRID),
           "n_validation_markets": len(val_ids), "n_test_markets": int(test["market_id"].nunique()),
           "winner": winner, "validation": validation, "validation_agree_grid": {str(k): v for k, v in agree_grid.items()},
           "test": testing}
    HERE.mkdir(exist_ok=True)
    (HERE / "results.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
