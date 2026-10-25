/**
 * Horizon agent: plain-language tasks → a plan list of bets (or sells). Planning
 * uses Gemini via our API (POST /api/agent) with a deterministic parser as fallback. Every bet goes
 * through checkBet (Horizon's call; at least $1, at most the budget). The plan is shown as a
 * list; the panel sets up Polymarket's ticket for the top few, one at a time; the user presses Trade.
 */
import { cohere, decide, decideEventCached, searchMarkets, domainOf, feeOf, type Decision, type Model } from './horizon';
import { caution, context,
  checkBet, getAccount, inPlay, outlook, pnlTotal, pWinOf, quotes, refresh, setBankroll, suggested,
  type Position, type Quote, type Side,
} from './ledger';
import { fallbackHint, prepareOrder } from './prepareOrder';
import { markPage, stylePage } from './pageStyle';
import { intendedAction, verdictOf } from './policy';
import { fetchMe, openMyResults } from './me';
import { isPaper } from './paper';
import { localJournal } from './journal';

export const API = 'https://oxhack26-production.up.railway.app';
const GAMMA = 'https://gamma-api.polymarket.com';

/** kind = which thinking-orb animation the panel shows while this step runs. */
export type StepKind = 'searching' | 'working' | 'shaping' | 'solving';
export type Step = { id: number; text: string; status: 'run' | 'ok' | 'fail' | 'info'; detail?: string; kind?: StepKind };
export type PlanItem =
  | { kind: 'buy'; q: Quote; side: Side; amount: number; name: string; suggested?: number }
  | { kind: 'sell'; q: Quote; pos: Position; fraction: number; name: string };
export type Ctx = { model: Model; tabId?: number; onStep: (s: Step) => void; signal: { stop: boolean }; plan: PlanItem[] };

let stepId = 0;
export function stepper(ctx: Pick<Ctx, 'onStep'>, kind: StepKind = 'working') {
  return (text: string, status: Step['status'] = 'run', detail?: string) => {
    const s: Step = { id: ++stepId, text, status, detail, kind };
    ctx.onStep(s);
    return (status2: Step['status'], detail2?: string, text2?: string) => ctx.onStep({ ...s, status: status2, detail: detail2, text: text2 ?? s.text });
  };
}
export const money = (x: number) => `${x < 0 ? '−' : ''}$${Math.abs(x) >= 100 ? Math.round(Math.abs(x)).toLocaleString() : Math.abs(x).toFixed(2).replace(/\.00$/, '')}`;
const short = (s: string, n = 48) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
/** The leg label alone ("24°C", "<8M") means nothing out of context: use the question then. */
export const nameOf = (x: { label: string; question: string }) => (x.label && x.label !== x.question && x.label.length >= 14 ? x.label : x.question);
const sideOf = (d: Decision): Side | undefined => { const a = intendedAction(d); return a === 'BUY_YES' ? 'YES' : a === 'BUY_NO' ? 'NO' : undefined; };

// ---------- market scan ----------

export type MarketPick = Quote & { decision: Decision };

/** Open yes/no markets ending within `withinHours` (optionally under a Gamma tag), best advantage first. */
export async function scanMarkets(m: Model, tag = 'all', withinHours = 24, top = 10, now = new Date()): Promise<{ picks: MarketPick[]; scanned: number }> {
  const base = new URLSearchParams({ closed: 'false', include_tag: 'true', limit: '100', order: 'volume24hr', ascending: 'false',
    end_date_min: now.toISOString(), end_date_max: new Date(now.getTime() + withinHours * 3.6e6).toISOString() });
  if (tag && tag !== 'all') {
    const t = await fetch(`${GAMMA}/tags/slug/${encodeURIComponent(tag)}`);
    if (!t.ok) throw new Error(`unknown topic "${tag}"`);
    base.set('tag_id', String((await t.json()).id));
    base.set('related_tags', 'true');
  }
  const batches = await Promise.all(Array.from({ length: 6 }, (_, i) =>
    fetch(`${GAMMA}/markets?${base}&offset=${i * 100}`).then((r) => (r.ok ? r.json() : [])).catch(() => [])));
  const seen = new Set<string>();
  const negRisk = new Set<string>();
  const picks: MarketPick[] = [];
  for (const mk of batches.flat() as Record<string, any>[]) {
    if (seen.has(mk.id)) continue;
    seen.add(mk.id);
    let outcomes: string[] = [];
    try { outcomes = JSON.parse(mk.outcomes ?? '[]').map((o: string) => o.toLowerCase()); } catch { /* skip */ }
    if (outcomes.join() !== 'yes,no' || mk.closed || mk.acceptingOrders === false) continue;
    const bid = Number(mk.bestBid), ask = Number(mk.bestAsk);
    if (!(bid > 0 && bid < ask && ask < 1)) continue;
    const hours = (new Date(mk.endDate).getTime() - now.getTime()) / 3.6e6;
    const price = (bid + ask) / 2;
    // Out-of-band legs stay in (q = price) so an event's book sums the same way as on the site; dropped after coherence.
    if (!(hours > 0)) continue;
    const tags = (mk.tags ?? []).map((x: { slug: string }) => x.slug);
    const ev = mk.events?.[0];
    const domain = domainOf(m, tags);
    const fee = feeOf(m, mk, domain);
    const ctx = context(mk);
    // In progress: drop. Smaller than anything tested: keep as a book leg for coherence; cohere() gives it no call.
    const why = caution({ ...ctx, endDate: mk.endDate }, now.getTime());
    if (why && why.startsWith('Event in progress')) continue;
    picks.push({ marketSlug: mk.slug, eventSlug: ev?.slug ?? mk.slug, question: mk.question, label: mk.groupItemTitle || mk.question,
      bid, ask, closed: false, endDate: mk.endDate, domain, fee, ...ctx, decision: decide(m, price, hours, domain, ask - bid, fee) });
    if (mk.negRisk || ev?.negRisk) negRisk.add(ev?.slug ?? mk.slug);
  }
  // COH, exactly as /api/live: per event and end time, scale q across the legs (cohere), then one bet per event.
  const groups = new Map<string, MarketPick[]>();
  for (const p of picks) { const k = `${p.eventSlug}|${p.endDate}`; groups.set(k, [...(groups.get(k) ?? []), p]); }
  for (const g of groups.values()) {
    const legs = cohere(m, g.map((p) => ({ question: p.question, label: p.label, marketSlug: p.marketSlug, bid: p.bid, ask: p.ask, decision: p.decision, fee: p.fee, volume: p.volume })), negRisk.has(g[0].eventSlug));
    legs.forEach((l, i) => { if (l.decision) g[i].decision = l.decision; });
  }
  // Neg-risk events whose book in this scan is incomplete (thin legs outside the top markets, sum < 0.95): fetch the
  // whole event and decide it as the event page does, so the scan never ranks an un-normalised leg (Hull–Brentford).
  const incomplete = [...groups.values()].filter((g) => negRisk.has(g[0].eventSlug) && g.reduce((t, p) => t + p.decision.price, 0) < 0.95)
    .map((g) => g[0].eventSlug).filter((x, i, a) => a.indexOf(x) === i).slice(0, 60);
  for (let i = 0; i < incomplete.length; i += 8) {
    await Promise.all(incomplete.slice(i, i + 8).map(async (slug) => {
      try {
        const ev = await decideEventCached(m, slug);
        for (const p of picks) if (p.eventSlug === slug) { const l = ev.legs.find((x) => x.marketSlug === p.marketSlug); if (l?.decision) p.decision = l.decision; }
      } catch { /* keep the scan's own decision */ }
    }));
  }
  const inBand = picks.filter((p) => p.decision.price >= m.tradable[0] && p.decision.price <= m.tradable[1]);
  inBand.sort((a, b) => b.decision.netEdge - a.decision.netEdge);
  // One bet per event: the best leg of each event only.
  const events = new Set<string>();
  const one = inBand.filter((p) => verdictOf(p.decision) !== 'SKIP').filter((p) => (events.has(p.eventSlug) ? false : (events.add(p.eventSlug), true)));
  // The scan only sees the top markets by volume, so an event's thin legs (a $1.5k draw) can be missing from its book.
  // Re-decide each finalist from its whole event (decideEvent: every leg, COH, one bet per event), like the site.
  const checked = await Promise.all(one.slice(0, top * 2).map(async (p) => {
    try {
      const ev = await decideEventCached(m, p.eventSlug);
      const leg = ev.legs.find((l) => l.marketSlug === p.marketSlug);
      return leg?.decision ? { ...p, decision: leg.decision } : p;
    } catch { return p; }
  }));
  const final = checked.filter((p) => verdictOf(p.decision) !== 'SKIP').sort((a, b) => b.decision.netEdge - a.decision.netEdge);
  return { picks: final.slice(0, top), scanned: seen.size };
}

/**
 * Has the user already bet here? An open position in the book in use (paper or real) on this market or its event,
 * or a ticket set up / placed for this market in the last 48 h (local journal, same paper/real mode).
 * Returns a plain reason, or undefined. Every agent bet and the card go through this, so nothing is bet twice.
 */
export async function alreadyIn(q: Pick<Quote, 'marketSlug' | 'eventSlug'>): Promise<string | undefined> {
  const a = await getAccount();
  const pos = a.positions.find((p) => p.status === 'open' && (p.marketSlug === q.marketSlug || (!!q.eventSlug && p.eventSlug === q.eventSlug)));
  if (pos) return pos.marketSlug === q.marketSlug
    ? `already bet on this market (${pos.side === 'YES' ? 'Yes' : 'No'}, $${pos.stake.toFixed(2)})`
    : `already have a bet on this event (${pos.label || pos.question})`;
  const paper = isPaper();
  // The latest entry for this market decides: a ticket set up and then skipped is not a bet.
  const hit = (await localJournal()).filter((e) => e.slug === q.marketSlug && e.status !== 'shown' && (e.source === 'paper') === paper
    && Date.now() - Date.parse(e.ts) < 48 * 3.6e6).sort((x, y) => Date.parse(y.ts) - Date.parse(x.ts))[0];
  if (hit?.status === 'placed') return 'already bet on this market';
  if (hit?.status === 'set_up') return 'already set up a ticket for this market';
  return undefined;
}

async function quoteOne(m: Model, slug: string): Promise<Quote | undefined> {
  return withEventDecision(m, (await quotes(m, [slug])).get(slug));
}

/** A quote's decision made the COH way: from its whole event (cohere + one bet per event), not the market alone. */
export async function withEventDecision(m: Model, q?: Quote): Promise<Quote | undefined> {
  if (!q?.decision || !q.eventSlug) return q;
  try {
    const ev = await decideEventCached(m, q.eventSlug);
    const leg = ev.legs.find((l) => l.marketSlug === q.marketSlug);
    return leg?.decision ? { ...q, decision: leg.decision } : q;
  } catch { return q; }
}
async function findPosition(ref: string): Promise<Position | undefined> {
  const a = await getAccount();
  const open = a.positions.filter((p) => p.status === 'open');
  return open.find((p) => p.id === ref) ?? open.find((p) => p.marketSlug === ref) ?? open.find((p) => p.question.toLowerCase().includes(ref.toLowerCase()));
}

/** Expected result of a plan's buys, by Monte Carlo on Horizon's probabilities (markets independent). */
export function planOutlook(items: PlanItem[]) {
  const bets = items.filter((i): i is Extract<PlanItem, { kind: 'buy' }> => i.kind === 'buy').map((i) => {
    const px = i.side === 'YES' ? i.q.ask : 1 - i.q.bid;
    return { shares: i.amount / px, stake: i.amount, pWin: i.q.decision ? pWinOf(i.q.decision, i.side) : px };
  });
  return { ...outlook(bets), total: bets.reduce((s, b) => s + b.stake, 0), n: bets.length };
}

// ---------- tools (planning only: buys and sells go into the plan list) ----------

type Args = Record<string, any>;
export async function runTool(ctx: Ctx, name: string, args: Args): Promise<Record<string, unknown>> {
  const { model: m } = ctx;
  const step = stepper(ctx, name === 'scan_markets' || name === 'get_decision' ? 'searching' : name === 'summarize_portfolio' ? 'solving' : 'working');
  switch (name) {
    case 'scan_markets': {
      const tag = String(args.tag ?? 'all'), within = Number(args.within_hours ?? 24), top = Math.min(Number(args.top ?? 10), 40);
      const done = step(within <= 24 ? `Looking at ${tag === 'all' ? '' : `${tag} `}markets that end tonight` : `Looking at ${tag === 'all' ? '' : `${tag} `}markets`);
      try {
        const found = await scanMarkets(m, tag, within, top + 10);
        const fresh: typeof found.picks = [];
        for (const p of found.picks) if (!(await alreadyIn(p))) fresh.push(p);
        const picks = fresh.slice(0, top), scanned = found.scanned;
        done('ok', undefined, picks.length ? `Found ${picks.length} good bet${picks.length === 1 ? '' : 's'} in ${scanned.toLocaleString()} markets` : `No good bets in ${scanned.toLocaleString()} markets`);
        const a = await getAccount();
        return { scanned, picks: picks.map((p) => ({ market: p.marketSlug, question: p.question, side: sideOf(p.decision),
          market_price: +p.decision.price.toFixed(3), horizon_prob: +p.decision.q.toFixed(3), suggested_bet: suggested(a, p.decision), hours_left: +p.decision.hours.toFixed(1),
          verdict: verdictOf(p.decision), check_back_in_hours: p.decision.checkBackInHours, event: p.eventSlug })),
          note: 'verdict BET = bet now; WAIT = Horizon only bets in the last 24 h: tell the user when to come back (check_back_in_hours), do not place_bet' };
      } catch (e) { done('fail', String((e as Error).message ?? e)); return { error: String((e as Error).message ?? e) }; }
    }
    case 'search_markets': {
      const query = String(args.query ?? '').trim();
      if (query.length < 2) return { error: 'query too short' };
      const done = step('Looking it up on Polymarket');
      const rows = await searchMarkets(m, query, Math.min(Number(args.top ?? 5), 10)).catch(() => []);
      done(rows.length ? 'ok' : 'fail', rows.length ? undefined : 'Nothing open matches');
      return { results: rows.map((r) => ({ event: r.slug, question: r.question, market_price: +r.decision.price.toFixed(3), hours_left: +r.decision.hours.toFixed(1) })),
        note: "call get_decision with an event slug for Horizon's call (all outcomes, one bet per event)" };
    }
    case 'get_decision': {
      const slug = String(args.slug ?? '');
      const done = step('Reading the market');
      const q = await quoteOne(m, slug);
      if (q?.decision) {
        done('ok');
        const a = await getAccount();
        return { market: q.marketSlug, event: q.eventSlug, question: q.question, side: sideOf(q.decision) ?? 'none', verdict: verdictOf(q.decision),
          market_price: q.decision.price, horizon_prob: q.decision.q, hours_left: +q.decision.hours.toFixed(1),
          check_back_in_hours: q.decision.checkBackInHours, suggested_bet: verdictOf(q.decision) === 'BET' ? suggested(a, q.decision) : 0,
          why: q.decision.blockedBy ? `one bet per event: ${q.decision.blockedBy} has the larger edge` : q.decision.reason };
      }
      try {
        const ev = await decideEventCached(m, slug);
        done('ok');
        return { event: slug, title: ev.title, legs: ev.legs.filter((l) => l.decision).map((l) => ({ market: l.marketSlug, label: l.label, side: sideOf(l.decision!) ?? 'none',
          verdict: verdictOf(l.decision!), market_price: l.decision!.price, horizon_prob: l.decision!.q, hours_left: +l.decision!.hours.toFixed(1),
          check_back_in_hours: l.decision!.checkBackInHours })) };
      } catch { done('fail', 'Not found'); return { error: `no market or event "${slug}"` }; }
    }
    case 'place_bet': {
      const slug = String(args.market ?? ''), side = String(args.side ?? '').toUpperCase() as Side;
      const q = await quoteOne(m, slug);
      if (!q) return { error: 'market not found' };
      const a = await getAccount();
      if (q.decision && verdictOf(q.decision) === 'SKIP' && !args.override) return { error: q.decision.blockedBy ? `one bet per event: Horizon backs ${q.decision.blockedBy} instead` : 'price is fair after costs (advantage under 1¢): skip' };
      if (q.decision && verdictOf(q.decision) === 'WAIT' && !args.override)
        return { error: `too early: Horizon only bets in the last 24 hours before the end; check back in about ${Math.round(q.decision.checkBackInHours ?? q.decision.hours - 24)} h`, verdict: 'WAIT' };
      // Never the same market or event twice: not in this plan, not if the user already bet (paper or real).
      if (ctx.plan.some((i) => i.kind === 'buy' && (i.q.marketSlug === q.marketSlug || (!!q.eventSlug && i.q.eventSlug === q.eventSlug))))
        return { error: 'already in this plan (one bet per event)', already_bet: true };
      const dup = await alreadyIn(q);
      if (dup && !args.override) { step(short(nameOf(q), 50), 'ok', `Skipped: ${dup}`); return { error: dup, already_bet: true, note: 'pick another market' }; }
      const c = checkBet(a, q, side, args.amount === undefined || args.amount === null ? undefined : Number(args.amount), !!args.override);
      if (!c.ok) { step(short(nameOf(q), 50), 'fail', c.error); return { error: c.error }; }
      ctx.plan.push({ kind: 'buy', q, side, amount: c.amount, name: q.question, suggested: c.suggested });
      return { added_to_plan: true, amount: c.amount, horizon_suggests: c.suggested, above_suggestion: c.above, capped_to_budget_from: c.capped,
        note: 'Horizon will set up this ticket on Polymarket; the user presses Trade' };
    }
    case 'adjust_stake': {
      const p = await findPosition(String(args.position ?? ''));
      if (!p) return { error: 'no such open bet' };
      const target = args.new_amount !== undefined ? Number(args.new_amount) : p.stake * Number(args.factor ?? 1);
      const q = await quoteOne(m, p.marketSlug);
      if (!q) return { error: 'no live price' };
      if (target < p.stake - 0.005) { ctx.plan.push({ kind: 'sell', q, pos: p, fraction: 1 - target / p.stake, name: nameOf(p) }); return { added_to_plan: true }; }
      if (target > p.stake + 0.005) {
        const c = checkBet(await getAccount(), q, p.side, target - p.stake, !!args.override);
        if (!c.ok) return { error: c.error };
        ctx.plan.push({ kind: 'buy', q, side: p.side, amount: c.amount, name: nameOf(p) });
        return { added_to_plan: true, capped: !!c.capped };
      }
      return { ok: true, unchanged: true };
    }
    case 'close_position': {
      const p = await findPosition(String(args.position ?? ''));
      if (!p) return { error: 'no such open bet' };
      const q = await quoteOne(m, p.marketSlug);
      if (!q) return { error: 'no live price' };
      ctx.plan.push({ kind: 'sell', q, pos: p, fraction: 1, name: nameOf(p) });
      return { added_to_plan: true };
    }
    case 'close_all': {
      const filter = String(args.filter ?? 'all');
      const a = await getAccount();
      const open = a.positions.filter((x) => x.status === 'open');
      const qs = await quotes(m, open.map((x) => x.marketSlug));
      const done = step('Checking your bets');
      let n = 0;
      for (const p of open) {
        const q = qs.get(p.marketSlug);
        if (!q || q.closed) continue;
        const val = p.shares * (p.side === 'YES' ? q.bid : 1 - q.ask);
        const keep = filter === 'losing' ? val >= p.stake : filter === 'winning' ? val <= p.stake
          : filter === 'no_edge' ? (!!q.decision && sideOf(q.decision) === p.side) : false;
        if (keep) continue;
        ctx.plan.push({ kind: 'sell', q, pos: p, fraction: 1, name: nameOf(p) });
        n++;
      }
      done('ok', undefined, n ? `${n} to sell` : 'Nothing to sell');
      return { added_to_plan: n };
    }
    case 'open_market_in_tab': {
      const done = stepper(ctx, 'shaping')('Opening the market');
      await openEvent(ctx, String(args.slug ?? ''));
      done('ok');
      return { ok: true };
    }
    case 'prepare_ticket_on_page': {
      const q = await quoteOne(m, String(args.market ?? ''));
      if (!q) return { error: 'market not found' };
      const a = await getAccount();
      const r = await fillTicket(ctx, q, String(args.side ?? 'YES').toUpperCase() as Side, Number(args.amount ?? (q.decision ? suggested(a, q.decision) : 5)), 'buy');
      return { ok: r.ok, error: r.error };
    }
    case 'open_my_results': {
      const done = step('Opening your results');
      await openMyResults();
      const me = await fetchMe();
      const paper = isPaper() ? await paperSummary(m) : undefined;
      done('ok');
      // In paper mode the practice book is what the user is playing with; the results page shows real decisions only.
      return { opened: true, summary: me?.summary, ...(paper ? { paper_mode: true, paper_book: paper, paper_summary: paperLine(paper),
        note: 'Paper trading is on: report the paper book (practice money, nothing on Polymarket). The results page shows real decisions only.' } : {}) };
    }
    case 'set_bankroll': {
      const n = Number(args.amount);
      if (!(n >= 1)) return { error: 'amount must be at least 1' };
      await setBankroll(n);
      step(`Budget set to ${money(n)}`, 'ok');
      return { ok: true, budget: n };
    }
    case 'summarize_portfolio': {
      const a = await getAccount();
      const open = a.positions.filter((x) => x.status === 'open');
      await refresh(await quotes(m, open.map((p) => p.marketSlug)));
      const a2 = await getAccount();
      const paper = isPaper() ? await paperSummary(m) : undefined;
      return { budget: a2.bankroll, bets_user_placed: open.length, dollars_in_those_bets: +inPlay(a2).toFixed(2), result_so_far: +pnlTotal(a2).toFixed(2),
        ...(paper ? { paper_mode: true, paper_book: paper, note: 'Paper trading is on: these practice bets were never sent to Polymarket.' } : {}) };
    }
    default:
      return { error: `unknown tool ${name}` };
  }
}

// ---------- paper book summary (paper mode) ----------

type PaperSum = { bankroll: number; open_bets: number; staked: number; marked_pnl: number; settled_pnl: number; settled_bets: number };
async function paperSummary(m: Model): Promise<PaperSum> {
  const a = await getAccount('paper');
  const open = a.positions.filter((x) => x.status === 'open');
  if (open.length) await refresh(await quotes(m, open.map((p) => p.marketSlug)), 'paper');
  const b = await getAccount('paper');
  const o = b.positions.filter((x) => x.status === 'open'), d = b.positions.filter((x) => x.status !== 'open');
  return { bankroll: b.bankroll, open_bets: o.length, staked: +o.reduce((s, p) => s + p.stake, 0).toFixed(2),
    marked_pnl: +o.reduce((s, p) => s + p.shares * (p.mark ?? p.avgPrice) - p.stake, 0).toFixed(2),
    settled_pnl: +d.reduce((s, p) => s + (p.pnl ?? 0), 0).toFixed(2), settled_bets: d.length };
}
const paperLine = (p: PaperSum) => !p.open_bets && !p.settled_bets ? 'Paper book: no paper bets yet.'
  : `Paper book: ${p.open_bets} open bet${p.open_bets === 1 ? '' : 's'} (${money(p.staked)}), ${p.marked_pnl >= 0 ? 'up' : 'down'} ${money(Math.abs(p.marked_pnl))} at today's prices${p.settled_bets ? `; ${p.settled_bets} settled, ${p.settled_pnl >= 0 ? '+' : '−'}${money(Math.abs(p.settled_pnl))}` : ''}.`;

// ---------- the page ----------

/**
 * Sports pages keep everything but the main lines under sub-tabs ("Exact Score", "Halves",
 * "Corners", "Goalscorers"). Which one a leg lives in, from its question and slug.
 */
export function subTabOf(q: Pick<Quote, 'question' | 'marketSlug'>): string | undefined {
  const t = `${q.question} ${q.marketSlug}`.toLowerCase();
  if (/^exact score:|exact-score/.test(t)) return 'Exact Score';
  if (/\b(1st|2nd|first|second) half\b|halftime|half-time|-1h-|-2h-/.test(t)) return 'Halves';
  if (/\bcorners?\b/.test(t)) return 'Corners';
  if (/\bto score\b|goalscorer|anytime scorer/.test(t)) return 'Goalscorers';
  return undefined;
}

/** True while Horizon is steering the tab, so the panel does not jump views mid-bet. */
export const pageDrive = { active: false };

/**
 * Open the market. With a market slug: the deep link polymarket.com/market/<slug>, which Polymarket
 * redirects to /event/<event>/<market> with that market preselected (sports: to the event page).
 * Waits for the load with a bounded poll; the ticket itself is awaited by prepareOrder.
 */
async function openEvent(ctx: Pick<Ctx, 'tabId'>, eventSlug: string, marketSlug?: string, force = false) {
  const url = marketSlug ? `https://polymarket.com/market/${marketSlug}` : `https://polymarket.com/event/${eventSlug}`;
  if (ctx.tabId === undefined) { await chrome.tabs.create({ url }); return; }
  const t = await chrome.tabs.get(ctx.tabId).catch(() => undefined);
  const here = marketSlug ? !!t?.url?.includes(marketSlug) || (!!t?.url?.includes('/sports/') && !!t?.url?.includes(eventSlug)) : !!t?.url?.includes(eventSlug);
  if (here && !force) return;
  if (here && force) await chrome.tabs.reload(ctx.tabId);
  else await chrome.tabs.update(ctx.tabId, { url });
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 250));
    const t2 = await chrome.tabs.get(ctx.tabId).catch(() => undefined);
    if (t2?.status === 'complete' && i >= 2) break;
  }
  await new Promise((r) => setTimeout(r, 600)); // first paint; prepareOrder then polls for the ticket (<= 5 s)
}

const plainPageError = (e: string) => /ticket not found/i.test(e) ? "Polymarket's order box is not on screen"
  : /wrong outcome/i.test(e) ? `Polymarket's ticket is on a different outcome${(e.match(/\(([^)]*)\)/) ?? [])[1] ? ` (${(e.match(/\(([^)]*)\)/) ?? [])[1]})` : ''}. Don't press Trade there`
  : /could not find this market/i.test(e) ? 'Could not find this outcome on the page'
  : /amount field/i.test(e) ? "Could not find Polymarket's amount box"
  : /Sell tab/i.test(e) ? "Could not find Polymarket's Sell tab"
  : /Receiving end|Could not establish/i.test(e) ? 'The page is still loading'
  : e;

/**
 * Fill Polymarket's ticket in the user's tab, every action narrated: open the market, pick the
 * outcome, type the amount. Stops there: the user presses Trade. On failure the outcome is
 * highlighted and the reason given in plain words.
 */
export async function fillTicket(ctx: Pick<Ctx, 'model' | 'tabId' | 'onStep'>, q: Quote, side: Side, amount: number, mode: 'buy' | 'sell', retry = false):
  Promise<{ ok: boolean; error?: string; label: string }> {
  const sh = stepper(ctx, 'shaping');
  let label = q.label.replace(/\s*\(.*\)\s*$/, '').replace(/\?$/, '').trim();
  if (ctx.tabId === undefined) return { ok: false, error: 'No browser tab to use', label };
  const open = sh('Opening the market on Polymarket');
  pageDrive.active = true;
  try {
    await openEvent(ctx, q.eventSlug, q.marketSlug, !!retry);
    open('ok');
    await stylePage(ctx.tabId);
    void markPage(ctx.tabId, 'act');
    const ev = await decideEventCached(ctx.model, q.eventSlug);
    const leg = ev.legs.find((l) => l.marketSlug === q.marketSlug);
    label = (leg?.label ?? q.label).replace(/\s*\(.*\)\s*$/, '').replace(/\?$/, '').trim();
    let cur: ((s: Step['status'], d?: string) => void) | undefined;
    const r = await prepareOrder({ tabId: ctx.tabId, eventSlug: q.eventSlug, marketSlug: q.marketSlug, label,
      legCount: ev.legs.filter((l) => l.decision).length, side, amount, bid: leg?.bid ?? q.bid, ask: leg?.ask ?? q.ask, mode, tab: subTabOf(q),
      onProgress: (t) => { cur?.('ok'); cur = sh(t); } });
    if (r.ok) { cur?.('ok'); void markPage(ctx.tabId, 'ok'); return { ok: true, label }; }
    void markPage(ctx.tabId, 'fail');
    const why = plainPageError(r.steps.filter((s) => !s.ok).map((s) => s.detail ?? s.step).join('; '));
    cur?.('fail', why);
    await fallbackHint(ctx.tabId, label, amount).catch(() => false);
    return { ok: false, error: why, label };
  } catch (e) {
    const why = plainPageError(String((e as Error).message ?? e));
    open('fail', why);
    return { ok: false, error: why, label };
  } finally {
    setTimeout(() => { pageDrive.active = false; }, 1500);
  }
}

// ---------- deterministic planner (no LLM needed) ----------

const TAGS: Record<string, string> = {
  sport: 'sports', sports: 'sports', football: 'soccer', soccer: 'soccer', nba: 'nba', basketball: 'basketball', nfl: 'nfl', nhl: 'nhl',
  tennis: 'tennis', mlb: 'mlb', baseball: 'baseball', esports: 'esports', crypto: 'crypto', bitcoin: 'bitcoin', politics: 'politics',
  election: 'elections', elections: 'elections', ufc: 'ufc', cricket: 'cricket', f1: 'f1', golf: 'golf', tech: 'tech', culture: 'culture',
};
const NUM_WORDS: Record<string, number> = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, twenty: 20, dozen: 12 };

/** Plan from words. Returns the answer text; buys/sells land in ctx.plan. */
export async function planFromWords(ctx: Ctx, text: string): Promise<string> {
  const t = text.toLowerCase().replace(/[’']/g, '').trim();
  const num = (re: RegExp) => { const mm = t.match(re); if (!mm) return undefined; const v = mm[1]; return NUM_WORDS[v] ?? Number(v.replace(/,/g, '')); };
  const tag = Object.keys(TAGS).find((k) => new RegExp(`\\b${k}\\b`).test(t));
  const within = /\btonight|today|next 24|24 ?h/.test(t) ? 24 : /\bweek\b/.test(t) ? 168 : num(/(\d+)\s*(?:h|hours?)\b/) ?? 24;
  const override = /\b(anyway|override|regardless|ignore (the )?(limit|cap|suggest))/.test(t);

  const budget = num(/(?:budget|bankroll)\D{0,12}\$?\s*([\d,]+)/);
  if (budget !== undefined && /\b(budget|bankroll)\b/.test(t)) { await runTool(ctx, 'set_bankroll', { amount: budget }); return `Your budget is ${money(budget)}.`; }

  if (/\b(close|sell|cash ?out|exit|get out)\b/.test(t)) {
    const filter = /\b(lost|losing|losers?|red|down)\b/.test(t) && !/\bedge\b/.test(t) ? 'losing' : /\b(edge|advantage|no longer|stale)\b/.test(t) ? 'no_edge'
      : /\b(winning|winners?|profit|green)\b/.test(t) ? 'winning' : 'all';
    const r = await runTool(ctx, 'close_all', { filter }) as { added_to_plan: number };
    return r.added_to_plan ? `Ready to sell ${r.added_to_plan} bet${r.added_to_plan === 1 ? '' : 's'}.` : 'Nothing to sell.';
  }

  const scale = /\b(lower|reduce|cut|decrease|halve|shrink|less|raise|increase|double|boost|more)\b/.test(t) && /\b(stakes?|bets?|everything|all|positions?|them)\b/.test(t);
  if (scale) {
    const down = /\b(lower|reduce|cut|decrease|halve|shrink|less)\b/.test(t);
    const p = num(/(\d+(?:\.\d+)?)\s*%/);
    let factor = /\bhalf|halve\b/.test(t) ? 0.5 : /\bdouble\b/.test(t) ? 2 : down ? 0.5 : 1.5;
    if (p !== undefined) factor = down ? 1 - p / 100 : 1 + p / 100;
    const a = await getAccount();
    const open = a.positions.filter((q) => q.status === 'open');
    if (!open.length) return 'You have no bets placed through Horizon yet.';
    const done = stepper(ctx)('Checking your bets');
    for (const q of open) await runTool(ctx, 'adjust_stake', { position: q.id, factor, override });
    done('ok');
    return ctx.plan.length ? 'Here is the change.' : 'Nothing to change.';
  }

  const amt = num(/\$\s*([\d,]+(?:\.\d+)?)/) ?? num(/([\d,]+(?:\.\d+)?)\s*(?:dollars|usd|bucks)\b/);
  const count = num(/\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|twenty|dozen)\s+(?:best|top|good|great|bets?|picks?|markets?)/) ?? (/\bbest( \w+)? (bet|market|pick)\b/.test(t) ? 1 : undefined);
  if (/\b(bet|place|put|buy|back|find|pick|play)\b/.test(t) || count !== undefined) {
    const n = Math.min(count ?? (amt !== undefined ? 1 : 5), 40);
    const where = tag ? TAGS[tag] : 'all';
    const s = await runTool(ctx, 'scan_markets', { tag: where, within_hours: within, top: Math.max(n * 2, 10) }) as { picks?: { market: string; side: Side }[]; error?: string };
    if (s.error) return `Could not look at the markets: ${s.error}.`;
    const a = await getAccount();
    const have = new Set(a.positions.filter((p) => p.status === 'open').map((p) => p.marketSlug));
    let added = 0;
    for (const p of s.picks ?? []) {
      if (added >= n || ctx.signal.stop) break;
      if (have.has(p.market)) continue;
      const r = await runTool(ctx, 'place_bet', { market: p.market, side: p.side, amount: amt, override }) as { added_to_plan?: boolean };
      if (r.added_to_plan) added++;
    }
    return added ? 'Here is the plan.' : `Nothing ${where === 'all' ? '' : `in ${where} `}is a good bet right now. Horizon would wait.`;
  }

  if (/\b(my (stats|results|record)|how am i doing|am i (up|down)|show (me )?my)\b/.test(t)) {
    const r = await runTool(ctx, 'open_my_results', {}) as { summary?: string; paper_summary?: string };
    if (r.paper_summary) return `${r.paper_summary} Your real results are open in a new tab.`;
    return r.summary ? `${r.summary}. Your results are open in a new tab.` : 'Your results are open in a new tab.';
  }

  if (/\b(how|status|portfolio|summary|doing|budget|p&l|pnl)\b/.test(t)) {
    const s = await runTool(ctx, 'summarize_portfolio', {}) as { bets_user_placed: number; result_so_far: number };
    return s.bets_user_placed ? `${s.bets_user_placed} bets placed, ${s.result_so_far >= 0 ? 'up' : 'down'} ${money(Math.abs(s.result_so_far))} so far.` : 'No bets placed yet.';
  }
  // A question about one market ("Will Mbappé win the Ballon d'Or?"): look it up and answer with Horizon's numbers.
  const subject = text.replace(/^\s*(will|would|what about|how about|should i (bet on|back)|is|does|can)\s+/i, '').replace(/[?!.]+\s*$/, '').trim();
  if (subject.length >= 6) {
    const done = stepper(ctx)('Looking it up on Polymarket');
    const rows = await searchMarkets(ctx.model, subject, 3).catch(() => []);
    done(rows.length ? 'ok' : 'fail');
    const r = rows[0];
    if (r) {
      const d = r.decision, v = verdictOf(d);
      const pc = (x: number) => `${Math.round(x * 100)}%`;
      const verdict = v === 'BET' ? `the price looks too ${intendedAction(d) === 'BUY_YES' ? 'low' : 'high'}; Horizon would back ${intendedAction(d) === 'BUY_YES' ? 'Yes' : 'No'}`
        : v === 'WAIT' ? 'there may be an edge, but Horizon waits until the last 24 hours before the end'
        : 'the price looks about right; Horizon would skip it';
      await runTool(ctx, 'open_market_in_tab', { slug: r.slug }).catch(() => undefined);
      return `**${r.question}** Polymarket says ${pc(d.price)}, Horizon ${pc(d.q)}: ${verdict}. The market is open in your tab.`;
    }
  }
  return 'Sorry, I did not catch that. Try "Bet on my 5 best tonight", "Sell what lost its edge" or ask about one market.';
}

// ---------- Gemini planning via our API ----------

type Part = { text?: string; functionCall?: { name: string; args?: Args; id?: string }; functionResponse?: unknown; [k: string]: unknown };
type Content = { role: string; parts: Part[] };

export async function llmAvailable(): Promise<boolean> {
  try {
    const r = await fetch(`${API}/api/agent`, { signal: AbortSignal.timeout(3000) });
    return r.ok && !!(await r.json()).llm;
  } catch { return false; }
}

/** Last few user requests and answers, so a follow-up ("now $5 each", "and the other one?") has context. */
const memory: Content[] = [];
const MEMORY_TURNS = 6;

async function pageContext(tabId?: number): Promise<string> {
  if (tabId === undefined) return '';
  const t = await chrome.tabs.get(tabId).catch(() => undefined);
  const slug = t?.url?.match(/polymarket\.com\/(?:[a-z]{2}\/)?event\/([^/?#]+)/)?.[1];
  return slug ? ` The user's tab is on the Polymarket event "${slug}": "this market/match/one" means that event (get_decision with slug "${slug}").` : '';
}

/** Gemini plans with the tools above (buys/sells only queue). Undefined if the LLM is unavailable. */
export async function planWithLLM(ctx: Ctx, text: string): Promise<string | undefined> {
  const contents: Content[] = [...memory, { role: 'user', parts: [{ text }] }];
  const a = await getAccount();
  const context = `now ${new Date().toISOString()}; the user's budget is $${a.bankroll}; ${a.positions.filter((p) => p.status === 'open').length} bets they placed after Horizon set them up. Horizon only sets up tickets; the user presses Trade on Polymarket.${isPaper() ? ' Paper trading is on (practice money).' : ''}${await pageContext(ctx.tabId)}`;
  const remember = (answer: string) => {
    memory.push({ role: 'user', parts: [{ text }] }, { role: 'model', parts: [{ text: answer }] });
    memory.splice(0, Math.max(0, memory.length - MEMORY_TURNS * 2));
    return answer;
  };
  for (let i = 0; i < 25 && !ctx.signal.stop; i++) {
    let res: Response;
    try {
      res = await fetch(`${API}/api/agent`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ contents, context }), signal: AbortSignal.timeout(45000) });
    } catch { if (i === 0) return undefined; throw new Error('lost the connection to Horizon'); }
    if (!res.ok) { if (i === 0) return undefined; throw new Error(`agent error ${res.status}`); }
    const { content } = await res.json() as { content: Content };
    contents.push(content);
    const calls = content.parts.filter((p) => p.functionCall);
    if (!calls.length) return remember(content.parts.map((p) => p.text ?? '').join('').trim() || (ctx.plan.length ? 'Here is the plan.' : 'Nothing to do right now.'));
    // Lookups run together; plan-changing tools keep their order (the plan list is ranked).
    const lookup = (n: string) => n === 'get_decision' || n === 'search_markets';
    const results: Part[] = new Array(calls.length);
    const answer = async (k: number) => {
      const f = calls[k].functionCall!;
      results[k] = { functionResponse: { id: f.id, name: f.name, response: await runTool(ctx, f.name, f.args ?? {}) } };
    };
    await Promise.all(calls.map((c, k) => (lookup(c.functionCall!.name) ? answer(k) : undefined)));
    for (const [k, c] of calls.entries()) {
      if (lookup(c.functionCall!.name)) continue;
      if (ctx.signal.stop) break;
      await answer(k);
    }
    contents.push({ role: 'user', parts: results.filter(Boolean) });
  }
  return ctx.signal.stop ? 'Stopped.' : remember(ctx.plan.length ? 'Here is the plan.' : 'I could not finish that; try a shorter request.');
}
