"""Trading rules for model v2: Polymarket taker fees, conservative edge, fractional Kelly,
one trade per market at the earliest qualifying horizon, held to resolution, and caps so the
whole book never stakes more than one starting bankroll at a time."""
import heapq

import numpy as np
import pandas as pd

from models import in_band

# docs.polymarket.com/trading/fees: fee per share = rate * p * (1 - p); makers pay nothing.
FEE_RATE = {"sports": 0.05, "crypto": 0.07, "politics": 0.04, "science_tech": 0.04, "economics": 0.05,
            "culture": 0.05, "other": 0.05, "geopolitics": 0.0}
PER_TRADE_CAP, PER_EVENT_CAP, BANKROLL_CAP = 0.05, 0.10, 1.0
EPS = 0.01


def trade_cost(p, spread, fees_on, domain, min_half=0.01):
    p = np.asarray(p, float)
    half = np.maximum(np.nan_to_num(np.asarray(spread, float), nan=0.0) / 2, min_half)
    rate = np.array([FEE_RATE.get(d, 0.05) for d in domain])
    return half + np.asarray(fees_on, bool) * rate * p * (1 - p)


def decide(p, q, lo, hi, cost, min_edge=0.0, kelly_mult=0.25):
    p = np.asarray(p, float)
    buy_yes = lo - (p + cost)
    buy_no = (p - cost) - hi
    band = in_band(p)
    action = np.where(band & (buy_yes > min_edge), "BUY_YES",
                      np.where(band & (buy_no > min_edge), "BUY_NO", "NO_TRADE"))
    qc = np.where(action == "BUY_YES", lo, np.where(action == "BUY_NO", hi, q))
    py, pn = np.clip(p + cost, EPS, 1 - EPS), np.clip(1 - p + cost, EPS, 1 - EPS)
    kelly = np.where(action == "BUY_YES", (qc - py) / (1 - py),
                     np.where(action == "BUY_NO", ((1 - qc) - pn) / (1 - pn), 0.0))
    kelly = np.clip(kelly * kelly_mult, 0, PER_TRADE_CAP)
    edge = np.where(action == "BUY_NO", buy_no, buy_yes)
    return action, kelly, edge


def payoff(action, p, cost, y):
    return np.where(action == "BUY_YES", y / np.clip(p + cost, EPS, 1) - 1,
                    np.where(action == "BUY_NO", (1 - y) / np.clip(1 - p + cost, EPS, 1) - 1, 0.0))


def earliest_trades(df, q, lo, hi, cost, min_edge, kelly_mult):
    t = df.assign(q=q, q_lo=lo, q_hi=hi, cost=cost)
    t["action"], t["kelly"], t["edge"] = decide(t["price_yes"].to_numpy(), q, lo, hi, cost, min_edge, kelly_mult)
    t = t[t["action"] != "NO_TRADE"].sort_values("horizon_hours", ascending=False)
    t = t.groupby("market_id").head(1).copy()
    t["ret"] = payoff(t["action"].to_numpy(), t["price_yes"].to_numpy(), t["cost"].to_numpy(), t["outcome"].to_numpy())
    t["entry_at"] = t["end_date"] - pd.to_timedelta(t["horizon_hours"], unit="h")
    return t


def apply_caps(trades):
    t = trades.sort_values(["entry_at", "market_id"]).copy()
    open_, used, by_event, stakes = [], 0.0, {}, []
    for r in t.itertuples():
        while open_ and open_[0][0] <= r.entry_at:
            _, stake, ev = heapq.heappop(open_)
            used -= stake
            by_event[ev] -= stake
        s = min(r.kelly, PER_EVENT_CAP - by_event.get(r.event_slug, 0.0), BANKROLL_CAP - used)
        s = max(s, 0.0)
        stakes.append(s)
        if s > 0:
            used += s
            by_event[r.event_slug] = by_event.get(r.event_slug, 0.0) + s
            heapq.heappush(open_, (r.resolved_at, s, r.event_slug))
    t["stake"] = stakes
    t["kelly"] = t["stake"]
    return t
