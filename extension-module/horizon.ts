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
  fee_rates?: Record<string, number>; // taker fee rate by domain, used when a market has no feeSchedule
  policy?: Policy; // V3: min net edge + enter only within enter_from_hours of the end
  version?: string;
};
/** Trading rule chosen on validation (integrations/playoff): V3 = net edge >= 1¢ and within 24 h of the end. */
export type Policy = { name?: string; min_edge?: number; enter_from_hours?: number | null };
export const WAIT_REASON = "Wait: best time is within 24h of the end";

/** Polymarket taker fee per share = rate * (p(1-p))^exponent (docs.polymarket.com/trading/fees). */
export type Fee = { rate: number; exponent: number };
type Fit = { intercept: number; coef: number[] };

export type Action = "BUY_YES" | "BUY_NO" | "NO_TRADE";
export type Decision = {
  price: number; hours: number; domain: string; cost: number;
  q: number; lo: number; hi: number; action: Action; kelly: number; netEdge: number; reason: string;
  /** true when the edge is there but the rule says enter later; wouldBe = the action then. */
  wait: boolean; wouldBe: Action | null; checkBackInHours: number | null;
  /** One bet per event: set when another outcome of the same event has the larger edge. */
  blockedBy?: string;
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

const domainFeeRate = (m: Model, domain: string) => m.fee_rates?.[domain] ?? m.fee_rates?.other ?? 0;

/** A Gamma market's taker fee: its own feeSchedule, else the model's domain rate; zero when fees are off. */
export function feeOf(m: Model, mk: Record<string, any>, domain: string): Fee {
  if (!mk.feesEnabled) return { rate: 0, exponent: 1 };
  const s = mk.feeSchedule ?? {};
  return { rate: typeof s.rate === "number" ? s.rate : domainFeeRate(m, domain), exponent: Number(s.exponent) || 1 };
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

/** price = order-book mid, spread = ask - bid (NaN if unknown), hours = to the scheduled end.
 *  fee = feeOf(m, market, domain); omitted = the domain's rate (as if fees are on). */
export function decide(m: Model, price: number, hours: number, domain: string, spread: number,
  fee: Fee = { rate: domainFeeRate(m, domain), exponent: 1 }, policy: Policy | false = m.policy ?? {}): Decision {
  const pol: Policy = policy || {};
  const feePerShare = fee.rate * Math.pow(price * (1 - price), fee.exponent);
  const cost = (Number.isFinite(spread) ? Math.max(spread / 2, m.min_half_spread) : m.min_half_spread) + feePerShare;
  const inBand = price >= m.tradable[0] && price <= m.tradable[1];
  if (!inBand) {
    return { price, hours, domain, cost, q: price, lo: price, hi: price, action: "NO_TRADE", kelly: 0, netEdge: 0, wait: false, wouldBe: null, checkBackInHours: null,
      reason: `Market at ${(price * 100).toFixed(1)}%: too close to certain, a ${Math.round(cost * 100)}¢ cost exceeds any edge` };
  }
  const x = features(m, price, hours);
  const q = prob(m.main, x);
  const qs = m.boot.map((f) => prob(f, x));
  const lo = percentile(qs, m.interval_percentiles[0]);
  const hi = percentile(qs, m.interval_percentiles[1]);
  return decideWithQ(m, price, q, lo, hi, hours, domain, spread, fee, policy);
}

/** The decision rule for a given probability and band (used by decide and by event coherence). */
export function decideWithQ(m: Model, price: number, q: number, lo: number, hi: number, hours: number, domain: string, spread: number,
  fee: Fee = { rate: domainFeeRate(m, domain), exponent: 1 }, policy: Policy | false = m.policy ?? {}): Decision {
  const pol: Policy = policy || {};
  const feePerShare = fee.rate * Math.pow(price * (1 - price), fee.exponent);
  const cost = (Number.isFinite(spread) ? Math.max(spread / 2, m.min_half_spread) : m.min_half_spread) + feePerShare;
  const inBand = price >= m.tradable[0] && price <= m.tradable[1];
  if (!inBand) {
    return { price, hours, domain, cost, q: price, lo: price, hi: price, action: "NO_TRADE", kelly: 0, netEdge: 0, wait: false, wouldBe: null, checkBackInHours: null,
      reason: `Market at ${(price * 100).toFixed(1)}%: too close to certain, a ${Math.round(cost * 100)}¢ cost exceeds any edge` };
  }

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
  const base: Decision = { price, hours, domain, cost, q, lo, hi, action, kelly, netEdge, reason, wait: false, wouldBe: null, checkBackInHours: null };
  if (action !== "NO_TRADE" && netEdge < (pol.min_edge ?? 0)) {
    return { ...base, action: "NO_TRADE", kelly: 0,
      reason: `Net edge ${(netEdge * 100).toFixed(1)}¢ is under the ${Math.round((pol.min_edge ?? 0) * 100)}¢ minimum: not worth the risk` };
  }
  if (action !== "NO_TRADE" && pol.enter_from_hours != null && hours > pol.enter_from_hours) {
    return { ...base, action: "NO_TRADE", kelly: 0, wait: true, wouldBe: action, reason: WAIT_REASON,
      checkBackInHours: Math.round((hours - pol.enter_from_hours) * 10) / 10 };
  }
  return base;
}

// ---------- Gamma ----------

export type Leg = { question: string; label: string; marketSlug?: string; bid?: number; ask?: number; decision?: Decision; skip?: string; fee?: Fee };

/**
 * COH: on a negRisk event (outcomes are mutually exclusive), when >= 2 open priced legs have mid
 * prices summing to [0.95, 1.25], Horizon's probabilities are scaled to sum to 1 (each band keeps
 * its offsets from the model's q), and every leg is re-decided with the same V3 rule. Then ONE BET
 * PER EVENT: only the leg with the largest net edge keeps its call (now or after its wait).
 */
export function cohere(m: Model, legs: Leg[], negRisk: boolean): Leg[] {
  const priced = legs.filter((l) => l.decision && l.bid !== undefined && l.ask !== undefined);
  let out = legs;
  const mids = priced.reduce((s, l) => s + l.decision!.price, 0);
  if (negRisk && priced.length >= 2 && mids >= 0.95 && mids <= 1.25) {
    const sumQ = priced.reduce((s, l) => s + l.decision!.q, 0);
    out = legs.map((l) => {
      if (!priced.includes(l) || !(sumQ > 0)) return l;
      const d0 = l.decision!;
      const q = clip(d0.q / sumQ, 1e-4, 1 - 1e-4);
      const lo = clip(q - (d0.q - d0.lo), 1e-4, 1 - 1e-4), hi = clip(q + (d0.hi - d0.q), 1e-4, 1 - 1e-4);
      return { ...l, decision: decideWithQ(m, d0.price, q, lo, hi, d0.hours, d0.domain, (l.ask as number) - (l.bid as number), l.fee) };
    });
  }
  return onePerEvent(out);
}

/** Keep the call only on the leg with the largest net edge (trades and waits alike). */
export function onePerEvent(legs: Leg[]): Leg[] {
  const wants = (d?: Decision) => !!d && (d.action !== "NO_TRADE" || (d.wait && !!d.wouldBe));
  const best = legs.filter((l) => wants(l.decision)).sort((a, b) => b.decision!.netEdge - a.decision!.netEdge)[0];
  if (!best) return legs;
  return legs.map((l) => (l === best || !wants(l.decision) ? l : {
    ...l, decision: { ...l.decision!, action: "NO_TRADE", kelly: 0, wait: false, wouldBe: null, checkBackInHours: null, blockedBy: best.label,
      reason: `One bet per event: ${best.label} has the larger edge` },
  }));
}

const GAMMA = "https://gamma-api.polymarket.com";

/** All binary legs of a Polymarket event page, each with Horizon's decision (or why it is skipped). */
export async function decideEvent(m: Model, slug: string, now = new Date()): Promise<{ title: string; legs: Leg[]; tags: string[]; endDate?: string }> {
  const res = await fetch(`${GAMMA}/events?slug=${encodeURIComponent(slug)}`);
  if (!res.ok) throw new Error(`Gamma ${res.status}`);
  const [event] = await res.json();
  if (!event) throw new Error("event not found");
  const eventTags = (event.tags ?? []).map((t: { slug: string }) => t.slug);
  const legs: Leg[] = (event.markets ?? []).map((mk: Record<string, any>) => {
    const question = mk.question as string;
    const label = (mk.groupItemTitle as string) || question;
    let outcomes: string[] = [];
    try { outcomes = JSON.parse(mk.outcomes ?? "[]").map((o: string) => o.toLowerCase()); } catch { /* not binary */ }
    if (outcomes.join() !== "yes,no") return { question, label, skip: "not a yes/no market" };
    if (mk.closed || !mk.acceptingOrders) return { question, label, skip: "closed" };
    const bid = Number(mk.bestBid), ask = Number(mk.bestAsk);
    if (!(bid > 0 && bid < ask && ask < 1)) return { question, label, skip: "no two-sided order book" };
    const end = new Date(mk.endDate ?? event.endDate);
    const hours = (end.getTime() - now.getTime()) / 3.6e6;
    if (!(hours > 0)) return { question, label, skip: "past its end date" };
    const tags = [...(mk.tags ?? []).map((t: { slug: string }) => t.slug), ...eventTags];
    const domain = domainOf(m, tags);
    const fee = feeOf(m, mk, domain);
    return { question, label, marketSlug: mk.slug as string, bid, ask, fee, decision: decide(m, (bid + ask) / 2, hours, domain, ask - bid, fee) };
  });
  return { title: event.title, legs: cohere(m, legs, !!(event.negRisk ?? event.enableNegRisk)), tags: eventTags, endDate: event.endDate };
}

/** One bet per event in ranked lists: after sorting best-first, keep only the first row of each event (in place). */
export function dedupeEvents<T extends { slug: string }>(rows: T[]) {
  const seen = new Set<string>();
  for (let i = 0; i < rows.length; i++) {
    if (seen.has(rows[i].slug)) rows.splice(i--, 1);
    else seen.add(rows[i].slug);
  }
  return rows;
}

/** "Edge per trade is largest at 12h" from the backtest, for the card's "when" line. */
export function bestHorizon(m: Model) {
  return [...m.by_horizon].sort((a, b) => b.mean_return_per_trade - a.mean_return_per_trade)[0];
}

// ---------- scan (same filters as backend/horizon_mcp.py horizon_scan) ----------

export type ScanRow = { question: string; slug: string; url: string; decision: Decision };

/** Open yes/no markets with a tag, ending within `withinHours`, two-sided book, in the band, ranked by net edge. */
export async function scanTag(m: Model, tag: string, withinHours = 24, top = 5, pages = 10, now = new Date()):
  Promise<{ rows: ScanRow[]; scanned: number; priced: number; trades: number }> {
  const t = await fetch(`${GAMMA}/tags/slug/${encodeURIComponent(tag)}`);
  if (!t.ok) throw new Error(`unknown tag ${tag}`);
  const { id } = await t.json();
  const end = new Date(now.getTime() + withinHours * 3.6e6);
  const base = new URLSearchParams({
    tag_id: String(id), related_tags: "true", closed: "false", include_tag: "true", limit: "100",
    order: "volume24hr", ascending: "false", end_date_min: now.toISOString(), end_date_max: end.toISOString(),
  });
  const batches = await Promise.all(Array.from({ length: pages }, (_, i) =>
    fetch(`${GAMMA}/markets?${base}&offset=${i * 100}`).then((r) => (r.ok ? r.json() : [])).catch(() => [])));
  const seen = new Set<string>();
  const rows: ScanRow[] = [];
  for (const mk of batches.flat() as Record<string, any>[]) {
    if (seen.has(mk.id)) continue;
    seen.add(mk.id);
    let outcomes: string[] = [];
    try { outcomes = JSON.parse(mk.outcomes ?? "[]").map((o: string) => o.toLowerCase()); } catch { /* skip */ }
    if (outcomes.join() !== "yes,no" || mk.closed || !mk.acceptingOrders) continue;
    const bid = Number(mk.bestBid), ask = Number(mk.bestAsk);
    if (!(bid > 0 && bid < ask && ask < 1)) continue;
    const hours = (new Date(mk.endDate).getTime() - now.getTime()) / 3.6e6;
    const price = (bid + ask) / 2;
    if (!(hours > 0 && hours <= withinHours) || price < m.tradable[0] || price > m.tradable[1]) continue;
    const tags = (mk.tags ?? []).map((x: { slug: string }) => x.slug);
    const slug = mk.events?.[0]?.slug ?? mk.slug;
    const domain = domainOf(m, tags);
    rows.push({ question: mk.question, slug, url: `https://polymarket.com/event/${slug}`,
      decision: decide(m, price, hours, domain, ask - bid, feeOf(m, mk, domain)) });
  }
  rows.sort((a, b) => b.decision.netEdge - a.decision.netEdge);
  dedupeEvents(rows);
  const trades = rows.filter((r) => r.decision.action !== "NO_TRADE");
  return { rows: (trades.length ? trades : rows).slice(0, top), scanned: seen.size, priced: rows.length, trades: trades.length };
}

// ---------- bridge: prediction markets about any page ----------

const CRYPTO: Record<string, string> = {
  btc: "bitcoin", xbt: "bitcoin", bitcoin: "bitcoin", eth: "ethereum", ether: "ethereum", ethereum: "ethereum",
  sol: "solana", solana: "solana", xrp: "xrp", ripple: "xrp", doge: "dogecoin", dogecoin: "dogecoin",
  bnb: "bnb", ada: "cardano", cardano: "cardano", hype: "hyperliquid", hyperliquid: "hyperliquid",
};
const STOP = new Set(("a an the and or of to in on for at by with from as is are was were be been it its this that these those " +
  "news live latest today update updates video watch price prices chart charts market markets usd usdt live-score score " +
  "vs v how why what when who will would could should can may new after over under into about says say said report").split(" "));
const SITE = /\b(bbc|reuters|cnn|guardian|nytimes|new york times|bloomberg|coingecko|coinmarketcap|binance|tradingview|espn|sky sports|the athletic|ap news|associated press|politico|fox news|yahoo|google)\b/i;

/** The page's subject as a search query: a crypto name from tickers/pairs, else the title's distinctive words. */
export function subjectOf(title = "", url = ""): { query: string; crypto: boolean } | undefined {
  const text = `${url} ${title}`.toLowerCase();
  for (const tok of text.split(/[^a-z0-9]+/)) {
    const base = tok.replace(/(usdt|usdc|busd|usd|perp|eur|gbp)$/, "");
    if (CRYPTO[tok] || (base !== tok && CRYPTO[base])) return { query: CRYPTO[tok] ?? CRYPTO[base], crypto: true };
  }
  const segs = title.split(/\s+[-|–—:·]\s+/).filter((s) => !SITE.test(s) || s.split(/\s+/).length > 3);
  const main = (segs.sort((a, b) => b.length - a.length)[0] ?? title).replace(/[“”"'‘’?!.,()]/g, " ");
  const words = main.split(/\s+/).filter((w) => w.length > 2 && !STOP.has(w.toLowerCase()) && !/^\d+$/.test(w));
  const capital = words.filter((w) => /^[A-Z]/.test(w));
  const pick = (capital.length >= 2 ? capital : words).slice(0, 3);
  return pick.length ? { query: pick.join(" "), crypto: false } : undefined;
}

/** Open yes/no Polymarket legs matching a query (Gamma public-search), with Horizon's decision, best first. */
export async function searchMarkets(m: Model, query: string, top = 6, now = new Date()): Promise<ScanRow[]> {
  const res = await fetch(`${GAMMA}/public-search?${new URLSearchParams({ q: query, limit_per_type: "12", events_status: "active" })}`);
  if (!res.ok) throw new Error(`Gamma ${res.status}`);
  const { events = [] } = await res.json();
  const rows: (ScanRow & { volume: number })[] = [];
  const seen = new Set<string>();
  for (const ev of events as Record<string, any>[]) {
    const tags = (ev.tags ?? []).map((t: { slug: string }) => t.slug);
    for (const mk of (ev.markets ?? []) as Record<string, any>[]) {
      let outcomes: string[] = [];
      try { outcomes = JSON.parse(mk.outcomes ?? "[]").map((o: string) => o.toLowerCase()); } catch { /* skip */ }
      if (outcomes.join() !== "yes,no" || mk.closed || mk.acceptingOrders === false || seen.has(mk.id)) continue;
      seen.add(mk.id);
      const bid = Number(mk.bestBid), ask = Number(mk.bestAsk);
      if (!(bid > 0 && bid < ask && ask < 1)) continue;
      const hours = (new Date(mk.endDate ?? ev.endDate).getTime() - now.getTime()) / 3.6e6;
      const price = (bid + ask) / 2;
      if (!(hours > 0) || price < m.tradable[0] || price > m.tradable[1]) continue;
      const domain = tags.length ? domainOf(m, tags) : (/bitcoin|ethereum|solana|xrp|crypto/i.test(ev.title) ? "crypto" : "other");
      rows.push({ question: mk.question, slug: ev.slug, url: `https://polymarket.com/event/${ev.slug}`,
        decision: decide(m, price, hours, domain, ask - bid, feeOf(m, mk, domain)), volume: Number(mk.volume24hr ?? mk.volumeNum ?? 0) });
    }
  }
  rows.sort((a, b) => b.decision.netEdge - a.decision.netEdge || b.volume - a.volume);
  dedupeEvents(rows);
  return rows.slice(0, top);
}
