/**
 * Horizon agent: plain-language tasks → tool calls the panel executes itself, step by step.
 * With a Gemini key on the API (POST /api/agent) the LLM plans; without one, a deterministic
 * parser covers the common tasks. Every bet goes through demo.placeBet (Horizon's decide() +
 * suggested-bet cap + loss limit). Demo money only; page actions never confirm a trade.
 */
import { decideEvent, domainOf, type Decision, type Model } from './horizon';
import {
  decideQ, equity, getAccount, lossToday, outlook, placeBet, pWinOf, quotes, refresh, resetAccount, sell, suggested,
  type Position, type Quote, type Side,
} from './demo';
import { prepareOrder } from './prepareOrder';

export const API = 'https://horizon-api-iota.vercel.app';
const GAMMA = 'https://gamma-api.polymarket.com';

export type Step = { id: number; text: string; status: 'run' | 'ok' | 'fail' | 'info'; detail?: string };
export type Ctx = { model: Model; tabId?: number; onStep: (s: Step) => void; signal: { stop: boolean } };

let stepId = 0;
function stepper(ctx: Ctx) {
  return (text: string, status: Step['status'] = 'run', detail?: string) => {
    const s: Step = { id: ++stepId, text, status, detail };
    ctx.onStep(s);
    return (status2: Step['status'], detail2?: string, text2?: string) => ctx.onStep({ ...s, status: status2, detail: detail2, text: text2 ?? s.text });
  };
}
const money = (x: number) => `${x < 0 ? '−' : ''}$${Math.abs(x) >= 100 ? Math.round(Math.abs(x)).toLocaleString() : Math.abs(x).toFixed(2)}`;
const signedMoney = (x: number) => `${x >= 0 ? '+' : '−'}${money(Math.abs(x))}`;
/** The leg label alone ("24°C", "<8M") means nothing out of context: use the question then. */
const nameOf = (x: { label: string; question: string }) => (x.label && x.label !== x.question && x.label.length >= 14 ? x.label : x.question);
const short = (s: string, n = 48) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

// ---------- market scan with market slugs and quotes ----------

export type Pick = Quote & { decision: Decision };

/** Open yes/no markets ending within `withinHours` (optionally under a Gamma tag), best advantage first. */
export async function scanMarkets(m: Model, tag = 'all', withinHours = 24, top = 10, now = new Date()): Promise<{ picks: Pick[]; scanned: number }> {
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
  const picks: Pick[] = [];
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
    picks.push({ marketSlug: mk.slug, eventSlug: ev?.slug ?? mk.slug, question: mk.question, label: mk.groupItemTitle || mk.question,
      bid, ask, closed: false, endDate: mk.endDate, domain, feesEnabled: !!mk.feesEnabled,
      decision: decideQ(m, price, hours, domain, ask - bid, !!mk.feesEnabled) });
  }
  picks.sort((a, b) => b.decision.netEdge - a.decision.netEdge);
  return { picks: picks.filter((p) => p.decision.action !== 'NO_TRADE').slice(0, top), scanned: seen.size };
}

async function quoteOne(m: Model, slug: string): Promise<Quote | undefined> {
  return (await quotes(m, [slug])).get(slug);
}
const sideOf = (d: Decision): Side | undefined => (d.action === 'BUY_YES' ? 'YES' : d.action === 'BUY_NO' ? 'NO' : undefined);

async function findPosition(ref: string): Promise<Position | undefined> {
  const a = await getAccount();
  const open = a.positions.filter((p) => p.status === 'open');
  return open.find((p) => p.id === ref) ?? open.find((p) => p.marketSlug === ref) ?? open.find((p) => p.question.toLowerCase().includes(ref.toLowerCase()));
}

export async function portfolioOutlook(m: Model) {
  const a = await getAccount();
  const open = a.positions.filter((p) => p.status === 'open');
  const qs = await quotes(m, open.map((p) => p.marketSlug));
  await refresh(m, qs);
  const a2 = await getAccount();
  const open2 = a2.positions.filter((p) => p.status === 'open');
  const bets = open2.map((p) => {
    const d = qs.get(p.marketSlug)?.decision;
    return { shares: p.shares, stake: p.stake, value: p.stake, pWin: d ? pWinOf(d, p.side) : p.qAtOpen };
  });
  return { account: a2, open: open2, ...outlook(bets) };
}

// ---------- tools ----------

type Args = Record<string, any>;
export async function runTool(ctx: Ctx, name: string, args: Args): Promise<Record<string, unknown>> {
  const { model: m } = ctx;
  const step = stepper(ctx);
  switch (name) {
    case 'scan_markets': {
      const tag = String(args.tag ?? 'all'), within = Number(args.within_hours ?? 24), top = Math.min(Number(args.top ?? 10), 40);
      const done = step(`Scanning ${tag === 'all' ? 'all' : tag} markets ending within ${within}h`);
      try {
        const { picks, scanned } = await scanMarkets(m, tag, within, top);
        done('ok', `${scanned} markets checked, ${picks.length} with an advantage`);
        const a = await getAccount();
        return { scanned, picks: picks.map((p) => ({ market: p.marketSlug, event: p.eventSlug, question: p.question, side: sideOf(p.decision),
          market_price: +p.decision.price.toFixed(3), horizon_prob: +p.decision.q.toFixed(3), advantage_cents: +(p.decision.netEdge * 100).toFixed(1),
          suggested_bet: suggested(a, p.decision), hours_left: +p.decision.hours.toFixed(1) })) };
      } catch (e) { done('fail', String((e as Error).message ?? e)); return { error: String((e as Error).message ?? e) }; }
    }
    case 'get_decision': {
      const slug = String(args.slug ?? '');
      const done = step(`Reading Horizon's call on ${short(slug, 40)}`);
      const q = await quoteOne(m, slug);
      if (q?.decision) { done('ok', q.decision.reason); return { market: q.marketSlug, question: q.question, side: sideOf(q.decision) ?? 'none', ...pickFields(q.decision) }; }
      try {
        const ev = await decideEvent(m, slug);
        done('ok', `${ev.legs.filter((l) => l.decision).length} legs priced`);
        return { event: slug, title: ev.title, legs: ev.legs.filter((l) => l.decision).map((l) => ({ market: l.marketSlug, label: l.label, side: sideOf(l.decision!) ?? 'none', ...pickFields(l.decision!) })) };
      } catch (e) { done('fail', 'not found'); return { error: `no market or event "${slug}"` }; }
    }
    case 'place_bet': {
      const slug = String(args.market ?? ''), side = String(args.side ?? '').toUpperCase() as Side;
      const amount = args.amount === undefined || args.amount === null ? undefined : Number(args.amount);
      const done = step(`Bet ${amount !== undefined ? money(amount) : 'suggested'} on ${side} · ${short(slug, 36)}`);
      const q = await quoteOne(m, slug);
      if (!q) { done('fail', 'market not found'); return { error: 'market not found' }; }
      const r = await placeBet(m, q, side, amount, 'agent', !!args.override);
      if (!r.ok) { done('fail', r.error); return { error: r.error }; }
      const p = r.position;
      done('ok', `${money(r.position.stake)} on ${side} at ${Math.round(fillFrom(p) * 100)}¢${r.capped ? ` (capped from ${money(r.capped)} to Horizon's suggested bet)` : ''}`,
        `Bet on ${side} · ${short(nameOf(q), 44)}`);
      return { ok: true, position: p.id, question: q.question, side, staked: +p.stake.toFixed(2), price: +p.avgPrice.toFixed(3),
        win_chance: +p.qAtOpen.toFixed(3), capped_from: r.capped, note: r.note };
    }
    case 'adjust_stake': {
      const p = await findPosition(String(args.position ?? ''));
      if (!p) { step('Change a bet', 'fail', 'no such open bet'); return { error: 'no such open bet' }; }
      const target = args.new_amount !== undefined ? Number(args.new_amount) : p.stake * Number(args.factor ?? 1);
      const done = step(`${target < p.stake ? 'Lower' : 'Raise'} ${short(nameOf(p), 36)}: ${money(p.stake)} → ${money(target)}`);
      const q = await quoteOne(m, p.marketSlug);
      if (!q) { done('fail', 'no live price'); return { error: 'no live price' }; }
      if (target < p.stake - 0.005) {
        const r = await sell(ctx.model, q, p.id, 1 - target / p.stake);
        if (!r.ok) { done('fail', r.error); return { error: r.error }; }
        done('ok', `sold part for ${money(r.proceeds!)} (${signedMoney(r.pnl!)})`);
        return { ok: true, new_stake: +target.toFixed(2), realized: +r.pnl!.toFixed(2) };
      }
      if (target > p.stake + 0.005) {
        const r = await placeBet(m, q, p.side, target - p.stake, 'agent', !!args.override);
        if (!r.ok) { done('fail', r.error); return { error: r.error }; }
        done('ok', r.capped ? `capped at Horizon's suggested bet: now ${money(r.position.stake)}` : `now ${money(r.position.stake)}`);
        return { ok: true, new_stake: +r.position.stake.toFixed(2), capped: !!r.capped };
      }
      done('ok', 'unchanged');
      return { ok: true, new_stake: p.stake };
    }
    case 'close_position': {
      const p = await findPosition(String(args.position ?? ''));
      if (!p) { step('Close a bet', 'fail', 'no such open bet'); return { error: 'no such open bet' }; }
      return closeOne(ctx, p);
    }
    case 'close_all': {
      const filter = String(args.filter ?? 'all');
      const a = await getAccount();
      const open = a.positions.filter((x) => x.status === 'open');
      const qs = await quotes(m, open.map((x) => x.marketSlug));
      const chosen = open.filter((p) => {
        const q = qs.get(p.marketSlug);
        const val = p.shares * (q && q.bid > 0 ? (p.side === 'YES' ? q.bid : 1 - q.ask) : p.mark ?? p.avgPrice);
        if (filter === 'losing') return val < p.stake;
        if (filter === 'winning') return val > p.stake;
        if (filter === 'no_edge') return !q?.decision || sideOf(q.decision) !== p.side;
        return true;
      });
      step(`${chosen.length} of ${open.length} open bets match “${filter.replace('_', ' ')}”`, 'info');
      const results = [];
      for (const p of chosen) { if (ctx.signal.stop) break; results.push(await closeOne(ctx, p, qs.get(p.marketSlug))); }
      return { closed: results.filter((r) => r.ok).length, realized: +results.reduce((s, r) => s + Number(r.pnl ?? 0), 0).toFixed(2) };
    }
    case 'open_market_in_tab': {
      const slug = String(args.slug ?? '');
      const done = step(`Opening ${short(slug, 40)} on Polymarket`);
      await openEvent(ctx, slug);
      done('ok');
      return { ok: true };
    }
    case 'prepare_ticket_on_page': {
      const slug = String(args.market ?? ''), side = String(args.side ?? 'YES').toUpperCase() as Side;
      const q = await quoteOne(m, slug);
      if (!q || ctx.tabId === undefined) { step('Show on Polymarket', 'fail', 'market or tab not found'); return { error: 'market or tab not found' }; }
      const a = await getAccount();
      const amount = Number(args.amount ?? (q.decision ? suggested(a, q.decision) : 10));
      return showOnPage(ctx, q, side, amount);
    }
    case 'set_bankroll': {
      const n = Number(args.amount);
      if (!(n >= 10 && n <= 1e6)) { step('Reset balance', 'fail', 'amount must be $10 – $1,000,000'); return { error: 'amount must be 10..1e6' }; }
      await resetAccount(n);
      step(`Demo balance reset to ${money(n)}`, 'ok');
      return { ok: true, balance: n };
    }
    case 'summarize_portfolio': {
      const done = step('Checking your bets at live prices');
      const o = await portfolioOutlook(m);
      const eq = equity(o.account), staked = o.open.reduce((s, p) => s + p.stake, 0);
      const lt = lossToday(o.account);
      done('ok', o.open.length ? `${o.open.length} open, ${money(staked)} in play · expected ${signedMoney(o.ev)} · ${Math.round(o.pDown * 100)}% chance to end down` : `no open bets · balance ${money(eq)}`);
      return { balance: +eq.toFixed(2), cash: +o.account.cash.toFixed(2), start: o.account.start, open_bets: o.open.length, staked: +staked.toFixed(2),
        expected_profit: +o.ev.toFixed(2), chance_end_down: +o.pDown.toFixed(3), loss_today: +lt.loss.toFixed(2), loss_limit: +lt.limit.toFixed(2) };
    }
    default:
      step(`Unknown tool ${name}`, 'fail');
      return { error: `unknown tool ${name}` };
  }
}

const fillFrom = (p: Position) => p.avgPrice;
const pickFields = (d: Decision) => ({ market_price: +d.price.toFixed(3), horizon_prob: +d.q.toFixed(3), range: [+d.lo.toFixed(3), +d.hi.toFixed(3)],
  advantage_cents: +(d.netEdge * 100).toFixed(1), suggested_fraction: +d.kelly.toFixed(4), hours_left: +d.hours.toFixed(1), reason: d.reason });

async function closeOne(ctx: Ctx, p: Position, q0?: Quote) {
  const done = stepper(ctx)(`Close ${p.side} · ${short(nameOf(p), 40)}`);
  const q = q0 ?? (await quoteOne(ctx.model, p.marketSlug));
  if (!q) { done('fail', 'no live price'); return { ok: false, error: 'no live price' }; }
  const r = await sell(ctx.model, q, p.id, 1);
  if (!r.ok) { done('fail', r.error); return { ok: false, error: r.error }; }
  done('ok', `sold for ${money(r.proceeds!)} · ${signedMoney(r.pnl!)}`);
  return { ok: true, pnl: r.pnl };
}

async function openEvent(ctx: Ctx, eventSlug: string) {
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

/** Drive the page to show the ticket (leg + outcome + amount). Never confirms. */
export async function showOnPage(ctx: Ctx, q: Quote, side: Side, amount: number) {
  const done = stepper(ctx)(`Show on Polymarket: ${side} ${money(amount)} · ${short(q.label, 36)}`);
  try {
    await openEvent(ctx, q.eventSlug);
    const ev = await decideEvent(ctx.model, q.eventSlug);
    const leg = ev.legs.find((l) => l.marketSlug === q.marketSlug);
    const label = (leg?.label ?? q.label).replace(/\s*\(.*\)\s*$/, '').replace(/\?$/, '').trim();
    const r = await prepareOrder({ tabId: ctx.tabId!, eventSlug: q.eventSlug, marketSlug: q.marketSlug, label,
      legCount: ev.legs.filter((l) => l.decision).length, side, amount, bid: leg?.bid ?? q.bid, ask: leg?.ask ?? q.ask });
    if (r.ok) done('ok', 'ticket filled on the page · Horizon never presses Trade');
    else done('fail', r.steps.filter((s) => !s.ok).map((s) => `${s.step}: ${s.detail ?? 'failed'}`).join('; '));
    return { ok: r.ok, steps: r.steps };
  } catch (e) {
    done('fail', String((e as Error).message ?? e));
    return { ok: false, error: String((e as Error).message ?? e) };
  }
}

// ---------- deterministic planner (no LLM needed) ----------

const TAGS: Record<string, string> = {
  sport: 'sports', sports: 'sports', football: 'soccer', soccer: 'soccer', nba: 'nba', basketball: 'basketball', nfl: 'nfl', nhl: 'nhl',
  tennis: 'tennis', mlb: 'mlb', baseball: 'baseball', esports: 'esports', crypto: 'crypto', bitcoin: 'bitcoin', politics: 'politics',
  election: 'elections', elections: 'elections', ufc: 'ufc', cricket: 'cricket', f1: 'f1', golf: 'golf', tech: 'tech', culture: 'culture',
};
const NUM_WORDS: Record<string, number> = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, twenty: 20, dozen: 12 };

export type Plan = { summary: string; run: (ctx: Ctx) => Promise<string> } | { error: string };

export function parseCommand(text: string): Plan {
  const t = text.toLowerCase().replace(/[’']/g, '').trim();
  const num = (re: RegExp) => { const m = t.match(re); if (!m) return undefined; const v = m[1]; return NUM_WORDS[v] ?? Number(v.replace(/,/g, '')); };
  const tag = Object.keys(TAGS).find((k) => new RegExp(`\\b${k}\\b`).test(t));
  const within = /\btonight|today|next 24|24 ?h/.test(t) ? 24 : /\bweek\b/.test(t) ? 168 : num(/(\d+)\s*(?:h|hours?)\b/) ?? 24;
  const override = /\b(anyway|override|regardless|ignore (the )?(limit|cap|suggest))/.test(t);

  // reset / bankroll
  const bank = num(/(?:balance|bankroll|start(?:ing)?(?: with)?|reset(?: to)?)\D{0,12}\$?\s*([\d,]+)/);
  if (/\b(reset|set (my )?(balance|bankroll)|start over)\b/.test(t)) {
    const n = bank ?? 1000;
    return { summary: `Reset the demo balance to $${n.toLocaleString()}`, run: async (ctx) => { await runTool(ctx, 'set_bankroll', { amount: n }); return `Fresh start: $${n.toLocaleString()} of demo money.`; } };
  }

  // close
  if (/\b(close|sell|cash ?out|exit|get out)\b/.test(t)) {
    const filter = /\b(lost|losing|losers?|red|down)\b/.test(t) ? 'losing' : /\b(edge|advantage|no longer|stale)\b/.test(t) ? 'no_edge'
      : /\b(winning|winners?|profit|green|up)\b/.test(t) ? 'winning' : 'all';
    return { summary: `Close ${filter === 'all' ? 'every open bet' : filter === 'no_edge' ? 'bets Horizon no longer backs' : `${filter} bets`}`,
      run: async (ctx) => {
        const r = await runTool(ctx, 'close_all', { filter }) as { closed: number; realized: number };
        const s = await runTool(ctx, 'summarize_portfolio', {}) as { balance: number };
        return r.closed ? `Closed ${r.closed} bet${r.closed === 1 ? '' : 's'} for ${signedMoney(r.realized)} in total. Balance ${money(s.balance)}.` : 'Nothing to close.';
      } };
  }

  // raise / lower all stakes
  const scale = /\b(lower|reduce|cut|decrease|halve|shrink|raise|increase|double|boost|up)\b/.test(t) && /\b(stakes?|bets?|everything|all|positions?|them)\b/.test(t);
  if (scale) {
    const down = /\b(lower|reduce|cut|decrease|halve|shrink)\b/.test(t);
    const p = num(/(\d+(?:\.\d+)?)\s*%/);
    const x = num(/(\d+(?:\.\d+)?)\s*x\b/) ?? num(/by (?:a factor of )?(\d+(?:\.\d+)?)\b/);
    let factor = /\bhalf|halve\b/.test(t) ? 0.5 : /\bdouble\b/.test(t) ? 2 : /\bthird\b/.test(t) ? (down ? 2 / 3 : 4 / 3) : /\bquarter\b/.test(t) ? (down ? 0.75 : 1.25) : down ? 0.5 : 1.5;
    if (p !== undefined) factor = down ? 1 - p / 100 : 1 + p / 100;
    else if (x !== undefined && x > 0) factor = down ? 1 / x : x;
    factor = Math.max(0, factor);
    return { summary: `${down ? 'Lower' : 'Raise'} every open bet to ${Math.round(factor * 100)}% of its size`,
      run: async (ctx) => {
        const a = await getAccount();
        const open = a.positions.filter((q) => q.status === 'open');
        if (!open.length) { stepper(ctx)('No open bets to change', 'info'); return 'You have no open bets yet.'; }
        for (const q of open) { if (ctx.signal.stop) break; await runTool(ctx, 'adjust_stake', { position: q.id, factor, override }); }
        const s = await runTool(ctx, 'summarize_portfolio', {}) as { staked: number; expected_profit: number; chance_end_down: number };
        return `Now ${money(s.staked)} in play · expected ${signedMoney(s.expected_profit)} · ${Math.round(s.chance_end_down * 100)}% chance to end down.${!down && !override ? ' Raises stop at Horizon\'s suggested bet; say "anyway" to go past it.' : ''}`;
      } };
  }

  // bet $X on the best <tag> market
  const amt = num(/\$\s*([\d,]+(?:\.\d+)?)/) ?? num(/([\d,]+(?:\.\d+)?)\s*(?:dollars|usd|bucks)\b/);
  const count = num(/\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|twenty|dozen)\s+(?:best|top|good|great|bets?|picks?|markets?)/) ?? (/\bbest (bet|market|pick)\b/.test(t) ? 1 : undefined);
  if (/\b(bet|place|put|buy|back|find|pick|play)\b/.test(t) || count !== undefined) {
    const n = Math.min(count ?? (amt !== undefined ? 1 : 5), 40);
    const where = tag ? TAGS[tag] : 'all';
    return { summary: `${amt !== undefined ? `Bet $${amt}` : 'Place'} ${n === 1 ? 'on the best' : `the ${n} best`} ${where === 'all' ? '' : `${where} `}market${n === 1 ? '' : 's'} ending within ${within}h`,
      run: async (ctx) => {
        const s = await runTool(ctx, 'scan_markets', { tag: where, within_hours: within, top: Math.max(n * 2, 10) }) as { picks?: { market: string; side: Side; question: string; suggested_bet: number }[]; error?: string };
        if (s.error) return `Could not scan: ${s.error}.`;
        const a = await getAccount();
        const have = new Set(a.positions.filter((p) => p.status === 'open').map((p) => p.marketSlug));
        const picks = (s.picks ?? []).filter((p) => !have.has(p.market)).slice(0, n);
        if (!picks.length) return `No ${where === 'all' ? '' : `${where} `}market ending within ${within}h has an advantage after costs right now. Horizon would rather not bet.`;
        // Plan outlook before acting (Monte Carlo on Horizon's q).
        let placed = 0, staked = 0;
        for (const p of picks) {
          if (ctx.signal.stop) break;
          const r = await runTool(ctx, 'place_bet', { market: p.market, side: p.side, amount: amt, override }) as { ok?: boolean; staked?: number };
          if (r.ok) { placed++; staked += r.staked ?? 0; }
        }
        const o = await portfolioOutlook(ctx.model);
        const lastN = o.open.slice(0, placed);
        const planOut = outlook(lastN.map((p) => ({ shares: p.shares, stake: p.stake, pWin: p.qAtOpen })));
        stepper(ctx)(`Plan: ${placed} bet${placed === 1 ? '' : 's'}, ${money(staked)} staked · expected ${signedMoney(planOut.ev)} · ~${Math.round(planOut.pDown * 100)}% chance these end down`, 'info',
          'Monte Carlo on Horizon\'s probabilities, markets treated as independent. Not a promise.');
        return placed
          ? `${placed} bet${placed === 1 ? '' : 's'}, ${money(staked)} staked. Expected ${signedMoney(planOut.ev)}, ~${Math.round(planOut.pDown * 100)}% chance they end down. Demo money.`
          : 'No bet went through (see the steps).';
      } };
  }

  if (/\b(how|status|portfolio|summary|summari[sz]e|doing|balance|p&l|pnl)\b/.test(t)) {
    return { summary: 'Check your bets', run: async (ctx) => {
      const s = await runTool(ctx, 'summarize_portfolio', {}) as { balance: number; open_bets: number; expected_profit: number; chance_end_down: number; start: number };
      return `Balance ${money(s.balance)} (${signedMoney(s.balance - s.start)} since start). ${s.open_bets ? `${s.open_bets} open: expected ${signedMoney(s.expected_profit)}, ${Math.round(s.chance_end_down * 100)}% chance to end down.` : 'No open bets.'}`;
    } };
  }
  return { error: 'I did not catch that. Try “Place my 5 best bets tonight”, “Lower all stakes by half”, “Close the losers” or “Bet $20 on the best sports market”.' };
}

// ---------- Gemini loop via our API ----------

type Part = { text?: string; functionCall?: { name: string; args?: Args }; functionResponse?: unknown; [k: string]: unknown };
type Content = { role: string; parts: Part[] };

export async function llmAvailable(): Promise<boolean> {
  try {
    const r = await fetch(`${API}/api/agent`, { signal: AbortSignal.timeout(3000) });
    return r.ok && !!(await r.json()).llm;
  } catch { return false; }
}

/** Runs the Gemini plan → tools → results loop. Returns undefined if the LLM is unavailable (503 / network). */
export async function runLLM(ctx: Ctx, text: string): Promise<string | undefined> {
  const contents: Content[] = [{ role: 'user', parts: [{ text }] }];
  const a = await getAccount();
  const context = `balance $${equity(a).toFixed(2)}, cash $${a.cash.toFixed(2)}, ${a.positions.filter((p) => p.status === 'open').length} open bets, daily loss limit ${Math.round(a.lossLimitPct * 100)}%`;
  for (let i = 0; i < 25 && !ctx.signal.stop; i++) {
    let res: Response;
    try {
      res = await fetch(`${API}/api/agent`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ contents, context }), signal: AbortSignal.timeout(45000) });
    } catch { if (i === 0) return undefined; throw new Error('lost the connection to Horizon'); }
    if (res.status === 503 && i === 0) return undefined;
    if (!res.ok) { if (i === 0) return undefined; throw new Error(`agent error ${res.status}`); }
    const { content } = await res.json() as { content: Content };
    contents.push(content);
    const calls = content.parts.filter((p) => p.functionCall);
    if (!calls.length) return content.parts.map((p) => p.text ?? '').join('').trim() || 'Done.';
    const results: Part[] = [];
    for (const c of calls) {
      if (ctx.signal.stop) break;
      const out = await runTool(ctx, c.functionCall!.name, c.functionCall!.args ?? {});
      results.push({ functionResponse: { name: c.functionCall!.name, response: out } });
    }
    contents.push({ role: 'user', parts: results });
  }
  return ctx.signal.stop ? 'Stopped.' : 'Stopped after 25 steps.';
}
