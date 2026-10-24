"""Fitted model -> results/model.json, so the API, MCP and browser compute Horizon's q exactly (/api/model).

  python backend/export_model.py

Same fit as model.py and capsule.py (default time split, seed 0). The file is the model registry
entry too: `version` (fit date + content hash) and `metrics` (its own out-of-time scores).
Model file format (also what refit.py --candidate accepts):
  features   list of names, each a " * " product of logit(p) | log(clip(hours, 12, 720) / 24) | domain=<name>
  main       {"intercept": float, "coef": [one per feature]}
  boot       [{"intercept", "coef"}, ...]   bootstrap refits -> the 10-90% interval on q
  train_cutoff  "YYYY-MM-DD": every training market resolved before it (the out-of-time test starts there)
  decision constants (tradable, eps, min_half_spread, kelly_scale, kelly_cap, interval_percentiles,
  domain_tags, by_horizon) - copied from the current model when a candidate leaves them out.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "integrations"))

from common import DOMAIN_TAGS  # noqa: E402
from model import EPS, KELLY_CAP, KELLY_SCALE, TRADABLE, MarketBaseline, evaluate, load_horizons  # noqa: E402

LOGIT_P, LOG_H = "logit(p)", "log(clip(hours, 12, 720) / 24)"


def coefs(m):
    return {"intercept": float(m.intercept_[0]), "coef": [float(c) for c in m.coef_[0]]}


def feature_names(domains):
    """Column names of model.Calibrator.features, in the same order."""
    names = [LOGIT_P, LOG_H, f"{LOGIT_P} * {LOG_H}"]
    for d in domains[1:]:
        names += [f"domain={d}", f"domain={d} * {LOGIT_P}", f"domain={d} * {LOGIT_P} * {LOG_H}"]
    return names


def model_hash(m):
    blob = json.dumps({k: m[k] for k in ("features", "main", "boot")}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:7]


def metrics_of(backtest, calibration=None):
    o = backtest["overall"]
    rows = sum(h["n"] for h in calibration["all"]["horizons"]) if calibration else None
    return {"test_cutoff": backtest["cutoff"], "n_test_markets": backtest["n_test_markets"], "n_test_rows": rows,
            "n_train_markets": backtest["n_train_markets"],
            "brier_model": o["brier_model"], "brier_market": o["brier_market"],
            "logloss_model": o["logloss_model"], "logloss_market": o["logloss_market"]}


def export(model, backtest, calibration=None, now=None):
    """Fitted Calibrator + its backtest -> model.json dict (with version and metrics)."""
    if isinstance(model, MarketBaseline):
        raise ValueError("validation picked the market itself (no model beats it): nothing to export")
    now = now or datetime.now(timezone.utc)
    out = {
        "features": feature_names(model.domains),
        "main": coefs(model.main),
        "boot": [coefs(m) for m in model.boot],
        "interval_percentiles": [10, 90],
        "tradable": list(TRADABLE), "min_half_spread": 0.01, "eps": EPS,
        "kelly_scale": KELLY_SCALE, "kelly_cap": KELLY_CAP,
        "domain_tags": [[d, sorted(keys)] for d, keys in DOMAIN_TAGS],
        "by_horizon": [{"horizon_hours": h["horizon_hours"], "mean_return_per_trade": h["with_costs"]["mean_return_per_trade"]}
                       for h in backtest["by_horizon"]],
        "train_cutoff": backtest["cutoff"], "model_selection": backtest["model_selection"],
    }
    out["version"] = f"{now:%Y-%m-%d}-{model_hash(out)}"
    out["fitted_at"] = now.isoformat(timespec="seconds")
    out["metrics"] = metrics_of(backtest, calibration)
    return out


if __name__ == "__main__":
    model, cal, backtest = evaluate(load_horizons(ROOT / "data" / "horizons.csv"))
    out = export(model, backtest, cal)
    (HERE / "results" / "model.json").write_text(json.dumps(out, indent=1))
    print(f"wrote results/model.json {out['version']}: {len(out['boot'])} bootstrap sets, main {out['main']}")
