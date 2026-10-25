"""Horizon autotrader: keeps learning from newly resolved markets and bets a fixed bankroll on its own.

Run from the repo root:
  python integrations/autotrader.py --bankroll 1000            # loop forever, one cycle every 30 min
  python integrations/autotrader.py --bankroll 1000 --once     # one cycle, then exit
  python integrations/autotrader.py --status                   # bankroll, open bets, track record

Paper by default (simulated fills against the live order book, see polymarket_trading.py). Real
orders only with POLYMARKET_LIVE=1 in .env.local, and each order is still capped at
POLYMARKET_MAX_BET_USD.

Each cycle:
1. Learn (every --retrain-hours): fetch markets that resolved since the newest row we have, score
   the current model on them *before* it sees them (honest forward test, logged to the state file),
   then refit on everything. backend/model.py's select_model picks market / simple / full on a
   time-ordered validation slice, so a refit that stops beating the market falls back to "no trade".
2. Settle: bets on markets that have resolved are paid out into cash.
3. Trade: fetch open markets, run the model's decision rule (edge must survive cost and the
   model's own 10-90% interval), only 12h-7d from resolution (where the backtest made money), size by quarter Kelly on current equity, and buy with a limit
   price at the model's conservative fair value, so a fill never has negative expected edge.
State lives in data/raw/autotrader_state.json; learned rows in data/raw/horizons_learned.csv.
"""
import argparse
import json
import pickle
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

import fetch_horizons
import mcp_polymarket as pm
import polymarket_trading as trading
from common import DATA, RAW, ROOT

sys.path.insert(0, str(ROOT / "backend"))
import model as hz  # noqa: E402  (Role A's model, used read-only)

STATE = RAW / "autotrader_state.json"
MODEL = RAW / "autotrader_model.pkl"  # pickle written only by this script, in gitignored data/raw
LEARNED = RAW / "horizons_learned.csv"
LIVE = RAW / "autotrader_live.csv"
MIN_ORDER_USD = 1.0
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # market names are not cp1252


def now():
    return datetime.now(timezone.utc)


def log(msg):
    print(f"[{now():%H:%M:%S}] {msg}", flush=True)


def load_state(bankroll):
    if STATE.exists():
        return json.loads(STATE.read_text())
    return dict(bankroll=bankroll, mode=trading.mode(), started_at=now().isoformat(timespec="seconds"),
                last_retrain=None, retrains=[], bets=[])


def save_state(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1, default=str))


# ---------- learn ----------

def all_rows():
    df = hz.load_horizons(DATA / "horizons.csv")
    if LEARNED.exists():
        df = pd.concat([df, hz.load_horizons(LEARNED)], ignore_index=True)
    return df.drop_duplicates(["market_id", "horizon_hours"], keep="last").reset_index(drop=True)


def fetch_resolved(since, min_volume):
    """Rows for markets whose scheduled end falls in [since, now): same rules as fetch_horizons.py."""
    fetch_horizons.HIST.mkdir(parents=True, exist_ok=True)
    listed = [m for m in fetch_horizons.list_markets(since, now(), min_volume) if fetch_horizons.is_yes_no(m)]
    with ThreadPoolExecutor(8) as pool:
        chunks = list(pool.map(lambda m: _safe_rows(m), listed))
    return pd.DataFrame([r for c in chunks for r in c])


def _safe_rows(m):
    try:
        return fetch_horizons.rows_for(m)
    except Exception as e:  # one bad market must not stop the loop
        log(f"  skip {m.get('id')}: {e}")
        return []


def forward_score(model, new):
    """Log loss / Brier of the model vs the market on markets it has never seen."""
    new = new[hz.in_band(new["price_yes"])]
    if new.empty:
        return None
    q, _, _ = model.predict(new["price_yes"], new["horizon_hours"], new["domain"])
    y = new["outcome"].to_numpy()
    return dict(n_rows=int(len(new)), n_markets=int(new["market_id"].nunique()),
                logloss_market=round(hz.log_loss(new["price_yes"], y), 4), logloss_model=round(hz.log_loss(q, y), 4),
                brier_market=round(hz.brier(new["price_yes"], y), 4), brier_model=round(hz.brier(q, y), 4))


def retrain(s, a, rng):
    df = all_rows()
    model = pickle.loads(MODEL.read_bytes()) if MODEL.exists() else None
    since = df["resolved_at"].max() - timedelta(days=2)  # overlap: late-closing markets
    log(f"learning: fetching markets resolved since {since:%Y-%m-%d %H:%M}")
    new = fetch_resolved(since.to_pydatetime(), a.min_volume)
    if not new.empty:
        new = _normalise(new)
        new = new[~new.set_index(["market_id", "horizon_hours"]).index.isin(
            df.set_index(["market_id", "horizon_hours"]).index)]
    entry = dict(at=now().isoformat(timespec="seconds"), new_markets=int(new["market_id"].nunique()) if len(new) else 0)
    if model is not None and len(new):
        entry["forward"] = forward_score(model, new)
    if len(new):
        old = pd.read_csv(LEARNED) if LEARNED.exists() else pd.DataFrame()
        pd.concat([old, new.assign(resolved_at=new["resolved_at"].map(lambda t: t.isoformat()))],
                  ignore_index=True).to_csv(LEARNED, index=False)
        df = all_rows()
    model, selection = hz.select_model(df, rng)
    MODEL.write_bytes(pickle.dumps(model))
    entry.update(train_markets=int(df["market_id"].nunique()), selection=selection)
    s["retrains"].append(entry)
    s["last_retrain"] = entry["at"]
    f = entry.get("forward")
    log(f"learned {entry['new_markets']} new markets, model={selection['chosen']}, trained on {entry['train_markets']}"
        + (f"; forward test on unseen: logloss model {f['logloss_model']} vs market {f['logloss_market']}" if f else ""))
    return model


def _normalise(new):
    new = new.copy()
    new["resolved_at"] = pd.to_datetime(new["resolved_at"], utc=True, format="ISO8601")
    new["domain"] = new["domain"].fillna("other").str.lower()
    new["spread"] = pd.to_numeric(new.get("spread"), errors="coerce")
    return new[new["outcome"].isin([0, 1])]


# ---------- bankroll ----------

def settle(s):
    for b in s["bets"]:
        if b.get("status") != "open":
            continue
        try:
            m = pm.get_market(b["market_id"])
        except Exception as e:
            log(f"  could not check {b['market_id'][:10]}: {e}")
            continue
        if m["closed"]:
            won = m["outcomes"].get("Yes" if b["side"] == "YES" else "No", 0)
            b.update(status="settled", payout_usd=round(b["shares"] * won, 4), settled_at=now().isoformat(timespec="seconds"))
            b["pnl_usd"] = round(b["payout_usd"] - b["cost_usd"], 4)
            log(f"settled {b['side']} '{b['question'][:60]}': {'WON' if won else 'lost'} {b['pnl_usd']:+.2f}")


def books(s):
    spent = sum(b["cost_usd"] for b in s["bets"])
    paid = sum(b.get("payout_usd", 0) for b in s["bets"])
    open_cost = sum(b["cost_usd"] for b in s["bets"] if b["status"] == "open")
    cash = s["bankroll"] - spent + paid
    return dict(cash=round(cash, 2), open_cost=round(open_cost, 2), equity=round(cash + open_cost, 2),
                realised_pnl=round(sum(b.get("pnl_usd", 0) for b in s["bets"]), 2),
                n_open=sum(b["status"] == "open" for b in s["bets"]),
                n_settled=sum(b["status"] == "settled" for b in s["bets"]),
                n_won=sum(b.get("pnl_usd", 0) > 0 for b in s["bets"] if b["status"] == "settled"))


# ---------- trade ----------

def trade(s, model, a):
    subprocess.run([sys.executable, str(ROOT / "integrations" / "fetch_live.py"), "--min-volume", str(a.min_volume),
                    "--out", str(LIVE)], check=True, capture_output=True)
    live = pd.read_csv(LIVE)
    picks = [x for x in hz.live_report(model, live, a.fee, a.min_half_spread, n_trades=10_000, n_no_trade=0)
             if x["action"] != "NO_TRADE" and a.min_hours <= x["hours_to_resolution"] <= a.max_hours]
    # Polymarket lists some questions twice (separate markets, same event): treat them as one.
    held = {k for b in s["bets"] if b["status"] == "open" for k in (b["market_id"], b["question"])}
    bk = books(s)
    log(f"{len(live)} open markets, {len(picks)} with edge after costs; equity ${bk['equity']}, cash ${bk['cash']}")
    for x in sorted(picks, key=lambda x: -x["net_edge"]):
        if x["market_id"] in held or x["question"] in held:
            continue
        bk = books(s)
        room = a.max_exposure * bk["equity"] - bk["open_cost"]
        stake = min(x["kelly_fraction"] * bk["equity"], bk["cash"], room)
        if trading.LIVE:
            stake = min(stake, trading.MAX_BET_USD)
        if stake < MIN_ORDER_USD:
            continue
        side = "YES" if x["action"] == "BUY_YES" else "NO"
        # Never pay more per share than the model's conservative fair value minus a small buffer.
        fair = x["q_low"] if side == "YES" else 1 - x["q_high"]
        limit = round(fair - a.min_edge, 3)
        try:
            r = trading.place_bet(pm.get_market(x["market_id"]), side, round(stake, 2), limit_price=limit,
                                  confirm=True, note=f"auto: q={x['q_yes']} edge={x['net_edge']}")
        except ValueError as e:
            log(f"  skip '{x['question'][:50]}': {e}")
            continue
        cost = r.get("cost_usd", r.get("fillable_usd"))
        s["bets"].append(dict(placed_at=now().isoformat(timespec="seconds"), market_id=x["market_id"],
                              question=x["question"], domain=x["domain"], side=side, cost_usd=cost,
                              shares=r["shares"], avg_price=r["avg_price"], market_price=x["price_yes"],
                              q_yes=x["q_yes"], net_edge=x["net_edge"], hours_to_resolution=x["hours_to_resolution"],
                              mode=trading.mode(), status="open", url=x["url"], order=r.get("order")))
        held |= {x["market_id"], x["question"]}
        save_state(s)
        log(f"BET {side} ${cost:.2f} @ {r['avg_price']} on '{x['question'][:60]}' (model {x['q_yes']:.0%} vs market {x['price_yes']:.0%})")


# ---------- main ----------

def status(s):
    bk = books(s)
    print(json.dumps(dict(mode=s["mode"], bankroll=s["bankroll"], started_at=s["started_at"], **bk,
                          last_retrain=s["last_retrain"], retrains=s["retrains"][-3:],
                          open_bets=[{k: b[k] for k in ("side", "cost_usd", "avg_price", "q_yes", "question")}
                                     for b in s["bets"] if b["status"] == "open"]), indent=1))


def cycle(s, a, rng):
    due = s["last_retrain"] is None or not MODEL.exists() or \
        now() - datetime.fromisoformat(s["last_retrain"]) > timedelta(hours=a.retrain_hours)
    model = retrain(s, a, rng) if due else pickle.loads(MODEL.read_bytes())
    save_state(s)
    settle(s)
    save_state(s)
    trade(s, model, a)
    save_state(s)
    bk = books(s)
    log(f"cycle done: equity ${bk['equity']} ({bk['equity'] - s['bankroll']:+.2f}), {bk['n_open']} open, "
        f"{bk['n_won']}/{bk['n_settled']} settled bets won")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bankroll", type=float, default=1000)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--every-minutes", type=float, default=30)
    ap.add_argument("--retrain-hours", type=float, default=24)
    ap.add_argument("--max-exposure", type=float, default=0.5, help="max share of equity in open bets")
    ap.add_argument("--min-edge", type=float, default=0.005, help="extra edge per share required at fill")
    ap.add_argument("--min-hours", type=float, default=12, help="skip markets closer than this to resolution")
    # The out-of-time backtest found the edge at 1-7 days and none at 30 days (backend/results/backtest.json).
    ap.add_argument("--max-hours", type=float, default=168, help="skip markets further than this from resolution")
    ap.add_argument("--min-volume", type=float, default=50000)
    ap.add_argument("--fee", type=float, default=0.0)
    ap.add_argument("--min-half-spread", type=float, default=0.01)
    a = ap.parse_args()
    s = load_state(a.bankroll)
    if a.status:
        return status(s)
    if s["mode"] != trading.mode():
        sys.exit(f"state file is {s['mode']} but trading mode is {trading.mode()}: move {STATE} aside first")
    rng = np.random.default_rng(0)
    log(f"autotrader {trading.mode().upper()} mode, bankroll ${s['bankroll']}")
    while True:
        try:
            cycle(s, a, rng)
        except Exception as e:  # keep the loop alive through API hiccups
            log(f"cycle failed: {e!r}")
        if a.once:
            break
        time.sleep(a.every_minutes * 60)


if __name__ == "__main__":
    main()
