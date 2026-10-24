# backend/tests/test_trader.py
from datetime import datetime, timezone

from invest.store import Store
from invest.trader import acquire_lock, run_cycle

NOW = datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc)
FRESH = "2026-10-24T17:55:00+00:00"


def item(market_id="m1", **kw):
    base = dict(market_id=market_id, question=f"Will {market_id} happen?", action="BUY_YES", net_edge=0.03,
                kelly_fraction=0.02, q_yes=0.50, q_low=0.48, q_high=0.52, fee=0.0,
                url=f"https://polymarket.com/event/ev-{market_id}", hours_to_resolution=48)
    return {**base, **kw}


class FakeBroker:
    ceiling = 25.0

    def __init__(self, ask=0.40, outcome=None, fail=False, min_size=None):
        self.ask, self.outcome, self.fail, self.min_size, self.bought = ask, outcome, fail, min_size, []

    def market(self, market_id):
        if self.fail:
            raise RuntimeError("gamma down")
        return {"market_id": market_id}

    def quote(self, m, side, usd):
        return {"shares": usd / self.ask, "avg_price": self.ask, "worst_price": self.ask,
                "fillable_usd": usd, "min_order_size": self.min_size}

    def buy(self, m, side, usd, worst_price, note):
        self.bought.append((m["market_id"], side, usd))
        return {"shares": usd / self.ask, "cost": usd, "avg_price": self.ask}

    def mark(self, m, side):
        return self.ask, self.outcome


def test_buys_best_edge_first_and_spends_cash(tmp_path):
    s = Store(tmp_path)
    p = s.new_plan(1000, 25, 100, FRESH)
    b = FakeBroker()
    live = {"updated_at": FRESH, "markets": [item("m1", net_edge=0.01), item("m2", net_edge=0.05),
                                             item("m3", action="NO_TRADE", net_edge=0.0)]}
    run_cycle(s, b, live, NOW, total_cap=500)
    assert [x[0] for x in b.bought] == ["m2", "m1"]
    plan = s.plan(p["id"])
    assert plan["cash"] == 960.0 and len(plan["positions"]) == 2
    assert [e["kind"] for e in s.events(p["id"])] == ["buy", "buy"]
    assert s.equity()[-1]["invested"] == 1000


def test_skips_when_edge_vanished_at_fill_price(tmp_path):
    s = Store(tmp_path)
    p = s.new_plan(1000, 25, 100, FRESH)
    run_cycle(s, FakeBroker(ask=0.49), {"updated_at": FRESH, "markets": [item()]}, NOW, total_cap=500)
    ev = s.events(p["id"])[0]
    assert ev["kind"] == "skip" and ev["reason"] == "edge_vanished"
    assert s.plan(p["id"])["cash"] == 1000


def test_skips_below_polymarket_minimum(tmp_path):
    s = Store(tmp_path)
    p = s.new_plan(1000, 25, 100, FRESH)
    run_cycle(s, FakeBroker(min_size="500"), {"updated_at": FRESH, "markets": [item()]}, NOW, total_cap=500)
    assert s.events(p["id"])[0]["reason"] == "below_minimum"


def test_total_exposure_cap_across_plans(tmp_path):
    s = Store(tmp_path)
    s.new_plan(1000, 25, 100, FRESH)
    b = FakeBroker()
    run_cycle(s, b, {"updated_at": FRESH, "markets": [item("m1"), item("m2")]}, NOW, total_cap=25)
    assert sum(x[2] for x in b.bought) == 25


def test_settles_won_bets_back_into_cash(tmp_path):
    s = Store(tmp_path)
    p = s.new_plan(1000, 25, 100, FRESH)
    run_cycle(s, FakeBroker(), {"updated_at": FRESH, "markets": [item()]}, NOW, total_cap=500)
    run_cycle(s, FakeBroker(outcome=1), {"updated_at": FRESH, "markets": []}, NOW, total_cap=500)
    plan = s.plan(p["id"])
    assert plan["positions"][0]["status"] == "won" and plan["cash"] == 1030.0
    settle = s.events(p["id"])[0]
    assert settle["kind"] == "settle" and settle["pnl"] == 30.0


def test_pauses_on_stale_data_and_does_not_buy(tmp_path):
    s = Store(tmp_path)
    p = s.new_plan(1000, 25, 100, FRESH)
    b = FakeBroker()
    run_cycle(s, b, {"updated_at": "2026-10-24T10:00:00+00:00", "markets": [item()]}, NOW, total_cap=500)
    assert b.bought == [] and s.plan(p["id"])["status"] == "paused"
    assert s.plan(p["id"])["pause_reason"] == "stale_data"


def test_three_errors_pause_the_plan(tmp_path):
    s = Store(tmp_path)
    p = s.new_plan(1000, 25, 100, FRESH)
    live = {"updated_at": FRESH, "markets": [item("m1"), item("m2"), item("m3")]}
    run_cycle(s, FakeBroker(fail=True), live, NOW, total_cap=500)
    run_cycle(s, FakeBroker(fail=True), live, NOW, total_cap=500)
    assert s.plan(p["id"])["status"] == "paused" and s.plan(p["id"])["pause_reason"] == "polymarket_errors"


def test_stopped_plan_settles_but_never_buys(tmp_path):
    s = Store(tmp_path)
    p = s.new_plan(1000, 25, 100, FRESH)
    p["status"] = "stopped"
    s.save_plan(p)
    b = FakeBroker()
    run_cycle(s, b, {"updated_at": FRESH, "markets": [item()]}, NOW, total_cap=500)
    assert b.bought == []


def test_lock_file(tmp_path):
    lock = tmp_path / "trader.lock"
    assert acquire_lock(lock, 1000.0) is True
    assert acquire_lock(lock, 1100.0, stale_s=1800) is False
    assert acquire_lock(lock, 5000.0, stale_s=1800) is True
