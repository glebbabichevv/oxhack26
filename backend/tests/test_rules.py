# backend/tests/test_rules.py
from datetime import datetime, timezone

from invest.rules import event_of, p_win, pause_reason, plan_value, size_bet

NOW = datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc)


def plan(**kw):
    base = dict(id="p1", budget=1000.0, max_bet=25.0, daily_loss_stop=100.0, status="running", cash=1000.0,
                positions=[], errors=0, day={"date": "2026-10-24", "start_value": 1000.0})
    return {**base, **kw}


def item(**kw):
    base = dict(market_id="m1", question="Will A win?", action="BUY_YES", net_edge=0.03, kelly_fraction=0.02,
                q_yes=0.47, q_low=0.45, q_high=0.49, fee=0.0, url="https://polymarket.com/event/ev-1",
                hours_to_resolution=48)
    return {**base, **kw}


def pos(**kw):
    base = dict(market_id="m9", event="ev-9", side="YES", shares=50.0, cost=20.0, status="open", mark=0.5)
    return {**base, **kw}


def test_event_of_takes_last_url_segment():
    assert event_of("https://polymarket.com/event/ev-1/") == "ev-1"


def test_p_win_is_conservative():
    assert p_win(item(), "YES") == 0.45
    assert round(p_win(item(), "NO"), 2) == 0.51


def test_plan_value_marks_open_positions():
    p = plan(cash=900.0, positions=[pos(), pos(status="won", mark=1.0)])
    assert plan_value(p) == 925.0


def test_stake_is_kelly_times_value_clipped_to_max_bet():
    assert size_bet(item(kelly_fraction=0.01), plan(), 1000.0, 25.0) == (10.0, None)
    assert size_bet(item(kelly_fraction=0.10), plan(), 1000.0, 25.0) == (25.0, None)


def test_stake_respects_global_ceiling():
    assert size_bet(item(kelly_fraction=0.10), plan(), 1000.0, 7.0) == (7.0, None)


def test_market_cap_five_percent_of_budget():
    p = plan(positions=[pos(market_id="m1", event="ev-1", cost=45.0)])
    assert size_bet(item(kelly_fraction=0.10), p, 1000.0, 25.0) == (5.0, None)


def test_event_cap_ten_percent_of_budget():
    p = plan(positions=[pos(market_id="m2", event="ev-1", cost=50.0), pos(market_id="m3", event="ev-1", cost=50.0)])
    assert size_bet(item(), p, 1000.0, 25.0) == (0.0, "limit_reached")


def test_never_both_sides_of_one_market():
    p = plan(positions=[pos(market_id="m1", side="NO", event="ev-1")])
    assert size_bet(item(), p, 1000.0, 25.0) == (0.0, "opposite_side_held")


def test_cash_limits_stake_and_tiny_stakes_skip():
    assert size_bet(item(kelly_fraction=0.10), plan(cash=12.0), 1000.0, 25.0) == (12.0, None)
    assert size_bet(item(kelly_fraction=0.0005), plan(), 1000.0, 25.0) == (0.0, "too_small")


def test_pause_reasons():
    assert pause_reason(plan(), 1000.0, "2026-10-24T17:00:00+00:00", NOW) is None
    assert pause_reason(plan(errors=3), 1000.0, "2026-10-24T17:00:00+00:00", NOW) == "polymarket_errors"
    assert pause_reason(plan(), 1000.0, "2026-10-24T15:00:00+00:00", NOW) == "stale_data"
    assert pause_reason(plan(), 1000.0, None, NOW) == "stale_data"
    assert pause_reason(plan(), 899.0, "2026-10-24T17:00:00+00:00", NOW) == "daily_loss"

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integrations"))
from polymarket_trading import exit_mark, resolution  # noqa: E402


def test_resolution_reads_settled_outcome_prices():
    open_m = dict(closed=False, outcomes={"Yes": 0.6, "No": 0.4})
    won_yes = dict(closed=True, outcomes={"Yes": 1.0, "No": 0.0})
    pending = dict(closed=True, outcomes={"Yes": 0.5, "No": 0.5})
    assert resolution(open_m, "YES") is None
    assert resolution(won_yes, "YES") == 1 and resolution(won_yes, "NO") == 0
    assert resolution(pending, "YES") is None


def test_exit_mark_is_what_selling_fetches():
    m = dict(best_bid="0.40", best_ask="0.43")
    assert exit_mark(m, "YES") == 0.40
    assert round(exit_mark(m, "NO"), 2) == 0.57
    assert exit_mark(dict(best_bid=None, best_ask=None), "YES") is None
