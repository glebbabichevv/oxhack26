import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INVEST_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DASHBOARD_PIN", "4321")
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
