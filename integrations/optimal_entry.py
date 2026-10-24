"""Optimal entry time: enter now, or wait for a better entry? (optimal stopping, Role C)

The decision rule in backend/model.py trades at the first horizon with an edge. But the payout per $1 depends on the
entry price, and the price moves while you wait. This answers "enter now or wait" with backward induction:

  R(p, h)  = expected return per $1 of entering now = payoff at the model's q, after spread + taker fee (0 if NO_TRADE)
  V(p, 12h) = R(p, 12h)
  V(p, h_k) = max( R(p, h_k),  E[ V(p', h_k+1) | p, h_k ] )      p' = price at the next horizon, 0 if it closed first

The transition p -> p' is empirical: from TRAIN markets only, price at h_k bucketed in logit space, all observed
next-horizon prices kept (a market that resolved before h_k+1 contributes 0: you missed it). Same model, same cost as
the backtest. Policy "stop": enter at the first horizon where R > 0 and R >= continuation value.

Result (results.json): on validation the simple rule "don't enter earlier than 24 h before the end" beats both the
current rule and optimal stopping, so it is the one chosen; on the test set it holds. The stopping model's job turned
out to be explaining *why*: waiting is worth more than a week-out edge, because the correction grows near resolution.

  python integrations/optimal_entry.py evaluate   # out-of-time: stop vs enter-at-first-edge -> integrations/entry/results.json
  python integrations/optimal_entry.py live       # open markets: ENTER_NOW / WAIT / NO_TRADE -> integrations/entry/live.json
"""
import argparse
import json
import subprocess
import sys

import numpy as np
import pandas as pd

from common import DATA, GAMMA, ROOT, get

sys.path.insert(0, str(ROOT / "backend"))
import model as M  # noqa: E402

H = [720, 168, 72, 24, 12]
ENTER_FROM = 24  # chosen on validation: see evaluate()
N_BINS = 30
GRID = np.linspace(0.005, 0.995, 397)
OUT = ROOT / "integrations" / "entry"


def fit():
    cutoff = json.loads((ROOT / "backend/results/backtest.json").read_text())["cutoff"]
    df = M.load_horizons(DATA / "horizons.csv")
    train, test, _ = M.split_by_time(df, cutoff)
    model, _ = M.select_model(train, np.random.default_rng(0))
    return df, train, test, model, cutoff


def wide(df):
    """One row per market: price at each horizon (NaN = no row: closed already, or not listed yet)."""
    w = df.pivot_table(index="market_id", columns="horizon_hours", values="price_yes", aggfunc="first")
    meta = df.groupby("market_id").agg(outcome=("outcome", "first"), domain=("domain", "first"),
                                       event=(M.event_key(df), "first"), fees_enabled=("fees_enabled", "first"),
                                       fee_rate=("fee_rate", "first"), fee_exponent=("fee_exponent", "first"))
    return w.reindex(columns=H).join(meta)


def expected_return(model, p, h, fee_rate, fee_exp, spread=None):
    """R(p, h): expected return per $1 of trading now under the model's decide() rule, its action and Kelly stake."""
    p = np.asarray(p, float)
    n = len(p)
    q, lo, hi = model.predict(p, np.full(n, float(h)) if np.isscalar(h) else h, np.full(n, "other"))
    fee = np.asarray(fee_rate, float) * (p * (1 - p)) ** np.asarray(fee_exp, float)
    cost = M.trade_cost(np.full(n, np.nan) if spread is None else np.asarray(spread, float), fee, 0.01)
    action, kelly, _ = M.decide(p, q, cost, lo, hi)
    return M.payoff(action, p, cost, q), action, kelly, cost


class Stopper:
    """Continuation values from TRAIN transitions, per fee schedule."""

    def __init__(self, model, train_wide):
        self.model = model
        self.edges, self.next = [], []
        for k in range(len(H) - 1):
            x = train_wide[train_wide[H[k]].notna()]
            lp = M.logit(x[H[k]].to_numpy())
            edges = np.quantile(lp, np.linspace(0, 1, N_BINS + 1)[1:-1])
            b = np.searchsorted(edges, lp)
            nxt = x[H[k + 1]].to_numpy()
            self.edges.append(edges)
            self.next.append([nxt[b == i] for i in range(N_BINS)])
        self.cache = {}

    def bin(self, k, p):
        return np.searchsorted(self.edges[k], M.logit(np.asarray(p, float)))

    def values(self, fee_rate, fee_exp):
        """C[k][bin] = E[V(p', h_k+1)] for this fee schedule (backward induction on GRID)."""
        key = (round(float(fee_rate), 4), float(fee_exp))
        if key in self.cache:
            return self.cache[key]
        V = np.maximum(expected_return(self.model, GRID, H[-1], key[0], key[1])[0], 0)
        C = [None] * (len(H) - 1)
        for k in range(len(H) - 2, -1, -1):
            C[k] = np.array([np.nan_to_num(np.interp(s, GRID, V), nan=0.0).mean() if len(s) else 0.0
                             for s in self.next[k]])  # NaN next price = closed first: value 0
            R = np.maximum(expected_return(self.model, GRID, H[k], key[0], key[1])[0], 0)
            V = np.maximum(R, C[k][self.bin(k, GRID)])
        self.cache[key] = C
        return C

    def wait_value(self, k, p, fee_rate, fee_exp):
        if k >= len(H) - 1:
            return np.zeros(len(np.atleast_1d(p)))
        return self.values(fee_rate, fee_exp)[k][self.bin(k, p)]


def fee_cols(w):
    on = w["fees_enabled"].astype(str).str.lower().eq("true")
    return np.where(on, w["fee_rate"].fillna(0), 0.0), w["fee_exponent"].fillna(1).to_numpy()


def run(test_wide, model, stopper, policy):
    """One trade per market. policy 'first': first horizon with an edge (backtest rule). 'stop': optimal stopping."""
    rate, exp = fee_cols(test_wide)
    rows = []
    for i, (mid, r) in enumerate(test_wide.iterrows()):
        for k, h in enumerate(H):
            p = r[h]
            if np.isnan(p):
                continue
            R, action, kelly, cost = expected_return(model, [p], h, [rate[i]], [exp[i]])
            if action[0] == "NO_TRADE":
                continue
            if policy == "stop" and stopper.wait_value(k, [p], rate[i], exp[i])[0] > R[0]:
                continue  # waiting is worth more: skip this horizon
            ret = M.payoff(action, np.array([p]), cost, np.array([r["outcome"]]))[0]
            rows.append(dict(market_id=mid, event=r["event"], domain=r["domain"], horizon=h, price=p,
                             action=action[0], kelly=kelly[0], exp_ret=R[0], ret=ret))
            break
    t = pd.DataFrame(rows)
    t["pnl"] = t["kelly"] * t["ret"]
    return t


def summary(t):
    return dict(n_trades=len(t), pnl_bankrolls=round(float(t["pnl"].sum()), 4),
                return_per_dollar_staked=round(float(t["pnl"].sum() / t["kelly"].sum()), 4),
                mean_return_per_trade=round(float(t["ret"].mean()), 4), hit_rate=round(float((t["ret"] > 0).mean()), 4),
                trades_by_horizon={int(h): int(n) for h, n in t["horizon"].value_counts().sort_index(ascending=False).items()})


def paired_ci(a, b, key, n=2000, seed=1):
    """90% CI of (stop - first) P&L, resampling whole events."""
    pa = a.groupby("event")[key].sum()
    pb = b.groupby("event")[key].sum()
    d = pb.reindex(pa.index.union(pb.index), fill_value=0) - pa.reindex(pa.index.union(pb.index), fill_value=0)
    rng = np.random.default_rng(seed)
    v = d.to_numpy()
    sums = np.array([v[rng.integers(0, len(v), len(v))].sum() for _ in range(n)])
    return round(float(v.sum()), 4), [round(float(x), 4) for x in np.percentile(sums, [5, 95])]


def only_from(w, max_h):
    """The same markets, but prices before max_h hours out are hidden: 'don't enter earlier than max_h'."""
    w = w.copy()
    for h in H:
        if h > max_h:
            w[h] = np.nan
    return w


RULES = {  # name -> (how to transform the market table, policy)
    "first edge (current)": (lambda w: w, "first"),
    "optimal stopping": (lambda w: w, "stop"),
    "only from 72h": (lambda w: only_from(w, 72), "first"),
    "only from 24h": (lambda w: only_from(w, 24), "first"),
    "only at 12h": (lambda w: only_from(w, 12), "first"),
}


def capped(t, meta):
    """Same trades with total open stake capped at 1 bankroll (backend/model.py exposure())."""
    # Sorted by resolution time like backend run_policy(): the cap is order-sensitive among same-time entries.
    x = t.join(meta, on="market_id").rename(columns={"horizon": "horizon_hours"}).sort_values(["resolved_at", "market_id"])
    peak, stake = M.exposure(x, x["kelly"].to_numpy())
    x = x.assign(kelly=stake, pnl=stake * x["ret"])
    return x[stake > 0], peak


def evaluate(a):
    df, train, test, model, cutoff = fit()
    # 1) Choose the rule on validation (last 20% of train by resolution time, select_model's split): test untouched.
    order = train.groupby("market_id")["resolved_at"].first().sort_values()
    val_ids = set(order.index[int(len(order) * 0.8):])
    fitp, val = train[~train.market_id.isin(val_ids)], train[train.market_id.isin(val_ids)]
    vmodel = M.Calibrator(["other"]).fit(fitp, np.random.default_rng(0))
    vstop, vw = Stopper(vmodel, wide(fitp)), wide(val)
    vres = {name: run(f(vw), vmodel, vstop, pol) for name, (f, pol) in RULES.items()}
    vbase = vres["first edge (current)"]
    validation = {name: dict(summary(t), gain_vs_current=paired_ci(vbase, t, "pnl")) for name, t in vres.items()}
    # Chosen = largest validation gain whose 90% CI clears zero; else keep the current rule.
    ok = {n: v["gain_vs_current"][0] for n, v in validation.items() if v["gain_vs_current"][1][0] > 0}
    chosen = max(ok, key=ok.get) if ok else "first edge (current)"
    # 2) Test, once, for every rule (all reported; only `chosen` was picked in advance).
    stopper, tw = Stopper(model, wide(train)), wide(test)
    meta = df.groupby("market_id").agg(end_date=("end_date", "first"), resolved_at=("resolved_at", "first"))
    tres = {name: run(f(tw), model, stopper, pol) for name, (f, pol) in RULES.items()}
    tbase = tres["first edge (current)"]
    cbase, _ = capped(tbase, meta)
    test_out = {}
    for name, tt in tres.items():
        ct, peak = capped(tt, meta)
        test_out[name] = dict(summary(tt), gain_vs_current=paired_ci(tbase, tt, "pnl"), peak_open_stake=round(peak, 3),
                              capped_1_bankroll=dict(n_trades=len(ct), pnl_bankrolls=round(float(ct["pnl"].sum()), 4),
                                                     gain_vs_current=paired_ci(cbase, ct, "pnl")))
    out = dict(cutoff=cutoff, n_validation_markets=len(vw), n_test_markets=len(tw), chosen_on_validation=chosen,
               validation=validation, test=test_out, method=__doc__.split(chr(10) * 2)[1])
    OUT.mkdir(exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(out, indent=1))
    for part, res in (("VALIDATION", validation), ("TEST", test_out)):
        print(part)
        for name, s in res.items():
            g = s["gain_vs_current"]
            c = s.get("capped_1_bankroll")
            print(f"  {name:22s} n={s['n_trades']:5d} pnl={s['pnl_bankrolls']:+.3f} per$={s['return_per_dollar_staked']:+.4f}"
                  f"  gain {g[0]:+.3f} CI {g[1]}" + (f"  | capped pnl {c['pnl_bankrolls']:+.3f} gain {c['gain_vs_current'][0]:+.3f} "
                                                      f"CI {c['gain_vs_current'][1]}" if c else ""))
    print("chosen on validation:", chosen)


def live(a):
    _, train, _, model, _ = fit()
    stopper = Stopper(model, wide(train))
    tmp = OUT / "_live.csv"
    OUT.mkdir(exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "integrations/fetch_live.py"), "--out", str(tmp)], check=True)
    lv = pd.read_csv(tmp)
    tmp.unlink()
    fees = {}
    ids = lv["market_id"].tolist()
    for i in range(0, len(ids), 100):
        for m in get(f"{GAMMA}/markets", [("limit", 100)] + [("condition_ids", c) for c in ids[i:i + 100]]) or []:
            fs = m.get("feeSchedule") or {}
            on = bool(m.get("feesEnabled")) and bool(fs)
            fees[m["conditionId"]] = (float(fs.get("rate") or 0) if on else 0.0, float(fs.get("exponent") or 1))
    rate = lv["market_id"].map(lambda m: fees.get(m, (0.0, 1.0))[0]).to_numpy()
    exp = lv["market_id"].map(lambda m: fees.get(m, (0.0, 1.0))[1]).to_numpy()
    h = lv["hours_to_resolution"].to_numpy()
    p = lv["price_yes"].to_numpy()
    R, action, kelly, _ = expected_return(model, p, h, rate, exp, lv["spread"].to_numpy())
    # Nearest horizon on the training grid (log scale); the next grid horizon is the "wait until" point.
    k = np.abs(np.log(np.clip(h, 1, None))[:, None] - np.log(H)[None, :]).argmin(axis=1)
    wait = np.array([stopper.wait_value(k[i], [p[i]], rate[i], exp[i])[0] for i in range(len(p))])
    rows = []
    for i, r in enumerate(lv.itertuples()):
        # Rule chosen on validation (results.json): don't enter earlier than ENTER_FROM hours before the scheduled end.
        if h[i] > ENTER_FROM:
            rec, until = "WAIT", ENTER_FROM
        elif action[i] != "NO_TRADE":
            rec, until = "ENTER_NOW", None
        else:
            rec, until = "NO_TRADE", None
        rows.append(dict(market_id=r.market_id, question=r.question, domain=r.domain, url=r.url, price_yes=p[i],
                         hours_to_resolution=h[i], action_now=str(action[i]), expected_return_now=round(float(R[i]), 4),
                         stopping_value_if_wait=round(float(wait[i]), 4), recommendation=rec,
                         check_back_in_hours=round(float(h[i] - until), 1) if until else None,
                         kelly_now=round(float(kelly[i]), 4)))
    out = pd.DataFrame(rows)
    (OUT / "live.json").write_text(json.dumps(rows, indent=1, default=float))
    print(out["recommendation"].value_counts().to_string())
    print(out[out.recommendation != "NO_TRADE"].sort_values("hours_to_resolution")
          [["question", "price_yes", "hours_to_resolution", "recommendation", "expected_return_now",
            "check_back_in_hours"]].head(12).to_string())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["evaluate", "live"])
    a = ap.parse_args()
    evaluate(a) if a.cmd == "evaluate" else live(a)
