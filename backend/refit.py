"""Refit Horizon on fresh data and promote the new model only if it is not worse out of time.

  .venv/bin/python refit.py                      # pull newly resolved markets, refit, gate, promote
  .venv/bin/python refit.py --no-fetch           # refit on data/horizons.csv as it is
  .venv/bin/python refit.py --candidate m.json   # gate an externally fitted model (same format as results/model.json)
  .venv/bin/python refit.py --dry-run            # score and log, never promote
  .venv/bin/python refit.py --rescore            # regenerate results/{backtest,calibration}.json for the current model

Gate (identical inputs for both models): test set = markets of events still running at
max(current train_cutoff, candidate train_cutoff) that resolved after it, the same split rule as
model.split_by_time, so neither model has seen a test market. Promote iff candidate Brier <= current Brier
(log loss printed too). Candidates with features this code cannot compute everywhere (the API's
horizon_mcp.py computes any "domain=<d>" product; extension-module/horizon.ts only the default three)
are refused unless --allow-new-features.

Every candidate goes to results/model_candidates/<version>.json; every decision is appended to
results/model_candidates/decisions.jsonl. Exit code 10 = promoted (scripts/refresh.sh then redeploys).
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "integrations"))

import export_model  # noqa: E402
import fetch_horizons  # noqa: E402
import horizon_mcp  # noqa: E402
from common import GAMMA, get  # noqa: E402
from model import FEE_RATES, POLICY, brier, evaluate, in_band, load_horizons, log_loss, split_by_time  # noqa: E402

DATA = ROOT / "data" / "horizons.csv"
RESULTS = HERE / "results"
CANDIDATES = RESULTS / "model_candidates"
MIN_TEST_ROWS = 2000
PROMOTED = 10
FEE_COLS = ["fees_enabled", "fee_rate", "fee_exponent"]


# ---------- data ----------

def gamma_fees(condition_ids):
    """conditionId -> (fees_enabled, rate, exponent) from Gamma's per-market fee schedule."""
    ids = list(dict.fromkeys(condition_ids))

    def batch(i):
        params = [("condition_ids", c) for c in ids[i:i + 100]] + [("limit", 100), ("closed", "true")]
        return get(f"{GAMMA}/markets", params)

    out = {}
    with ThreadPoolExecutor(8) as pool:
        for page in pool.map(batch, range(0, len(ids), 100)):
            for m in page:
                sched = m.get("feeSchedule") or {}
                out[m["conditionId"]] = (bool(m.get("feesEnabled")), sched.get("rate"), sched.get("exponent"))
    return out


def backfill_fees(df):
    """Add fees_enabled / fee_rate / fee_exponent where missing (Gamma's schedule; rate falls back to FEE_RATES)."""
    for c in FEE_COLS:
        df[c] = (df[c] if c in df else pd.Series(None, index=df.index)).astype(object)
    missing = df["fees_enabled"].isna()
    if not missing.any():
        return df
    fees = gamma_fees(df.loc[missing, "market_id"])
    got = df.loc[missing, "market_id"].map(fees)
    has = got.notna()
    idx = got[has].index
    df.loc[idx, "fees_enabled"] = pd.Series([f[0] for f in got[has]], index=idx, dtype=object)
    df.loc[idx, "fee_rate"] = pd.Series([f[1] if f[1] is not None else (FEE_RATES.get(d, FEE_RATES["other"]) if f[0] else 0.0)
                                         for f, d in zip(got[has], df.loc[idx, "domain"])], index=idx, dtype=object)
    df.loc[idx, "fee_exponent"] = pd.Series([f[2] if f[2] is not None else 1 for f in got[has]], index=idx, dtype=object)
    print(f"fees: backfilled {len(idx)} rows from Gamma ({int(missing.sum()) - len(idx)} not found, domain rate assumed)")
    return df


def update_data(path=DATA, overlap_days=7, min_volume=50000):
    """Append markets resolved since the last pull (same fetcher and filters as integrations/fetch_horizons.py)."""
    df = pd.read_csv(path)
    known = set(df["market_id"])
    since = pd.to_datetime(df["end_date"], utc=True, format="ISO8601").max().to_pydatetime() - timedelta(days=overlap_days)
    until = datetime.now(timezone.utc)
    fetch_horizons.HIST.mkdir(parents=True, exist_ok=True)
    listed = [m for m in fetch_horizons.list_markets(since, until, min_volume)
              if m.get("conditionId") not in known]
    print(f"data: {len(listed)} closed markets ending {since:%Y-%m-%d}..{until:%Y-%m-%d} not yet in {path.name}")
    rows, failed = [], 0
    with ThreadPoolExecutor(8) as pool:
        for f in as_completed([pool.submit(fetch_horizons.rows_for, m) for m in listed]):
            try:
                rows += f.result()
            except Exception:  # noqa: BLE001 - one bad market must not kill the refresh
                failed += 1
    new = pd.DataFrame(rows)
    out = pd.concat([df, new], ignore_index=True) if len(new) else df
    out = out.drop_duplicates(["market_id", "horizon_hours"], keep="first")
    out = backfill_fees(out).sort_values(["resolved_at", "market_id", "horizon_hours"])
    out.to_csv(path, index=False)
    print(f"data: +{len(out) - len(df)} rows, +{out['market_id'].nunique() - df['market_id'].nunique()} markets "
          f"({failed} failed) -> {out['market_id'].nunique()} markets")
    return out


# ---------- models from JSON ----------

class JsonModel:
    """model.json -> predict(price, hours, domain) -> (q, lo, hi), vectorised; same math as horizon_mcp.decide."""

    def __init__(self, m):
        self.m = horizon_mcp.load_model(m)

    def _X(self, p, h, dom):
        m = self.m
        pc = np.clip(p, m["eps"], 1 - m["eps"])
        val = {horizon_mcp.LOGIT_P: np.log(pc / (1 - pc)), horizon_mcp.LOG_H: np.log(np.clip(h, 12, 720) / 24)}
        cols = []
        for factors in m["_features"]:
            x = np.ones(len(p))
            for f in factors:
                x = x * (val[f] if f in val else (dom == f[7:]).astype(float))
            cols.append(x)
        return np.column_stack(cols)

    def predict(self, price, hours, domain):
        p, h, dom = np.asarray(price, float), np.asarray(hours, float), np.asarray(domain, dtype=object)
        X = self._X(p, h, dom)
        sig = lambda f: 1 / (1 + np.exp(-(f["intercept"] + X @ np.asarray(f["coef"]))))  # noqa: E731
        q = sig(self.m["main"])
        qs = np.stack([sig(f) for f in self.m["boot"]])
        lo_pct, hi_pct = self.m["interval_percentiles"]
        lo, hi = np.percentile(qs, lo_pct, axis=0), np.percentile(qs, hi_pct, axis=0)
        lo_b, hi_b = self.m["tradable"]
        band = (p >= lo_b) & (p <= hi_b)
        return np.where(band, q, p), np.where(band, lo, p), np.where(band, hi, p)


def complete(cand, current):
    """Fill decision constants a candidate leaves out from the current model; give it a version."""
    if not cand.get("train_cutoff"):
        raise ValueError("candidate has no train_cutoff: can't tell which markets it has seen, so it can't be tested out of time")
    out = {k: v for k, v in current.items()
           if not k.startswith("_") and k not in ("version", "metrics", "fitted_at", "train_cutoff", "model_selection", "features")}
    out.update({k: v for k, v in cand.items() if not k.startswith("_")})
    out.setdefault("features", horizon_mcp.DEFAULT_FEATURES)
    if "version" not in cand:
        out["version"] = f"{datetime.now(timezone.utc):%Y-%m-%d}-{export_model.model_hash(out)}"
    horizon_mcp.load_model(dict(out))  # validates features and coefficient counts
    return out


def score(model, test):
    q, _, _ = JsonModel(model).predict(test["price_yes"], test["horizon_hours"], test["domain"])
    y = test["outcome"].to_numpy()
    band = in_band(test["price_yes"])
    return {"brier": round(brier(q, y), 6), "logloss": round(log_loss(q, y), 6),
            "brier_in_band": round(brier(q[band], y[band]), 6)}


def gate(df, current, cand):
    cutoff = max(pd.Timestamp(current["train_cutoff"]), pd.Timestamp(cand["train_cutoff"]))
    _, test, cutoff = split_by_time(df, str(cutoff.date()))
    if len(test) < MIN_TEST_ROWS:
        return {"promote": False, "why": f"only {len(test)} test rows after {cutoff.date()} (< {MIN_TEST_ROWS})",
                "test_cutoff": str(cutoff.date()), "n_test_rows": len(test)}
    y = test["outcome"].to_numpy()
    s_cur, s_cand = score(current, test), score(cand, test)
    market = {"brier": round(brier(test["price_yes"], y), 6), "logloss": round(log_loss(test["price_yes"], y), 6)}
    promote = s_cand["brier"] <= s_cur["brier"]
    why = (f"candidate Brier {s_cand['brier']} {'<=' if promote else '>'} current {s_cur['brier']} "
           f"(market {market['brier']}) on {test['market_id'].nunique()} markets resolved after {cutoff.date()}")
    return {"promote": promote, "why": why, "test_cutoff": str(cutoff.date()), "n_test_rows": int(len(test)),
            "n_test_markets": int(test["market_id"].nunique()), "current": s_cur, "candidate": s_cand, "market": market}


# ---------- publish ----------

def stamp(data, version, now):
    return {"generated_at": now.isoformat(timespec="seconds"), "model_version": version,
            **{k: v for k, v in data.items() if k not in ("generated_at", "model_version")}}


def publish(model_json, cal, backtest, now):
    """Write the promoted model and its own out-of-time results (what /api/* serve)."""
    model_json["by_horizon"] = [{"horizon_hours": h["horizon_hours"], "mean_return_per_trade": h["with_costs"]["mean_return_per_trade"]}
                                for h in backtest["by_horizon"]]
    model_json["metrics"] = export_model.metrics_of(backtest, cal)
    model_json["fee_rates"] = FEE_RATES
    model_json["policy"] = {k: v for k, v in POLICY.items() if k != "note"}
    model_json["headline"] = {k: backtest["headline"][k] for k in ("per_dollar", "per_dollar_ci", "return", "return_ci", "n_trades")}
    (RESULTS / "model.json").write_text(json.dumps(model_json, indent=1))
    (RESULTS / "backtest.json").write_text(json.dumps(stamp(backtest, model_json["version"], now), indent=1, default=str))
    (RESULTS / "calibration.json").write_text(json.dumps(
        stamp({"cutoff": backtest["cutoff"], "by_domain": cal}, model_json["version"], now), indent=1))


def results_for(df, model_json):
    """Backtest + calibration of a model.json on its own time split (fees on)."""
    sel = model_json.get("model_selection") or {"chosen": "external"}
    _, cal, bt = evaluate(df, model_json["train_cutoff"], model=JsonModel(model_json), selection=sel)
    return cal, bt


def refresh_live(model_json):
    try:
        import live
        p = live.write_snapshot(horizon_mcp.load_model(dict(model_json)))
        print(f"live: snapshot {len(p['markets'])} markets ({p['n_trades']} trades)")
    except Exception as e:  # noqa: BLE001 - the API computes live on request anyway
        print(f"live: snapshot not refreshed ({e})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", help="externally fitted model JSON to gate instead of refitting")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rescore", action="store_true", help="regenerate results for the current model, no gate")
    ap.add_argument("--allow-new-features", action="store_true")
    a = ap.parse_args()
    now = datetime.now(timezone.utc)
    CANDIDATES.mkdir(parents=True, exist_ok=True)
    current = json.loads((RESULTS / "model.json").read_text())

    df_raw = pd.read_csv(DATA)
    if not a.no_fetch and not a.rescore:
        df_raw = update_data()
    elif df_raw.get("fees_enabled") is None or df_raw["fees_enabled"].isna().any():
        df_raw = backfill_fees(df_raw)
        df_raw.to_csv(DATA, index=False)
    df = load_horizons(DATA)

    if a.rescore:
        model, cal, bt = evaluate(df)  # model.py's own path: exact numbers if the data still gives this model
        if export_model.model_hash(export_model.export(model, bt, cal, now)) != export_model.model_hash(current):
            cal, bt = results_for(df, current)
        publish(current, cal, bt, now)
        refresh_live(current)
        print(f"rescored {current['version']}: return {bt['with_costs']['return']:+.3f} CI {bt['return_ci']}, "
              f"capped {bt['capped_exposure']['return']:+.3f}, peak open stake {bt['peak_open_stake']}")
        return 0

    if a.candidate:
        cand = complete(json.loads(Path(a.candidate).read_text()), current)
        cal = bt = None
        source = f"external:{a.candidate}"
    else:
        model, cal, bt = evaluate(df)
        cand = export_model.export(model, bt, cal, now)
        source = "refit"
    print(f"current {current.get('version')} (cutoff {current['train_cutoff']}) vs candidate {cand['version']} "
          f"(cutoff {cand['train_cutoff']}, {source})")
    (CANDIDATES / f"{cand['version']}.json").write_text(json.dumps(cand, indent=1))

    g = gate(df, current, cand)
    if cand["version"] == current.get("version"):
        g.update(promote=False, why="candidate is identical to the current model")
    new_feats = [f for f in cand["features"] if f not in horizon_mcp.DEFAULT_FEATURES]
    if g["promote"] and new_feats and not a.allow_new_features:
        g.update(promote=False, why=g["why"] + f"; refused: features {new_feats} are not computed by "
                 "extension-module/horizon.ts (pass --allow-new-features once the extension supports them)")
    if g["promote"] and a.dry_run:
        g.update(promote=False, why=g["why"] + "; dry run")
    print(("PROMOTE: " if g["promote"] else "KEEP current: ") + g["why"])
    with open(CANDIDATES / "decisions.jsonl", "a") as f:
        f.write(json.dumps({"at": now.isoformat(timespec="seconds"), "source": source, "current_version": current.get("version"),
                            "candidate_version": cand["version"], **g}) + "\n")
    if not g["promote"]:
        return 0
    if (CANDIDATES / f"{current.get('version')}.json").exists() is False and current.get("version"):
        (CANDIDATES / f"{current['version']}.json").write_text(json.dumps(current, indent=1))  # keep for rollback
    if cal is None:
        cal, bt = results_for(df, cand)
    publish(cand, cal, bt, now)
    refresh_live(cand)
    print(f"promoted {cand['version']}: Brier {bt['overall']['brier_model']} vs market {bt['overall']['brier_market']}, "
          f"return {bt['with_costs']['return']:+.3f}, capped {bt['capped_exposure']['return']:+.3f}")
    return PROMOTED


if __name__ == "__main__":
    sys.exit(main())
