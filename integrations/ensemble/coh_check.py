"""Look-ahead check for COH (TheMarkz3's 00:05 caveat), on VAL2 only, before the test is opened.

Our dataset keeps a market only if its LIFETIME volume >= $100k, so the legs of an event present at a horizon
can depend on what happened later (winners may attract volume). COH normalises q over those legs. Check:
ask Gamma for every VAL2 neg-risk event's full list of markets; call an event COMPLETE when every one of its
yes/no markets is in our dataset. Then rerun the paired COH - V3 comparison with coherence applied only to
complete events (other events keep M0's q, still one bet per event). If the per-$ gain survives, the
normalisation is not riding on volume-based selection.

  python integrations/ensemble/coh_check.py [--raw data/raw]   # -> integrations/ensemble/coh_check.json
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ensemble as E  # noqa: E402
import paired as PD  # noqa: E402

GAMMA = "https://gamma-api.polymarket.com"
CACHE = HERE / "gamma_event_legs.json"


def event_legs(slugs):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    for s in slugs:
        if s in cache:
            continue
        for attempt in range(5):
            try:
                r = requests.get(f"{GAMMA}/events", params={"slug": s}, timeout=30)
                r.raise_for_status()
                ev = r.json()
                ms = ev[0].get("markets", []) if ev else []
                cache[s] = sorted(m["conditionId"] for m in ms if m.get("conditionId"))
                break
            except (requests.RequestException, ValueError, KeyError, IndexError):
                time.sleep(2 ** attempt)
        time.sleep(0.05)
    CACHE.write_text(json.dumps(cache))
    return cache


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(E.ROOT / "data" / "raw"))
    a = ap.parse_args()
    df = E.B.load_horizons(E.ROOT / "data" / "horizons.csv")
    feats = E.build_table(E.ROOT / "data", Path(a.raw))
    train, _, _ = E.B.split_by_time(df, E.P.CUTOFF)
    order = train.groupby("market_id")["resolved_at"].first().sort_values()
    val_ids = set(order.index[int(len(order) * 0.8):])
    fit, val = train[~train["market_id"].isin(val_ids)], train[train["market_id"].isin(val_ids)]
    val = E.scored_rows(val, val["resolved_at"].min())
    qs, dlo, dhi = E.Members().fit(fit, feats).predict(val, feats)
    half = (val["resolved_at"] >= val["resolved_at"].quantile(0.5)).to_numpy()
    rows = val[half].reset_index(drop=True)
    q2, lo2, hi2 = E.sub(qs, half), dlo[half], dhi[half]

    ok, _ = E.book_groups(rows)
    slugs = sorted(rows.loc[ok, "event_slug"].unique())
    print(f"VAL2 events where coherence applies: {len(slugs)}; fetching Gamma legs", flush=True)
    legs = event_legs(slugs)
    ours = df[df["event_slug"].isin(slugs)].groupby("event_slug")["market_id"].apply(set).to_dict()
    complete = {s for s in slugs if legs.get(s) and set(legs[s]) <= ours.get(s, set())}
    share_missing = {s: 1 - len(ours.get(s, set()) & set(legs.get(s, []))) / max(1, len(legs.get(s, []))) for s in slugs}
    print(f"complete events: {len(complete)} of {len(slugs)}; median share of legs missing from our data: "
          f"{np.median(list(share_missing.values())):.2f}", flush=True)

    # COH restricted: normalise only within complete events
    m0 = q2["M0"]
    coh_all = E.coherent(rows, m0)
    is_complete = rows["event_slug"].isin(complete).to_numpy()
    coh_clean = np.where(is_complete, coh_all, m0)
    res = {"n_coherence_events": len(slugs), "n_complete": len(complete),
           "median_share_legs_missing": round(float(np.median(list(share_missing.values()))), 3)}
    orig = E.coherent
    for label, q in (("COH_all_books", coh_all), ("COH_complete_books_only", coh_clean)):
        E.coherent = lambda d, q0, _q=q: _q  # trades_for("COH") -> this q, still one bet per event
        tv, tc = PD.stake_trades(rows, "V3", q2, lo2, hi2), PD.stake_trades(rows, "COH", q2, lo2, hi2)
        E.coherent = orig
        mv, mc = PD.metrics(tv, rows, m0), PD.metrics(tc, rows, q)
        res[label] = {"V3": {k: round(v, 4) for k, v in mv.items()}, "COH": {k: round(v, 4) for k, v in mc.items()},
                      "n_trades": {"V3": int(len(tv)), "COH": int(len(tc))}}
        print(label, res[label], flush=True)
    (HERE / "coh_check.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
