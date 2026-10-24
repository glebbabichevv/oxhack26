import pandas as pd

from train import split_time, split_validation


def frame():
    rows = []
    for e, ends in {"a": ["2026-01-01", "2026-02-01"], "b": ["2026-04-01", "2026-06-01"],
                    "c": ["2026-06-02"], "d": ["2026-03-01"], "f": ["2026-05-01"]}.items():
        for i, d in enumerate(ends):
            rows.append({"market_id": f"{e}{i}", "event_slug": e, "resolved_at": pd.Timestamp(d, tz="UTC")})
    return pd.DataFrame(rows)


def test_time_split_keeps_events_whole_and_drops_early_legs():
    train, test = split_time(frame(), "2026-05-18")
    assert set(train.event_slug) == {"a", "d", "f"}
    assert set(test.market_id) == {"b1", "c0"}  # b0 resolved before the cutoff: dropped


def test_validation_is_last_events_by_end_time():
    train, _ = split_time(frame(), "2026-05-18")
    fit, val = split_validation(train, frac=0.34)
    assert set(val.event_slug) == {"f"} and set(fit.event_slug) == {"a", "d"}


def test_playoff_ties_within_tie_go_to_earliest_candidate(monkeypatch):
    import numpy as np
    import train

    x = 0.40
    tag_loss = {0.11: x, 0.12: x - 0.0004, 0.13: x - 0.0003, 0.14: x - 0.0006}  # M0, M1 C=.1, M1 C=1, M2
    tags = {("M0", ()): 0.11, ("M1", (0.1,)): 0.12, ("M1", (1.0,)): 0.13, ("M2", ()): 0.14}

    class Stub:
        def __init__(self, tag):
            self.tag = tag

        def fit(self, df):
            return self

        def predict(self, df):
            n = len(df)
            return np.full(n, self.tag), np.full(n, self.tag), np.full(n, self.tag)

    monkeypatch.setattr(train, "make", lambda name, **kw: Stub(tags[(name, tuple(kw.values()))]))
    monkeypatch.setattr(train.backend, "log_loss",
                        lambda q, y: tag_loss.get(round(float(np.asarray(q)[0]), 2), x + 0.01))
    val = pd.DataFrame({"price_yes": [0.5, 0.4, 0.6], "outcome": [1, 0, 1]})
    (name, kw), scores = train.playoff(val, val)
    assert (name, kw) == ("M1", {"C": 0.1})  # M2 is best by 0.0006 but M1(C=0.1) is within 0.0005 and earlier
    assert scores["M2"] < scores["M1_C0.1"] < scores["M0"]
