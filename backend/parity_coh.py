"""COH parity fixture for extension-module/parity.mjs: the El Clasico book of Sat night (Barça / Draw / Real at
~60 / 16 / 25¢, 20 h out, sports, neg-risk) decided by the backend's live path (coherence_scales -> decide ->
one_bet_per_event). Writes backend/results/parity_coh.json; parity.mjs checks horizon.ts cohere() agrees."""
import json
from pathlib import Path

import horizon_mcp as H

BOOK = [("FC Barcelona", 0.59, 0.60), ("Draw", 0.15, 0.16), ("Real Madrid CF", 0.24, 0.25)]
legs = [{"group": "lal-bar-rea", "neg_risk": True, "price": round((b + a) / 2, 4), "hours": 20.0, "domain": "sports", "label": n,
         "spread": round(a - b, 4)} for n, b, a in BOOK]
scales = H.coherence_scales(legs)
ds = [H.decide(l["price"], l["hours"], l["domain"], l["spread"], fee_rate=0.0, q_scale=s) for l, s in zip(legs, scales)]
H.one_bet_per_event(ds, [l["group"] for l in legs], [l["label"] for l in legs])
out = [{"label": l["label"], "bid": b, "ask": a, "q": round(d["q"], 6), "action": d["action"]} for l, (_, b, a), d in zip(legs, BOOK, ds)]
Path(__file__).parent.joinpath("results", "parity_coh.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out))
# Under 12 h: the same longshot that trades at 20 h gets no call at 8 h (nothing that short was ever tested).
short = [{"price": p, "hours": h, "action": d["action"], "untested": bool(d.get("untested"))}
         for p, h in ((0.2, 20.0), (0.2, 8.0), (0.6, 3.0)) for d in [H.decide(p, h, "sports", 0.01, fee_rate=0.0)]]
Path(__file__).parent.joinpath("results", "parity_untested.json").write_text(json.dumps(short, indent=1))
print(json.dumps(short))
