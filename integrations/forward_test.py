"""Forward test: freeze the model's calls on open markets now, score them after they resolve.

The backtest is out of time, but it is still history. This is the test nobody can fit after the
fact: predictions are written and committed to git *before* the outcomes exist.

  python integrations/forward_test.py snapshot   # fetch open markets ending in the next 48 h, save model calls
  python integrations/forward_test.py score      # check resolutions on Polymarket, write integrations/forward/score.json

Same model and decision rule as backend/model.py (same cutoff, same seed, same cost floor).
Scored set = markets whose *scheduled* end date has passed, so early resolutions can't select
on the outcome. Each market is scored from its earliest snapshot (the backtest's
"earliest horizon" rule).
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from common import DATA, GAMMA, ROOT, get, parse_ts

sys.path.insert(0, str(ROOT / "backend"))
import model as M  # noqa: E402

OUT = ROOT / "integrations" / "forward"


def git_head():
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def fit():
    """Rebuild exactly the model behind backend/results/live.json."""
    cutoff = json.loads((ROOT / "backend/results/backtest.json").read_text())["cutoff"]
    rng = np.random.default_rng(0)
    train, _, _ = M.split_by_time(M.load_horizons(DATA / "horizons.csv"), cutoff)
    model, selection = M.select_model(train, rng)
    return model, selection, cutoff


def snapshot(a):
    OUT.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc)
    tmp = OUT / "_live_tmp.csv"
    subprocess.run([sys.executable, str(ROOT / "integrations/fetch_live.py"), "--max-days", str(a.max_hours / 24),
                    "--min-volume", str(a.min_volume), "--out", str(tmp)], check=True)
    live = pd.read_csv(tmp)
    tmp.unlink()
    live["domain"] = live["domain"].fillna("other").str.lower()
    model, selection, cutoff = fit()
    p = live["price_yes"].to_numpy()
    q, lo, hi = model.predict(p, live["hours_to_resolution"], live["domain"])
    cost = M.trade_cost(pd.to_numeric(live["spread"], errors="coerce").to_numpy(), 0.0, 0.01)
    action, kelly, edge = M.decide(p, q, cost, lo, hi)
    rows = [dict(market_id=r.market_id, question=r.question, domain=r.domain, url=r.url, end_date=r.end_date,
                 volume_usd=r.volume_usd, spread=r.spread, price_yes=round(float(p[i]), 4),
                 hours_to_resolution=float(r.hours_to_resolution), q_yes=round(float(q[i]), 4),
                 q_low=round(float(lo[i]), 4), q_high=round(float(hi[i]), 4), cost=round(float(cost[i]), 4),
                 action=str(action[i]), kelly_fraction=round(float(kelly[i]), 4), net_edge=round(float(edge[i]), 4))
            for i, r in enumerate(live.itertuples())]
    snap = dict(taken_at=now.isoformat(timespec="seconds"), git_head=git_head(), cutoff=cutoff,
                model_selection=selection, min_volume=a.min_volume, max_hours=a.max_hours, markets=rows)
    path = OUT / f"snapshot_{now:%Y%m%dT%H%MZ}.json"
    path.write_text(json.dumps(snap, indent=1))
    n_trade = sum(r["action"] != "NO_TRADE" for r in rows)
    print(f"wrote {path.name}: {len(rows)} markets, {n_trade} trades. Commit and push it now: the commit is the timestamp.")


def resolution(market_id):
    """1 / 0 if the market resolved YES / NO, None if not resolved yet (or 50-50 / unknown)."""
    rows = get(f"{GAMMA}/markets", dict(condition_ids=market_id, closed="true")) or []  # gamma hides closed markets by default
    if not rows:
        return None
    prices = json.loads(rows[0].get("outcomePrices") or "[]")
    return {("1", "0"): 1, ("0", "1"): 0}.get(tuple(prices[:2]))


def score(a):
    now = datetime.now(timezone.utc)
    first = {}  # market_id -> (snapshot meta, row) from its earliest snapshot
    snaps = sorted(OUT.glob("snapshot_*.json"))
    for path in snaps:
        s = json.loads(path.read_text())
        for r in s["markets"]:
            first.setdefault(r["market_id"], (s["taken_at"], r))
    due = {k: v for k, v in first.items() if parse_ts(v[1]["end_date"]) <= now}
    scored = []
    for mid, (taken, r) in due.items():
        y = resolution(mid)
        if y is not None:
            scored.append(dict(r, taken_at=taken, outcome=y))
    df = pd.DataFrame(scored)
    if df.empty:
        print(f"{len(first)} markets in {len(snaps)} snapshots, {len(due)} past their end date, none resolved yet")
        return
    band = df[M.in_band(df["price_yes"])]
    y = band["outcome"].to_numpy()
    tr = df[df["action"] != "NO_TRADE"].copy()
    tr["ret"] = M.payoff(tr["action"].to_numpy(), tr["price_yes"].to_numpy(), tr["cost"].to_numpy(), tr["outcome"].to_numpy())
    tr["pnl"] = tr["ret"] * tr["kelly_fraction"]
    out = dict(
        scored_at=now.isoformat(timespec="seconds"), snapshots=[p.name for p in snaps],
        n_markets_frozen=len(first), n_due=len(due), n_resolved=len(df), n_in_band=len(band),
        brier_market=round(M.brier(band["price_yes"], y), 4) if len(band) else None,
        brier_model=round(M.brier(band["q_yes"], y), 4) if len(band) else None,
        trades=dict(n=len(tr), hit_rate=round(float((tr["ret"] > 0).mean()), 3) if len(tr) else None,
                    pnl_bankrolls=round(float(tr["pnl"].sum()), 4),
                    mean_return_per_trade=round(float(tr["ret"].mean()), 4) if len(tr) else None),
        calls=tr.sort_values("taken_at")[["question", "domain", "taken_at", "hours_to_resolution", "price_yes", "q_yes",
                                         "action", "kelly_fraction", "outcome", "ret", "pnl", "url"]].round(4).to_dict("records"),
    )
    (OUT / "score.json").write_text(json.dumps(out, indent=1, default=str))
    t = out["trades"]
    print(f"{len(first)} frozen, {len(due)} due, {len(df)} resolved ({len(band)} in 3-97c band)")
    print(f"Brier market {out['brier_market']}  model {out['brier_model']}")
    print(f"trades {t['n']}  hit {t['hit_rate']}  P&L {t['pnl_bankrolls']:+.4f} bankrolls  mean/trade {t['mean_return_per_trade']}")
    for c in out["calls"]:
        print(f"  {c['action']:8s} p={c['price_yes']:.3f} q={c['q_yes']:.3f} -> {'YES' if c['outcome'] else 'NO '}  "
              f"{c['ret']:+.2f}  {c['question'][:70]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["snapshot", "score"])
    ap.add_argument("--min-volume", type=float, default=10000)
    ap.add_argument("--max-hours", type=float, default=48)
    a = ap.parse_args()
    snapshot(a) if a.cmd == "snapshot" else score(a)
