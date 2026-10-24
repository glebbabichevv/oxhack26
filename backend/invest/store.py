"""JSON storage for invest plans, their event log and the equity history (data/raw, gitignored).

One process writes (the trader instance); writes are atomic (tmp file + os.replace) under one lock.
"""
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
_lock = threading.RLock()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, folder=None):
        self.dir = Path(folder or os.environ.get("INVEST_DATA_DIR") or DEFAULT_DIR)

    def _read(self, name, default):
        path = self.dir / name
        return json.loads(path.read_text()) if path.exists() else default

    def _write(self, name, data):
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f"{name}.tmp"
        tmp.write_text(json.dumps(data, indent=1))
        os.replace(tmp, self.dir / name)

    def plans(self):
        with _lock:
            return self._read("plans.json", [])

    def plan(self, plan_id):
        return next((p for p in self.plans() if p["id"] == plan_id), None)

    def save_plan(self, plan):
        with _lock:
            plans = [p for p in self._read("plans.json", []) if p["id"] != plan["id"]]
            self._write("plans.json", plans + [plan])

    def new_plan(self, budget, max_bet, daily_loss_stop, now):
        plan = dict(id=uuid.uuid4().hex[:8], created_at=now, budget=float(budget), max_bet=float(max_bet),
                    daily_loss_stop=float(daily_loss_stop), status="running", pause_reason=None,
                    cash=float(budget), positions=[], errors=0,
                    day={"date": None, "start_value": float(budget)}, last_check=None)
        self.save_plan(plan)
        return plan

    def log(self, plan_id, kind, now, **fields):
        event = {"id": uuid.uuid4().hex[:10], "plan_id": plan_id, "kind": kind, "t": now, **fields}
        with _lock:
            self._write("orders.json", self._read("orders.json", []) + [event])
        return event

    def events(self, plan_id=None, limit=None):
        with _lock:
            rows = [e for e in reversed(self._read("orders.json", [])) if plan_id is None or e["plan_id"] == plan_id]
        return rows[:limit] if limit else rows

    def add_equity(self, t, invested, value):
        with _lock:
            self._write("equity.json", self._read("equity.json", []) + [{"t": t, "invested": invested, "value": value}])

    def equity(self):
        with _lock:
            return self._read("equity.json", [])
