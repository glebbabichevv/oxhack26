"""Time capsule: seal Horizon's probabilities before the outcomes exist, open them after.

  python backend/capsule.py seal            # writes capsule/seal-<UTC>.json, prints its SHA-256 + the Discord line
  python backend/capsule.py seal --dry-run  # same, written to /tmp, nothing in capsule/ (rehearsal)
  python backend/capsule.py open <seal>     # scores a seal against resolutions -> capsule/open-<UTC>.json
  python backend/capsule.py open --all      # every seal: Brier + decisions' result per $1 after fees vs the
                                            # pre-registered expectations -> capsule/open-*.json,
                                            # backend/results/capsule_open.json, refreshed results/capsule.json
  python backend/capsule.py open --all --dry-run   # same scoring, written to the temp dir only (rehearsal)
  python backend/capsule.py summary [forward_score.json]   # -> backend/results/capsule.json for /api/capsule

The rules are pre-registered in capsule/EXPECTATIONS.md. The market filter below is the
deterministic rule stated there; do not change it after the first seal.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CAPSULE = ROOT / "capsule"
sys.path.insert(0, str(ROOT / "integrations"))

from common import GAMMA, domain_of, get, is_yes_no, parse_ts, tag_slugs  # noqa: E402
from model import (TRADABLE, brier, coherent, decide, fee_per_share, in_band, load_horizons, payoff,  # noqa: E402
                   select_model, split_by_time, trade_cost)

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
            neg_risk=bool(m.get("negRisk") or event.get("negRisk")),
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


def model_identity(model):
    """Version hash of the coefficients actually used (same recipe as export_model.model_hash) and of the
    shipped backend/results/model.json, so a seal names the exact model and policy it was made with."""
    from export_model import coefs, feature_names, model_hash
    used = {"features": feature_names(model.domains), "main": coefs(model.main), "boot": [coefs(m) for m in model.boot]}
    shipped = json.loads((HERE / "results" / "model.json").read_text())
    h = model_hash(used)
    return {"model_hash": h, "model_version": shipped.get("version"), "matches_shipped": shipped.get("version", "").endswith(h),
            "model_json_sha256": sha256(HERE / "results" / "model.json"), "policy": shipped.get("policy")}


def seal(dry_run=False):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    df = rows_from(fetch_open(now), now)
    model, selection, cutoff = fitted_model()
    ident = model_identity(model)
    pol = ident["policy"] or {}
    p = df["price_yes"].to_numpy()
    q, lo, hi = model.predict(p, df["hours_to_resolution"], df["domain"])
    if pol.get("coherent"):  # policy COH: q coherent across the legs of a complete-looking neg-risk book
        q0 = q
        q = coherent(df.assign(horizon_hours=df["end_date"]), q0)  # sealed legs of one event share the end date
        lo, hi = np.clip(q - (q0 - lo), 0, 1), np.clip(q + (hi - q0), 0, 1)
    action, kelly, net = decide(p, q, trade_cost(df["spread"].to_numpy(), 0.0, MIN_HALF_SPREAD), lo, hi,
                                hours=df["hours_to_resolution"].to_numpy(), min_edge=pol.get("min_edge", 0.0),
                                enter_from=pol.get("enter_from_hours"))
    if pol.get("one_per_event"):  # one bet per event: only the largest net edge keeps its BUY
        buy = action != "NO_TRADE"
        best = pd.Series(np.where(buy, net, -np.inf), index=df.index).groupby(df["event_slug"]).transform("max").to_numpy()
        drop = buy & (net < best)
        action, kelly = np.where(drop, "NO_TRADE", action), np.where(drop, 0.0, kelly)
    df = df.assign(q_yes=np.round(q, 6), q_low=np.round(lo, 6), q_high=np.round(hi, 6),
                   action=action, kelly_fraction=np.round(kelly, 4), net_edge=np.round(net, 4))
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    out = {
        "sealed_at": now.isoformat(), "deadline": DEADLINE.isoformat(),
        "expectations_sha256": sha256(CAPSULE / "EXPECTATIONS.md"),
        "code_commit": commit, "model_selection": selection, "train_cutoff": str(cutoff.date()), **ident,
        "filter": f"open yes/no Gamma markets, accepting orders, volume >= ${MIN_VOLUME:,}, two-sided book, "
                  f"scheduled end in ({now.isoformat()}, {DEADLINE.isoformat()}), mid price in "
                  f"{TRADABLE[0]:.0%}-{TRADABLE[1]:.0%}; one row per market",
        "primary_rule": f"volume_usd >= ${PRIMARY_VOLUME:,} at seal time",
        "n_markets": int(len(df)), "n_primary": int((df["volume_usd"] >= PRIMARY_VOLUME).sum()),
        "by_domain": df["domain"].value_counts().to_dict(),
        "markets": df.to_dict(orient="records"),
    }
    out_dir = Path("/tmp") if dry_run else CAPSULE
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{'dryrun-' if dry_run else ''}seal-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    path.write_text(json.dumps(out, indent=1))
    print(f"sealed {len(df)} markets ({out['n_primary']} primary) -> {path}")
    print(f"model {ident['model_version']} hash {ident['model_hash']} matches shipped: {ident['matches_shipped']} policy {pol.get('name')}")
    print(df["domain"].value_counts().to_string())
    h = sha256(path)
    print(f"SHA-256 {h}")
    print(f"Discord: locking in round {len(list(CAPSULE.glob('seal-*.json'))) + (1 if dry_run else 0)} of our sealed predictions, "
          f"{len(df)} markets, model {ident['model_version']}. sha256 {h}")
    if dry_run:
        print("DRY RUN: nothing written to capsule/, nothing to post")


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
    if not len(df):
        return {"n": 0}
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


def open_seal(seal_path, write_dir=CAPSULE):
    sealed = json.loads(Path(seal_path).read_text())
    df = pd.DataFrame(sealed["markets"])
    res, closed_at = {}, {}
    for i in range(0, len(df), 50):
        ids = df["gamma_id"].iloc[i:i + 50].tolist()
        # Gamma filters by closed=false unless asked: without closed=true every resolved market goes missing.
        for m in get(f"{GAMMA}/markets", [("id", x) for x in ids] + [("limit", 50), ("closed", "true")]):
            res[str(m["id"])] = resolution(m)
            ct = parse_ts(m.get("closedTime"))
            closed_at[str(m["id"])] = ct.isoformat() if ct else None
    df["y"] = df["gamma_id"].map(res)
    df["resolved_at"] = df["gamma_id"].map(closed_at)
    # Amendment 1: only markets that resolved after the seal's hash was posted publicly count.
    posts = json.loads((CAPSULE / "posts.json").read_text()) if (CAPSULE / "posts.json").exists() else {}
    posted_at = posts.get(Path(seal_path).name)
    # Compare as timestamps: when nothing has resolved yet the column is all NaN (float), not strings.
    res_ts = pd.to_datetime(df["resolved_at"], utc=True, errors="coerce")
    before_post = res_ts.notna() & (res_ts <= pd.Timestamp(posted_at)) if posted_at else pd.Series(False, index=df.index)
    scored = df[df["y"].notna() & ~before_post].astype({"y": int})
    rng = np.random.default_rng(0)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    out = {
        "seal": Path(seal_path).name, "seal_sha256": sha256(seal_path), "sealed_at": sealed["sealed_at"],
        "opened_at": now.isoformat(), "n_sealed": int(len(df)), "n_scored": int(len(scored)),
        "posted_at": posted_at,
        "n_excluded_resolved_before_post": int(before_post.sum()),
        "n_excluded_unresolved": int(df["y"].isna().sum()),
    }
    for tier, part in (("primary", scored[scored["volume_usd"] >= PRIMARY_VOLUME]), ("secondary", scored)):
        out[tier] = {
            "n_sealed": int((df["volume_usd"] >= PRIMARY_VOLUME).sum()) if tier == "primary" else int(len(df)),
            "all": score(part, rng),
            "sports": score(part[part["domain"] == "sports"], rng),
            "crypto": score(part[part["domain"] == "crypto"], rng),
            "other_domains": score(part[~part["domain"].isin(["sports", "crypto"])], rng),
        }
    out["decisions"] = decisions(scored, rng)
    out["expectations"] = {tier: verdicts(out[tier]) for tier in ("primary", "secondary")}
    if write_dir is None:
        return out
    path = Path(write_dir) / f"open-{now.strftime('%Y%m%dT%H%M%SZ')}-{Path(seal_path).stem}.json"
    path.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("seal", "n_sealed", "n_scored", "n_excluded_resolved_before_post",
                                           "n_excluded_unresolved", "expectations", "decisions")}, indent=1))
    print(f"-> {path}")
    return out


# Pre-registered in capsule/EXPECTATIONS.md ("What we expect"): direction of (market Brier - model Brier).
EXPECTED = {"all": ("model beats market by ~0.001", "positive"),
            "sports": ("model beats market by ~0.0015", "positive"),
            "crypto": ("no difference", "zero")}


def verdicts(tier):
    """Each pre-registered expectation against the observed gap and its 90% event-bootstrap interval."""
    out = {}
    for k, (claim, kind) in EXPECTED.items():
        s = tier.get(k, {})
        ci, gap = s.get("gap_ci90"), s.get("gap_market_minus_model")
        if not ci:
            v = "not enough resolved markets"
        elif kind == "positive":
            v = "as expected (interval above 0)" if ci[0] > 0 else "reversed (interval below 0)" if ci[1] < 0 else "inconclusive (interval spans 0)"
        else:
            v = "as expected (interval spans 0)" if ci[0] <= 0 <= ci[1] else "differs from 0"
        out[k] = {"expected": claim, "n": s.get("n", 0), "gap_market_minus_model": gap, "gap_ci90": ci, "verdict": v}
    return out


def decisions(scored, rng, n_boot=2000):
    """Result of the sealed BUY decisions, held to resolution, per $1 after costs: max(half-spread, 1c) plus the
    Polymarket taker fee at the sealed price (fees on, each domain's rate; the seal itself predates fees).
    Not the pre-registered metric (EXPECTATIONS.md: P&L is not the metric) - reported for transparency."""
    t = scored[scored["action"] != "NO_TRADE"]
    if not len(t):
        return {"n": 0}
    p = t["price_yes"].to_numpy(float)
    cost = trade_cost(t["spread"].to_numpy(float), fee_per_share(t), MIN_HALF_SPREAD)
    ret = payoff(t["action"].to_numpy(), p, cost, t["y"].to_numpy(float))
    k = t["kelly_fraction"].to_numpy(float) if "kelly_fraction" in t else np.ones(len(t))
    k = np.where(k > 0, k, 1e-9)
    out = {"n": int(len(t)), "per_dollar_kelly": round(float((k * ret).sum() / k.sum()), 4),
           "per_dollar_flat": round(float(ret.mean()), 4), "hit_rate": round(float((ret > 0).mean()), 4)}
    if len(t) >= 2:
        g = pd.DataFrame({"e": t["event_slug"].to_numpy(), "pnl": k * ret, "st": k}).groupby("e").sum()
        idx = rng.integers(0, len(g), (n_boot, len(g)))
        r = g["pnl"].to_numpy()[idx].sum(1) / g["st"].to_numpy()[idx].sum(1)
        out["per_dollar_kelly_ci90"] = [round(float(x), 4) for x in np.percentile(r, [5, 95])]
    return out


def open_all(dry_run=False):
    """Every seal in capsule/, scored with open_seal; one combined file for the site."""
    seals = sorted(CAPSULE.glob("seal-*.json"))
    write_dir = Path(tempfile.gettempdir()) if dry_run else CAPSULE
    opened = [open_seal(s, write_dir) for s in seals]
    now = datetime.now(timezone.utc).replace(microsecond=0)
    combined = {"opened_at": now.isoformat(), "dry_run": dry_run, "expectations": "capsule/EXPECTATIONS.md",
                "primary_seal": seals[0].name if seals else None, "seals": opened}
    target = (Path(tempfile.gettempdir()) / "capsule_open.json") if dry_run else (HERE / "results" / "capsule_open.json")
    target.write_text(json.dumps(combined, indent=1))
    print(f"{'DRY RUN: ' if dry_run else ''}{len(opened)} seal(s) opened -> {target}")
    if not dry_run:  # refresh /api/capsule, keeping the forward-test block already there
        prev = HERE / "results" / "capsule.json"
        forward = json.loads(prev.read_text()).get("forward") if prev.exists() else None
        summary(forward_data=forward)


def summary(forward_path=None, forward_data=None):
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
           "forward": json.loads(Path(forward_path).read_text()) if forward_path else forward_data}
    (HERE / "results" / "capsule.json").write_text(json.dumps(out, indent=1))
    print(f"wrote results/capsule.json: {len(seals)} seal(s), forward={'yes' if forward_path else 'no'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["seal", "open", "summary"])
    ap.add_argument("path", nargs="?")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--all", action="store_true", help="open: every seal in capsule/")
    a = ap.parse_args()
    {"seal": lambda: seal(a.dry_run),
     "open": lambda: open_all(a.dry_run) if a.all else open_seal(a.path),
     "summary": lambda: summary(a.path)}[a.cmd]()
