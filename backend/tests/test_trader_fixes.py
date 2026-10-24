import os
import subprocess
import sys

import invest.trader as t
from invest.store import Store
from invest.trader import acquire_lock, run_cycle
from test_trader import FRESH, NOW, BuyRaisesBroker, FakeBroker, item


class LogFailsOnBuyStore(Store):
    def log(self, plan_id, kind, now, **fields):
        if kind == "buy":
            raise OSError("disk full")
        return super().log(plan_id, kind, now, **fields)


def test_fill_is_persisted_even_if_logging_the_buy_fails(tmp_path):
    s = LogFailsOnBuyStore(tmp_path)
    p = s.new_plan(1000, 25, 100, FRESH)
    b = FakeBroker()
    run_cycle(s, b, {"updated_at": FRESH, "markets": [item("m1"), item("m2")]}, NOW, total_cap=500)
    plan = s.plan(p["id"])
    assert len(b.bought) == 1 and len(plan["positions"]) == 1  # nothing lost, nothing double counted
    assert plan["cash"] == 1000 - b.bought[0][2]
    assert plan["status"] == "paused" and plan["pause_reason"] == "check_fill"
    errs = [e for e in s.events(p["id"]) if e["kind"] == "error"]
    assert errs and errs[0]["possible_fill"] is True


def test_normal_fill_is_not_double_counted_by_the_merge(tmp_path):
    s = Store(tmp_path)
    p = s.new_plan(1000, 25, 100, FRESH)
    run_cycle(s, FakeBroker(), {"updated_at": FRESH, "markets": [item("m1")]}, NOW, total_cap=500)
    plan = s.plan(p["id"])
    assert len(plan["positions"]) == 1 and plan["cash"] == 1000 - plan["positions"][0]["cost"]


class PausePressBroker(BuyRaisesBroker):
    """The person presses Pause in the store while the failing buy is in flight."""

    def __init__(self, store, plan_id, **kw):
        super().__init__(**kw)
        self.store, self.plan_id = store, plan_id

    def buy(self, m, side, usd, worst_price, note):
        self.store.update_plan(self.plan_id, lambda p: p.update(status="paused", pause_reason="by_person"))
        return super().buy(m, side, usd, worst_price, note)


def test_check_fill_survives_a_pause_press_mid_cycle(tmp_path):
    s = Store(tmp_path)
    p = s.new_plan(1000, 25, 100, FRESH)
    run_cycle(s, PausePressBroker(s, p["id"]), {"updated_at": FRESH, "markets": [item("m1")]}, NOW, total_cap=500)
    plan = s.plan(p["id"])
    assert plan["status"] == "paused" and plan["pause_reason"] == "check_fill"


def test_stopped_stays_stopped_even_with_check_fill(tmp_path):
    s = Store(tmp_path)
    p = s.new_plan(1000, 25, 100, FRESH)

    class StopThenFail(BuyRaisesBroker):
        def buy(self, m, side, usd, worst_price, note):
            s.update_plan(p["id"], lambda x: x.update(status="stopped"))
            return super().buy(m, side, usd, worst_price, note)

    run_cycle(s, StopThenFail(), {"updated_at": FRESH, "markets": [item("m1")]}, NOW, total_cap=500)
    assert s.plan(p["id"])["status"] == "stopped"


def test_lock_with_dead_pid_and_fresh_timestamp_is_taken_over(tmp_path):
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert t._pid_alive(proc.pid) is False and t._pid_alive(os.getpid()) is True
    lock = tmp_path / "trader.lock"
    lock.write_text(f"{proc.pid} 1000.0")
    assert acquire_lock(lock, 1001.0) is True
    assert lock.read_text().split()[0] == str(os.getpid())


def test_lock_with_live_foreign_pid_is_respected(tmp_path, monkeypatch):
    lock = tmp_path / "trader.lock"
    lock.write_text(f"{os.getpid() + 1} 1000.0")
    monkeypatch.setattr(t, "_pid_alive", lambda pid: True)
    assert acquire_lock(lock, 1001.0) is False


def test_takeover_returns_false_if_another_process_won_the_race(tmp_path, monkeypatch):
    lock = tmp_path / "trader.lock"
    lock.write_text(f"{os.getpid() + 1} 1.0")  # stale
    real_replace = os.replace

    def racing_replace(src, dst):
        real_replace(src, dst)
        lock.write_text(f"{os.getpid() + 7} 2.0")  # someone else replaced right after us

    monkeypatch.setattr(t.os, "replace", racing_replace)
    assert acquire_lock(lock, 99999.0) is False
