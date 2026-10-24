"""Same event on Polymarket and Kalshi, 24 h before the scheduled end: how far apart are the prices, and whose
price was closer to the outcome? Evidence only: no model, no strategy. -> integrations/kalshi/match.json

  python integrations/kalshi_match.py [--since 2026-05-18] [--min-volume 20000]

Polymarket side: data/horizons.csv rows at horizon_hours == 24 (last trade at or before end - 24 h).
Kalshi side: settled binary markets (fetch_kalshi.list_markets), mid of the hourly candle's closing yes bid/ask at
or before its own expected_expiration_time - 24 h (<= 6 h stale); uses the candle cache from fetch_kalshi.py and
fetches only what is missing.
Matching (no prices involved): scheduled ends within 36 h, then word overlap between the Polymarket question and
the Kalshi title + yes-side subtitle (stop words and numbers dropped), Jaccard >= MIN_SIM, and the best match must be
unique for both sides. Same contract => same outcome, so pairs whose outcomes differ are dropped as mis-matched or
reversed (counted). Paired comparison: Brier of each venue's price on the same events, event-bootstrap CI.
"""
import argparse
import json
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import fetch_kalshi as K
from common import DATA, ROOT, parse_ts

OUT = ROOT / "integrations" / "kalshi"
MIN_SIM = 0.5
STOP = set("""will the a an of on in at to by for be is are vs v versus win wins winner game match yes no or and
            who what which before after end this that from with over under than more most top first""".split())


def words(s):
    return frozenset(w for w in re.findall(r"[a-z][a-z']+", (s or "").lower()) if w not in STOP and len(w) > 1)


def kalshi_24h(m):
    anchor = parse_ts(m.get("expected_expiration_time") or m.get("close_time"))
    close, open_ = parse_ts(m["close_time"]), parse_ts(m.get("open_time"))
    if not anchor or not close:
        return None
    t = anchor.timestamp() - 24 * 3600
    if t >= close.timestamp() or (open_ and t <= open_.timestamp()):
        return None
    start = int(anchor.timestamp() - (max(K.HORIZONS) + K.MAX_STALE_H) * 3600)
    cs = K.candles(m, start, int(min(close, anchor).timestamp()))
    best = None
    for c in cs:
        if t - K.MAX_STALE_H * 3600 <= c["end_period_ts"] <= t:
            best = c
    if best is None:
        return None
    bid = float((best.get("yes_bid") or {}).get("close_dollars") or 0)
    ask = float((best.get("yes_ask") or {}).get("close_dollars") or 0)
    if not 0 < bid < ask < 1:
        return None
    return {"ticker": m["ticker"], "event": m.get("event_ticker"), "text": f"{m.get('title') or ''} {m.get('yes_sub_title') or ''}",
            "end": anchor, "k_price": (bid + ask) / 2, "k_spread": ask - bid, "k_outcome": int(m["result"] == "yes"),
            "category": m.get("category")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-05-18")
    ap.add_argument("--min-volume", type=float, default=20000)
    a = ap.parse_args()
    K.CACHE.mkdir(parents=True, exist_ok=True)
    listing = K.CACHE.parent / f"kalshi_markets_{a.since}_{int(a.min_volume)}.json"
    if listing.exists():
        markets = json.loads(listing.read_text())
    else:
        markets = K.list_markets(datetime.fromisoformat(a.since).replace(tzinfo=timezone.utc), a.min_volume)
        listing.write_text(json.dumps(markets))
    print(f"{len(markets):,} Kalshi markets listed", flush=True)
    # text + date matching first (metadata only), candles only for candidates
    k = pd.DataFrame([{"i": i, "text": f"{m.get('title') or ''} {m.get('yes_sub_title') or ''}",
                       "end": parse_ts(m.get("expected_expiration_time") or m.get("close_time"))} for i, m in enumerate(markets)])
    k = k[k["end"].notna()].reset_index(drop=True)

    poly = pd.read_csv(DATA / "horizons.csv")
    poly = poly[(poly["horizon_hours"] == 24) & poly["outcome"].isin([0, 1])].copy()
    poly["end"] = pd.to_datetime(poly["end_date"], utc=True, format="ISO8601")
    poly = poly[poly["end"] >= pd.Timestamp(a.since, tz="UTC")].reset_index(drop=True)
    poly["w"] = poly["question"].map(words)
    k["w"] = k["text"].map(words)
    k["end"] = pd.to_datetime(k["end"], utc=True)

    # best Polymarket candidate for each Kalshi market, among ends within 36 h
    order = np.argsort(poly["end"].to_numpy())
    pend = poly["end"].dt.tz_convert(None).to_numpy()[order]
    best = []
    for i, r in k.iterrows():
        lo = np.searchsorted(pend, (r["end"] - pd.Timedelta(hours=36)).tz_convert(None).to_datetime64())
        hi = np.searchsorted(pend, (r["end"] + pd.Timedelta(hours=36)).tz_convert(None).to_datetime64())
        top, sim2, j_top = 0.0, 0.0, -1
        for j in order[lo:hi]:
            pw = poly.at[j, "w"]
            if not pw or not r["w"]:
                continue
            s = len(pw & r["w"]) / len(pw | r["w"])
            if s > top:
                top, sim2, j_top = s, top, j
            elif s > sim2:
                sim2 = s
        if top >= MIN_SIM and top > sim2:
            best.append((i, j_top, top))
    m = pd.DataFrame(best, columns=["ki", "pj", "sim"])
    m = m.sort_values("sim", ascending=False).drop_duplicates("pj")  # one Kalshi market per Polymarket market
    print(f"{len(m):,} text matches; fetching their 24 h quotes", flush=True)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as pool:
        quotes = list(pool.map(lambda i: kalshi_24h(markets[int(k.at[i, "i"])]), m["ki"]))
    m = m.assign(q=quotes)
    m = m[m["q"].notna()].reset_index(drop=True)
    k = k.join(pd.DataFrame([dict(q, ki=ki) for ki, q in zip(m["ki"], m["q"])]).set_index("ki").drop(columns=["text", "end"]))
    print(f"{len(m):,} with a two-sided quote 24 h before the end", flush=True)
    pairs = pd.concat([k.loc[m["ki"]].reset_index(drop=True), poly.loc[m["pj"]].reset_index(drop=True)
                       .rename(columns={"price_yes": "p_price", "outcome": "p_outcome", "end": "p_end"}),
                       m[["sim"]].reset_index(drop=True)], axis=1)
    n_text = len(pairs)
    agree = pairs["k_outcome"] == pairs["p_outcome"]
    pairs = pairs[agree].reset_index(drop=True)
    y = pairs["p_outcome"].to_numpy()
    d = (pairs["p_price"] - pairs["k_price"]).to_numpy()
    bp, bk = (pairs["p_price"] - y) ** 2, (pairs["k_price"] - y) ** 2
    ev = pairs["event_slug"].fillna(pairs["market_id"]).to_numpy()
    g = pd.DataFrame({"bp": bp, "bk": bk, "ev": ev}).groupby("ev").agg(["sum", "count"])
    sp, sk, cnt = g[("bp", "sum")].to_numpy(), g[("bk", "sum")].to_numpy(), g[("bp", "count")].to_numpy()
    rng = np.random.default_rng(0)
    idx = rng.integers(0, len(sp), (1000, len(sp)))
    dboot = (sp[idx].sum(1) - sk[idx].sum(1)) / cnt[idx].sum(1)
    out = {"since": a.since, "n_kalshi_listed": len(markets), "n_matches_with_24h_quote": int(len(m)),
           "n_text_matches": int(n_text), "n_dropped_outcome_mismatch": int((~agree).sum()),
           "n_pairs": int(len(pairs)), "n_events": int(len(sp)),
           "by_domain": pairs["domain"].value_counts().to_dict(),
           "abs_diff_cents": {"mean": round(float(np.abs(d).mean() * 100), 2), "median": round(float(np.median(np.abs(d)) * 100), 2),
                              "p90": round(float(np.percentile(np.abs(d), 90) * 100), 2)},
           "share_diff_ge_2c": round(float((np.abs(d) >= 0.02).mean()), 4),
           "share_diff_ge_5c": round(float((np.abs(d) >= 0.05).mean()), 4),
           "share_diff_gt_kalshi_spread": round(float((np.abs(d) > pairs["k_spread"]).mean()), 4),
           "median_kalshi_spread_cents": round(float(pairs["k_spread"].median() * 100), 2),
           "brier_polymarket": round(float(bp.mean()), 5), "brier_kalshi": round(float(bk.mean()), 5),
           "brier_diff_poly_minus_kalshi": round(float((bp - bk).mean()), 5),
           "brier_diff_ci": [round(float(x), 5) for x in np.percentile(dboot, [5, 95])],
           "closer_to_outcome_share": {"polymarket": round(float((bp < bk).mean()), 4), "kalshi": round(float((bk < bp).mean()), 4),
                                       "tie": round(float((bp == bk).mean()), 4)},
           "examples": pairs.sort_values("sim").head(5)[["question", "text", "p_price", "k_price", "p_outcome"]]
           .assign(text=lambda x: x["text"].str.slice(0, 90)).to_dict("records")
           + pairs.sort_values("sim").tail(3)[["question", "text", "p_price", "k_price", "p_outcome"]].to_dict("records")}
    OUT.mkdir(exist_ok=True)
    (OUT / "match.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    pairs.drop(columns=["w"]).to_csv(OUT / "matched_pairs.csv", index=False)
    print(json.dumps({x: v for x, v in out.items() if x != "examples"}, indent=1))
    for e in out["examples"]:
        print(" ", e)


if __name__ == "__main__":
    main()
