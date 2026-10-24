"""Exchange-implied probability for Polymarket crypto threshold markets.

Polymarket lists thousands of "Will Bitcoin be above $K on <date>?", "Will Bitcoin reach $K in <period>?",
"Will Solana dip to $K ...?" and "between $K1 and $K2" markets. Each one is a textbook option payoff on the
underlying coin, so the exchange already prices it: spot S, volatility sigma and time to expiry T give

  above K at T     digital call      P = N(d2),  d2 = (ln(S/K) - sigma^2 T/2) / (sigma sqrt T)
  between K1, K2   digital spread    P = N(d2(K1)) - N(d2(K2))
  reach K (> S)    one-touch         P(max S_t >= K), reflection principle for log-Brownian motion
  dip to K (< S)   one-touch, down   P(min S_t <= K), same by symmetry

with zero drift (hours to weeks, drift is noise next to sigma). Time enters as sqrt(T): the same 5% move is
likely a month out and nearly impossible an hour out, which is the TIME theme in one formula.

Sigma is realised volatility from Binance hourly candles strictly before the price timestamp (no leakage),
spot is the open of the hour containing the timestamp. One scale factor on sigma (fat tails, vol regime) is
fitted on the train period only.

Out-of-time check against the market price itself (same split as backend/model.py: events ending on or after
the cutoff are test), Brier and log loss, then a trade rule with Polymarket's crypto taker fee
(0.07 * p * (1 - p) per share, docs.polymarket.com/trading/fees) on top of the half-spread.

  python integrations/crypto_implied.py fetch     # Binance hourly candles -> data/raw/klines_<SYM>.csv (cached)
  python integrations/crypto_implied.py evaluate  # -> integrations/crypto/results.json + printed summary
"""
import json
import math
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = Path(__file__).resolve().parent / "crypto"
SYMBOLS = {"bitcoin": "BTCUSDT", "btc": "BTCUSDT", "ethereum": "ETHUSDT", "eth": "ETHUSDT",
           "solana": "SOLUSDT", "sol": "SOLUSDT", "xrp": "XRPUSDT"}
CUTOFF = "2026-05-18"          # backend/model.py: events ending on/after this date are test
VOL_HOURS = 24 * 14            # realised-vol window
FEE_RATE = 0.07                # Polymarket crypto taker fee rate
HOURS_PER_YEAR = 24 * 365


# ---------- data ----------

def fetch(start="2023-11-01"):
    RAW.mkdir(parents=True, exist_ok=True)
    for sym in sorted(set(SYMBOLS.values())):
        path = RAW / f"klines_{sym}.csv"
        t = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
        rows = []
        if path.exists():
            old = pd.read_csv(path)
            rows = old.values.tolist()
            t = int(old.open_ms.max()) + 3_600_000
        now = int(time.time() * 1000)
        while t < now:
            r = requests.get("https://data-api.binance.vision/api/v3/klines",
                             params={"symbol": sym, "interval": "1h", "startTime": t, "limit": 1000}, timeout=30)
            r.raise_for_status()
            k = r.json()
            if not k:
                break
            rows += [[x[0], float(x[1]), float(x[2]), float(x[3]), float(x[4])] for x in k]
            t = k[-1][0] + 3_600_000
        df = pd.DataFrame(rows, columns=["open_ms", "open", "high", "low", "close"]).drop_duplicates("open_ms")
        df.sort_values("open_ms").to_csv(path, index=False)
        print(sym, len(df), "hours")


def load_klines():
    out = {}
    for sym in sorted(set(SYMBOLS.values())):
        df = pd.read_csv(RAW / f"klines_{sym}.csv").sort_values("open_ms").reset_index(drop=True)
        lr = np.log(df.close).diff()
        # realised vol per sqrt(hour) from the VOL_HOURS candles that closed before this candle opened
        df["vol_h"] = lr.rolling(VOL_HOURS, min_periods=VOL_HOURS // 2).std().shift(1)
        out[sym] = df.set_index("open_ms")
    return out


# ---------- question parsing ----------

NUM = r"\$?\s?([\d][\d,]*(?:\.\d+)?)\s?(k|K)?"


def _num(s, k):
    v = float(s.replace(",", ""))
    return v * 1000 if k else v


def parse(question):
    q = question.replace("–", "-")
    m = re.search(r"(bitcoin|ethereum|solana|xrp|\bbtc\b|\beth\b|\bsol\b)", q, re.I)
    if not m:
        return None
    sym = SYMBOLS[m.group(1).lower()]
    if mm := re.search(r"between " + NUM + r" and " + NUM, q, re.I):
        return sym, "between", _num(mm.group(1), mm.group(2)), _num(mm.group(3), mm.group(4))
    if mm := re.search(r"(above|greater than|over) " + NUM, q, re.I):
        return sym, "above", _num(mm.group(2), mm.group(3)), None
    if mm := re.search(r"(below|less than|under) " + NUM, q, re.I):
        return sym, "below", _num(mm.group(2), mm.group(3)), None
    if mm := re.search(r"(reach|hit) " + NUM, q, re.I):
        return sym, "reach", _num(mm.group(2), mm.group(3)), None
    if mm := re.search(r"dip to " + NUM, q, re.I):
        return sym, "dip", _num(mm.group(1), mm.group(2)), None
    return None


# ---------- pricing ----------

def p_above(S, K, sig, T):
    s = sig * math.sqrt(T)
    return float(norm.cdf((math.log(S / K) - s * s / 2) / s))


def p_touch(S, K, sig, T):
    """P(path of a driftless-in-price log-Brownian motion touches K before T), K above or below S."""
    s = sig * math.sqrt(T)
    nu = -sig * sig / 2                       # log drift so that E[S_T] = S
    b = math.log(K / S)
    if b > 0:                                 # up barrier: P(max X >= b)
        return float(norm.cdf((-b + nu * T) / s) + math.exp(2 * nu * b / sig ** 2) * norm.cdf((-b - nu * T) / s))
    b = -b                                    # down barrier: P(min X <= -b) = P(max(-X) >= b), drift -nu
    return float(norm.cdf((-b - nu * T) / s) + math.exp(-2 * nu * b / sig ** 2) * norm.cdf((-b + nu * T) / s))


def implied(kind, S, K1, K2, sig, T):
    if kind == "above":
        return p_above(S, K1, sig, T)
    if kind == "below":
        return 1 - p_above(S, K1, sig, T)
    if kind == "between":
        return p_above(S, K1, sig, T) - p_above(S, K2, sig, T)
    return p_touch(S, K1, sig, T)            # reach / dip


# ---------- evaluation ----------

def build_rows(kl):
    d = pd.read_csv(ROOT / "data" / "horizons.csv")
    d = d[d.domain == "crypto"].copy()
    parsed = d.question.map(parse)
    d = d[parsed.notna()].copy()
    d[["sym", "kind", "k1", "k2"]] = pd.DataFrame(parsed[parsed.notna()].tolist(), index=d.index)
    ts = pd.to_datetime(d.price_ts, utc=True)
    end = pd.to_datetime(d.end_date, utc=True)
    d["T_h"] = (end - ts).dt.total_seconds() / 3600
    hour = (ts.dt.floor("h") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(milliseconds=1)
    S, V = [], []
    for sym, h in zip(d.sym, hour):
        row = kl[sym].loc[h] if h in kl[sym].index else None
        S.append(np.nan if row is None else row.open)
        V.append(np.nan if row is None else row.vol_h)
    d["S"], d["vol_h"] = S, V
    d = d[(d.T_h > 0.5) & d.S.notna() & d.vol_h.notna() & d.price_yes.between(0.03, 0.97)]
    # a touch market whose barrier is already on the wrong side is mis-parsed or already decided
    bad = ((d.kind == "reach") & (d.k1 <= d.S)) | ((d.kind == "dip") & (d.k1 >= d.S))
    d = d[~bad].copy()
    d["test"] = end.loc[d.index] >= pd.Timestamp(CUTOFF, tz="UTC")
    return d


def score(d, scale):
    return np.array([implied(k, s, a, b, v * scale, t) for k, s, a, b, v, t in
                     zip(d.kind, d.S, d.k1, d.k2, d.vol_h, d.T_h)]).clip(0.001, 0.999)


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def logloss(p, y):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def fit_blend(pe, pm, y):
    """logit q = a + b*logit(exchange) + c*logit(market), fitted by Newton's method on train."""
    X = np.column_stack([np.ones_like(pe), logit(pe), logit(pm)])
    w = np.array([0.0, 0.5, 0.5])
    for _ in range(50):
        q = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (q - y)
        H = X.T @ (X * (q * (1 - q))[:, None]) + 1e-6 * np.eye(3)
        w -= np.linalg.solve(H, g)
    return w


def blend(w, pe, pm):
    return 1 / (1 + np.exp(-(w[0] + w[1] * logit(pe) + w[2] * logit(pm))))


def trade(d, q, label):
    """One trade per market at its earliest horizon with positive net edge, held to resolution."""
    d = d.assign(q=q)
    spread = d.spread.fillna(0.02)
    d["cost_yes"] = np.maximum(spread / 2, 0.01) + FEE_RATE * d.price_yes * (1 - d.price_yes)
    d["edge_yes"] = d.q - (d.price_yes + d.cost_yes)
    d["edge_no"] = (1 - d.q) - (1 - d.price_yes + d.cost_yes)
    d = d.sort_values("horizon_hours", ascending=False)
    picks = []
    for mid, g in d.groupby("market_id", sort=False):
        for _, r in g.iterrows():
            if r.edge_yes > 0:
                picks.append((r.event_slug, r.horizon_hours, r.outcome / (r.price_yes + r.cost_yes) - 1)); break
            if r.edge_no > 0:
                picks.append((r.event_slug, r.horizon_hours, (1 - r.outcome) / (1 - r.price_yes + r.cost_yes) - 1)); break
    if not picks:
        return {"label": label, "n_trades": 0}
    p = pd.DataFrame(picks, columns=["event", "h", "ret"])
    # event bootstrap: markets of one event (strike ladder) move together
    ev = p.groupby("event").ret.agg(["sum", "count"])
    rng = np.random.default_rng(0)
    boots = []
    for _ in range(2000):
        s = ev.sample(len(ev), replace=True, random_state=rng.integers(1 << 31))
        boots.append(s["sum"].sum() / s["count"].sum())
    lo, hi = np.percentile(boots, [5, 95])
    return {"label": label, "n_trades": int(len(p)), "n_events": int(len(ev)),
            "mean_return_per_dollar": round(float(p.ret.mean()), 4),
            "ci90": [round(float(lo), 4), round(float(hi), 4)],
            "hit_rate": round(float((p.ret > 0).mean()), 4)}


def evaluate():
    kl = load_klines()
    d = build_rows(kl)
    tr, te = d[~d.test], d[d.test]
    y_tr, y_te = tr.outcome.values.astype(float), te.outcome.values.astype(float)
    # one vol scale, chosen on train by log loss
    grid = np.round(np.arange(0.6, 2.01, 0.05), 2)
    ll = [logloss(score(tr, s), y_tr) for s in grid]
    scale = float(grid[int(np.argmin(ll))])
    pe_tr, pe_te = score(tr, scale), score(te, scale)
    w = fit_blend(pe_tr, tr.price_yes.values, y_tr)
    pb_te = blend(w, pe_te, te.price_yes.values)

    res = {"cutoff": CUTOFF, "vol_window_hours": VOL_HOURS, "vol_scale": scale,
           "blend_weights": {"const": round(w[0], 3), "exchange": round(w[1], 3), "market": round(w[2], 3)},
           "n_train_rows": int(len(tr)), "n_test_rows": int(len(te)),
           "n_test_markets": int(te.market_id.nunique()), "overall": {}, "by_kind": [], "by_horizon": [], "trades": []}
    pm = te.price_yes.values
    res["overall"] = {"brier_market": brier(pm, y_te), "brier_exchange": brier(pe_te, y_te), "brier_blend": brier(pb_te, y_te),
                      "logloss_market": logloss(pm, y_te), "logloss_exchange": logloss(pe_te, y_te),
                      "logloss_blend": logloss(pb_te, y_te)}
    for key, col in (("by_kind", "kind"), ("by_horizon", "horizon_hours")):
        for v, idx in te.groupby(col).groups.items():
            m = te.index.get_indexer(idx)
            yy = y_te[m]
            res[key].append({col: v if col == "kind" else int(v), "n": int(len(m)),
                             "brier_market": round(brier(pm[m], yy), 4), "brier_exchange": round(brier(pe_te[m], yy), 4),
                             "brier_blend": round(brier(pb_te[m], yy), 4)})
    res["trades"] = [trade(te, pe_te, "exchange only"), trade(te, pb_te, "blend (exchange + market)")]
    for k in ("overall",):
        res[k] = {a: round(b, 4) for a, b in res[k].items()}
    OUT.mkdir(exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"fetch": fetch, "evaluate": evaluate}[sys.argv[1] if len(sys.argv) > 1 else "evaluate"]()
