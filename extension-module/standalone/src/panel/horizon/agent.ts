/**
 * Horizon agent: plain-language tasks → a plan list of bets (or sells). Planning
 * uses Gemini via our API (POST /api/agent) with a deterministic parser as fallback. Every bet goes
 * through checkBet (Horizon's call, suggested-bet cap, daily loss limit). The plan is shown as a
 * list; the panel sets up Polymarket's ticket for the top few, one at a time; the user presses Trade.
 */
import { decide, decideEvent, domainOf, feeOf, type Decision, type Model } from './horizon';
import {
  checkBet, getAccount, inPlay, lossToday, outlook, pnlTotal, pWinOf, quotes, refresh, setBankroll, suggested,
  type Position, type Quote, type Side,
} from './ledger';
import { fallbackHint, prepareOrder } from './prepareOrder';
import { markPage, stylePage } from './pageStyle';

export const API = 'https://oxhack26-production.up.railway.app';
const GAMMA = 'https://gamma-api.polymarket.com';

/** kind = which thinking-orb animation the panel shows while this step runs. */
export type StepKind = 'searching' | 'working' | 'shaping' | 'solving';
export type Step = { id: number; text: string; status: 'run' | 'ok' | 'fail' | 'info'; detail?: string; kind?: StepKind };
export type PlanItem =
  | { kind: 'buy'; q: Quote; side: Side; amount: number; name: string }
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
const sideOf = (d: Decision): Side | undefined => (d.action === 'BUY_YES' ? 'YES' : d.action === 'BUY_NO' ? 'NO' : undefined);

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
    if (!(hours > 0) || price < m.tradable[0] || price > m.tradable[1]) continue;
    const tags = (mk.tags ?? []).map((x: { slug: string }) => x.slug);
    const ev = mk.events?.[0];
    const domain = domainOf(m, tags);
    const fee = feeOf(m, mk, domain);
    picks.push({ marketSlug: mk.slug, eventSlug: ev?.slug ?? mk.slug, question: mk.question, label: mk.groupItemTitle || mk.question,
      bid, ask, closed: false, endDate: mk.endDate, domain, fee, decision: decide(m, price, hours, domain, ask - bid, fee) });
  }
  picks.sort((a, b) => b.decision.netEdge - a.decision.netEdge);
  return { picks: picks.filter((p) => p.decision.action !== 'NO_TRADE').slice(0, top), scanned: seen.size };
}

async function quoteOne(m: Model, slug: string): Promise<Quote | undefined> {
  return (await quotes(m, [slug])).get(slug);
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
        const { picks, scanned } = await scanMarkets(m, tag, within, top);
        done('ok', undefined, picks.length ? `Found ${picks.length} good bet${picks.length === 1 ? '' : 's'} in ${scanned.toLocaleString()} markets` : `No good bets in ${scanned.toLocaleString()} markets`);
        const a = await getAccount();
        return { scanned, picks: picks.map((p) => ({ market: p.marketSlug, question: p.question, side: sideOf(p.decision),
          market_price: +p.decision.price.toFixed(3), horizon_prob: +p.decision.q.toFixed(3), suggested_bet: suggested(a, p.decision), hours_left: +p.decision.hours.toFixed(1) })) };
      } catch (e) { done('fail', String((e as Error).message ?? e)); return { error: String((e as Error).message ?? e) }; }
    }
    case 'get_decision': {
      const slug = String(args.slug ?? '');
      const done = step('Reading the market');
      const q = await quoteOne(m, slug);
      if (q?.decision) { done('ok'); return { market: q.marketSlug, question: q.question, side: sideOf(q.decision) ?? 'none', market_price: q.decision.price, horizon_prob: q.decision.q }; }
      try {
        const ev = await decideEvent(m, slug);
        done('ok');
        return { event: slug, title: ev.title, legs: ev.legs.filter((l) => l.decision).map((l) => ({ market: l.marketSlug, label: l.label, side: sideOf(l.decision!) ?? 'none', market_price: l.decision!.price, horizon_prob: l.decision!.q })) };
      } catch { done('fail', 'Not found'); return { error: `no market or event "${slug}"` }; }
    }
    case 'place_bet': {
      const slug = String(args.market ?? ''), side = String(args.side ?? '').toUpperCase() as Side;
      const q = await quoteOne(m, slug);
      if (!q) return { error: 'market not found' };
      const a = await getAccount();
      const c = checkBet(a, q, side, args.amount === undefined || args.amount === null ? undefined : Number(args.amount), !!args.override);
      if (!c.ok) { step(short(nameOf(q), 50), 'fail', c.error); return { error: c.error }; }
      ctx.plan.push({ kind: 'buy', q, side, amount: c.amount, name: q.question });
      return { added_to_plan: true, amount: c.amount, capped_from: c.capped, note: 'Horizon will set up this ticket on Polymarket; the user presses Trade' };
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
      return { budget: a2.bankroll, bets_user_placed: open.length, dollars_in_those_bets: +inPlay(a2).toFixed(2), result_so_far: +pnlTotal(a2).toFixed(2),
        loss_today: +lossToday(a2).loss.toFixed(2), daily_loss_limit: +lossToday(a2).limit.toFixed(2) };
    }
    default:
      return { error: `unknown tool ${name}` };
  }
}

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

async function openEvent(ctx: Pick<Ctx, 'tabId'>, eventSlug: string) {
  const url = `https://polymarket.com/event/${eventSlug}`;
  if (ctx.tabId === undefined) { await chrome.tabs.create({ url }); return; }
  const t = await chrome.tabs.get(ctx.tabId).catch(() => undefined);
  if (t?.url?.includes(eventSlug)) return;
  await chrome.tabs.update(ctx.tabId, { url });
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 250));
    const t2 = await chrome.tabs.get(ctx.tabId).catch(() => undefined);
    if (t2?.status === 'complete') break;
  }
  await new Promise((r) => setTimeout(r, 2500)); // let Polymarket hydrate the order ticket
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
export async function fillTicket(ctx: Pick<Ctx, 'model' | 'tabId' | 'onStep'>, q: Quote, side: Side, amount: number, mode: 'buy' | 'sell'):
  Promise<{ ok: boolean; error?: string; label: string }> {
  const sh = stepper(ctx, 'shaping');
  let label = q.label.replace(/\s*\(.*\)\s*$/, '').replace(/\?$/, '').trim();
  if (ctx.tabId === undefined) return { ok: false, error: 'No browser tab to use', label };
  const open = sh('Opening the market on Polymarket');
  pageDrive.active = true;
  try {
    await openEvent(ctx, q.eventSlug);
    open('ok');
    await stylePage(ctx.tabId);
    void markPage(ctx.tabId, 'act');
    const ev = await decideEvent(ctx.model, q.eventSlug);
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

  if (/\b(how|status|portfolio|summary|doing|budget|p&l|pnl)\b/.test(t)) {
    const s = await runTool(ctx, 'summarize_portfolio', {}) as { bets_user_placed: number; result_so_far: number };
    return s.bets_user_placed ? `${s.bets_user_placed} bets placed, ${s.result_so_far >= 0 ? 'up' : 'down'} ${money(Math.abs(s.result_so_far))} so far.` : 'No bets placed yet.';
  }
  return 'Sorry, I did not catch that. Try "Bet on my 5 best tonight" or "Sell what lost its edge".';
}

// ---------- Gemini planning via our API ----------

type Part = { text?: string; functionCall?: { name: string; args?: Args }; functionResponse?: unknown; [k: string]: unknown };
type Content = { role: string; parts: Part[] };

export async function llmAvailable(): Promise<boolean> {
  try {
    const r = await fetch(`${API}/api/agent`, { signal: AbortSignal.timeout(3000) });
    return r.ok && !!(await r.json()).llm;
  } catch { return false; }
}

/** Gemini plans with the tools above (buys/sells only queue). Undefined if the LLM is unavailable. */
export async function planWithLLM(ctx: Ctx, text: string): Promise<string | undefined> {
  const contents: Content[] = [{ role: 'user', parts: [{ text }] }];
  const a = await getAccount();
  const context = `the user's budget is $${a.bankroll}; ${a.positions.filter((p) => p.status === 'open').length} bets they placed after Horizon set them up; daily loss limit ${Math.round(a.lossLimitPct * 100)}% of the budget. Horizon only sets up tickets; the user presses Trade on Polymarket.`;
  for (let i = 0; i < 25 && !ctx.signal.stop; i++) {
    let res: Response;
    try {
      res = await fetch(`${API}/api/agent`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ contents, context }), signal: AbortSignal.timeout(45000) });
    } catch { if (i === 0) return undefined; throw new Error('lost the connection to Horizon'); }
    if (!res.ok) { if (i === 0) return undefined; throw new Error(`agent error ${res.status}`); }
    const { content } = await res.json() as { content: Content };
    contents.push(content);
    const calls = content.parts.filter((p) => p.functionCall);
    if (!calls.length) return content.parts.map((p) => p.text ?? '').join('').trim() || 'Here is the plan.';
    const results: Part[] = [];
    for (const c of calls) {
      if (ctx.signal.stop) break;
      const out = await runTool(ctx, c.functionCall!.name, c.functionCall!.args ?? {});
      results.push({ functionResponse: { name: c.functionCall!.name, response: out } });
    }
    contents.push({ role: 'user', parts: results });
  }
  return ctx.signal.stop ? 'Stopped.' : 'Here is the plan.';
}
