// Parity: the TS module must reproduce the Python pipeline. Inputs and Python outputs come from a
// capsule seal or a fee fixture from backend/parity_fees.py (both computed by backend/model.py); coefficients from backend/results/model.json.
//   node extension-module/parity.mjs capsule/seal-<ts>.json
import { readFileSync } from "node:fs";
import { decide } from "./horizon.ts";

const model = JSON.parse(readFileSync(new URL("../backend/results/model.json", import.meta.url)));
const seal = JSON.parse(readFileSync(process.argv[2]));
let worst = 0, mismatched = 0;
for (const r of seal.markets) {
  // Seals predate fees (fee_rate absent -> 0); fee fixtures (backend/parity_fees.py) carry each market's schedule.
  const d = decide(model, r.price_yes, r.hours_to_resolution, r.domain, r.spread ?? NaN, { rate: r.fee_rate ?? 0, exponent: r.fee_exponent ?? 1 }, r.policy ?? false);  // seals: no fee, no policy
  worst = Math.max(worst, Math.abs(d.q - r.q_yes), Math.abs(d.lo - r.q_low), Math.abs(d.hi - r.q_high), Math.abs(d.netEdge - r.net_edge));
  if (d.action !== r.action) mismatched++;
}
console.log(`${seal.markets.length} markets · max |diff| ${worst.toExponential(2)} · action mismatches ${mismatched}`);
process.exit(worst < 1e-4 && mismatched === 0 ? 0 : 1);
