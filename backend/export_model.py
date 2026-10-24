"""Fitted model -> results/model.json, so a browser can compute Horizon's q exactly (/api/model).

  python backend/export_model.py

Same fit as model.py and capsule.py (default time split, seed 0). Only the simple model
(features logit(p), log(h/24), their product) is exportable; refuses anything else.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "integrations"))

from common import DOMAIN_TAGS  # noqa: E402
from capsule import fitted_model  # noqa: E402
from model import EPS, KELLY_CAP, KELLY_SCALE, TRADABLE  # noqa: E402


def coefs(m):
    return {"intercept": float(m.intercept_[0]), "coef": [float(c) for c in m.coef_[0]]}


model, selection, cutoff = fitted_model()
if selection["chosen"] != "simple":
    sys.exit(f"export supports the simple model only, got {selection['chosen']}")
backtest = json.loads((HERE / "results" / "backtest.json").read_text())
out = {
    "features": ["logit(p)", "log(clip(hours, 12, 720) / 24)", "logit(p) * log(clip(hours, 12, 720) / 24)"],
    "main": coefs(model.main),
    "boot": [coefs(m) for m in model.boot],
    "interval_percentiles": [10, 90],
    "tradable": list(TRADABLE), "min_half_spread": 0.01, "eps": EPS,
    "kelly_scale": KELLY_SCALE, "kelly_cap": KELLY_CAP,
    "domain_tags": [[d, sorted(keys)] for d, keys in DOMAIN_TAGS],
    "by_horizon": [{"horizon_hours": h["horizon_hours"], "mean_return_per_trade": h["with_costs"]["mean_return_per_trade"]}
                   for h in backtest["by_horizon"]],
    "train_cutoff": str(cutoff.date()), "model_selection": selection,
}
(HERE / "results" / "model.json").write_text(json.dumps(out, indent=1))
print(f"wrote results/model.json: {len(out['boot'])} bootstrap sets, main {out['main']}")
