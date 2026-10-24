// Horizon in the browser: the same calibration map and decision rule as backend/model.py,
// computed from the fitted coefficients served by GET /api/model. No backend call per market.
// Parity with Python is checked by extension-module/parity.mjs.

export type Model = {
  main: Fit;
  boot: Fit[];
  interval_percentiles: [number, number];
  tradable: [number, number];
  min_half_spread: number;
  eps: number;
  kelly_scale: number;
  kelly_cap: number;
  domain_tags: [string, string[]][];
  by_horizon: { horizon_hours: number; mean_return_per_trade: number }[];
};
type Fit = { intercept: number; coef: number[] };

export type Action = "BUY_YES" | "BUY_NO" | "NO_TRADE";
export type Decision = {
  price: number; hours: number; domain: string; cost: number;
  q: number; lo: number; hi: number; action: Action; kelly: number; netEdge: number; reason: string;
};

const clip = (x: number, a: number, b: number) => Math.min(Math.max(x, a), b);

function features(m: Model, price: number, hours: number) {
  const p = clip(price, m.eps, 1 - m.eps);
  const lp = Math.log(p / (1 - p));
  const lh = Math.log(clip(hours, 12, 720) / 24); // stay inside the trained range
  return [lp, lh, lp * lh];
}

const prob = (f: Fit, x: number[]) => 1 / (1 + Math.exp(-(f.intercept + f.coef.reduce((s, c, i) => s + c * x[i], 0))));

// numpy.percentile with the default linear interpolation.
function percentile(values: number[], pct: number) {
  const s = [...values].sort((a, b) => a - b);
  const k = (s.length - 1) * (pct / 100);
  const f = Math.floor(k), c = Math.ceil(k);
  return f === c ? s[f] : s[f] + (s[c] - s[f]) * (k - f);
}

export function domainOf(m: Model, tagSlugs: string[]) {
  const slugs = new Set(tagSlugs);
  for (const [domain, keys] of m.domain_tags) if (keys.some((k) => slugs.has(k))) return domain;
  return "other";
}

const pct = (x: number) => `${Math.round(x * 100)}%`;
function horizonLabel(h: number) {
  return h >= 48 ? `${Math.round(h / 24)}d` : `${Math.max(1, Math.round(h))}h`;
}

/** price = order-book mid, spread = ask - bid (NaN if unknown), hours = to the scheduled end. */
export function decide(m: Model, price: number, hours: number, domain: string, spread: number): Decision {
  const cost = Number.isFinite(spread) ? Math.max(spread / 2, m.min_half_spread) : m.min_half_spread;
  const inBand = price >= m.tradable[0] && price <= m.tradable[1];
  if (!inBand) {
    return { price, hours, domain, cost, q: price, lo: price, hi: price, action: "NO_TRADE", kelly: 0, netEdge: 0,
      reason: `Market at ${(price * 100).toFixed(1)}%: too close to certain, a ${Math.round(cost * 100)}¢ cost exceeds any edge` };
  }
  const x = features(m, price, hours);
  const q = prob(m.main, x);
  const qs = m.boot.map((f) => prob(f, x));
  const lo = percentile(qs, m.interval_percentiles[0]);
  const hi = percentile(qs, m.interval_percentiles[1]);

  const buyYes = lo - (price + cost);
  const buyNo = (price - cost) - hi;
  const action: Action = buyYes > 0 ? "BUY_YES" : buyNo > 0 ? "BUY_NO" : "NO_TRADE";
  const qc = action === "BUY_YES" ? lo : action === "BUY_NO" ? hi : q;
  const py = clip(price + cost, m.eps, 1 - m.eps), pn = clip(1 - price + cost, m.eps, 1 - m.eps);
  const raw = action === "BUY_YES" ? (qc - py) / (1 - py) : action === "BUY_NO" ? ((1 - qc) - pn) / (1 - pn) : 0;
  const kelly = clip(raw * m.kelly_scale, 0, m.kelly_cap);
  const netEdge = action === "BUY_NO" ? buyNo : buyYes;
  const gap = Math.abs(q - price) * 100;
  const reason = action === "NO_TRADE"
    ? `Model ${pct(q)} (range ${pct(lo)}–${pct(hi)}) vs market ${pct(price)}: the ${gap.toFixed(1)}¢ gap is inside the model's uncertainty plus ${Math.round(cost * 100)}¢ cost`
    : `${horizonLabel(hours)} out, ${domain}: model ${pct(q)} vs market ${pct(price)}, net edge ${(netEdge * 100).toFixed(1)}¢`;
  return { price, hours, domain, cost, q, lo, hi, action, kelly, netEdge, reason };
}

// ---------- Gamma ----------

export type Leg = { question: string; decision?: Decision; skip?: string };

const GAMMA = "https://gamma-api.polymarket.com";

/** All binary legs of a Polymarket event page, each with Horizon's decision (or why it is skipped). */
export async function decideEvent(m: Model, slug: string, now = new Date()): Promise<{ title: string; legs: Leg[] }> {
  const res = await fetch(`${GAMMA}/events?slug=${encodeURIComponent(slug)}`);
  if (!res.ok) throw new Error(`Gamma ${res.status}`);
  const [event] = await res.json();
  if (!event) throw new Error("event not found");
  const eventTags = (event.tags ?? []).map((t: { slug: string }) => t.slug);
  const legs: Leg[] = (event.markets ?? []).map((mk: Record<string, any>) => {
    const question = mk.question as string;
    let outcomes: string[] = [];
    try { outcomes = JSON.parse(mk.outcomes ?? "[]").map((o: string) => o.toLowerCase()); } catch { /* not binary */ }
    if (outcomes.join() !== "yes,no") return { question, skip: "not a yes/no market" };
    if (mk.closed || !mk.acceptingOrders) return { question, skip: "closed" };
    const bid = Number(mk.bestBid), ask = Number(mk.bestAsk);
    if (!(bid > 0 && bid < ask && ask < 1)) return { question, skip: "no two-sided order book" };
    const end = new Date(mk.endDate ?? event.endDate);
    const hours = (end.getTime() - now.getTime()) / 3.6e6;
    if (!(hours > 0)) return { question, skip: "past its end date" };
    const tags = [...(mk.tags ?? []).map((t: { slug: string }) => t.slug), ...eventTags];
    return { question, decision: decide(m, (bid + ask) / 2, hours, domainOf(m, tags), ask - bid) };
  });
  return { title: event.title, legs };
}

/** "Edge per trade is largest at 12h" from the backtest, for the card's "when" line. */
export function bestHorizon(m: Model) {
  return [...m.by_horizon].sort((a, b) => b.mean_return_per_trade - a.mean_return_per_trade)[0];
}
