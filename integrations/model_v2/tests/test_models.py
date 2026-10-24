import numpy as np
import pandas as pd

from models import M0, M1, M2, anchor, in_band


def toy(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.05, 0.95, n)
    true = 1 / (1 + np.exp(-0.85 * np.log(p / (1 - p))))  # overconfident market
    return pd.DataFrame({
        "price_yes": p, "horizon_hours": rng.choice([12, 24, 72, 168, 720], n),
        "domain": rng.choice(["sports", "politics", "crypto"], n), "by_date": rng.random(n) < 0.2,
        "n_legs": rng.integers(1, 4, n), "book_share": rng.uniform(0.2, 1, n),
        "mom24": rng.normal(0, 0.02, n), "mom72": rng.normal(0, 0.03, n), "vol72": rng.uniform(0, 0.03, n),
        "outcome": (rng.random(n) < true).astype(int), "event_slug": [f"e{i // 2}" for i in range(n)]})


def test_anchor_limits_logodds_shift():
    p = np.array([0.5, 0.5, 0.2])
    q = anchor(np.array([0.99, 0.01, 0.2]), p, max_shift=0.7)
    lo, hi = 1 / (1 + np.exp(0.7)), 1 / (1 + np.exp(-0.7))
    assert np.allclose(q, [hi, lo, 0.2])


def test_out_of_band_returns_price():
    df = toy()
    df.loc[:4, "price_yes"] = [0.01, 0.02, 0.98, 0.99, 0.5]
    for m in (M0(), M1()):
        q, lo, hi = m.fit(df).predict(df.head(5))
        assert np.allclose(q[:4], df.price_yes[:4]) and np.allclose(lo[:4], df.price_yes[:4])


def test_models_learn_overconfidence_and_bands_bracket_q():
    df = toy(6000)
    for m in (M0(), M1(), M2()):
        q, lo, hi = m.fit(df).predict(df)
        b = in_band(df.price_yes)
        assert np.all(lo[b] <= q[b] + 1e-9) and np.all(q[b] <= hi[b] + 1e-9)
        long = b & (df.price_yes < 0.2)
        assert q[long].mean() > df.price_yes[long].mean()  # longshots corrected upward
