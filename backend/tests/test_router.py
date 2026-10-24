import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INVEST_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DASHBOARD_PIN", "4321")
    monkeypatch.setenv("TRADER_ENABLED", "1")
    import invest_router
    importlib.reload(invest_router)
    app = FastAPI()
    app.include_router(invest_router.router)
    return TestClient(app)


PIN = {"X-Dashboard-Pin": "4321"}
BODY = {"budget": 1000, "max_bet": 10, "daily_loss_stop": 100}


def test_reads_need_no_pin(client):
    r = client.get("/api/plans")
    assert r.status_code == 200 and r.json()["plans"] == [] and r.json()["interval_min"] == 10


def test_create_needs_right_pin(client):
    assert client.post("/api/plans", json=BODY).status_code == 401
    assert client.post("/api/plans", json=BODY, headers={"X-Dashboard-Pin": "0000"}).status_code == 401
    r = client.post("/api/plans", json=BODY, headers=PIN)
    assert r.status_code == 200 and r.json()["status"] == "running" and r.json()["profit"] == 0


def test_three_wrong_pins_lock_writes(client):
    for _ in range(3):
        client.post("/api/plans", json=BODY, headers={"X-Dashboard-Pin": "0000"})
    assert client.post("/api/plans", json=BODY, headers=PIN).status_code == 429


def test_max_bet_above_server_ceiling_is_refused(client):
    r = client.post("/api/plans", json={**BODY, "max_bet": 10_000}, headers=PIN)
    assert r.status_code == 400


def test_pause_resume_stop(client):
    pid = client.post("/api/plans", json=BODY, headers=PIN).json()["id"]
    assert client.post(f"/api/plans/{pid}/pause", headers=PIN).json()["status"] == "paused"
    assert client.post(f"/api/plans/{pid}/resume", headers=PIN).json()["status"] == "running"
    assert client.post(f"/api/plans/{pid}/stop", headers=PIN).json()["status"] == "stopped"
    assert client.post(f"/api/plans/{pid}/resume", headers=PIN).status_code == 400
    assert client.post("/api/plans/nope/pause", headers=PIN).status_code == 404


def test_orders_and_pnl(client):
    client.post("/api/plans", json=BODY, headers=PIN)
    assert client.get("/api/orders").json()[0]["kind"] == "start"
    pnl = client.get("/api/pnl").json()
    assert pnl["real"] == [] and pnl["backtest_budget"] == 1000
    assert len(pnl["backtest"]) > 0 and isinstance(pnl["backtest"][0]["value"], float)


def test_resume_on_running_plan_is_refused(client):
    pid = client.post("/api/plans", json=BODY, headers=PIN).json()["id"]
    r = client.post(f"/api/plans/{pid}/resume", headers=PIN)
    assert r.status_code == 400 and r.json()["detail"] == "Only a paused plan can be resumed"


def test_pause_on_paused_plan_keeps_auto_pause_reason(client):
    import invest_router
    pid = client.post("/api/plans", json=BODY, headers=PIN).json()["id"]
    invest_router.store.update_plan(pid, lambda p: p.update(status="paused", pause_reason="check_fill"))
    r = client.post(f"/api/plans/{pid}/pause", headers=PIN)
    assert r.status_code == 400 and r.json()["detail"] == "This plan is not running"
    assert invest_router.store.plan(pid)["pause_reason"] == "check_fill"


def test_resume_logs_previous_reason(client):
    pid = client.post("/api/plans", json=BODY, headers=PIN).json()["id"]
    client.post(f"/api/plans/{pid}/pause", headers=PIN)
    client.post(f"/api/plans/{pid}/resume", headers=PIN)
    resume = client.get(f"/api/orders?plan={pid}").json()[0]
    assert resume["kind"] == "resume" and resume["prev_reason"] == "by_person"


def test_infinity_is_rejected_as_invalid_input(client):
    r = client.post("/api/plans", content='{"budget": Infinity, "max_bet": 10, "daily_loss_stop": 100}',
                    headers={**PIN, "Content-Type": "application/json"})
    assert r.status_code == 422


def test_max_bet_above_budget_is_refused(client):
    r = client.post("/api/plans", json={"budget": 5, "max_bet": 10, "daily_loss_stop": 1}, headers=PIN)
    assert r.status_code == 400 and r.json()["detail"] == "Max per bet can't be more than the budget"


def test_daily_loss_stop_above_budget_is_refused(client):
    r = client.post("/api/plans", json={"budget": 5, "max_bet": 1, "daily_loss_stop": 6}, headers=PIN)
    assert r.status_code == 400 and r.json()["detail"] == "The daily loss stop can't be more than the budget"


def test_writes_refused_when_not_the_trader_host(client, monkeypatch):
    monkeypatch.delenv("TRADER_ENABLED")
    r = client.post("/api/plans", json=BODY, headers=PIN)
    assert r.status_code == 503 and r.json()["detail"] == "This server does not run the trader; use the trading host"


def test_pin_unset_is_503(client, monkeypatch):
    monkeypatch.delenv("DASHBOARD_PIN")
    assert client.post("/api/plans", json=BODY, headers=PIN).status_code == 503
