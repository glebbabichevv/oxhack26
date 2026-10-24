# backend/tests/test_store.py
from invest.store import Store

NOW = "2026-10-24T18:00:00+00:00"


def test_new_plan_is_saved_and_starts_running(tmp_path):
    s = Store(tmp_path)
    p = s.new_plan(1000, 25, 100, NOW)
    assert p["status"] == "running" and p["cash"] == 1000 and p["positions"] == []
    assert s.plan(p["id"])["budget"] == 1000
    assert (tmp_path / "plans.json").exists()


def test_save_plan_replaces_by_id(tmp_path):
    s = Store(tmp_path)
    p = s.new_plan(1000, 25, 100, NOW)
    p["cash"] = 900
    s.save_plan(p)
    assert len(s.plans()) == 1 and s.plan(p["id"])["cash"] == 900


def test_events_newest_first_and_filtered(tmp_path):
    s = Store(tmp_path)
    s.log("a", "buy", NOW, question="Q1")
    s.log("b", "buy", "2026-10-24T18:05:00+00:00", question="Q2")
    s.log("a", "skip", "2026-10-24T18:10:00+00:00", reason="edge_vanished")
    assert [e["kind"] for e in s.events("a")] == ["skip", "buy"]
    assert len(s.events(limit=1)) == 1


def test_equity_appends(tmp_path):
    s = Store(tmp_path)
    s.add_equity(NOW, 1000, 1010)
    assert s.equity() == [{"t": NOW, "invested": 1000, "value": 1010}]


def test_env_var_sets_default_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("INVEST_DATA_DIR", str(tmp_path))
    s = Store()
    s.new_plan(500, 10, 50, NOW)
    assert (tmp_path / "plans.json").exists()


def test_reads_on_empty_folder_return_empty(tmp_path):
    s = Store(tmp_path)
    assert s.plans() == [] and s.events() == [] and s.equity() == []


def test_plan_read_back_by_fresh_store(tmp_path):
    p = Store(tmp_path).new_plan(1000, 25, 100, NOW)
    assert Store(tmp_path).plan(p["id"])["budget"] == 1000


def test_no_tmp_file_left_after_writes(tmp_path):
    s = Store(tmp_path)
    s.new_plan(1000, 25, 100, NOW)
    s.log("a", "buy", NOW)
    s.add_equity(NOW, 1000, 1010)
    assert list(tmp_path.glob("*.tmp")) == []


def test_update_plan_mutates_and_persists(tmp_path):
    s = Store(tmp_path)
    p = s.new_plan(1000, 25, 100, NOW)
    updated = s.update_plan(p["id"], lambda plan: plan.update(cash=750))
    assert updated["cash"] == 750 and Store(tmp_path).plan(p["id"])["cash"] == 750


def test_update_plan_unknown_id_returns_none(tmp_path):
    s = Store(tmp_path)
    s.new_plan(1000, 25, 100, NOW)
    assert s.update_plan("nope", lambda plan: plan.update(cash=0)) is None
