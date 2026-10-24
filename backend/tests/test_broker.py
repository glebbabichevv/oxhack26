import pytest

from invest import broker as broker_mod
from invest.broker import Broker


def buy(monkeypatch, reply):
    monkeypatch.setattr(broker_mod.trading, "place_bet", lambda *a, **k: reply)
    return Broker.buy(None, {"market_id": "m"}, "YES", 5.0, 0.5, note="t")  # no instance: never builds the real Broker


def test_paper_fill_has_no_order_id(monkeypatch):
    r = buy(monkeypatch, {"status": "paper_filled", "shares": 10.0, "cost_usd": 5.0})
    assert r == {"shares": 10.0, "cost": 5.0, "avg_price": 0.5, "order_id": None, "status": None}


def test_live_matched_fill(monkeypatch):
    reply = {"status": "sent", "order": {"success": True, "orderID": "0x1", "status": "matched",
                                         "makingAmount": "5", "takingAmount": "10"}}
    r = buy(monkeypatch, reply)
    assert r["shares"] == 10 and r["cost"] == 5 and r["order_id"] == "0x1" and r["status"] == "matched"


def test_live_delayed_reply_is_not_a_fill_and_error_carries_the_reply(monkeypatch):
    reply = {"status": "sent", "order": {"success": True, "status": "delayed", "makingAmount": "", "takingAmount": ""}}
    with pytest.raises(RuntimeError) as e:
        buy(monkeypatch, reply)
    assert "delayed" in str(e.value)


def test_live_rejection_includes_raw_reply_truncated(monkeypatch):
    reply = {"status": "sent", "order": {"success": False, "errorMsg": "", "junk": "x" * 1000}}
    with pytest.raises(RuntimeError) as e:
        buy(monkeypatch, reply)
    assert "rejected" in str(e.value) and len(str(e.value)) < 700
