/**
 * Bets placed through Horizon, kept in chrome.storage.local: what Polymarket confirmed, marked to
 * the live mid price, settled at $1/$0 per share when Gamma reports the market resolved. The
 * user's budget ("bankroll") sizes suggested bets (¼ Kelly, max 5%) and caps a single bet.
 * Horizon only fills Polymarket's ticket; the user presses Trade. Nothing here moves money.
 */
import { decide, domainOf, feeOf, type Decision, type Fee, type Model } from './horizon';
import { isPaper } from './paper';

export type Side = 'YES' | 'NO';
export type Position = {
  id: string; marketSlug: string; eventSlug: string; question: string; label: string; side: Side;
  shares: number; stake: number; avgPrice: number; qAtOpen: number; openedAt: string; by: 'you' | 'agent';
  status: 'open' | 'closed' | 'settled'; exitPrice?: number; closedAt?: string; pnl?: number;
  mark?: number; markAt?: string; endDate?: string; feesPaid?: number; pmMessage?: string;
};
export type Account = {
  bankroll: number; positions: Position[];
};
export type Quote = {
  marketSlug: string; eventSlug: string; question: string; label: string; bid: number; ask: number;
  closed: boolean; settled?: 0 | 1; endDate?: string; decision?: Decision; domain?: string; fee?: Fee; conditionId?: string;
  /** Lifetime volume (USD) and when the real-world event starts (kick-off, rally), from Gamma. */
  volume?: number; startsAt?: string;
};

/** Two books with the same maths: 'real' (what the user placed on Polymarket) and 'paper' (practice, never on Polymarket). */
export type Book = 'real' | 'paper';
/** The book in use: paper while Paper trading is on (sizing, checks and budget then follow the paper book). */
export const activeBook = (): Book => (isPaper() ? 'paper' : 'real');
const keyOf = (book: Book = 'real') => (book === 'paper' ? 'horizonPaper' : 'horizonLedger');
const GAMMA = 'https://gamma-api.polymarket.com';
export const fresh = (bankroll = 1000): Account => ({ bankroll, positions: [] });

/** Older builds stored a daily loss limit (and a demo account) that could block betting: drop them. */
export function migrate() {
  void chrome.storage.local.remove(['horizonDemo', 'horizonBankroll']).catch(() => {});
  return mutate((a) => { const x = a as Account & { lossLimitPct?: number; day?: unknown }; delete x.lossLimitPct; delete x.day; });
}

// ---------- storage, serialised so parallel calls never clobber each other ----------

let chain: Promise<unknown> = Promise.resolve();
export async function getAccount(book: Book = activeBook()): Promise<Account> {
  const KEY = keyOf(book);
  const r = await chrome.storage.local.get(KEY).catch(() => ({} as Record<string, unknown>));
  return (r[KEY] as Account | undefined) ?? fresh();
}
export function mutate<T>(fn: (a: Account) => Promise<T> | T, book: Book = 'real'): Promise<T> {
  const KEY = keyOf(book);
  const run = chain.then(async () => {
    const a = await getAccount(book);
    const out = await fn(a);
    await chrome.storage.local.set({ [KEY]: a });
    return out;
  });
  chain = run.catch(() => undefined);
  return run;
}
export function onAccount(cb: (a: Account) => void, book: Book = activeBook()) {
  const KEY = keyOf(book);
  const l = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
    if (area === 'local' && changes[KEY]?.newValue) cb(changes[KEY].newValue as Account);
  };
  chrome.storage.onChanged.addListener(l);
  return () => chrome.storage.onChanged.removeListener(l);
}

// ---------- prices ----------

const parse = (s: unknown): string[] => { try { return JSON.parse(String(s ?? '[]')); } catch { return []; } };

/** Training floor: every market in the 34,677-market training/test set had at least this lifetime volume. */
export const MIN_TRAINED_VOLUME = 100_000;
export function context(mk: Record<string, any>): { volume: number; startsAt?: string } {
  const ev = mk.events?.[0];
  const raw = (mk.gameStartTime as string | undefined)?.replace(' ', 'T').replace(/\+00$/, 'Z') ?? ev?.startTime ?? ev?.eventStartTime ?? undefined;
  return { volume: Number(mk.volumeNum ?? mk.volume ?? 0), startsAt: raw && !Number.isNaN(Date.parse(raw)) ? raw : undefined };
}
/** Why Horizon should not advise here, or undefined: the event is already under way, or the market is smaller than any it was tested on. */
export function caution(q: { volume?: number; startsAt?: string; endDate?: string }, now = Date.now()): string | undefined {
  const start = q.startsAt ? Date.parse(q.startsAt) : NaN, end = q.endDate ? Date.parse(q.endDate) : NaN;
  if (start <= now && !(end <= now)) return 'Event in progress: the price already reflects what is happening.';
  if (q.volume !== undefined && q.volume < MIN_TRAINED_VOLUME) return `Smaller market than any Horizon was tested on ($${Math.round(q.volume).toLocaleString()} traded; every test market had $100k+).`;
  return undefined;
}

function toQuote(m: Model | undefined, mk: Record<string, any>, now = new Date()): Quote {
  const bid = Number(mk.bestBid), ask = Number(mk.bestAsk);
  const ev = mk.events?.[0];
  const prices = parse(mk.outcomePrices).map(Number);
  const settled = mk.closed && prices.length === 2 && (prices[0] === 1 || prices[1] === 1) ? (prices[0] === 1 ? 1 : 0) : undefined;
  const q: Quote = { marketSlug: mk.slug, eventSlug: ev?.slug ?? mk.slug, question: mk.question, label: mk.groupItemTitle || mk.question,
    bid, ask, closed: !!mk.closed, settled, endDate: mk.endDate ?? ev?.endDate, conditionId: mk.conditionId, ...context(mk) };
  const hours = (new Date(q.endDate ?? 0).getTime() - now.getTime()) / 3.6e6;
  const binary = parse(mk.outcomes).map((o) => o.toLowerCase()).join() === 'yes,no';
  if (m && binary && !mk.closed && mk.acceptingOrders !== false && bid > 0 && bid < ask && ask < 1 && hours > 0) {
    const tags = [...(mk.tags ?? []), ...(ev?.tags ?? [])].map((t: { slug: string }) => t.slug);
    q.domain = domainOf(m, tags);
    q.fee = feeOf(m, mk, q.domain);
    q.decision = decide(m, (bid + ask) / 2, hours, q.domain, ask - bid, q.fee);
  }
  return q;
}

/** Live quotes by market slug (open and closed markets; Gamma hides closed ones unless asked). */
export async function quotes(m: Model | undefined, slugs: string[]): Promise<Map<string, Quote>> {
  const out = new Map<string, Quote>();
  const uniq = [...new Set(slugs)].filter(Boolean);
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

/** What one share costs (buy) or brings (sell) at the touch: the spread is paid. */
export const fillPrice = (q: Pick<Quote, 'bid' | 'ask'>, side: Side, buy: boolean) =>
  buy ? (side === 'YES' ? q.ask : 1 - q.bid) : (side === 'YES' ? q.bid : 1 - q.ask);
const mid = (q: Pick<Quote, 'bid' | 'ask'>, side: Side) => (side === 'YES' ? (q.bid + q.ask) / 2 : 1 - (q.bid + q.ask) / 2);
/** Polymarket taker fee per share at price p, the same schedule decide() charges (feeOf). */
export const feePerShare = (q: Pick<Quote, 'fee'>, p: number) => (q.fee ? q.fee.rate * Math.pow(p * (1 - p), q.fee.exponent) : 0);

export const markValue = (p: Position) => p.shares * (p.mark ?? p.avgPrice);
/** Total result of every bet placed through Horizon: realised + marked to market. */
export function pnlTotal(a: Account) {
  return a.positions.reduce((s, p) => s + (p.pnl ?? 0) + (p.status === 'open' ? markValue(p) - p.stake : 0), 0);
}
export const inPlay = (a: Account) => a.positions.filter((p) => p.status === 'open').reduce((s, p) => s + p.stake, 0);
/** Horizon's suggested bet in dollars: ¼ Kelly of the budget (already capped at 5%). */
export const suggested = (a: Account, d: Decision) => Math.floor(d.kelly * a.bankroll * 100) / 100;

/** Monte Carlo over bets using Horizon's q for each side: expected P&L and P(end down). */
export function outlook(bets: { shares: number; stake: number; pWin: number; value?: number }[], sims = 20000) {
  const ev = bets.reduce((s, b) => s + b.pWin * b.shares - (b.value ?? b.stake), 0);
  if (!bets.length) return { ev: 0, pDown: 0 };
  let down = 0;
  for (let k = 0; k < sims; k++) {
    let t = 0;
    for (const b of bets) t += (Math.random() < b.pWin ? b.shares : 0) - (b.value ?? b.stake);
    if (t < 0) down++;
  }
  return { ev, pDown: down / sims };
}
export const pWinOf = (d: Decision, side: Side) => (side === 'YES' ? d.q : 1 - d.q);

// ---------- guardrails (checked BEFORE anything happens on Polymarket) ----------

export type Check = { ok: true; amount: number; suggested: number; above: boolean; capped?: number; against?: boolean } | { ok: false; error: string };

/** The model must back the side (unless overridden). The amount is the user's: at least $1,
 *  never more than the budget, and it may exceed Horizon's suggestion (flagged as `above`). */
export function checkBet(a: Account, q: Quote, side: Side, amount: number | undefined, override = false): Check {
  const d = q.decision;
  if (q.closed || !d) return { ok: false, error: 'This market is closed or has no live price' };
  // A market Horizon will back once its window opens (V3 "wait") counts as backed for planning.
  const backs = (d.action !== 'NO_TRADE' ? d.action : d.wait ? d.wouldBe : null) === (side === 'YES' ? 'BUY_YES' : 'BUY_NO');
  if (!backs && !override) {
    return { ok: false, error: d.action === 'NO_TRADE' ? 'Horizon sees no advantage here after costs' : `Horizon backs ${d.action === 'BUY_YES' ? 'Yes' : 'No'} here, not ${side === 'YES' ? 'Yes' : 'No'}` };
  }
  // Polymarket's minimum is $1: a smaller suggestion becomes a $1 bet rather than none.
  const sug = backs ? Math.max(1, suggested(a, d)) : 0;
  let amt = amount ?? sug;
  let capped: number | undefined;
  if (amt > a.bankroll) { capped = amt; amt = a.bankroll; }
  amt = Math.floor(amt * 100) / 100;
  if (!(amt >= 1)) return { ok: false, error: 'The bet would be under $1, the smallest Polymarket takes' };
  return { ok: true, amount: amt, suggested: sug, above: amt > sug + 0.005, capped, against: !backs };
}

// ---------- recording what Polymarket confirmed ----------

export function recordBuy(q: Quote, side: Side, amount: number, by: 'you' | 'agent', pmMessage: string, book: Book = 'real') {
  return mutate((a) => {
    const d = q.decision;
    const px = fillPrice(q, side, true);
    const fee = feePerShare(q, px);
    const shares = amount / (px + fee);
    let pos = a.positions.find((p) => p.status === 'open' && p.marketSlug === q.marketSlug && p.side === side);
    if (pos) {
      pos.shares += shares; pos.stake += amount; pos.avgPrice = pos.stake / pos.shares; pos.feesPaid = (pos.feesPaid ?? 0) + shares * fee; pos.pmMessage = pmMessage;
    } else {
      pos = { id: Math.random().toString(36).slice(2, 8), marketSlug: q.marketSlug, eventSlug: q.eventSlug, question: q.question, label: q.label,
        side, shares, stake: amount, avgPrice: px, qAtOpen: d ? pWinOf(d, side) : px, openedAt: new Date().toISOString(), by, status: 'open',
        mark: mid(q, side), markAt: new Date().toISOString(), endDate: q.endDate, feesPaid: shares * fee, pmMessage };
      a.positions.unshift(pos);
    }
    return { ...pos };
  }, book);
}

/** Record a sale of `fraction` of a position that Polymarket confirmed. */
export function recordSell(q: Quote, id: string, fraction: number, pmMessage: string, book: Book = 'real') {
  return mutate((a) => {
    const p = a.positions.find((x) => x.id === id && x.status === 'open');
    if (!p) return undefined;
    const f = Math.min(Math.max(fraction, 0), 1);
    const px = fillPrice(q, p.side, false);
    const fee = feePerShare(q, px);
    const sh = p.shares * f, basis = p.stake * f;
    const proceeds = sh * (px - fee);
    const pnl = proceeds - basis;
    p.feesPaid = (p.feesPaid ?? 0) + sh * fee;
    p.pmMessage = pmMessage;
    if (f >= 0.999) Object.assign(p, { status: 'closed', exitPrice: px, closedAt: new Date().toISOString(), pnl: (p.pnl ?? 0) + pnl, mark: px });
    else { p.shares -= sh; p.stake -= basis; p.pnl = (p.pnl ?? 0) + pnl; }
    return { proceeds, pnl };
  }, book);
}

/** Forget a bet locally (it stays on Polymarket). */
export function forget(id: string) {
  return mutate((a) => { a.positions = a.positions.filter((p) => p.id !== id); });
}

/** Mark open bets to the live mid and settle the ones whose market has resolved. */
export function refresh(map: Map<string, Quote>, book: Book = 'real') {
  return mutate((a) => {
    for (const p of a.positions) {
      if (p.status !== 'open') continue;
      const q = map.get(p.marketSlug);
      if (!q) continue;
      if (q.closed && q.settled !== undefined) {
        const won = (q.settled === 1) === (p.side === 'YES');
        const payout = won ? p.shares : 0;
        Object.assign(p, { status: 'settled', exitPrice: won ? 1 : 0, closedAt: new Date().toISOString(), pnl: (p.pnl ?? 0) + payout - p.stake, mark: won ? 1 : 0 });
      } else if (q.bid > 0 && q.ask < 1) {
        p.mark = mid(q, p.side);
        p.markAt = new Date().toISOString();
      }
    }
  }, book);
}

/** Paper book: start again with $1,000 (or the given amount). */
export function resetPaper(bankroll = 1000) {
  return mutate((a) => { a.bankroll = bankroll; a.positions = []; }, 'paper');
}

export function setBankroll(n: number, book: Book = activeBook()) {
  return mutate((a) => { a.bankroll = Math.min(Math.max(n, 1), 1e7); }, book);
}
