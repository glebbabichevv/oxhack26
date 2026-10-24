import numpy as np
import pandas as pd

from features import book_features, by_date, path_stats


def test_by_date_matches_deadline_questions_only():
    q = pd.Series(["Will X happen by December 31?", "Ceasefire before 2027?",
                   "Will the Lakers win on Oct 25?", "Fed cut by end of year?", "Who wins the election?"])
    assert by_date(q).tolist() == [True, True, False, True, False]


def test_book_features_per_event_and_horizon():
    df = pd.DataFrame({"event_slug": ["e", "e", "e", "s"], "horizon_hours": [24, 24, 72, 24],
                       "price_yes": [0.6, 0.5, 0.3, 0.4]})
    out = book_features(df)
    assert out.n_legs.tolist() == [2, 2, 1, 1]
    assert np.allclose(out.book_share, [0.6 / 1.1, 0.5 / 1.1, 1.0, 1.0])


def test_path_stats_never_looks_past_the_horizon():
    t = np.arange(0, 200) * 3600.0
    p = np.where(t <= 100 * 3600, 0.5, 0.9)  # jump AFTER `at`
    mom24, mom72, vol72 = path_stats(t, p, at=100 * 3600.0)
    assert mom24 == 0 and mom72 == 0 and vol72 == 0


def test_path_stats_momentum_and_volatility():
    t = np.arange(0, 100) * 3600.0
    p = 0.2 + 0.001 * np.arange(100)
    mom24, mom72, vol72 = path_stats(t, p, at=99 * 3600.0)
    assert np.isclose(mom24, 0.024) and np.isclose(mom72, 0.072) and np.isclose(vol72, 0.0, atol=1e-12)


def test_path_stats_empty_history_is_zero():
    assert path_stats(np.array([]), np.array([]), at=10.0) == (0.0, 0.0, 0.0)
