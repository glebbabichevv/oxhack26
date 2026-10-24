import numpy as np
import pandas as pd

from decision import apply_caps, decide, payoff, trade_cost


def test_cost_adds_polymarket_taker_fee_only_when_enabled():
    c = trade_cost(np.array([0.5, 0.5, 0.2]), np.array([np.nan, 0.04, np.nan]),
                   np.array([True, False, True]), np.array(["sports", "sports", "geopolitics"]))
    assert np.allclose(c, [0.01 + 0.05 * 0.25, 0.02, 0.01])


def test_decide_requires_conservative_edge_and_scales_kelly():
    p = np.array([0.30, 0.30, 0.70])
    q = np.array([0.40, 0.33, 0.55]); lo = np.array([0.38, 0.31, 0.53]); hi = np.array([0.42, 0.35, 0.57])
    action, kelly, edge = decide(p, q, lo, hi, np.full(3, 0.01), min_edge=0.02, kelly_mult=0.25)
    assert action.tolist() == ["BUY_YES", "NO_TRADE", "BUY_NO"]
    assert np.isclose(edge[0], 0.38 - 0.31)
    assert np.isclose(kelly[0], min(0.05, 0.25 * (0.38 - 0.31) / (1 - 0.31)))


def test_payoff_held_to_resolution():
    r = payoff(np.array(["BUY_YES", "BUY_NO", "NO_TRADE"]), np.array([0.4, 0.4, 0.4]), np.full(3, 0.01),
               np.array([1, 1, 1]))
    assert np.allclose(r, [1 / 0.41 - 1, -1, 0])


def trades(rows):
    t = pd.DataFrame(rows, columns=["market_id", "event_slug", "kelly", "entry_at", "resolved_at"])
    t["entry_at"] = pd.to_datetime(t.entry_at, utc=True)
    t["resolved_at"] = pd.to_datetime(t.resolved_at, utc=True)
    return t


def test_event_cap_limits_stake_per_event():
    t = apply_caps(trades([("a", "e", 0.05, "2026-06-01", "2026-06-05"),
                           ("b", "e", 0.05, "2026-06-01", "2026-06-05"),
                           ("c", "e", 0.05, "2026-06-01", "2026-06-05")]))
    assert np.isclose(t.stake.sum(), 0.10)


def test_bankroll_cap_and_release_on_resolution():
    rows = [(f"m{i}", f"e{i}", 0.05, "2026-06-01", "2026-06-10") for i in range(30)]  # 1.5 wanted
    rows.append(("late", "eL", 0.05, "2026-06-11", "2026-06-12"))  # after all released
    t = apply_caps(trades(rows)).set_index("market_id")
    assert np.isclose(t.stake.drop("late").sum(), 1.0)
    assert np.isclose(t.loc["late", "stake"], 0.05)
    assert np.allclose(t.kelly, t.stake)
