"""Fee-aware parity fixture: live Gamma markets -> Python reference decisions (model.py, sklearn path, with fees).

  .venv/bin/python parity_fees.py [out.json]          # default data/raw/parity_fees.json
  python3 horizon_mcp.py parity data/raw/parity_fees.json
  node extension-module/parity.mjs data/raw/parity_fees.json

The capsule seal predates fees, so it can't check the fee term; this fixture can.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "integrations"))

import export_model  # noqa: E402
import horizon_mcp  # noqa: E402
import live  # noqa: E402
from model import decide, evaluate, load_horizons, trade_cost  # noqa: E402

out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "data" / "raw" / "parity_fees.json"
model, cal, bt = evaluate(load_horizons(HERE.parent / "data" / "horizons.csv"))
current = json.loads((HERE / "results" / "model.json").read_text())
if export_model.model_hash(export_model.export(model, bt, cal)) != export_model.model_hash(current):
    sys.exit("data/horizons.csv no longer reproduces results/model.json; run on the data the model was fitted on")

now = datetime.now(timezone.utc)
rows = []
for mk in live.fetch_open(now):
    r = live._row(mk, now, horizon_mcp.MODEL)
    if r and 0.03 <= r["price_yes"] <= 0.97:  # in band, like the seal (out of band is NO_TRADE by rule)
        rate, exp = horizon_mcp.fee_of(mk, r["domain"])
        rows.append({"price_yes": r["price_yes"], "hours_to_resolution": r["hours_to_resolution"], "domain": r["domain"],
                     "spread": r["spread"], "fee_rate": rate, "fee_exponent": exp})
p = np.array([r["price_yes"] for r in rows])
q, lo, hi = model.predict(p, [r["hours_to_resolution"] for r in rows], [r["domain"] for r in rows])
fee = np.array([r["fee_rate"] * (r["price_yes"] * (1 - r["price_yes"])) ** r["fee_exponent"] for r in rows])
cost = trade_cost(np.array([r["spread"] for r in rows]), fee, 0.01)
action, kelly, net = decide(p, q, cost, lo, hi)
for i, r in enumerate(rows):
    r.update(q_yes=float(q[i]), q_low=float(lo[i]), q_high=float(hi[i]), action=str(action[i]),
             kelly_fraction=float(kelly[i]), net_edge=float(net[i]), cost=float(cost[i]))
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"made_at": now.isoformat(timespec="seconds"), "markets": rows}))
print(f"{len(rows)} markets ({int((fee > 0).sum())} with fees, {int((action != 'NO_TRADE').sum())} trades) -> {out}")
