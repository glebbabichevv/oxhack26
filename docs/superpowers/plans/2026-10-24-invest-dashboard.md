# Invest Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A simple `/invest` page where a worker sees the model's profit and starts a real-money plan ("invest $1000") that a server-side loop spreads across Polymarket bets automatically, inside hard limits.

**Architecture:** A new `backend/invest/` package holds four focused units: JSON storage, pure sizing/pause rules, a Polymarket broker adapter, and the trading cycle. `backend/invest_router.py` exposes `/api/plans`, `/api/orders` and `/api/pnl`, and starts the 10-minute loop only when `TRADER_ENABLED=1`. The Next.js app gets an `/invest` page built from four small components that call that API.

**Tech Stack:** Python 3, FastAPI, pytest + FastAPI TestClient (httpx 0.28 is installed), the existing `integrations/polymarket_trading.py` and `integrations/mcp_polymarket.py`; Next.js 15, React 19, Tailwind 4, Recharts 2.

**Spec:** `docs/superpowers/specs/2026-10-24-invest-dashboard-design.md`

## Global Constraints

- **Real money.** Live mode is `POLYMARKET_LIVE=1` and is only switched on in Task 8, after the paper run passes. Every task before that runs in paper mode.
- **Ceilings.** `POLYMARKET_MAX_BET_USD` (raised to 25) is the hard per-bet ceiling, and a plan's `max_bet` may never exceed it. `MAX_TOTAL_EXPOSURE_USD` (default 200) caps open stake across all plans.
- **Spread limits.**
  - At most 5% of a plan's budget in one market, and at most 10% in one event (the event slug comes from the market URL).
  - Never hold both YES and NO on the same market.
- **Stake and fills.**
  - The stake is `kelly_fraction × plan value`; `kelly_fraction` from `/api/live` is already the clipped ¼-Kelly.
  - Each buy is re-quoted on the live order book and skipped if `p_win_conservative − avg_price − fee ≤ 0`. For YES, `p_win_conservative = q_low`; for NO it is `1 − q_high`.
  - Orders are fill-and-kill, capped at the quoted worst price.
- **Auto-pause** triggers on: 3 consecutive Polymarket errors; `/api/live` `updated_at` older than 2 hours; or (day's starting value − current value) > `daily_loss_stop`.
- **Stop** ends buying only; open bets ride to settlement.
- **Storage.** `plans.json`, `orders.json` and `equity.json` live in `data/raw/` (gitignored), overridable with `INVEST_DATA_DIR`.
- **PIN.**
  - `DASHBOARD_PIN` arrives in the `X-Dashboard-Pin` header and is checked on every write; reads need no PIN.
  - 3 wrong tries lock writes for 5 minutes.
- **Secrets.** The private key never leaves the backend, and no secret is ever committed.
- **Hosting.** The production API runs on Vercel, which is serverless, so the loop and its JSON files must run on a separate always-on instance. The frontend reaches it through `NEXT_PUBLIC_TRADER_URL`, which defaults to `NEXT_PUBLIC_API_URL`.
- **Copy and accessibility.**
  - Plain English, no jargon.
  - Colour is never the only signal: every number carries a +/− sign or a word.
  - Every control is keyboard-usable with a visible focus ring.
  - The page works at 375px width.
  - Styling follows `DESIGN.md`, using the existing `frontend/design/components`.
- **Commands.**
  - All Python tests run from `backend/`: `python -m pytest tests -q`.
  - All git commands run in the worktree `C:\Users\toaya\oxhack26-invest` on branch `int/invest-dashboard`.
  - Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## File map

| File | Responsibility |
|---|---|
| `backend/invest/__init__.py` | Package marker (empty) |
| `backend/invest/store.py` | Read/write plans, the event log and equity history as JSON (atomic writes, one lock) |
| `backend/invest/rules.py` | Pure functions: `event_of`, `plan_value`, `size_bet`, `pause_reason`, `p_win` |
| `backend/invest/broker.py` | Adapter over `integrations/`: `market`, `quote`, `buy`, `mark` |
| `backend/invest/trader.py` | `run_cycle` (settle → mark → pause check → buy round → equity point), `run_once`, `loop`, lock file |
| `backend/invest_router.py` | API endpoints, PIN check, starting the loop |
| `backend/app.py` | +2 lines: include the router, register the trader |
| `backend/tests/` | `test_store.py`, `test_rules.py`, `test_trader.py`, `test_router.py` |
| `integrations/polymarket_trading.py` | + `resolution(m, side)` and `exit_mark(m, side)` |
| `frontend/lib/invest.ts` | Types, `TRADER_URL`, fetchers, `postWithPin`, feed sentence builder |
| `frontend/components/invest/ProfitChart.tsx` | Real vs backtest profit in $ |
| `frontend/components/invest/StartPlan.tsx` | "Start investing" form + confirmation |
| `frontend/components/invest/PlanCard.tsx` | One plan's status + Pause / Resume / Stop |
| `frontend/components/invest/BetsFeed.tsx` | Recent bets in plain English |
| `frontend/app/invest/page.tsx` | The page: tiles, chart, start/plan cards, feed, PIN field |
| `.env.example`, `backend/README.md`, `CLAUDE.md` (API contract), `team/inbox/A.md`, `team/inbox/B.md` | Docs and hand-off |

---

### Task 1: JSON store

**Files:**
- Create: `backend/invest/__init__.py`, `backend/invest/store.py`
- Test: `backend/tests/test_store.py`

**Interfaces:**
- Produces:
  - `Store(folder: str | Path | None = None)` with methods:
    - `.plans() -> list[dict]`
    - `.plan(plan_id: str) -> dict | None`
    - `.save_plan(plan: dict) -> None`
    - `.new_plan(budget: float, max_bet: float, daily_loss_stop: float, now: str) -> dict`
    - `.log(plan_id: str | None, kind: str, now: str, **fields) -> dict`
    - `.events(plan_id: str | None = None, limit: int | None = None) -> list[dict]` (newest first)
    - `.add_equity(t: str, invested: float, value: float) -> None`
    - `.equity() -> list[dict]`
  - `now_iso() -> str`
  - The plan dict shape is: `{id, created_at, budget, max_bet, daily_loss_stop, status: "running"|"paused"|"stopped", pause_reason: str|None, cash, positions: [], errors: 0, day: {date: None, start_value: budget}, last_check: None}`
  - A position dict is: `{market_id, event, question, side, shares, cost, avg_price, p_model, bought_at, end_hours, url, status: "open"|"won"|"lost", mark, payout}`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run the test and check that it fails**

Run: `cd backend && python -m pytest tests/test_store.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'invest'`

- [ ] **Step 3: Write the implementation**

```python
# backend/invest/__init__.py
```

```python
# backend/invest/store.py
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
        rows = [e for e in reversed(self._read("orders.json", [])) if plan_id is None or e["plan_id"] == plan_id]
        return rows[:limit] if limit else rows

    def add_equity(self, t, invested, value):
        with _lock:
            self._write("equity.json", self._read("equity.json", []) + [{"t": t, "invested": invested, "value": value}])

    def equity(self):
        return self._read("equity.json", [])
```

- [ ] **Step 4: Run the test and check that it passes**

Run: `cd backend && python -m pytest tests/test_store.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/invest/__init__.py backend/invest/store.py backend/tests/test_store.py
git commit -m "invest: JSON store for plans, event log and equity history"
```

---

### Task 2: Sizing and pause rules (pure)

**Files:**
- Create: `backend/invest/rules.py`
- Test: `backend/tests/test_rules.py`

**Interfaces:**
- Consumes: the plan and position dict shapes from Task 1, and the `/api/live` item shape (`market_id, question, action, net_edge, kelly_fraction, q_yes, q_low, q_high, fee, url, hours_to_resolution`).
- Produces:
  - `MIN_STAKE_USD = 1.0`, `MARKET_SHARE = 0.05`, `EVENT_SHARE = 0.10`, `STALE_HOURS = 2`, `MAX_ERRORS = 3`
  - `event_of(url: str) -> str`
  - `side_of(item: dict) -> "YES" | "NO"`
  - `p_win(item: dict, side: str) -> float` (conservative: `q_low` for YES, `1 − q_high` for NO)
  - `plan_value(plan: dict) -> float` (cash + open shares × mark)
  - `size_bet(item: dict, plan: dict, value: float, ceiling: float) -> tuple[float, str | None]`
  - `pause_reason(plan: dict, value: float, updated_at: str | None, now: datetime) -> str | None`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run the test and check that it fails**

Run: `cd backend && python -m pytest tests/test_rules.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'invest.rules'`

- [ ] **Step 3: Write the implementation**

```python
# backend/invest/rules.py
"""Pure sizing and safety rules for invest plans (no network, no files)."""
from datetime import datetime, timedelta

MIN_STAKE_USD = 1.0
MARKET_SHARE = 0.05  # max share of a plan's budget in one market
EVENT_SHARE = 0.10   # max share in one event (its legs are correlated)
STALE_HOURS = 2
MAX_ERRORS = 3


def event_of(url):
    return url.rstrip("/").split("/")[-1]


def side_of(item):
    return "YES" if item["action"] == "BUY_YES" else "NO"


def p_win(item, side):
    """Chance this side wins, taken at the cautious end of the model's interval."""
    return item["q_low"] if side == "YES" else 1 - item["q_high"]


def plan_value(plan):
    held = sum(p["shares"] * (p.get("mark") or 0) for p in plan["positions"] if p["status"] == "open")
    return round(plan["cash"] + held, 2)


def size_bet(item, plan, value, ceiling):
    """Dollar stake for one live decision: ¼-Kelly of plan value, clipped by every limit. (0, reason) to skip."""
    side = side_of(item)
    held = [p for p in plan["positions"] if p["status"] == "open"]
    if any(p["market_id"] == item["market_id"] and p["side"] != side for p in held):
        return 0.0, "opposite_side_held"
    in_market = sum(p["cost"] for p in held if p["market_id"] == item["market_id"])
    in_event = sum(p["cost"] for p in held if p["event"] == event_of(item["url"]))
    room = min(plan["max_bet"], ceiling, plan["cash"],
               MARKET_SHARE * plan["budget"] - in_market, EVENT_SHARE * plan["budget"] - in_event)
    if room < MIN_STAKE_USD:
        return 0.0, "limit_reached"
    stake = min(item["kelly_fraction"] * value, room)
    if stake < MIN_STAKE_USD:
        return 0.0, "too_small"
    return round(stake, 2), None


def pause_reason(plan, value, updated_at, now):
    if plan["errors"] >= MAX_ERRORS:
        return "polymarket_errors"
    if updated_at is None or now - datetime.fromisoformat(updated_at.replace("Z", "+00:00")) > timedelta(hours=STALE_HOURS):
        return "stale_data"
    if plan["day"]["start_value"] - value > plan["daily_loss_stop"]:
        return "daily_loss"
    return None
```

- [ ] **Step 4: Run the test and check that it passes**

Run: `cd backend && python -m pytest tests/test_rules.py -q`
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/invest/rules.py backend/tests/test_rules.py
git commit -m "invest: sizing (quarter Kelly, market/event/cash caps) and auto-pause rules"
```

---

### Task 3: Broker adapter and settlement helpers

**Files:**
- Modify: `integrations/polymarket_trading.py` (add two functions after `read_ledger`)
- Create: `backend/invest/broker.py`
- Test: `backend/tests/test_rules.py` gets 2 more tests (the helpers are pure on a market dict)

**Interfaces:**
- Consumes: `mcp_polymarket.get_market(market_id) -> dict`, which returns the `summarise()` shape (`closed`, `outcomes`, `best_bid`, `best_ask`, `token_ids`, …). Also `polymarket_trading.quote(m, side, usd)` and `polymarket_trading.place_bet(m, side, usd, limit_price, confirm=True, note)`.
- Produces:
  - In `polymarket_trading.py`:
    - `resolution(m, side) -> 1 | 0 | None`
    - `exit_mark(m, side) -> float | None`
  - `Broker` in `backend/invest/broker.py`, with:
    - `.mode -> "paper" | "live"`
    - `.ceiling -> float` (`MAX_BET_USD`)
    - `.market(market_id) -> dict`
    - `.quote(m, side, usd) -> dict` (the `trading.quote` shape: `shares, avg_price, worst_price, fillable_usd, min_order_size`)
    - `.buy(m, side, usd, worst_price, note) -> {"shares": float, "cost": float, "avg_price": float}`
    - `.mark(m, side) -> tuple[float | None, int | None]`, meaning `(exit price, outcome)`

- [ ] **Step 1: Write the failing test** (append to `backend/tests/test_rules.py`)

```python
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
```

- [ ] **Step 2: Run the test and check that it fails**

Run: `cd backend && python -m pytest tests/test_rules.py -q`
Expected: FAIL with `ImportError: cannot import name 'exit_mark'`

- [ ] **Step 3: Add the helpers to `integrations/polymarket_trading.py`** (directly after `def read_ledger(): ...`)

```python
def resolution(m, side):
    """1 if `side` won, 0 if it lost, None while unresolved (closed markets settle to outcome prices 1/0)."""
    if not m["closed"]:
        return None
    price = m["outcomes"].get("Yes" if side == "YES" else "No")
    if price is None or 0.02 < price < 0.98:
        return None
    return 1 if price >= 0.98 else 0


def exit_mark(m, side):
    """What selling one share now would fetch: the YES bid, or 1 - YES ask for a NO share."""
    if side == "YES":
        return float(m["best_bid"]) if m.get("best_bid") is not None else None
    return 1 - float(m["best_ask"]) if m.get("best_ask") is not None else None
```

- [ ] **Step 4: Create `backend/invest/broker.py`**

```python
"""Polymarket access for the trader: the integrations/ code, paper or live by POLYMARKET_LIVE."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integrations"))
import mcp_polymarket as pm  # noqa: E402
import polymarket_trading as trading  # noqa: E402


class Broker:
    mode = trading.mode()
    ceiling = trading.MAX_BET_USD

    def market(self, market_id):
        return pm.get_market(market_id)

    def quote(self, m, side, usd):
        return trading.quote(m, side, usd)

    def buy(self, m, side, usd, worst_price, note):
        r = trading.place_bet(m, side, usd, limit_price=worst_price, confirm=True, note=note)
        if r["status"] == "paper_filled":
            shares, cost = r["shares"], r["cost_usd"]
        else:  # live FAK order: makingAmount = USDC paid, takingAmount = shares received
            order = r.get("order") or {}
            if not order.get("success", False):
                raise RuntimeError(f"order rejected: {order.get('errorMsg') or order}")
            shares, cost = float(order.get("takingAmount") or 0), float(order.get("makingAmount") or 0)
        if shares <= 0:
            raise RuntimeError("order filled nothing")
        return {"shares": shares, "cost": round(cost, 4), "avg_price": round(cost / shares, 4)}

    def mark(self, m, side):
        return trading.exit_mark(m, side), trading.resolution(m, side)
```

- [ ] **Step 5: Run the tests and check that they pass**

Run: `cd backend && python -m pytest tests/test_rules.py -q && python -c "from invest.broker import Broker; print(Broker.mode, Broker.ceiling)"`
Expected: `12 passed`, then `paper 10.0` (or the value in `.env.local`)

- [ ] **Step 6: Commit**

```bash
git add integrations/polymarket_trading.py backend/invest/broker.py backend/tests/test_rules.py
git commit -m "invest: broker adapter; resolution and exit_mark helpers in polymarket_trading"
```

---

### Task 4: Trading cycle

**Files:**
- Create: `backend/invest/trader.py`
- Test: `backend/tests/test_trader.py`

**Interfaces:**
- Consumes: `Store` (Task 1), all of `rules` (Task 2), the `Broker` interface (Task 3; tests use a fake with the same methods), and a live payload `{"updated_at": str, "markets": [item, ...]}`.
- Produces:
  - `run_cycle(store: Store, broker, live: dict, now: datetime, total_cap: float) -> None`
  - `run_once(store, broker) -> None` (fetches `live.get_live()`, reads `MAX_TOTAL_EXPOSURE_USD`)
  - `async loop(store, broker, interval_s: int = 600) -> None`
  - `acquire_lock(path: Path, now: float, stale_s: int = 1800) -> bool`
  - `INTERVAL_S = 600`
  - The event kinds it writes are: `buy`, `skip` (with `reason` ∈ `edge_vanished | below_minimum | no_liquidity`), `settle`, `pause` (with `reason`), and `error` (with `text`).

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run the test and check that it fails**

Run: `cd backend && python -m pytest tests/test_trader.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'invest.trader'`

- [ ] **Step 3: Write the implementation**

```python
# backend/invest/trader.py
"""The auto-buyer: every 10 minutes, settle and mark each plan's bets, check its safety stops,
then buy the best live edges inside its limits. Paper or live is the broker's business."""
import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .rules import MAX_ERRORS, event_of, p_win, pause_reason, plan_value, side_of, size_bet

INTERVAL_S = 600


def _iso(now):
    return now.isoformat(timespec="seconds")


def settle_and_mark(store, broker, plan, now):
    for p in plan["positions"]:
        if p["status"] != "open":
            continue
        mark, outcome = broker.mark(broker.market(p["market_id"]), p["side"])
        if outcome is None:
            p["mark"] = mark if mark is not None else p["mark"]
            continue
        payout = round(p["shares"] * outcome, 4)
        plan["cash"] = round(plan["cash"] + payout, 4)
        p.update(status="won" if outcome else "lost", payout=payout, mark=float(outcome))
        store.log(plan["id"], "settle", _iso(now), question=p["question"], side=p["side"], outcome=outcome,
                  cost=p["cost"], payout=payout, pnl=round(payout - p["cost"], 4), url=p["url"])


def buy_round(store, broker, plan, live, now, value, room):
    """Returns the stake spent, so the caller can shrink the shared exposure room."""
    spent = 0.0
    picks = sorted((i for i in live["markets"] if i["action"] != "NO_TRADE" and i["net_edge"] > 0),
                   key=lambda i: -i["net_edge"])
    for item in picks:
        if plan["errors"] >= MAX_ERRORS:
            break
        stake, _ = size_bet(item, plan, value, min(broker.ceiling, room - spent))
        if not stake:
            continue
        side = side_of(item)
        base = dict(question=item["question"], side=side, url=item["url"])
        try:
            m = broker.market(item["market_id"])
            q = broker.quote(m, side, stake)
            if not q["shares"]:
                store.log(plan["id"], "skip", _iso(now), reason="no_liquidity", **base)
                continue
            if q.get("min_order_size") and q["shares"] < float(q["min_order_size"]):
                store.log(plan["id"], "skip", _iso(now), reason="below_minimum", **base)
                continue
            if p_win(item, side) - q["avg_price"] - (item.get("fee") or 0) <= 0:
                store.log(plan["id"], "skip", _iso(now), reason="edge_vanished", price=q["avg_price"], **base)
                continue
            fill = broker.buy(m, side, q["fillable_usd"], q["worst_price"], note=f"plan {plan['id']}")
        except Exception as e:  # network / order errors count towards the auto-pause
            plan["errors"] += 1
            store.log(plan["id"], "error", _iso(now), text=str(e)[:300], **base)
            continue
        plan["errors"] = 0
        plan["cash"] = round(plan["cash"] - fill["cost"], 4)
        spent += fill["cost"]
        p_model = item["q_yes"] if side == "YES" else 1 - item["q_yes"]
        plan["positions"].append(dict(
            market_id=item["market_id"], event=event_of(item["url"]), question=item["question"], side=side,
            shares=fill["shares"], cost=fill["cost"], avg_price=fill["avg_price"], p_model=round(p_model, 4),
            bought_at=_iso(now), end_hours=item["hours_to_resolution"], url=item["url"],
            status="open", mark=fill["avg_price"], payout=None))
        store.log(plan["id"], "buy", _iso(now), cost=fill["cost"], shares=fill["shares"], price=fill["avg_price"],
                  p_model=round(p_model, 4), hours_to_resolution=item["hours_to_resolution"], **base)
    return spent


def run_cycle(store, broker, live, now, total_cap):
    plans = store.plans()
    open_stake = sum(p["cost"] for pl in plans for p in pl["positions"] if p["status"] == "open")
    room = max(total_cap - open_stake, 0.0)
    for plan in plans:
        try:
            settle_and_mark(store, broker, plan, now)
        except Exception as e:
            plan["errors"] += 1
            store.log(plan["id"], "error", _iso(now), text=f"settling: {str(e)[:300]}")
        value = plan_value(plan)
        today = now.date().isoformat()
        if plan["day"]["date"] != today:
            plan["day"] = {"date": today, "start_value": value}
        if plan["status"] == "running":
            reason = pause_reason(plan, value, live.get("updated_at"), now)
            if reason:
                plan.update(status="paused", pause_reason=reason)
                store.log(plan["id"], "pause", _iso(now), reason=reason)
            else:
                room -= buy_round(store, broker, plan, live, now, value, room)
                if plan["errors"] >= MAX_ERRORS:
                    plan.update(status="paused", pause_reason="polymarket_errors")
                    store.log(plan["id"], "pause", _iso(now), reason="polymarket_errors")
        plan["last_check"] = _iso(now)
        store.save_plan(plan)
    plans = store.plans()
    store.add_equity(_iso(now), round(sum(p["budget"] for p in plans), 2), round(sum(plan_value(p) for p in plans), 2))


def acquire_lock(path, now, stale_s=1800):
    """One trader per data folder: take the lock if it is missing or its heartbeat is stale."""
    path = Path(path)
    if path.exists() and now - float(path.read_text().split()[1]) < stale_s:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{os.getpid()} {now}")
    return True


def run_once(store, broker):
    import live as live_feed  # backend/live.py: the same decisions /api/live serves
    total_cap = float(os.environ.get("MAX_TOTAL_EXPOSURE_USD") or 200)
    run_cycle(store, broker, live_feed.get_live(), datetime.now(timezone.utc), total_cap)


async def loop(store, broker, interval_s=INTERVAL_S):
    lock, me = store.dir / "trader.lock", str(os.getpid())
    while True:
        mine = lock.exists() and lock.read_text().split()[0] == me
        if mine or acquire_lock(lock, time.time()):
            lock.write_text(f"{me} {time.time()}")  # heartbeat: another process may take over after 30 min of silence
            try:
                await asyncio.to_thread(run_once, store, broker)
            except Exception as e:
                store.log(None, "error", _iso(datetime.now(timezone.utc)), text=f"cycle failed: {str(e)[:300]}")
        await asyncio.sleep(interval_s)
```

- [ ] **Step 4: Run the tests and check that they pass**

Run: `cd backend && python -m pytest tests -q`
Expected: all pass (`4 + 12 + 9 = 25 passed`)

- [ ] **Step 5: Commit**

```bash
git add backend/invest/trader.py backend/tests/test_trader.py
git commit -m "invest: trading cycle (settle, mark, auto-pause, buy round, equity) and single-runner lock"
```

---

### Task 5: API endpoints, PIN, starting the loop

**Files:**
- Create: `backend/invest_router.py`
- Modify: `backend/app.py` (append after the agent router line)
- Test: `backend/tests/test_router.py`

**Interfaces:**
- Consumes: `Store`, `plan_value`, `Broker.mode` / `Broker.ceiling`, `trader.loop`, and `backend/results/backtest.json` (`with_costs.equity: [{t, value}]`, where value is in starting-bankroll units starting at 1).
- Produces:

| Endpoint | Returns |
|---|---|
| `GET /api/plans` | `{"mode": "paper"\|"live", "interval_min": 10, "max_bet_ceiling": float, "plans": [PlanSummary]}` |
| `POST /api/plans` | `PlanSummary`. Body `{budget, max_bet, daily_loss_stop}` plus the `X-Dashboard-Pin` header. |
| `POST /api/plans/{id}/{pause\|resume\|stop}` | `PlanSummary` |
| `GET /api/orders?plan=&limit=50` | `[Event]` |
| `GET /api/pnl` | `{"real": [{t, value}], "backtest": [{t, value}], "backtest_budget": float}`, values as $ profit |

  `PlanSummary` = `{id, status, pause_reason, budget, max_bet, daily_loss_stop, cash, value, profit, profit_pct, open_bets, last_check, created_at}`

  Errors: 401 `"Wrong PIN"`, 429 `"Too many wrong PINs; try again in 5 minutes"`, 503 `"DASHBOARD_PIN is not set on the server"`, 404 for an unknown plan, 400 if `max_bet > ceiling`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_router.py
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
```

- [ ] **Step 2: Run the test and check that it fails**

Run: `cd backend && python -m pytest tests/test_router.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'invest_router'`

- [ ] **Step 3: Write `backend/invest_router.py`**

```python
"""Invest dashboard API: plans (create / pause / resume / stop), the bets feed, real vs backtest profit.

Writes need the X-Dashboard-Pin header (DASHBOARD_PIN in .env.local). The trading loop runs only
where TRADER_ENABLED=1 — an always-on host, never the serverless deploy.
"""
import asyncio
import hmac
import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from invest.rules import plan_value
from invest.store import Store, now_iso

HERE = Path(__file__).parent
router = APIRouter()
store = Store()
PIN = os.environ.get("DASHBOARD_PIN")
_fails = {"n": 0, "until": 0.0}


def _broker_meta():
    try:
        from invest.broker import Broker
        return Broker.mode, float(Broker.ceiling)
    except Exception:  # integrations deps missing on this host: reads still work
        return "paper", float(os.environ.get("POLYMARKET_MAX_BET_USD") or 10)


def require_pin(pin):
    if not PIN:
        raise HTTPException(503, "DASHBOARD_PIN is not set on the server")
    if time.time() < _fails["until"]:
        raise HTTPException(429, "Too many wrong PINs; try again in 5 minutes")
    if not hmac.compare_digest(pin or "", PIN):
        _fails["n"] += 1
        if _fails["n"] >= 3:
            _fails.update(n=0, until=time.time() + 300)
        raise HTTPException(401, "Wrong PIN")
    _fails["n"] = 0


def summary(plan):
    value = plan_value(plan)
    profit = round(value - plan["budget"], 2)
    keys = ("id", "status", "pause_reason", "budget", "max_bet", "daily_loss_stop", "cash", "last_check", "created_at")
    return {**{k: plan[k] for k in keys}, "value": value, "profit": profit,
            "profit_pct": round(profit / plan["budget"], 4),
            "open_bets": sum(p["status"] == "open" for p in plan["positions"])}


class PlanIn(BaseModel):
    budget: float = Field(gt=0, le=1_000_000)
    max_bet: float = Field(gt=0)
    daily_loss_stop: float = Field(gt=0)


@router.get("/api/plans")
def list_plans():
    mode, ceiling = _broker_meta()
    return {"mode": mode, "interval_min": 10, "max_bet_ceiling": ceiling,
            "plans": [summary(p) for p in sorted(store.plans(), key=lambda p: p["created_at"], reverse=True)]}


@router.post("/api/plans")
def create_plan(body: PlanIn, x_dashboard_pin: str | None = Header(default=None)):
    require_pin(x_dashboard_pin)
    _, ceiling = _broker_meta()
    if body.max_bet > ceiling:
        raise HTTPException(400, f"Max per bet can be at most ${ceiling:g} on this server")
    now = now_iso()
    plan = store.new_plan(body.budget, body.max_bet, body.daily_loss_stop, now)
    store.log(plan["id"], "start", now, budget=body.budget, max_bet=body.max_bet)
    return summary(plan)


@router.post("/api/plans/{plan_id}/{action}")
def control_plan(plan_id: str, action: str, x_dashboard_pin: str | None = Header(default=None)):
    require_pin(x_dashboard_pin)
    plan = store.plan(plan_id)
    if plan is None:
        raise HTTPException(404, "No such plan")
    if action not in ("pause", "resume", "stop"):
        raise HTTPException(404, "Unknown action")
    if plan["status"] == "stopped":
        raise HTTPException(400, "This plan is stopped; start a new one")
    if action == "resume":  # a person chose to carry on: today's loss stop counts from now
        plan.update(status="running", pause_reason=None, errors=0)
        plan["day"]["start_value"] = plan_value(plan)
    else:
        plan.update(status="paused" if action == "pause" else "stopped", pause_reason="by_person" if action == "pause" else None)
    store.save_plan(plan)
    store.log(plan_id, action, now_iso())
    return summary(plan)


@router.get("/api/orders")
def orders(plan: str | None = None, limit: int = 50):
    return store.events(plan, min(limit, 500))


def _backtest_equity():
    for folder in (HERE / "results", HERE / "examples"):
        path = folder / "backtest.json"
        if path.exists():
            return json.loads(path.read_text())["with_costs"]["equity"]
    return []


@router.get("/api/pnl")
def pnl():
    budget = sum(p["budget"] for p in store.plans()) or 1000.0
    real = [{"t": e["t"], "value": round(e["value"] - e["invested"], 2)} for e in store.equity()]
    # Backtest equity is in starting-bankroll units from 1.0; show it as $ profit on the same budget.
    backtest = [{"t": e["t"], "value": round((e["value"] - 1) * budget, 2)} for e in _backtest_equity()]
    return {"real": real, "backtest": backtest, "backtest_budget": budget}


def start_trader(app):
    """Run the 10-minute loop inside this process when TRADER_ENABLED=1."""
    if os.environ.get("TRADER_ENABLED") != "1":
        return

    async def _start():
        from invest.broker import Broker
        from invest.trader import loop
        asyncio.get_running_loop().create_task(loop(store, Broker()))

    app.add_event_handler("startup", _start)
```

- [ ] **Step 4: Wire it into `backend/app.py`** (append at the end of the file)

```python
# Invest dashboard: plans, bets feed, profit; the trading loop only where TRADER_ENABLED=1.
from invest_router import router as invest_router, start_trader  # noqa: E402
app.include_router(invest_router)
start_trader(app)
```

- [ ] **Step 5: Run the tests and check that they pass, then smoke-test the app**

Run: `cd backend && python -m pytest tests -q`
Expected: all pass (`31 passed`)

Run: `cd backend && python -c "import app; print([r.path for r in app.app.routes if 'plans' in r.path or 'pnl' in r.path])"`
Expected: `['/api/plans', '/api/plans', '/api/plans/{plan_id}/{action}', '/api/pnl']`

- [ ] **Step 6: Commit**

```bash
git add backend/invest_router.py backend/app.py backend/tests/test_router.py
git commit -m "invest: /api/plans, /api/orders, /api/pnl with PIN on writes; loop behind TRADER_ENABLED"
```

---

### Task 6: Frontend data layer and profit chart

**Files:**
- Create: `frontend/lib/invest.ts`, `frontend/components/invest/ProfitChart.tsx`

**Interfaces:**
- Consumes: the Task 5 endpoints, `API_URL` and `cents` / `pct` from `@/lib/api`, and `ASH, INK, SEAM, axisTick, gridProps, tooltipProps, xAxisProps` from `@/design/components/chartTheme`.
- Produces:
  - Types `PlanSummary`, `PlansPayload`, `InvestEvent`, `Pnl`
  - `TRADER_URL`
  - `getTrader<T>(path) -> Promise<T>`
  - `postWithPin<T>(path, pin, body?) -> Promise<T>` (throws `Error(message)` with the server's `detail`)
  - `money(x, signed?) -> string`
  - `sentence(e: InvestEvent) -> { text: string; tone: "up" | "down" | "muted"; chip: string }`
  - `<ProfitChart real backtest />`

- [ ] **Step 1: Write `frontend/lib/invest.ts`**

```ts
// Types, fetchers and plain-English copy for the invest dashboard (/api/plans, /api/orders, /api/pnl).
import { API_URL, cents, pct } from "@/lib/api";

// The trader runs on an always-on host; on a single-server setup it is the same as the main API.
export const TRADER_URL = (process.env.NEXT_PUBLIC_TRADER_URL ?? API_URL).replace(/\/$/, "");

export type PlanStatus = "running" | "paused" | "stopped";
export type PlanSummary = {
  id: string; status: PlanStatus; pause_reason: string | null; budget: number; max_bet: number;
  daily_loss_stop: number; cash: number; value: number; profit: number; profit_pct: number;
  open_bets: number; last_check: string | null; created_at: string;
};
export type PlansPayload = { mode: "paper" | "live"; interval_min: number; max_bet_ceiling: number; plans: PlanSummary[] };
export type InvestEvent = {
  id: string; plan_id: string | null; kind: "start" | "buy" | "skip" | "settle" | "pause" | "resume" | "stop" | "error";
  t: string; question?: string; side?: "YES" | "NO"; cost?: number; price?: number; p_model?: number;
  hours_to_resolution?: number; outcome?: 0 | 1; payout?: number; pnl?: number; reason?: string; text?: string;
  url?: string; budget?: number;
};
export type Pnl = { real: { t: string; value: number }[]; backtest: { t: string; value: number }[]; backtest_budget: number };

export async function getTrader<T>(path: string): Promise<T> {
  const res = await fetch(`${TRADER_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

export async function postWithPin<T>(path: string, pin: string, body?: unknown): Promise<T> {
  const res = await fetch(`${TRADER_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Dashboard-Pin": pin },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { detail?: string }).detail ?? `Request failed (${res.status})`);
  return data as T;
}

export const money = (x: number, signed = false) => {
  const s = `$${Math.abs(x).toLocaleString("en-US", { maximumFractionDigits: Math.abs(x) >= 100 ? 0 : 2 })}`;
  return signed ? `${x >= 0 ? "+" : "−"}${s}` : `${x < 0 ? "−" : ""}${s}`;
};

const when = (h?: number) => (h === undefined ? "" : h < 24 ? `in ${Math.max(1, Math.round(h))} hours` : `in ${Math.round(h / 24)} days`);

const SKIP: Record<string, string> = {
  edge_vanished: "the price moved and the edge was gone",
  below_minimum: "the bet was below Polymarket's minimum size",
  no_liquidity: "nobody was selling at a fair price",
};
export const PAUSE: Record<string, string> = {
  daily_loss: "today's loss passed the limit you set",
  polymarket_errors: "Polymarket returned errors three times in a row",
  stale_data: "the model's prices were more than 2 hours old",
  by_person: "someone pressed Pause",
};

export function sentence(e: InvestEvent): { text: string; tone: "up" | "down" | "muted"; chip: string } {
  const q = e.question ? `“${e.question}”` : "";
  switch (e.kind) {
    case "buy":
      return { chip: "Open", tone: "muted",
        text: `Bought ${e.side} on ${q} at ${cents(e.price ?? 0)}, ${money(e.cost ?? 0)}. Model thinks ${pct(e.p_model ?? 0)}. Settles ${when(e.hours_to_resolution)}.` };
    case "settle":
      return e.outcome
        ? { chip: `Won ${money(e.pnl ?? 0, true)}`, tone: "up", text: `${e.side} on ${q} won. Paid out ${money(e.payout ?? 0)}.` }
        : { chip: `Lost ${money(e.pnl ?? 0, true)}`, tone: "down", text: `${e.side} on ${q} lost.` };
    case "skip":
      return { chip: "Skipped", tone: "muted", text: `Skipped ${q}: ${SKIP[e.reason ?? ""] ?? e.reason}.` };
    case "pause":
      return { chip: "Paused", tone: "down", text: `Investing paused because ${PAUSE[e.reason ?? ""] ?? e.reason}.` };
    case "start":
      return { chip: "Started", tone: "muted", text: `New plan started with ${money(e.budget ?? 0)}.` };
    case "resume":
      return { chip: "Resumed", tone: "muted", text: "Investing resumed." };
    case "stop":
      return { chip: "Stopped", tone: "muted", text: "Plan stopped. Open bets will settle on their own." };
    default:
      return { chip: "Problem", tone: "down", text: `Something went wrong talking to Polymarket${e.text ? `: ${e.text}` : ""}.` };
  }
}
```

- [ ] **Step 2: Write `frontend/components/invest/ProfitChart.tsx`**

```tsx
"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ASH, INK, SEAM, axisTick, gridProps, tooltipProps, xAxisProps } from "@/design/components/chartTheme";
import { money, type Pnl } from "@/lib/invest";

type Row = { t: string; real?: number; backtest?: number };

// Real points are timestamps, backtest points are dates: merge on the day, carry each line forward.
function merge(pnl: Pnl): Row[] {
  const rows = new Map<string, Row>();
  for (const p of pnl.backtest) rows.set(p.t.slice(0, 10), { ...rows.get(p.t.slice(0, 10)), t: p.t.slice(0, 10), backtest: p.value });
  for (const p of pnl.real) rows.set(p.t.slice(0, 10), { ...rows.get(p.t.slice(0, 10)), t: p.t.slice(0, 10), real: p.value });
  let b: number | undefined;
  return [...rows.values()].sort((x, y) => x.t.localeCompare(y.t)).map((r) => {
    b = r.backtest ?? b;
    return { ...r, backtest: b };
  });
}

const day = (t: string) => new Date(t).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

export function ProfitChart({ pnl }: { pnl: Pnl }) {
  const data = merge(pnl);
  return (
    <figure>
      <div className="h-[300px]" role="img" aria-label={`Profit chart. Real money so far: ${money(pnl.real.at(-1)?.value ?? 0, true)}. Model test since May, after costs, on ${money(pnl.backtest_budget)}: ${money(pnl.backtest.at(-1)?.value ?? 0, true)}.`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 4 }}>
            <CartesianGrid {...gridProps} />
            <XAxis {...xAxisProps} dataKey="t" tickFormatter={day} minTickGap={48} />
            <YAxis tick={axisTick} tickLine={false} axisLine={false} width={64} tickFormatter={(v: number) => money(v, true)} />
            <ReferenceLine y={0} stroke={SEAM} />
            <Tooltip {...tooltipProps} labelFormatter={day}
              formatter={(v: number, name: string) => [money(v, true), name === "real" ? "Our real money" : "Model test (after costs)"]} />
            <Line dataKey="backtest" stroke={ASH} strokeWidth={2} strokeDasharray="5 4" dot={false} connectNulls isAnimationActive={false} />
            <Line dataKey="real" stroke={INK} strokeWidth={2.5} dot={{ r: 2.5, fill: INK }} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[13px] text-ink-muted">
        <span className="inline-flex items-center gap-2"><svg width="20" height="3" aria-hidden><line x1="0" y1="1.5" x2="20" y2="1.5" stroke={INK} strokeWidth="2.5" /></svg>Our real money</span>
        <span className="inline-flex items-center gap-2"><svg width="20" height="3" aria-hidden><line x1="0" y1="1.5" x2="20" y2="1.5" stroke={ASH} strokeWidth="2" strokeDasharray="5 4" /></svg>If we'd followed the model since May (test, after costs, on {money(pnl.backtest_budget)})</span>
      </figcaption>
      <p className="mt-2 text-[13px] text-ink-faint">The dashed line is a test on past markets, not money we made. The solid line is real.</p>
    </figure>
  );
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/invest.ts frontend/components/invest/ProfitChart.tsx
git commit -m "invest UI: API client, plain-English feed copy, profit chart (real vs backtest)"
```

---

### Task 7: The `/invest` page

**Files:**
- Create: `frontend/components/invest/StartPlan.tsx`, `frontend/components/invest/PlanCard.tsx`, `frontend/components/invest/BetsFeed.tsx`, `frontend/app/invest/page.tsx`
- Modify: `frontend/app/page.tsx` (add an "Invest" link to the existing `Nav` `links` array)

**Interfaces:**
- Consumes: everything from Task 6, plus `Nav, Hero, KpiRow, Section, FramedCard` from `@/design/components/Page` and `Button` from `@/design/components/Button`.
- Produces:
  - `<StartPlan ceiling pin onDone />`
  - `<PlanCard plan intervalMin pin onChange />`
  - `<BetsFeed events />`
  - The page at `/invest`

- [ ] **Step 1: Write `frontend/components/invest/StartPlan.tsx`**

```tsx
"use client";

import { useState } from "react";
import { Button } from "@/design/components/Button";
import { money, postWithPin, type PlanSummary } from "@/lib/invest";

const field = "mt-1.5 h-12 w-full rounded-xl border border-hairline bg-white px-4 text-[18px] tabular-nums text-ink-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-ink-strong";

export function StartPlan({ ceiling, pin, onDone }: { ceiling: number; pin: string; onDone: () => void }) {
  const [budget, setBudget] = useState(1000);
  const [maxBet, setMaxBet] = useState(Math.min(25, ceiling));
  const [stop, setStop] = useState(100);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = budget > 0 && maxBet > 0 && maxBet <= ceiling && stop > 0;

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await postWithPin<PlanSummary>("/api/plans", pin, { budget, max_bet: maxBet, daily_loss_stop: stop });
      setConfirming(false);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="grid gap-5" onSubmit={(e) => { e.preventDefault(); if (valid) setConfirming(true); }}>
      <label className="block text-[15px] font-medium text-ink-strong">How much do you want to invest? ($)
        <input className={field} type="number" min={1} step={1} inputMode="numeric" value={budget} onChange={(e) => setBudget(+e.target.value)} />
      </label>
      <label className="block text-[15px] font-medium text-ink-strong">Most it may put on one bet ($)
        <input className={field} type="number" min={1} max={ceiling} step={1} inputMode="numeric" value={maxBet} onChange={(e) => setMaxBet(+e.target.value)} />
        <span className="mt-1 block text-[13px] font-normal text-ink-muted">Up to {money(ceiling)} on this server.</span>
      </label>
      <label className="block text-[15px] font-medium text-ink-strong">Stop for the day if we lose more than ($)
        <input className={field} type="number" min={1} step={1} inputMode="numeric" value={stop} onChange={(e) => setStop(+e.target.value)} />
      </label>
      {!confirming ? (
        <Button type="submit" className="h-12 text-[16px]" disabled={!valid || !pin}>{pin ? "Start investing" : "Enter the PIN above to start"}</Button>
      ) : (
        <div className="rounded-2xl bg-fill-soft p-5" role="alertdialog" aria-labelledby="confirm-text">
          <p id="confirm-text" className="text-[16px] leading-[1.5] text-ink-strong">
            This uses <b>real money</b>: up to {money(budget)} in bets of up to {money(maxBet)} each, only when the model sees an
            edge after fees. It checks every 10 minutes and stops for the day after a {money(stop)} loss.
          </p>
          <div className="mt-4 flex gap-3">
            <Button type="button" className="h-11" onClick={start} disabled={busy}>{busy ? "Starting…" : "Yes, start"}</Button>
            <Button type="button" variant="quiet" className="h-11" onClick={() => setConfirming(false)}>Cancel</Button>
          </div>
        </div>
      )}
      {error ? <p role="alert" className="text-[14px] font-medium text-down">{error}</p> : null}
    </form>
  );
}
```

- [ ] **Step 2: Write `frontend/components/invest/PlanCard.tsx`**

```tsx
"use client";

import { useState } from "react";
import { Button } from "@/design/components/Button";
import { PAUSE, money, postWithPin, type PlanSummary } from "@/lib/invest";

function ago(iso: string | null) {
  if (!iso) return "not yet";
  const min = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
  return min < 1 ? "just now" : min < 60 ? `${min} min ago` : `${Math.round(min / 60)} h ago`;
}

export function PlanCard({ plan, intervalMin, pin, onChange }: { plan: PlanSummary; intervalMin: number; pin: string; onChange: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function act(action: "pause" | "resume" | "stop") {
    if (action === "stop" && !window.confirm("Stop this plan? It will not place new bets. Open bets still settle.")) return;
    setBusy(true);
    setError(null);
    try {
      await postWithPin(`/api/plans/${plan.id}/${action}`, pin);
      onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const status =
    plan.status === "running" ? `Running · checks every ${intervalMin} min · last check ${ago(plan.last_check)}`
    : plan.status === "paused" ? `Paused: ${PAUSE[plan.pause_reason ?? ""] ?? plan.pause_reason}`
    : "Stopped · open bets will settle on their own";

  return (
    <div className="rounded-2xl border border-hairline p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-[17px] font-semibold text-ink-strong">{money(plan.budget)} plan</span>
        <span className={`text-[15px] font-semibold tabular-nums ${plan.profit >= 0 ? "text-up" : "text-down"}`}>
          {plan.profit >= 0 ? "Up" : "Down"} {money(plan.profit, true)} ({(plan.profit_pct * 100).toFixed(1)}%)
        </span>
      </div>
      <p className="mt-1 text-[14px] text-ink-muted" aria-live="polite">{status}</p>
      <p className="mt-1 text-[14px] text-ink-muted tabular-nums">{plan.open_bets} open bets · {money(plan.cash)} cash not yet used · max {money(plan.max_bet)} per bet</p>
      {plan.status !== "stopped" ? (
        <div className="mt-4 flex flex-wrap gap-3">
          {plan.status === "running"
            ? <Button className="h-11 px-6" onClick={() => act("pause")} disabled={busy || !pin}>Pause</Button>
            : <Button className="h-11 px-6" onClick={() => act("resume")} disabled={busy || !pin}>Resume</Button>}
          <Button variant="quiet" className="h-11 px-6" onClick={() => act("stop")} disabled={busy || !pin}>Stop</Button>
        </div>
      ) : null}
      {error ? <p role="alert" className="mt-3 text-[14px] font-medium text-down">{error}</p> : null}
    </div>
  );
}
```

- [ ] **Step 3: Write `frontend/components/invest/BetsFeed.tsx`**

```tsx
import { sentence, type InvestEvent } from "@/lib/invest";

const tone = { up: "bg-up-tint text-up", down: "bg-down-tint text-down", muted: "bg-fill-soft text-ink-strong" };

export function BetsFeed({ events }: { events: InvestEvent[] }) {
  if (!events.length) return <p className="text-[15px] text-ink-muted">No bets yet. The first check runs within 10 minutes of starting a plan.</p>;
  return (
    <ul className="divide-y divide-hairline">
      {events.map((e) => {
        const s = sentence(e);
        return (
          <li key={e.id} className="flex items-start justify-between gap-4 py-3.5">
            <div className="min-w-0">
              <p className="text-[15px] leading-[1.5] text-ink-strong">
                {e.url ? <a className="underline-offset-2 hover:underline focus-visible:outline-2" href={e.url} target="_blank" rel="noreferrer">{s.text}</a> : s.text}
              </p>
              <time className="text-[12px] text-ink-faint tabular-nums" dateTime={e.t}>
                {new Date(e.t).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
              </time>
            </div>
            <span className={`shrink-0 rounded-full px-2.5 py-1 text-[13px] font-semibold tabular-nums ${tone[s.tone]}`}>{s.chip}</span>
          </li>
        );
      })}
    </ul>
  );
}
```

- [ ] **Step 4: Write `frontend/app/invest/page.tsx`**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { FramedCard, Hero, KpiRow, Nav, Section } from "@/design/components/Page";
import { BetsFeed } from "@/components/invest/BetsFeed";
import { PlanCard } from "@/components/invest/PlanCard";
import { ProfitChart } from "@/components/invest/ProfitChart";
import { StartPlan } from "@/components/invest/StartPlan";
import { getTrader, money, type InvestEvent, type PlansPayload, type Pnl } from "@/lib/invest";

const REFRESH_MS = 30_000;
const PIN_KEY = "horizon-dashboard-pin";

export default function InvestPage() {
  const [plans, setPlans] = useState<PlansPayload>();
  const [events, setEvents] = useState<InvestEvent[]>([]);
  const [pnl, setPnl] = useState<Pnl>();
  const [error, setError] = useState<string | null>(null);
  const [pin, setPin] = useState("");

  useEffect(() => {
    try { setPin(sessionStorage.getItem(PIN_KEY) ?? ""); } catch { /* storage blocked: ask again */ }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [p, e, n] = await Promise.all([
        getTrader<PlansPayload>("/api/plans"), getTrader<InvestEvent[]>("/api/orders?limit=30"), getTrader<Pnl>("/api/pnl"),
      ]);
      setPlans(p); setEvents(e); setPnl(n); setError(null);
    } catch {
      setError("Can't reach the trading server right now. Numbers below may be out of date.");
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  function savePin(v: string) {
    setPin(v);
    try { sessionStorage.setItem(PIN_KEY, v); } catch { /* keep it in memory only */ }
  }

  const all = plans?.plans ?? [];
  const invested = all.reduce((s, p) => s + p.budget, 0);
  const value = all.reduce((s, p) => s + p.value, 0);
  const cash = all.reduce((s, p) => s + p.cash, 0);
  const profit = value - invested;
  const active = all.filter((p) => p.status !== "stopped");

  return (
    <main className="mx-auto max-w-[1120px] px-4 pb-24 md:px-8">
      <Nav links={[{ label: "Model", href: "/" }, { label: "Invest", href: "/invest" }]} />
      <Hero first="Invest with the model" lead="Give it a budget. It bets only when prices look wrong after fees, spreads the money across many markets, and stops itself if things go badly." />
      {plans?.mode === "live"
        ? <p className="mt-6 inline-block rounded-full bg-down-tint px-3 py-1 text-[13px] font-semibold text-down">Real money</p>
        : plans ? <p className="mt-6 inline-block rounded-full bg-fill-soft px-3 py-1 text-[13px] font-semibold text-ink-strong">Practice mode: simulated money on live prices</p> : null}
      {error ? <p role="alert" className="mt-4 text-[15px] font-medium text-down">{error}</p> : null}

      <KpiRow items={[
        { label: "Invested", value: money(invested) },
        { label: "Now worth", value: money(value) },
        { label: "Profit", value: money(profit, true), note: invested ? `${profit >= 0 ? "+" : "−"}${Math.abs((profit / invested) * 100).toFixed(1)}%` : undefined, tone: profit > 0 ? "up" : profit < 0 ? "down" : undefined },
        { label: "Cash not yet used", value: money(cash) },
      ]} />

      <Section title="Profit so far" lead="What our real money has made, next to what the model would have made on past markets.">
        <FramedCard title="Profit in dollars">{pnl ? <ProfitChart pnl={pnl} /> : <p className="text-ink-muted">Loading…</p>}</FramedCard>
      </Section>

      <Section title="Your plans" lead="Changes need the team PIN. Looking does not.">
        <div className="grid gap-6">
          <label className="block max-w-[240px] text-[15px] font-medium text-ink-strong">Team PIN
            <input className="mt-1.5 h-12 w-full rounded-xl border border-hairline px-4 text-[18px] tracking-[0.3em] focus:outline-none focus-visible:ring-2 focus-visible:ring-ink-strong"
              type="password" inputMode="numeric" autoComplete="off" value={pin} onChange={(e) => savePin(e.target.value)} />
          </label>
          {active.map((p) => <PlanCard key={p.id} plan={p} intervalMin={plans?.interval_min ?? 10} pin={pin} onChange={refresh} />)}
          <FramedCard title="Start investing">
            <StartPlan ceiling={plans?.max_bet_ceiling ?? 25} pin={pin} onDone={refresh} />
          </FramedCard>
        </div>
      </Section>

      <Section title="Recent bets" lead="Every bet, skip and settlement, newest first.">
        <FramedCard><BetsFeed events={events} /></FramedCard>
      </Section>
    </main>
  );
}
```

- [ ] **Step 5: Add the nav link on the main page**

In `frontend/app/page.tsx`, find the `<Nav links={[...]}` call and add `{ label: "Invest", href: "/invest" }` as the last item of the `links` array.

- [ ] **Step 6: Type-check and build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: no type errors, and the build lists `/invest`

- [ ] **Step 7: Verify in the browser (paper mode)**

1. In `.env.local` (repo root), set `DASHBOARD_PIN=` to any 4–8 digits and `POLYMARKET_MAX_BET_USD=25`.
2. Start the backend: `cd backend && TRADER_ENABLED=1 uvicorn app:app --port 8000`.
3. Open `http://localhost:3000/invest` through the `frontend` dev server (`.claude/launch.json`).
4. Check:
   - The tiles show $0, and the chart shows only the dashed line.
   - Enter the PIN, start a $1000 plan, see the confirmation, then Yes: a plan card appears with "Running" and a "New plan started" feed row.
   - Pause works, then Resume, then a wrong PIN shows "Wrong PIN".
   - At 375px width, nothing scrolls sideways; Tab reaches every control and shows a focus ring.

- [ ] **Step 8: Commit**

```bash
git add frontend/components/invest frontend/app/invest/page.tsx frontend/app/page.tsx
git commit -m "invest UI: /invest page (tiles, profit chart, start/pause/stop with PIN, bets feed)"
```

---

### Task 8: Paper end-to-end, docs, hand-off, then real money

**Files:**
- Modify: `.env.example`, `backend/README.md`, `CLAUDE.md` (API contract section), `team/inbox/A.md`, `team/inbox/B.md`

- [ ] **Step 1: Paper run against live Polymarket prices**

Run from `backend/` with `POLYMARKET_LIVE=0`:

```bash
python -c "
from invest.store import Store, now_iso; from invest.broker import Broker; from invest.trader import run_once
s = Store(); p = s.new_plan(1000, 25, 100, now_iso()); run_once(s, Broker())
plan = s.plan(p['id']); print(plan['cash'], len(plan['positions']))
for e in s.events(p['id'])[:10]: print(e['kind'], e.get('reason',''), e.get('question','')[:60], e.get('cost',''))"
```

Expected: several `buy` lines across different markets, each ≤ $25 and no event over $100, with cash reduced by the sum of their costs. Skips may appear. If there are zero buys and no errors, check that `/api/live` has `BUY_*` rows with `net_edge > 0` right now and record that in the PR. It isn't a bug.

- [ ] **Step 2: Document the settings** (append to `.env.example`)

```
# Invest dashboard (backend/invest_router.py)
DASHBOARD_PIN=
# Run the 10-minute trading loop in this process (only on the always-on host, never on Vercel)
TRADER_ENABLED=0
# Cap on open stake across all plans, in USD
MAX_TOTAL_EXPOSURE_USD=200
# Where plans.json / orders.json / equity.json live (default data/raw)
INVEST_DATA_DIR=
```

Also set `POLYMARKET_MAX_BET_USD=25` in `.env.example`. In `frontend/.env.example`, add `NEXT_PUBLIC_TRADER_URL=` with the comment "always-on trader host; defaults to NEXT_PUBLIC_API_URL".

- [ ] **Step 3: Update `backend/README.md`** with a short "Invest dashboard" section covering:
- **What runs where:** Vercel serves reads only; the always-on host runs `TRADER_ENABLED=1 uvicorn app:app --host 0.0.0.0 --port 8000` with `.env.local`.
- **The three JSON files.**
- **Redemption:** in live mode, winning shares must be redeemed on polymarket.com ("Claim") before that USDC can fund new bets; the plan's cash is bookkeeping.

- [ ] **Step 4: API contract.** Add a "v1.4 additions (invest)" block to the CLAUDE.md API contract with the five endpoints and shapes from Task 5. Contract changes are Role A's call (CLAUDE.md rule 7), so this goes in the PR description for A to approve, not straight to `main`.

- [ ] **Step 5: Hand-off notes**
- Append to `team/inbox/A.md`: `- [ ] From C: PR int/invest-dashboard adds backend/invest/ + invest_router.py (real-money auto-invest, PIN-gated, loop only when TRADER_ENABLED=1). Needs your review of sizing/caps and the contract v1.4 block; Vercel stays read-only.`
- Append to `team/inbox/B.md`: `- [ ] From C: PR int/invest-dashboard adds frontend/app/invest + components/invest (uses Page/Button/chartTheme as-is). Please /design-review it.`

- [ ] **Step 6: Commit, push, open the PR**

```bash
git add .env.example frontend/.env.example backend/README.md CLAUDE.md team/inbox/A.md team/inbox/B.md
git commit -m "invest: env, README, contract v1.4 draft, inbox notes"
git push -u origin int/invest-dashboard
gh pr create --base main --title "Invest dashboard: real-money auto-invest plans + profit chart" --body-file -
```

The PR body covers: the spec link, what's tested (the pytest count and the paper-run output), the live rollout steps below, and the attribution line `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

- [ ] **Step 7: Real money, with a person watching (not automated)**

Only after A approves and merges.

1. On the always-on host, set `POLYMARKET_LIVE=1`, the wallet keys, `MAX_TOTAL_EXPOSURE_USD=50` and `TRADER_ENABLED=1`.
2. Start a **$50** plan with a $5 max bet.
3. Watch one cycle. Check that each `buy` event's `cost` and `shares` match the trade on polymarket.com. This is how we confirm that `makingAmount` / `takingAmount` parse correctly in `Broker.buy`.
4. Wait for one settlement.
5. Only then raise `MAX_TOTAL_EXPOSURE_USD` and start the $1000 plan.

---

## Self-review

- **Spec coverage:**
  - Screen tiles, chart, start card, status and feed: Tasks 6–7.
  - ¼-Kelly with the market, event, cash and ceiling caps, and opposite side never held: Task 2.
  - Re-quote, edge check, FAK capped at worst price, and minimum order: Tasks 3–4.
  - Settlement and marks at the bid: Tasks 3–4.
  - Auto-pause and the Stop semantics: Tasks 2, 4 and 5.
  - Single runner: Task 4.
  - Storage, endpoints, PIN and lockout: Tasks 1 and 5.
  - Keys and caps, hosting, and the paper → $50 → $1000 rollout: Task 8.
  - Unit tests and paper end-to-end: every task, plus Task 8.
  - UI QA: Task 7, Step 7.
- **Deviation from the spec, flagged:** the spec said `GET /api/plans` returns plans. It returns `{mode, interval_min, max_bet_ceiling, plans}` so the page can show practice vs real mode and the per-bet ceiling.
- **Known limitation, documented in Task 8:** live winnings need redeeming on Polymarket before that USDC can be reused.
