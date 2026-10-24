/**
 * Demo account: simulated money on live Polymarket prices. Persisted in chrome.storage.local.
 * Fills pay the spread (buy YES at the ask, NO at 1 − bid; sell YES at the bid, NO at 1 − ask),
 * open bets are marked to the live mid, and a bet settles at $1/$0 per share when Gamma reports
 * the market closed with a final outcome. Real outcomes, pretend dollars; nothing is ever sent
 * to Polymarket.
 */
import { decide, domainOf, type Decision, type Model } from './horizon';

export type Side = 'YES' | 'NO';
export type Position = {
  id: string; marketSlug: string; eventSlug: string; question: string; label: string; side: Side;
  shares: number; stake: number; avgPrice: number; spreadPaid: number; qAtOpen: number;
  openedAt: string; by: 'you' | 'agent';
  status: 'open' | 'closed' | 'settled'; exitPrice?: number; closedAt?: string; pnl?: number;
  mark?: number; markAt?: string; endDate?: string; feesPaid?: number;
};
export type Account = {
  start: number; cash: number; positions: Position[]; lossLimitPct: number;
  day: { date: string; equity: number };
};
export type Quote = {
  marketSlug: string; eventSlug: string; question: string; label: string; bid: number; ask: number;
  closed: boolean; settled?: 0 | 1; endDate?: string; decision?: Decision; domain?: string; feesEnabled?: boolean;
};

/**
 * decide() with the market's fee flag. The fee-aware horizon.ts (Agent ①) takes feesEnabled as a
 * 6th argument; the current one ignores it, so swapping horizon.ts in stays a file copy.
 */
export function decideQ(m: Model, price: number, hours: number, domain: string, spread: number, feesEnabled: boolean): Decision {
  return (decide as unknown as (...a: unknown[]) => Decision)(m, price, hours, domain, spread, feesEnabled);
}
/** Polymarket taker fee per share at price p: rate[domain] × feesEnabled × p(1−p) (0 until model.json has fee_rates). */
export function feePerShare(m: Model | undefined, q: Pick<Quote, 'domain' | 'feesEnabled'>, p: number) {
  const rates = (m as unknown as { fee_rates?: Record<string, number> } | undefined)?.fee_rates;
  if (!q.feesEnabled || !rates) return 0;
  const r = rates[q.domain ?? 'other'] ?? rates.other ?? 0;
  return r * p * (1 - p);
}

const KEY = 'horizonDemo';
const GAMMA = 'https://gamma-api.polymarket.com';
const today = () => new Date().toLocaleDateString('en-CA');
export const fresh = (start = 1000): Account => ({ start, cash: start, positions: [], lossLimitPct: 0.2, day: { date: today(), equity: start } });

// ---------- storage, serialised so the agent's parallel calls never clobber each other ----------

let chain: Promise<unknown> = Promise.resolve();
export async function getAccount(): Promise<Account> {
  const r = await chrome.storage.local.get(KEY).catch(() => ({} as Record<string, unknown>));
  const a = (r[KEY] as Account | undefined) ?? fresh();
  return a;
}
export function mutate<T>(fn: (a: Account) => Promise<T> | T): Promise<T> {
  const run = chain.then(async () => {
    const a = await getAccount();
    const out = await fn(a);
    await chrome.storage.local.set({ [KEY]: a });
    return out;
  });
  chain = run.catch(() => undefined);
  return run;
}
export function onAccount(cb: (a: Account) => void) {
  const l = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
    if (area === 'local' && changes[KEY]?.newValue) cb(changes[KEY].newValue as Account);
  };
  chrome.storage.onChanged.addListener(l);
  return () => chrome.storage.onChanged.removeListener(l);
}

// ---------- prices ----------

const parse = (s: unknown): string[] => { try { return JSON.parse(String(s ?? '[]')); } catch { return []; } };

function toQuote(m: Model | undefined, mk: Record<string, any>, now = new Date()): Quote {
  const bid = Number(mk.bestBid), ask = Number(mk.bestAsk);
  const ev = mk.events?.[0];
  const prices = parse(mk.outcomePrices).map(Number);
  const settled = mk.closed && prices.length === 2 && (prices[0] === 1 || prices[1] === 1) ? (prices[0] === 1 ? 1 : 0) : undefined;
  const q: Quote = { marketSlug: mk.slug, eventSlug: ev?.slug ?? mk.slug, question: mk.question, label: mk.groupItemTitle || mk.question,
    bid, ask, closed: !!mk.closed, settled, endDate: mk.endDate ?? ev?.endDate, feesEnabled: !!mk.feesEnabled };
  const hours = (new Date(q.endDate ?? 0).getTime() - now.getTime()) / 3.6e6;
  const binary = parse(mk.outcomes).map((o) => o.toLowerCase()).join() === 'yes,no';
  if (m && binary && !mk.closed && mk.acceptingOrders !== false && bid > 0 && bid < ask && ask < 1 && hours > 0) {
    const tags = [...(mk.tags ?? []), ...(ev?.tags ?? [])].map((t: { slug: string }) => t.slug);
    q.domain = domainOf(m, tags);
    q.decision = decideQ(m, (bid + ask) / 2, hours, q.domain, ask - bid, !!mk.feesEnabled);
  }
  return q;
}

/** Live quotes by market slug (open and closed markets; Gamma hides closed ones unless asked). */
export async function quotes(m: Model | undefined, slugs: string[]): Promise<Map<string, Quote>> {
  const out = new Map<string, Quote>();
  const uniq = [...new Set(slugs)];
  for (let i = 0; i < uniq.length; i += 20) {
    const part = uniq.slice(i, i + 20);
    const qs = part.map((s) => `slug=${encodeURIComponent(s)}`).join('&');
    const [open, closed] = await Promise.all([
      fetch(`${GAMMA}/markets?${qs}&include_tag=true`).then((r) => (r.ok ? r.json() : [])).catch(() => []),
      fetch(`${GAMMA}/markets?${qs}&closed=true`).then((r) => (r.ok ? r.json() : [])).catch(() => []),
    ]);
    for (const mk of [...closed, ...open] as Record<string, any>[]) out.set(mk.slug, toQuote(m, mk));
  }
  return out;
}

// ---------- maths ----------

export const fillPrice = (q: Pick<Quote, 'bid' | 'ask'>, side: Side, buy: boolean) =>
  buy ? (side === 'YES' ? q.ask : 1 - q.bid) : (side === 'YES' ? q.bid : 1 - q.ask);
const mid = (q: Pick<Quote, 'bid' | 'ask'>, side: Side) => (side === 'YES' ? (q.bid + q.ask) / 2 : 1 - (q.bid + q.ask) / 2);

export const markValue = (p: Position) => p.shares * (p.mark ?? p.avgPrice);
export function equity(a: Account) {
  return a.cash + a.positions.filter((p) => p.status === 'open').reduce((s, p) => s + markValue(p), 0);
}
export function rollDay(a: Account) {
  if (a.day.date !== today()) a.day = { date: today(), equity: equity(a) };
}
/** Today's loss so far as a fraction of the day's starting equity, and whether the limit is hit. */
export function lossToday(a: Account) {
  const base = a.day.date === today() ? a.day.equity : equity(a);
  const loss = Math.max(0, base - equity(a));
  return { loss, limit: base * a.lossLimitPct, hit: loss >= base * a.lossLimitPct - 1e-9 };
}
/** Horizon's suggested bet in dollars: ¼ Kelly of the current balance (already capped at 5%). */
export const suggested = (a: Account, d: Decision) => Math.floor(d.kelly * equity(a) * 100) / 100;

/** Monte Carlo over open bets using Horizon's q for each side: expected P&L and P(end down). */
export function outlook(bets: { shares: number; stake: number; pWin: number; value?: number }[], sims = 20000) {
  // P&L relative to the current value of each bet (value defaults to its stake, i.e. a new bet).
  const ev = bets.reduce((s, b) => s + b.pWin * b.shares - (b.value ?? b.stake), 0);
  if (!bets.length) return { ev: 0, pDown: 0, best: 0, worst: 0 };
  let down = 0;
  const totals: number[] = [];
  for (let k = 0; k < sims; k++) {
    let t = 0;
    for (const b of bets) t += (Math.random() < b.pWin ? b.shares : 0) - (b.value ?? b.stake);
    if (t < 0) down++;
    totals.push(t);
  }
  totals.sort((x, y) => x - y);
  return { ev, pDown: down / sims, worst: totals[Math.floor(sims * 0.05)], best: totals[Math.floor(sims * 0.95)] };
}
export const pWinOf = (d: Decision, side: Side) => (side === 'YES' ? d.q : 1 - d.q);

// ---------- actions (all inside mutate) ----------

export type BetResult = { ok: true; position: Position; capped?: number; note?: string } | { ok: false; error: string };

/** Open (or add to) a position. Guardrails: model must back the side, ≤ suggested unless override, cash, loss limit. */
export function placeBet(m: Model, q: Quote, side: Side, amount: number | undefined, by: 'you' | 'agent', override = false): Promise<BetResult> {
  return mutate((a) => {
    rollDay(a);
    const d = q.decision;
    if (q.closed || !d) return { ok: false as const, error: 'market is closed or has no two-sided price' };
    const backs = d.action === (side === 'YES' ? 'BUY_YES' : 'BUY_NO');
    if (!backs && !override) {
      return { ok: false as const, error: d.action === 'NO_TRADE' ? 'Horizon sees no advantage here after costs' : `Horizon backs ${d.action === 'BUY_YES' ? 'YES' : 'NO'}, not ${side}` };
    }
    if (lossToday(a).hit) return { ok: false as const, error: `daily loss limit reached (${Math.round(a.lossLimitPct * 100)}% of today's balance)` };
    const sug = backs ? suggested(a, d) : 0;
    let amt = amount ?? sug;
    let capped: number | undefined;
    if (!override && amt > sug + 0.005) { capped = amt; amt = sug; }
    amt = Math.min(amt, a.cash);
    amt = Math.floor(amt * 100) / 100;
    if (!(amt >= 0.5)) return { ok: false as const, error: amt < 0.5 && a.cash < 0.5 ? 'no demo cash left' : 'bet would be under $0.50' };
    const px = fillPrice(q, side, true);
    const fee = feePerShare(m, q, px);
    const shares = amt / (px + fee); // the stake covers price + taker fee
    const spreadPaid = shares * (px - mid(q, side));
    a.cash -= amt;
    let pos = a.positions.find((p) => p.status === 'open' && p.marketSlug === q.marketSlug && p.side === side);
    if (pos) {
      pos.shares += shares; pos.stake += amt; pos.avgPrice = pos.stake / pos.shares; pos.spreadPaid += spreadPaid; pos.feesPaid = (pos.feesPaid ?? 0) + shares * fee;
    } else {
      pos = { id: Math.random().toString(36).slice(2, 8), marketSlug: q.marketSlug, eventSlug: q.eventSlug, question: q.question, label: q.label,
        side, shares, stake: amt, avgPrice: px, spreadPaid, qAtOpen: pWinOf(d, side), openedAt: new Date().toISOString(), by, status: 'open',
        mark: mid(q, side), markAt: new Date().toISOString(), endDate: q.endDate, feesPaid: shares * fee };
      a.positions.unshift(pos);
    }
    return { ok: true as const, position: { ...pos }, capped, note: override && !backs ? 'against Horizon (your override)' : undefined };
  });
}

/** Sell `fraction` (0..1] of a position at the live bid side. */
export function sell(m: Model | undefined, q: Quote, id: string, fraction = 1): Promise<{ ok: boolean; error?: string; proceeds?: number; pnl?: number }> {
  return mutate((a) => {
    rollDay(a);
    const p = a.positions.find((x) => x.id === id && x.status === 'open');
    if (!p) return { ok: false, error: 'position not found or already closed' };
    if (q.closed || !(q.bid > 0 && q.ask < 1)) return { ok: false, error: 'market has no live price to sell into' };
    const f = Math.min(Math.max(fraction, 0), 1);
    const px = fillPrice(q, p.side, false);
    const sh = p.shares * f, basis = p.stake * f;
    const fee = feePerShare(m, q, px);
    const proceeds = sh * (px - fee);
    p.feesPaid = (p.feesPaid ?? 0) + sh * fee;
    a.cash += proceeds;
    const pnl = proceeds - basis;
    if (f >= 0.999) {
      Object.assign(p, { status: 'closed', exitPrice: px, closedAt: new Date().toISOString(), pnl: (p.pnl ?? 0) + pnl, shares: p.shares, mark: px });
    } else {
      p.shares -= sh; p.stake -= basis; p.pnl = (p.pnl ?? 0) + pnl; p.spreadPaid *= 1 - f;
    }
    return { ok: true, proceeds, pnl };
  });
}

/** Mark open bets to the live mid and settle the ones whose market has resolved. */
export function refresh(m: Model | undefined, map: Map<string, Quote>) {
  return mutate((a) => {
    const settledNow: Position[] = [];
    for (const p of a.positions) {
      if (p.status !== 'open') continue;
      const q = map.get(p.marketSlug);
      if (!q) continue;
      if (q.closed && q.settled !== undefined) {
        const won = (q.settled === 1) === (p.side === 'YES');
        const payout = won ? p.shares : 0;
        a.cash += payout;
        Object.assign(p, { status: 'settled', exitPrice: won ? 1 : 0, closedAt: new Date().toISOString(), pnl: (p.pnl ?? 0) + payout - p.stake, mark: won ? 1 : 0 });
        settledNow.push(p);
      } else if (q.bid > 0 && q.ask < 1) {
        p.mark = mid(q, p.side);
        p.markAt = new Date().toISOString();
      }
    }
    rollDay(a);
    void m;
    return settledNow;
  });
}

export function resetAccount(start: number, lossLimitPct?: number) {
  return mutate((a) => { const keep = lossLimitPct ?? a.lossLimitPct; Object.assign(a, fresh(start), { lossLimitPct: keep }); return a; });
}
export function setLossLimit(pct: number) {
  return mutate((a) => { a.lossLimitPct = Math.min(Math.max(pct, 0.01), 1); });
}
