// Parity: the TS module must reproduce the Python pipeline. Inputs and Python outputs come from a
// capsule seal or a fee fixture from backend/parity_fees.py (both computed by backend/model.py); coefficients from backend/results/model.json.
//   node extension-module/parity.mjs capsule/seal-<ts>.json
import { readFileSync } from "node:fs";
import { cohere, decide } from "./horizon.ts";

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

// Coherence (COH) case: a negRisk event with three legs whose mids sum into [0.95, 1.25] must come back
// with probabilities summing to 1, bands keeping their offsets, and at most one leg backed.
const legs = [[0.585, 0.59, 0.6], [0.155, 0.15, 0.16], [0.245, 0.24, 0.25]].map(([p, b, a], i) => ({
  question: `leg ${i}`, label: `leg ${i}`, bid: b, ask: a, fee: { rate: 0, exponent: 1 }, decision: decide(model, p, 20, "sports", a - b, { rate: 0, exponent: 1 }),
}));
const coh = cohere(model, legs, true);
const sumQ = coh.reduce((s, l) => s + l.decision.q, 0);
const offsetsKept = coh.every((l, i) => Math.abs((l.decision.q - l.decision.lo) - (legs[i].decision.q - legs[i].decision.lo)) < 1e-9 || l.decision.lo <= 1e-4);
const backed = coh.filter((l) => l.decision.action !== "NO_TRADE" || l.decision.wait).length;
const notNeg = cohere(model, legs, false).reduce((s, l) => s + l.decision.q, 0);
console.log(`COH: sum q ${sumQ.toFixed(6)} (was ${legs.reduce((s, l) => s + l.decision.q, 0).toFixed(4)}; not negRisk ${notNeg.toFixed(4)}) · offsets kept ${offsetsKept} · backed legs ${backed}`);
const cohOk = Math.abs(sumQ - 1) < 1e-6 && offsetsKept && backed <= 1;
process.exit(worst < 1e-4 && mismatched === 0 && cohOk ? 0 : 1);
