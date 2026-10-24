"""Model v2 playoff entrants. All share fit(df) -> self and predict(df) -> (q, lo, hi).

The band is the 10th-90th percentile of q over refits on events resampled with replacement.
Outside the tradable band the model is neither trained nor used: q = lo = hi = price.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

TRADABLE = (0.03, 0.97)
DOMAINS = ["sports", "crypto", "politics", "economics", "culture", "science_tech", "geopolitics"]


def logit(p):
    p = np.clip(np.asarray(p, float), 0.01, 0.99)
    return np.log(p / (1 - p))


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def in_band(p):
    p = np.asarray(p, float)
    return (p >= TRADABLE[0]) & (p <= TRADABLE[1])


def anchor(q_raw, p, max_shift=0.7):
    return sigmoid(logit(p) + np.clip(logit(q_raw) - logit(p), -max_shift, max_shift))


def base_cols(df):
    lp = logit(df["price_yes"])
    lh = np.log(np.clip(df["horizon_hours"].to_numpy(float), 12, 720) / 24)
    return lp, lh


def full_matrix(df):
    lp, lh = base_cols(df)
    cols = [lp, lh, lp * lh, df["by_date"].to_numpy(float), lp * df["by_date"].to_numpy(float),
            np.log(df["n_legs"].to_numpy(float)), df["book_share"].to_numpy(float),
            df["mom24"].to_numpy(float), df["mom72"].to_numpy(float), df["vol72"].to_numpy(float),
            lp * df["vol72"].to_numpy(float)]
    cols += [(df["domain"] == d).to_numpy(float) for d in DOMAINS]
    return np.column_stack(cols)


class _Base:
    n_boot = 40

    def _x(self, df):
        raise NotImplementedError

    def _new(self):
        raise NotImplementedError

    def _q(self, est, df):
        return est.predict_proba(self._x(df))[:, 1]

    def fit(self, df, seed=0):
        df = df[in_band(df["price_yes"])].reset_index(drop=True)
        y = df["outcome"].to_numpy()
        self.main = self._new().fit(self._x(df), y)
        rng = np.random.default_rng(seed)
        groups = df.groupby("event_slug").indices
        ids = np.array(list(groups))
        self.boot = []
        for _ in range(self.n_boot):
            pick = np.concatenate([groups[i] for i in rng.choice(ids, len(ids))])
            self.boot.append(self._new().fit(self._x(df.iloc[pick]), y[pick]))
        return self

    def predict(self, df):
        p = df["price_yes"].to_numpy(float)
        q = self._q(self.main, df)
        qs = np.stack([self._q(m, df) for m in self.boot])
        lo, hi = np.percentile(qs, 10, axis=0), np.percentile(qs, 90, axis=0)
        lo, hi = np.minimum(lo, q), np.maximum(hi, q)
        b = in_band(p)
        return np.where(b, q, p), np.where(b, lo, p), np.where(b, hi, p)


class M0(_Base):
    """Current backend 'simple' calibration: logit(price), log horizon, interaction."""
    name = "M0"

    def _x(self, df):
        lp, lh = base_cols(df)
        return np.column_stack([lp, lh, lp * lh])

    def _new(self):
        return LogisticRegression(C=1.0, max_iter=2000)


class M1(_Base):
    """Logistic on all features, standardised."""
    name = "M1"

    def __init__(self, C=1.0):
        self.C = C

    def _x(self, df):
        return full_matrix(df)

    def _new(self):
        from sklearn.pipeline import make_pipeline
        return make_pipeline(StandardScaler(), LogisticRegression(C=self.C, max_iter=3000))


class M2(_Base):
    """Gradient boosting on all features, anchored to the market (log-odds shift <= 0.7)."""
    name = "M2"
    n_boot = 20

    def _x(self, df):
        return full_matrix(df)

    def _new(self):
        return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300,
                                              min_samples_leaf=200, early_stopping=True,
                                              validation_fraction=0.15, random_state=0)

    def _q(self, est, df):
        return anchor(est.predict_proba(self._x(df))[:, 1], df["price_yes"].to_numpy(float))


def make(name, **kw):
    return {"M0": M0, "M1": M1, "M2": M2}[name](**kw)
