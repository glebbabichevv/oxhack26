"""Long run: the headline V3 test trades, laid out for the site's "long run" section.

Re-runs model.evaluate on data/horizons.csv (same split, policy, fees, caps as backend/results),
grabs the headline trades frame from inside evaluate (model.robustness receives exactly
with_c), applies model.exposure's 1-bankroll cap like the headline does, and writes
frontend/public/longrun.json:
  trades[]       one per test trade, in resolution order: t, per_dollar (result per $1 after fees), won, event_id, stake
  cumulative[]   running result after fees: per $1 staked (Kelly-weighted) and for $1-per-trade
  portfolios     event bootstrap (2,000 draws, seed 0) of 10 / 50 / 200 equal $1 bets
  streaks        the real longest losing streak, and how likely a 20-loss run is
Re-runnable whenever the policy changes:  cd backend && python longrun.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import model as M

HERE = Path(__file__).parent
OUT = HERE.parent / "frontend" / "public" / "longrun.json"
SIZES = (10, 50, 200)
DRAWS = 2000
STREAK = 20


def headline_trades():
    cap = {}
    orig = M.robustness

    def grab(t):
        cap["t"] = t.copy()
        return orig(t)

    M.robustness = grab
    try:
        df = M.load_horizons(HERE.parent / "data" / "horizons.csv")
        _, _, backtest = M.evaluate(df)
    finally:
        M.robustness = orig
    trades = cap["t"]
    _, capped = M.exposure(trades, trades["kelly"].to_numpy())  # open stake <= 1 bankroll, as the headline
    t = trades.assign(kelly=capped)[capped > 0].sort_values("resolved_at").reset_index(drop=True)
    return t, backtest


def longest_run(lost):
    best = cur = 0
    for x in lost:
        cur = cur + 1 if x else 0
        best = max(best, cur)
    return best


def count_runs(lost, k):
    """Distinct losing streaks of length >= k in the sequence."""
    n = cur = 0
    for x in lost:
        cur = cur + 1 if x else 0
        if cur == k:
            n += 1
    return n


def bootstrap(t, rng):
    """Portfolios of N equal $1 bets drawn by resampling whole events (legs of one event stay together)."""
    key = t[M.event_key(t)].to_numpy()
    groups = [g.to_numpy() for _, g in t.groupby(key, sort=False)["ret"]]
    out = {}
    for n in SIZES:
        totals, has_streak = np.empty(DRAWS), np.zeros(DRAWS, bool)
        for d in range(DRAWS):
            rets = []
            while len(rets) < n:
                rets.extend(groups[rng.integers(len(groups))])
            r = np.asarray(rets[:n])
            totals[d] = r.sum()
            has_streak[d] = longest_run(r <= 0) >= STREAK
        p5, p50, p95 = np.percentile(totals, [5, 50, 95])
        out[str(n)] = {"n_bets": n, "p5": round(float(p5), 2), "p50": round(float(p50), 2), "p95": round(float(p95), 2),
                       "share_up": round(float((totals > 0).mean()), 4),
                       "share_with_20_loss_streak": round(float(has_streak.mean()), 4)}
    return out


def main():
    t, backtest = headline_trades()
    ret, stake = t["ret"].to_numpy(), t["kelly"].to_numpy()
    won = ret > 0
    ts = pd.to_datetime(t["resolved_at"], utc=True)
    key = t[M.event_key(t)].astype(str).to_numpy()
    hit = float(won.mean())
    real_streak = longest_run(~won)
    boot = bootstrap(t, np.random.default_rng(0))
    p_run = (1 - hit) ** STREAK
    cum_pd = np.cumsum(stake * ret) / np.cumsum(stake)
    cum_eq = np.cumsum(ret)
    out = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
        "policy": backtest.get("policy"),
        "headline": backtest.get("headline"),
        "n_trades": int(len(t)),
        "hit_rate": round(hit, 4),
        "per_dollar": round(float((stake * ret).sum() / stake.sum()), 4),
        "per_dollar_equal": round(float(ret.mean()), 4),
        "trades": [{"t": a.isoformat(timespec="seconds"), "per_dollar": round(float(r), 4), "won": bool(w), "event_id": e,
                    "stake": round(float(s), 5)} for a, r, w, e, s in zip(ts, ret, won, key, stake)],
        # running result after fees, thinned to <= ~800 points for the chart (the last trade always kept)
        "cumulative": [{"t": ts[i].isoformat(timespec="seconds"), "per_dollar": round(float(cum_pd[i]), 4), "equal_usd": round(float(cum_eq[i]), 2)}
                       for i in sorted(set(range(0, len(t), max(1, len(t) // 800))) | {len(t) - 1})],
        "portfolios": boot,
        "streaks": {
            "longest_losing_streak": int(real_streak),
            "streak": STREAK,
            "p_given_run_all_lose": round(float(p_run), 5),
            "p_streak_in_200": boot["200"]["share_with_20_loss_streak"],
            "streaks_ge_20_in_test": int(count_runs(~won, STREAK)),
            "note": f"With a {hit:.0%} hit rate, a given run of {STREAK} bets all loses with probability (1 - {hit:.2f})^{STREAK}; "
                    "across hundreds of bets such a streak becomes likely. That is why each stake is a small slice of the "
                    "bankroll (a quarter of the Kelly stake, at most 5%).",
        },
        "caption": "Test-set trades, not a promise.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")))
    s = out["streaks"]
    print(f"trades {out['n_trades']}  hit {hit:.3f}  per $1 {out['per_dollar']:+.4f} (equal {out['per_dollar_equal']:+.4f})")
    print(f"longest losing streak {real_streak}  P(given 20 all lose) {p_run:.4f}  P(20-streak within 200) {s['p_streak_in_200']}")
    for n, b in boot.items():
        print(f"{n:>4} bets: p5 {b['p5']:+.2f}  p50 {b['p50']:+.2f}  p95 {b['p95']:+.2f}  up {b['share_up']:.0%}  20-streak {b['share_with_20_loss_streak']:.0%}")
    print(f"distinct 20+ losing streaks in the test sequence: {s['streaks_ge_20_in_test']}")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
