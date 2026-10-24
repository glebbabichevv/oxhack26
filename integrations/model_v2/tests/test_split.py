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
