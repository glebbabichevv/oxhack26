"""Time capsule: seal Horizon's probabilities before the outcomes exist, open them after.

  python backend/capsule.py seal            # writes capsule/seal-<UTC>.json, prints its SHA-256
  python backend/capsule.py open <seal>     # scores a seal against resolutions -> capsule/open-<UTC>.json
  python backend/capsule.py summary [forward_score.json]   # -> backend/results/capsule.json for /api/capsule

The rules are pre-registered in capsule/EXPECTATIONS.md. The market filter below is the
deterministic rule stated there; do not change it after the first seal.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CAPSULE = ROOT / "capsule"
sys.path.insert(0, str(ROOT / "integrations"))

from common import GAMMA, domain_of, get, is_yes_no, parse_ts, tag_slugs  # noqa: E402
from model import (TRADABLE, brier, decide, in_band, load_horizons, select_model,  # noqa: E402
                   split_by_time, trade_cost)

DEADLINE = datetime(2026, 10, 25, 13, 0, tzinfo=timezone.utc)  # Sun 13:00 UTC, judging starts
MIN_VOLUME = 1_000  # secondary analysis: every market with volume >= $1k at seal time
PRIMARY_VOLUME = 10_000  # primary analysis: closest to the training population (>= $50k at close)
MIN_HALF_SPREAD = 0.01


def fetch_open(now):
    """Every open yes/no market ending before DEADLINE, paging by end date (Gamma caps offsets at 2,100)."""
    markets, start = {}, now
    while True:
        page, offset = [], 0
        while offset < 2000:
            got = get(f"{GAMMA}/markets", dict(
                closed="false", active="true", limit=100, offset=offset, volume_num_min=MIN_VOLUME,
                end_date_min=start.strftime("%Y-%m-%dT%H:%M:%SZ"), end_date_max=DEADLINE.strftime("%Y-%m-%dT%H:%M:%SZ"),
                order="endDate", ascending="true", include_tag="true"))
            page += got
            offset += 100
            if len(got) < 100:
                break
        new = [m for m in page if m["id"] not in markets]
        for m in page:
            markets[m["id"]] = m
        if offset < 2000 or not new:
            return list(markets.values())
        start = max(parse_ts(m["endDate"]) for m in page)  # next window starts at the last end date seen


def rows_from(markets, now):
    rows = []
    for m in markets:
        bid, ask, end = m.get("bestBid"), m.get("bestAsk"), parse_ts(m.get("endDate"))
        if not is_yes_no(m) or not m.get("acceptingOrders") or bid is None or ask is None or not end:
            continue
        bid, ask = float(bid), float(ask)
        if not 0 < bid < ask < 1 or not now < end < DEADLINE:
            continue
        price = (bid + ask) / 2
        if not in_band(price):
            continue
        event = (m.get("events") or [{}])[0]
        rows.append(dict(
            gamma_id=str(m["id"]), market_id=m["conditionId"], event_slug=event.get("slug") or m.get("slug"),
            question=m["question"], domain=domain_of(tag_slugs(m)), end_date=end.isoformat(),
            hours_to_resolution=round((end - now).total_seconds() / 3600, 2),
            price_yes=round(price, 4), spread=round(ask - bid, 4), volume_usd=round(float(m.get("volumeNum") or 0), 2)))
    return pd.DataFrame(rows).drop_duplicates("market_id")


def fitted_model():
    """Exactly the model behind backend/results: default time split, seed 0."""
    train, _, cutoff = split_by_time(load_horizons(ROOT / "data" / "horizons.csv"), None)
    model, selection = select_model(train, np.random.default_rng(0))
    return model, selection, cutoff


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seal():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    df = rows_from(fetch_open(now), now)
    model, selection, cutoff = fitted_model()
    p = df["price_yes"].to_numpy()
    q, lo, hi = model.predict(p, df["hours_to_resolution"], df["domain"])
    action, kelly, net = decide(p, q, trade_cost(df["spread"].to_numpy(), 0.0, MIN_HALF_SPREAD), lo, hi)
    df = df.assign(q_yes=np.round(q, 6), q_low=np.round(lo, 6), q_high=np.round(hi, 6),
                   action=action, kelly_fraction=np.round(kelly, 4), net_edge=np.round(net, 4))
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    out = {
        "sealed_at": now.isoformat(), "deadline": DEADLINE.isoformat(),
        "expectations_sha256": sha256(CAPSULE / "EXPECTATIONS.md"),
        "code_commit": commit, "model_selection": selection, "train_cutoff": str(cutoff.date()),
        "filter": f"open yes/no Gamma markets, accepting orders, volume >= ${MIN_VOLUME:,}, two-sided book, "
                  f"scheduled end in ({now.isoformat()}, {DEADLINE.isoformat()}), mid price in "
                  f"{TRADABLE[0]:.0%}-{TRADABLE[1]:.0%}; one row per market",
        "primary_rule": f"volume_usd >= ${PRIMARY_VOLUME:,} at seal time",
        "n_markets": int(len(df)), "n_primary": int((df["volume_usd"] >= PRIMARY_VOLUME).sum()),
        "by_domain": df["domain"].value_counts().to_dict(),
        "markets": df.to_dict(orient="records"),
    }
    CAPSULE.mkdir(exist_ok=True)
    path = CAPSULE / f"seal-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(out, indent=1))
    print(f"sealed {len(df)} markets ({out['n_primary']} primary) -> {path.relative_to(ROOT)}")
    print(df["domain"].value_counts().to_string())
    print(f"SHA-256 {sha256(path)}")


def resolution(m):
    """1 / 0 for a final YES / NO, else None (open, disputed, 50/50, cancelled)."""
    if not m.get("closed") or (m.get("umaResolutionStatus") or "resolved") != "resolved":
        return None
    try:
        yes = float(json.loads(m["outcomePrices"])[0])
    except (KeyError, ValueError, IndexError):
        return None
    return 1 if yes > 0.99 else 0 if yes < 0.01 else None


def score(df, rng, n_boot=2000):
    y, q, p = df["y"].to_numpy(), df["q_yes"].to_numpy(), df["price_yes"].to_numpy()
    out = {"n": int(len(df)), "brier_model": round(brier(q, y), 5), "brier_market": round(brier(p, y), 5)}
    if len(df) < 2:
        return out
    # 90% CI of (market - model) Brier, resampling events so legs of one match move together.
    d = pd.DataFrame({"e": df["event_slug"], "g": (p - y) ** 2 - (q - y) ** 2})
    by_event = d.groupby("e")["g"].agg(["sum", "count"])
    s, c = by_event["sum"].to_numpy(), by_event["count"].to_numpy()
    idx = rng.integers(0, len(s), (n_boot, len(s)))
    gaps = s[idx].sum(1) / c[idx].sum(1)
    out["gap_market_minus_model"] = round(float(d["g"].mean()), 5)
    out["gap_ci90"] = [round(float(x), 5) for x in np.percentile(gaps, [5, 95])]
    return out


def open_seal(seal_path):
    sealed = json.loads(Path(seal_path).read_text())
    df = pd.DataFrame(sealed["markets"])
    res = {}
    for i in range(0, len(df), 50):
        ids = df["gamma_id"].iloc[i:i + 50].tolist()
        for m in get(f"{GAMMA}/markets", [("id", x) for x in ids] + [("limit", 50)]):
            res[str(m["id"])] = resolution(m)
    df["y"] = df["gamma_id"].map(res)
    scored = df[df["y"].notna()].astype({"y": int})
    rng = np.random.default_rng(0)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    out = {
        "seal": Path(seal_path).name, "seal_sha256": sha256(seal_path), "sealed_at": sealed["sealed_at"],
        "opened_at": now.isoformat(), "n_sealed": int(len(df)), "n_scored": int(len(scored)),
        "n_excluded_unresolved": int(len(df) - len(scored)),
    }
    for tier, part in (("primary", scored[scored["volume_usd"] >= PRIMARY_VOLUME]), ("secondary", scored)):
        out[tier] = {
            "n_sealed": int((df["volume_usd"] >= PRIMARY_VOLUME).sum()) if tier == "primary" else int(len(df)),
            "all": score(part, rng),
            "sports": score(part[part["domain"] == "sports"], rng),
            "crypto": score(part[part["domain"] == "crypto"], rng),
            "other_domains": score(part[~part["domain"].isin(["sports", "crypto"])], rng),
        }
    path = CAPSULE / f"open-{now.strftime('%Y%m%dT%H%M%SZ')}-{Path(seal_path).stem}.json"
    path.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    print(f"-> {path.relative_to(ROOT)}")


def summary(forward_path=None):
    """Everything the site shows about sealed predictions: each seal (hash, counts) with its latest
    opening if any, plus C's forward-test score (integrations/forward/score.json) when given."""
    seals = []
    for path in sorted(CAPSULE.glob("seal-*.json")):
        s = json.loads(path.read_text())
        opens = sorted(CAPSULE.glob(f"open-*-{path.stem}.json"))
        seals.append({
            "name": path.name, "sealed_at": s["sealed_at"], "deadline": s["deadline"], "sha256": sha256(path),
            "timestamped": path.with_suffix(".json.ots").exists(),
            "n_markets": s["n_markets"], "n_primary": s.get("n_primary"), "by_domain": s["by_domain"],
            "opened": json.loads(opens[-1].read_text()) if opens else None,
        })
    out = {"seals": seals, "expectations": "capsule/EXPECTATIONS.md",
           "forward": json.loads(Path(forward_path).read_text()) if forward_path else None}
    (HERE / "results" / "capsule.json").write_text(json.dumps(out, indent=1))
    print(f"wrote results/capsule.json: {len(seals)} seal(s), forward={'yes' if forward_path else 'no'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["seal", "open", "summary"])
    ap.add_argument("path", nargs="?")
    a = ap.parse_args()
    {"seal": lambda: seal(), "open": lambda: open_seal(a.path), "summary": lambda: summary(a.path)}[a.cmd]()
