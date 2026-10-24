import numpy as np
import pandas as pd

from decision import apply_caps, decide, earliest_trades, payoff, trade_cost


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
    assert np.isclose(kelly[2], min(0.05, 0.25 * ((1 - 0.57) - (1 - 0.70 + 0.01)) / (1 - (1 - 0.70 + 0.01))))


def test_payoff_held_to_resolution():
    r = payoff(np.array(["BUY_YES", "BUY_NO", "NO_TRADE"]), np.array([0.4, 0.4, 0.4]), np.full(3, 0.01),
               np.array([1, 1, 1]))
    assert np.allclose(r, [1 / 0.41 - 1, -1, 0])
    r_no_win = payoff(np.array(["BUY_NO"]), np.array([0.4]), np.array([0.01]), np.array([0]))
    assert np.isclose(r_no_win[0], 1 / (1 - 0.4 + 0.01) - 1)


def test_earliest_trades_picks_longest_qualifying_horizon_and_drops_no_trade():
    end = pd.Timestamp("2026-07-01", tz="UTC")
    df = pd.DataFrame({
        "market_id": ["A", "A", "B", "B", "B", "C"],
        "event_slug": ["ea", "ea", "eb", "eb", "eb", "ec"],
        "horizon_hours": [720, 168, 24, 720, 168, 720],
        "price_yes": [0.30] * 6,
        "outcome": [1, 1, 0, 0, 0, 1],
        "end_date": [end] * 6,
        "resolved_at": [end] * 6,
    })
    # A and B qualify (buy-yes edge 0.09 > 0.02) only where lo=0.40; everything else is NO_TRADE.
    lo = np.array([0.40, 0.40, 0.40, 0.30, 0.30, 0.30])
    hi = np.array([0.42, 0.42, 0.42, 0.35, 0.35, 0.35])
    q = (lo + hi) / 2
    cost = np.full(6, 0.01)
    t = earliest_trades(df, q, lo, hi, cost, min_edge=0.02, kelly_mult=0.25).set_index("market_id")
    assert sorted(t.index) == ["A", "B"]
    assert t.loc["A", "horizon_hours"] == 720
    assert t.loc["B", "horizon_hours"] == 24
    assert t.loc["A", "entry_at"] == end - pd.Timedelta(hours=720)
    assert t.loc["B", "entry_at"] == end - pd.Timedelta(hours=24)
    expected = payoff(np.array(["BUY_YES", "BUY_YES"]), np.array([0.30, 0.30]), np.full(2, 0.01),
                      np.array([1, 0]))
    assert np.allclose(t.loc[["A", "B"], "ret"].to_numpy(), expected)


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
    out = apply_caps(trades(rows))
    assert (out.stake > 0).all()  # zero-stake trades are not returned
    t = out.set_index("market_id")
    assert len(t) == 21  # 20 first-wave trades that fit the bankroll, plus the late one
    assert np.isclose(t.stake.drop("late").sum(), 1.0)
    assert np.isclose(t.loc["late", "stake"], 0.05)
    assert np.allclose(t.kelly, t.stake)


def test_entry_at_resolution_time_gets_full_stake_when_bankroll_full():
    rows = [(f"m{i}", f"e{i}", 0.05, "2026-06-01", "2026-06-05") for i in range(20)]  # fills bankroll
    rows.append(("x", "eX", 0.05, "2026-06-05", "2026-06-06"))  # enters exactly when the others resolve
    t = apply_caps(trades(rows)).set_index("market_id")
    assert np.isclose(t.loc["x", "stake"], 0.05)


def test_event_cap_frees_up_after_release():
    rows = [("a", "e", 0.05, "2026-06-01", "2026-06-05"),
            ("b", "e", 0.05, "2026-06-01", "2026-06-05"),
            ("c", "e", 0.05, "2026-06-06", "2026-06-07")]  # entering after a and b resolved
    t = apply_caps(trades(rows)).set_index("market_id")
    assert np.isclose(t.loc["c", "stake"], 0.05)
    assert (t.stake > 0).all()
