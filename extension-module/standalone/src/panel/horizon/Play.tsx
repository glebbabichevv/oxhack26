/**
 * Horizon for everyone. One line and one button per market; the agent turns any request into a
 * plan list and sets up the top few tickets on Polymarket; "My decisions" is this install's
 * decision journal with real results once markets resolve. Visual language from the Argos panel.
 * Horizon fills Polymarket's ticket in the user's tab and stops; the user presses Trade.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { ThinkingOrb, type OrbState } from 'thinking-orbs';
import { decideEvent, searchMarkets, subjectOf, type Decision, type Leg, type Model, type ScanRow } from './horizon';
import { caution, checkBet, getAccount, onAccount, quotes, recordBuy, recordSell, refresh, resetPaper, setBankroll, suggested, type Account, type Position, type Quote, type Side } from './ledger';
import { fillTicket, subTabOf, llmAvailable, planFromWords, planWithLLM, scanMarkets, type Ctx, type MarketPick, type PlanItem, type Step } from './agent';
import { installId, localJournal, onJournal, record, webUrl, type Entry } from './journal';
import { AssistantMessage, UserMessage } from './argos/Message';
import { isPaper, setPaper, usePaper } from './paper';
import { apiJSON, gammaLastOk, gammaOk, hhmm } from './net';
import { fetchMe, getWallet, heldOnEvent, type WalletPos, openMyResults, setWallet, upDown, WALLET_RE, type Me } from './me';
import { intendedAction, verdictOf, verdictRank } from './policy';
import { API } from './agent';

/** "Why wait" numbers from the backtest (return per $1 by horizon, after costs); none if offline. */
let whyCache: Promise<string | undefined> | undefined;
function whyWait(): Promise<string | undefined> {
  whyCache ??= apiJSON<any>('/api/backtest').then(({ data: b }) => {
    const by = new Map<number, number>((b?.by_horizon ?? []).map((h: any) => [h.horizon_hours, h.with_costs?.mean_return_per_trade]));
    const late = [by.get(24), by.get(12)].filter((x): x is number => typeof x === 'number');
    if (!late.length) return undefined;
    const c = (x: number) => `${x >= 0 ? '' : '−'}${Math.round(Math.abs(x) * 100)}¢`;
    const avg = late.reduce((s2, x) => s2 + x, 0) / late.length;
    const parts = [by.get(72) !== undefined ? `3 days out ${c(by.get(72)!)}` : '', by.get(168) !== undefined ? `a week out ${c(by.get(168)!)}` : ''].filter(Boolean);
    return `Why wait: in our test, bets placed within 24h of the end earned ~${c(avg)} per $1${parts.length ? `; ${parts.join(', ')}` : ''}.`;
  }).catch(() => undefined);
  return whyCache;
}
function WhyWait() {
  const [t, setT] = useState<string>();
  useEffect(() => { void whyWait().then(setT); }, []);
  return t ? <p className="mt-1.5 text-caption text-[#64748b]">{t}</p> : <p className="mt-1.5 text-caption text-[#64748b]">Why wait: in our test, bets placed within 24h of the end earned much more per $1 than earlier ones.</p>;
}

export const UP = '#15803d';
export const DOWN = '#e11d48';
export const MARKET = '#a1a1aa';
export const INK = '#0f172a';
const MUTED = '#64748b';

export const money = (x: number) => {
  const a = Math.abs(x);
  const s = a >= 100 ? Math.round(a).toLocaleString() : a.toFixed(2).replace(/\.00$/, '');
  return `${x < 0 ? '−' : ''}$${s}`;
};
const pct = (x: number) => `${Math.round(x * 100)}%`;
const sideOf = (d: Decision): Side | undefined => { const a = intendedAction(d); return a === 'BUY_YES' ? 'YES' : a === 'BUY_NO' ? 'NO' : undefined; };
const clean = (s: string) => s.replace(/\s*\(.*\)\s*$/, '').replace(/\s+/g, ' ').trim();
/** "Price too low" when Horizon backs Yes, "too high" when it backs No, else fair. */
const priceWord = (d: Decision) => (d.blockedBy ? `One bet per event: ${clean(d.blockedBy)} has the larger edge`
  : verdictOf(d) === 'SKIP' ? 'Price fair, skip' : intendedAction(d) === 'BUY_YES' ? 'Price too low' : 'Price too high');
const stakeFor = (a: Account | undefined, d: Decision) => Math.max(1, Math.floor(a ? suggested(a, d) : 0));
/** One plain reason per decision. */
export const reasonOf = (d: Decision) => intendedAction(d) === 'BUY_YES'
  ? (d.price < 0.5 ? 'Long shots like this come true more often than their price says.' : 'Horizon thinks this is more likely than the price says.')
  : intendedAction(d) === 'BUY_NO'
    ? (d.price > 0.5 ? 'Favourites like this lose more often than their price says.' : 'Horizon thinks this is less likely than the price says.')
    : 'The price looks about right.';

/** Best window from the backtest: 24h to 12h before the scheduled end, in local time. */
export function bestTime(hours: number) {
  if (hours <= 12) return 'Best time: now, it ends soon';
  if (hours <= 24) return 'Best time: now';
  const end = Date.now() + hours * 3.6e6;
  const a = new Date(end - 24 * 3.6e6), b = new Date(end - 12 * 3.6e6);
  const hm = (d: Date) => { const r = new Date(Math.round(d.getTime() / 3.6e6) * 3.6e6); return r.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false }); };
  const today = new Date(); const tmr = new Date(Date.now() + 864e5);
  const same = (x: Date, y: Date) => x.toDateString() === y.toDateString();
  const day = same(a, today) ? (a.getHours() >= 18 ? 'tonight' : 'today') : same(a, tmr) ? (a.getHours() >= 18 ? 'tomorrow night' : 'tomorrow')
    : a.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
  return `Best time: ${day} ${hm(a)}–${hm(b)}`;
}

// ---------- icons (drawn, one stroke weight) ----------

const Icon = ({ d, size = 16, stroke = 1.8 }: { d: string; size?: number; stroke?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d={d} />
  </svg>
);
const I = {
  up: 'M12 19V5m0 0l-6 6m6-6l6 6',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  cross: 'M6 6l12 12M18 6L6 18',
  chevron: 'M9 6l6 6-6 6',
  gear: 'M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z',
  back: 'M15 6l-6 6 6 6',
  external: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
};
const Loader = ({ color = MUTED, dot = 4 }: { color?: string; dot?: number }) => <span className="hz-loader" style={{ ['--dot' as string]: `${dot}px`, color }} aria-label="Working"><i /><i /><i /></span>;

// ---------- account (budget + the bets the user said they placed) ----------

export function useAccount(): Account | undefined {
  const [a, setA] = useState<Account>();
  useEffect(() => { void getAccount().then(setA); return onAccount(setA); }, []);
  return a;
}

/** Mark open bets to live prices (and settle resolved ones) every 30s while the panel is open. */
export function useMarking(model: Model | undefined, a: Account | undefined) {
  const openKey = a?.positions.filter((p) => p.status === 'open').map((p) => p.marketSlug).join() ?? '';
  useEffect(() => {
    if (!openKey) return;
    let dead = false;
    const tick = async () => { const qs = await quotes(model, openKey.split(',')); if (!dead) await refresh(qs); };
    void tick();
    const t = setInterval(() => void tick(), 30000);
    return () => { dead = true; clearInterval(t); };
  }, [model, openKey]);
}

// ---------- chrome ----------

export type TabName = 'bet' | 'decisions';

export function Header({ onSettings }: { onSettings: () => void }) {
  const paperHdr = usePaper();
  return (
    <div className="flex items-center justify-between gap-3 px-4 pb-2 pt-3">
      <span className="flex items-center gap-2"><span className="hz-display text-[26px] leading-none text-[#0f172a]">Horizon</span>{paperHdr ? <PaperBadge /> : null}</span>
      <button type="button" onClick={onSettings} aria-label="Budget" title="Budget" className="hz-chip flex h-[30px] w-[30px] items-center justify-center rounded-full text-[#475569]">
        <Icon d={I.gear} size={15} />
      </button>
    </div>
  );
}

export function Tabs({ tab, setTab }: { tab?: TabName; setTab: (t: TabName) => void }) {
  const items: [TabName, string][] = [['bet', 'Bet'], ['decisions', 'My decisions']];
  return (
    <div role="tablist" className="hz-seg mx-4 mb-1 grid grid-cols-2 rounded-control p-[3px]">
      {items.map(([k, label]) => (
        <button key={k} role="tab" aria-selected={tab === k} type="button" onClick={() => setTab(k)}
          className={`rounded-[9px] py-[6px] text-footnote font-semibold transition-ui duration-fast ease-soft ${tab === k ? 'hz-seg-on text-[#0f172a]' : 'text-[#64748b] hover:text-[#0f172a]'}`}>
          {label}
        </button>
      ))}
    </div>
  );
}

export function Welcome({ onGo }: { onGo: () => void }) {
  return (
    <div className="hz-enter flex min-h-full flex-col justify-between px-6 pb-6 pt-12">
      <div>
        <div className="mb-6 flex justify-center"><ThinkingOrb state="searching" size={64} theme="light" style={{ width: 72, height: 72 }} /></div>
        <h1 className="hz-display text-center text-[38px] leading-[1.05]">Find the bets where the price is wrong</h1>
        <p className="mx-auto mt-4 max-w-[32ch] text-center text-subhead text-[#334155]">Horizon finds bets where Polymarket's price is wrong, and tells you how much to put on.</p>
      </div>
      <div className="mt-10">
        <button type="button" onClick={onGo} className="hz-cta h-12 w-full rounded-control bg-[#0f172a] text-subhead font-semibold text-white">Show me tonight's best bets</button>
        <p className="mt-3 text-center text-caption text-[#94a3b8]">18+. Horizon sets up the bet; you press Trade on Polymarket.</p>
      </div>
    </div>
  );
}

// ---------- live steps ----------

function StepMark({ s }: { s: Step }) {
  if (s.status === 'run') return <span className="flex h-5 w-5 shrink-0 items-center justify-center"><Loader /></span>;
  if (s.status === 'ok') return <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full" style={{ color: UP, background: 'rgba(21,128,61,0.10)' }}><Icon d={I.check} size={12} stroke={2.4} /></span>;
  if (s.status === 'fail') return <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full" style={{ color: DOWN, background: 'rgba(225,29,72,0.10)' }}><Icon d={I.cross} size={11} stroke={2.4} /></span>;
  return <span className="flex h-5 w-5 shrink-0 items-center justify-center"><span className="h-1.5 w-1.5 rounded-full bg-[#0f172a]" /></span>;
}
const ORB_FOR: Record<string, OrbState> = { searching: 'searching', working: 'working', shaping: 'shaping', solving: 'solving' };

function Thinking({ steps, fallback }: { steps: Step[]; fallback: string }) {
  const current = [...steps].reverse().find((x) => x.status === 'run');
  const label = `${current?.text ?? fallback}…`;
  return (
    <span className="hz-reason-pill">
      <ThinkingOrb state={current?.kind ? ORB_FOR[current.kind] : 'composing'} size={64} theme="light" style={{ width: 32, height: 32, flexShrink: 0 }} />
      <span className="hz-orb-label text-footnote" data-text={label}>{label}</span>
    </span>
  );
}

function Steps({ steps }: { steps: Step[] }) {
  return (
    <ol className="mt-3 space-y-2" aria-live="polite">
      {steps.map((x) => (
        <li key={x.id} className="hz-step flex gap-2.5"><StepMark s={x} />
          <span className="min-w-0 pt-[1px] text-body text-[#334155]">{x.text}{x.detail ? <span className="block text-caption text-[#64748b]">{x.detail}</span> : null}</span></li>
      ))}
    </ol>
  );
}

// ---------- setting a bet up on Polymarket, one at a time ----------

const journalOf = (item: PlanItem, source: 'card' | 'agent' | 'paper', status: 'shown' | 'set_up' | 'placed' | 'skipped') => {
  if (item.kind !== 'buy' || !item.q.decision) return;
  void record({ marketId: item.q.conditionId, slug: item.q.marketSlug, question: item.q.question, d: item.q.decision, stake: item.amount, source, status });
};

/**
 * For each item: fill Polymarket's ticket (narrated, Argos thinking orb), then stop. The user
 * presses Trade there and tells Horizon "I placed it" or "Skip"; both go to the journal.
 */
export function PaperBadge() {
  return <span className="inline-flex items-center rounded-full bg-[rgba(15,23,42,0.07)] px-2 py-[1px] text-[10.5px] font-semibold uppercase tracking-[0.04em] text-[#475569]">Paper</span>;
}

/** The same walk on Polymarket in both modes; in paper mode the last step records to the paper book instead of the user pressing Trade. */
export function Doer(props: { model: Model; tabId?: number; items: PlanItem[]; source: 'card' | 'agent'; onFinish: (placed: number) => void }) {
  return <RealDoer {...props} />;
}

/** Paper: record at the live ask read now (+ taker fee), with the card's event-level decision. */
async function addPaper(model: Model, it: PlanItem, by: 'you' | 'agent') {
  if (it.kind !== 'buy') return false;
  const live = (await quotes(model, [it.q.marketSlug]).catch(() => new Map<string, Quote>())).get(it.q.marketSlug);
  const q = live && live.bid > 0 && live.ask < 1 ? { ...live, decision: it.q.decision } : it.q;
  await recordBuy(q, it.side, it.amount, by, 'Paper bet (ticket walked on Polymarket, not bought)', 'paper');
  journalOf(it, 'paper', 'placed');
  return true;
}

function RealDoer({ model, tabId, items, source, onFinish }: { model: Model; tabId?: number; items: PlanItem[]; source: 'card' | 'agent'; onFinish: (placed: number) => void }) {
  const paper = useRef(isPaper()).current;
  // Agent plans in paper mode: walk every ticket like real, then one press adds them all.
  const batch = paper && source === 'agent' && items.length > 1;
  const [walked, setWalked] = useState<{ item: PlanItem; ok: boolean; label: string }[]>([]);
  const [i, setI] = useState(0);
  const [steps, setSteps] = useState<Step[]>([]);
  const [phase, setPhase] = useState<'filling' | 'ready' | 'confirmAll' | 'finished'>('filling');
  const [fill, setFill] = useState<{ ok: boolean; error?: string; label: string }>();
  const [placed, setPlaced] = useState(0);
  const item = items[i];
  const run = useRef(-1);
  useEffect(() => {
    if (!item || run.current === i) return;
    run.current = i;
    setSteps([]); setPhase('filling'); setFill(undefined);
    const acc: Step[] = [];
    const ctx = { model, tabId, onStep: (s: Step) => { const k = acc.findIndex((x) => x.id === s.id); if (k >= 0) acc[k] = s; else acc.push(s); setSteps([...acc]); } };
    const amount = item.kind === 'buy' ? item.amount : item.pos.shares * item.fraction;
    const side = item.kind === 'buy' ? item.side : item.pos.side;
    void fillTicket(ctx, item.q, side, amount, item.kind).then((r) => {
      setFill(r);
      if (!paper && r.ok) journalOf(item, source, 'set_up');
      if (batch) {
        setWalked((w) => [...w, { item, ok: r.ok, label: r.label }]);
        setTimeout(() => { if (i + 1 >= items.length) setPhase('confirmAll'); else setI(i + 1); }, 1200); // let the user see the ticket
      } else setPhase('ready');
    });
  }, [i, item, model, tabId, source, paper, batch, items.length]);
  const addAll = async () => {
    let n = 0;
    for (const w of walked) if (await addPaper(model, w.item, 'agent')) n++;
    setPhase('finished'); onFinish(n);
  };
  const next = async (did: boolean) => {
    if (paper) {
      const ok = did ? await addPaper(model, item, source === 'agent' ? 'agent' : 'you') : false;
      const n = placed + (ok ? 1 : 0);
      setPlaced(n);
      if (i + 1 >= items.length) { setPhase('finished'); onFinish(n); } else setI(i + 1);
      return;
    }
    const n = placed + (did ? 1 : 0);
    if (item.kind === 'buy') {
      journalOf(item, source, did ? 'placed' : 'skipped');
      if (did) void recordBuy(item.q, item.side, item.amount, source === 'agent' ? 'agent' : 'you', 'Placed by you on Polymarket');
    } else if (did) void recordSell(item.q, item.pos.id, item.fraction, 'Sold by you on Polymarket');
    setPlaced(n);
    if (i + 1 >= items.length) { setPhase('finished'); onFinish(n); } else setI(i + 1);
  };
  if (phase === 'finished' || !item) return null;
  if (phase === 'confirmAll') {
    const buys = walked.filter((w) => w.item.kind === 'buy');
    const total = buys.reduce((s2, w) => s2 + (w.item.kind === 'buy' ? w.item.amount : 0), 0);
    return (
      <div className="hz-card hz-enter mt-3 rounded-card px-4 py-3.5">
        <p className="flex items-center gap-2 text-subhead font-semibold">All {walked.length} tickets walked on Polymarket <PaperBadge /></p>
        <ul className="mt-1 space-y-0.5">{walked.map((w, k) => <li key={k} className="text-footnote" style={{ color: w.ok ? '#334155' : '#64748b' }}>{w.item.kind === 'buy' ? `${money(w.item.amount)} on ${w.label || clean(w.item.name)} · ${w.item.side === 'YES' ? 'Yes' : 'No'}` : clean(w.item.name)}{w.ok ? '' : ' (ticket not filled)'}</li>)}</ul>
        <p className="mt-1 text-caption text-[#94a3b8]">Nothing was bought. Adding records them at the live price now, with Polymarket's fee.</p>
        <div className="mt-3 flex gap-2">
          <button type="button" onClick={() => void addAll()} className="hz-cta h-10 flex-1 rounded-control text-body font-semibold text-white" style={{ background: INK }}>Add {buys.length} to paper book ({money(total)})</button>
          <button type="button" onClick={() => { setPhase('finished'); onFinish(0); }} className="hz-chip h-10 rounded-control px-4 text-body font-semibold text-[#475569]">Skip</button>
        </div>
      </div>
    );
  }
  const side = item.kind === 'buy' ? item.side : item.pos.side;
  const what = item.kind === 'buy'
    ? `${money(item.amount)} on ${fill?.label ?? clean(item.name)} · ${side === 'YES' ? 'Yes' : 'No'}`
    : `${item.fraction >= 0.999 ? 'all' : 'part'} of ${fill?.label ?? clean(item.name)}`;
  return (
    <div className="hz-enter mt-3">
      {items.length > 1 || paper ? <p className="flex items-center gap-2 text-footnote font-medium text-[#64748b]">{items.length > 1 ? `${i + 1} of ${items.length} · ${clean(item.name)}` : null}{paper ? <PaperBadge /> : null}</p> : null}
      {phase === 'filling' ? <div className="mt-1"><Thinking steps={steps} fallback="Opening Polymarket" /></div> : null}
      <Steps steps={steps} />
      {phase === 'ready' ? (
        <div className="hz-card hz-enter mt-3 rounded-card px-4 py-3.5">
          {fill?.ok ? (
            <>
              <p className="text-subhead font-semibold">Ready on Polymarket</p>
              <p className="mt-0.5 text-body text-[#334155]">{paper ? `${what}. Paper mode: don't press Trade; add it to your paper book instead.` : item.kind === 'buy' ? `${what}. Press Trade to place it.` : `Selling ${what}. Press Sell to do it.`}</p>
            </>
          ) : (
            <>
              <p className="text-subhead font-semibold">Set this one up by hand</p>
              <p className="mt-0.5 text-body text-[#334155]">{fill?.error ?? 'The page did not respond'}. On Polymarket: {item.kind === 'buy' ? what : `sell ${what}`}.</p>
            </>
          )}
          <div className="mt-3 flex gap-2">
            {paper ? (
              <button type="button" onClick={() => void next(true)} className="hz-cta h-10 flex-1 rounded-control text-body font-semibold text-white" style={{ background: INK }}>Add to paper book</button>
            ) : <button type="button" onClick={() => void next(true)} className="hz-chip h-10 flex-1 rounded-control text-body font-semibold" style={{ color: UP }}>I placed it</button>}
            <button type="button" onClick={() => void next(false)} className="hz-chip h-10 flex-1 rounded-control text-body font-semibold text-[#475569]">Skip</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ---------- the amount: Horizon suggests, the user decides ----------

const stepOf = (v: number) => (v < 10 ? 1 : v < 50 ? 5 : 10);

/** "− $2 +" with tap-to-type. Min $1 (Polymarket's minimum), max the budget. */
export function AmountControl({ value, onChange, max, compact = false, label }: { value: number; onChange: (v: number) => void; max: number; compact?: boolean; label?: string }) {
  const [text, setText] = useState<string>();
  const clamp = (v: number) => Math.min(Math.max(1, Math.round(v * 100) / 100), Math.max(1, max));
  const commit = () => { if (text !== undefined) { const n = Number(text.replace(/[$,\s]/g, '')); if (n > 0) onChange(clamp(n)); setText(undefined); } };
  const h = compact ? 'h-8' : 'h-12', w = compact ? 'w-7' : 'w-10';
  return (
    <div className={`flex shrink-0 items-center rounded-control border border-[rgba(15,23,42,0.12)] bg-white/80 ${h}`} aria-label={label ?? 'Amount'}>
      <button type="button" aria-label="Less" onClick={() => onChange(clamp(value - stepOf(value - 0.01)))} disabled={value <= 1} className={`flex ${h} ${w} items-center justify-center text-[#334155] disabled:opacity-30`}><Icon d="M6 12h12" size={compact ? 13 : 16} /></button>
      <span className={`flex items-center font-semibold ${compact ? 'text-footnote' : 'text-subhead'}`}>
        $<input inputMode="decimal" aria-label="Amount in dollars" value={text ?? String(value)} onFocus={(e) => { setText(String(value)); e.currentTarget.select(); }}
          onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
          className="bg-transparent text-center outline-none" style={{ width: `${Math.max(2, String(text ?? value).length) + 0.5}ch` }} />
      </span>
      <button type="button" aria-label="More" onClick={() => onChange(clamp(value + stepOf(value)))} disabled={value >= max} className={`flex ${h} ${w} items-center justify-center text-[#334155] disabled:opacity-30`}><Icon d="M12 6v12M6 12h12" size={compact ? 13 : 16} /></button>
    </div>
  );
}

// ---------- the main card: one line, one button ----------

export function BetCard({ model, a, marketSlug, title, d, tabId, onDetails }: {
  model: Model; a?: Account; marketSlug: string; title: string; d: Decision; tabId?: number; onDetails?: () => void;
}) {
  const paper = usePaper();
  const [quote, setQuote] = useState<Quote>();
  const [held, setHeld] = useState<WalletPos[]>([]);
  useEffect(() => { if (quote?.eventSlug) void heldOnEvent(quote.eventSlug).then(setHeld); }, [quote?.eventSlug]);
  const mine = held.find((p) => p.conditionId && p.conditionId === quote?.conditionId && (p.size ?? 0) > 0);
  const holding = mine ? 0 : held.length;
  const unsure = d.untested ? 'Closer to the end than anything Horizon was tested on (12 h).' : quote ? caution(quote) : undefined;
  const verdict = unsure || holding || mine ? 'SKIP' : verdictOf(d);
  const side = verdict === 'SKIP' ? undefined : sideOf(d);
  const sug = stakeFor(a, d);
  const kellyUsd = a ? suggested(a, d) : 0; // the true ¼ Kelly amount, before Polymarket's $1 minimum
  const [chosen, setChosen] = useState<number>();
  const amount = chosen ?? sug;
  const [doing, setDoing] = useState<PlanItem[]>();
  const [msg, setMsg] = useState<{ ok: boolean; text: string }>();
  useEffect(() => {
    let dead = false;
    void quotes(model, [marketSlug]).then((m) => {
      const q0 = m.get(marketSlug);
      if (dead || !q0) return;
      // The card's d was decided with the whole event (COH); never let the single-market quote override it.
      const q = q0.decision ? { ...q0, decision: d } : q0;
      setQuote(q);
      if (q.decision) void record({ marketId: q.conditionId, slug: q.marketSlug, question: q.question, d: q.decision, stake: side ? stakeFor(a, q.decision) : 0, source: 'card', status: 'shown' });
    });
    return () => { dead = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model, marketSlug]);
  const start = async () => {
    setMsg(undefined);
    const q0 = quote ?? (await quotes(model, [marketSlug])).get(marketSlug);
    if (!q0 || !side) { setMsg({ ok: false, text: 'Could not get a live price. Try again.' }); return; }
    // The card's decision is the event-level one (coherence, one bet per event); bet on that.
    const q = { ...q0, decision: d };
    const c = checkBet(await getAccount(), q, side, amount);
    if (!c.ok) { setMsg({ ok: false, text: `${c.error}.` }); return; }
    setDoing([{ kind: 'buy', q, side, amount: c.amount, name: title, suggested: c.suggested }]);
  };
  return (
    <article className="hz-card hz-enter rounded-panel p-4">
      <h2 className="hz-display text-[27px] leading-[1.1] [overflow-wrap:anywhere]">{clean(title)}</h2>
      <p className="mt-2.5 text-subhead text-[#475569]">
        Market {pct(d.price)} · Horizon <b className="font-semibold text-[#0f172a]">{pct(d.q)}</b> · <b className="font-semibold" style={{ color: side && verdict === 'BET' ? UP : MUTED }}>{unsure ? 'Not sure here' : mine ? 'You hold this' : holding ? 'Already in' : priceWord(d)}</b>
      </p>
      {unsure ? <p className="mt-1.5 text-footnote text-[#64748b]">{unsure} Horizon gives no advice on this one.</p> : null}
      {!unsure && holding ? <p className="mt-1.5 text-footnote text-[#64748b]">You already hold {holding} bet{holding > 1 ? 's' : ''} on this event: a second one is the same risk, so Horizon won&apos;t suggest more.</p> : null}
      {mine && quote ? <PositionAdvice pos={mine} q={quote} d={d} unsure={!!unsure} title={title} onSell={(it) => setDoing([it])} busy={!!doing} /> : null}
      {verdict === 'SKIP' && !unsure && !holding && !mine && Math.abs(d.q - d.price) >= 0.01 ? <p className="mt-1.5 text-footnote text-[#64748b]">Horizon&apos;s range is {pct(d.lo)}–{pct(d.hi)}; after the spread and fees ({Math.max(1, Math.round(d.cost * 100))}¢) that gap isn&apos;t a safe edge.</p> : null}
      {d.domain === 'crypto' ? <p className="mt-1 text-caption text-[#94a3b8]">Crypto: our tests show no edge here. Polymarket prices these well.</p> : null}
      {side && verdict === 'BET' ? <p className="mt-1.5 inline-flex items-center gap-1.5 text-footnote text-[#64748b]"><Icon d={I.clock} size={13} /> {bestTime(d.hours)}</p> : null}
      {side && verdict === 'WAIT' ? (
        <div className="mt-4 rounded-card bg-[rgba(15,23,42,0.04)] px-3.5 py-3">
          <p className="inline-flex items-center gap-1.5 text-subhead font-semibold text-[#0f172a]"><Icon d={I.clock} size={15} /> Wait. {bestTime(d.hours)}</p>
          <WhyWait />
        </div>
      ) : null}
      {side && verdict === 'BET' && !doing ? (
        <>
          <div className="mt-4 flex items-stretch gap-2">
            <AmountControl value={amount} onChange={setChosen} max={a?.bankroll ?? 1000} />
            <button type="button" onClick={() => void start()} className="hz-cta h-12 flex-1 rounded-control px-2 text-subhead font-semibold text-white" style={{ background: UP }}>
              {paper ? 'Paper bet' : 'Set up'} {money(amount)} on {side === 'YES' && !/\?\s*$/.test(title) && clean(title).length <= 16 ? clean(title) : side === 'YES' ? 'Yes' : 'No'}
            </button>
          </div>
          <p className="mt-1.5 text-caption text-[#94a3b8]">
            {kellyUsd < 1
              ? <>Horizon suggests {money(kellyUsd)} (¼ Kelly of your {money(a?.bankroll ?? 1000)} budget) · Polymarket minimum is $1</>
              : <>Horizon suggests {money(sug)} (¼ Kelly, at most 5% of your {money(a?.bankroll ?? 1000)} budget)</>}
            {amount > Math.max(1, sug) ? <span className="text-[#64748b]"> · above Horizon&apos;s suggestion</span> : null}
          </p>
        </>
      ) : null}
      {msg ? <p className="mt-2 text-footnote font-medium" style={{ color: msg.ok ? UP : DOWN }}>{msg.text}</p> : null}
      {doing ? <Doer model={model} tabId={tabId} items={doing} source="card" onFinish={(n) => { setDoing(undefined); setMsg({ ok: true, text: paper ? (n ? 'Paper bet placed. See My decisions → Paper.' : 'Paper bet not placed.') : n ? 'Saved in My decisions.' : 'Skipped. Saved in My decisions.' }); }} /> : null}
      {onDetails ? <button type="button" onClick={onDetails} className="mt-3 text-footnote font-medium text-[#64748b] underline decoration-[rgba(15,23,42,0.15)] underline-offset-[3px] hover:text-[#0f172a]">Details</button> : null}
    </article>
  );
}

/** The test result in one line under the card, from /api/backtest's headline (fallback: the shipped V3 numbers). */
let trustCache: Promise<{ c: number; lo: number; hi: number; n: number; cachedAt?: number } | undefined> | undefined;
function TrustLine() {
  const [t, setT] = useState<{ c: number; lo: number; hi: number; n: number; cachedAt?: number }>({ c: 0.31, lo: 0.23, hi: 0.40, n: 10579 });
  useEffect(() => {
    trustCache ??= apiJSON<any>('/api/backtest').then(({ data: b, cachedAt }) => {
      const h = b?.headline;
      return typeof h?.per_dollar === 'number' ? { c: h.per_dollar, lo: h.per_dollar_ci?.[0] ?? h.per_dollar, hi: h.per_dollar_ci?.[1] ?? h.per_dollar, n: b.n_test_markets ?? 10579, cachedAt } : undefined;
    }).catch(() => undefined);
    void trustCache.then((x) => { if (x) setT(x); });
  }, []);
  const c = (x: number) => `${x >= 0 ? '+' : '−'}${Math.round(Math.abs(x) * 100)}¢`;
  return (
    <p className="mt-6 border-t border-[rgba(15,23,42,0.06)] pt-3 text-caption leading-relaxed text-[#94a3b8]">
      On {t.n.toLocaleString()} past markets it never saw, this rule made <b className="font-semibold text-[#475569]">{c(t.c)} per $1</b> after fees (likely {c(t.lo)} to {c(t.hi)}), mostly on sports. Most single bets lose; it adds up over many.{' '}
      <a href="https://web-production-c7376.up.railway.app" target="_blank" rel="noreferrer" className="text-[#64748b] underline decoration-[rgba(15,23,42,0.15)] underline-offset-2">How we know</a>
      {t.cachedAt ? <span className="block">Offline copy · cached at {hhmm(t.cachedAt)}</span> : null}
    </p>
  );
}

/**
 * A position the public wallet already holds on this market: HOLD or SELL. Rule (under test until the
 * dynamic-exit check lands): sell if what the market pays now (bid for Yes, 1 − ask for No) is at least
 * Horizon's value of the side plus the cost. Sell only fills the ticket; the human presses.
 */
function PositionAdvice({ pos, q, d, unsure, title, onSell, busy }: { pos: WalletPos; q: Quote; d: Decision; unsure: boolean; title: string; onSell: (it: PlanItem) => void; busy: boolean }) {
  const side: Side = /^no$/i.test(pos.outcome ?? '') ? 'NO' : 'YES';
  const pays = side === 'YES' ? q.bid : 1 - q.ask;
  const worth = side === 'YES' ? d.q : 1 - d.q;
  const sell = !unsure && pays >= worth + d.cost;
  const shares = Math.floor((pos.size ?? 0) * 100) / 100;
  const c = (x: number) => `${Math.round(x * 100)}¢`;
  const synthetic: Position = { id: `wallet-${q.conditionId}-${side}`, marketSlug: q.marketSlug, eventSlug: q.eventSlug, question: q.question, label: q.label, side,
    shares, stake: shares * (pos.avgPrice ?? pays), avgPrice: pos.avgPrice ?? pays, qAtOpen: worth, openedAt: new Date().toISOString(), by: 'you', status: 'open' };
  return (
    <div className="mt-4 rounded-card bg-[rgba(15,23,42,0.04)] px-3.5 py-3">
      <p className="text-footnote text-[#475569]">You hold {shares.toLocaleString()} {side === 'YES' ? 'Yes' : 'No'} shares{pos.avgPrice ? ` (bought at ${c(pos.avgPrice)})` : ''}.</p>
      {/* COH+DYNAMIC (sell when what the market pays >= Horizon's value + cost): same money, smaller drawdown on the test. */}
      {unsure ? null : sell ? (
        <>
          <p className="mt-1 text-subhead font-semibold text-[#0f172a]">Sell: the market now pays {c(pays)}, Horizon values it at {c(worth)}.</p>
          <button type="button" disabled={busy} onClick={() => onSell({ kind: 'sell', q, pos: synthetic, fraction: 1, name: title })}
            className="hz-cta mt-3 h-11 w-full rounded-control text-subhead font-semibold text-white disabled:opacity-50" style={{ background: INK }}>Set up sale of {shares.toLocaleString()} shares</button>
        </>
      ) : <p className="mt-1 text-subhead font-semibold text-[#0f172a]">Hold: Horizon values it at {c(worth)}, the market pays {c(pays)}.</p>}
      <p className="mt-1.5 text-caption text-[#94a3b8]">Selling early did not add profit in our test; it slightly reduced drawdown (+30.9¢ vs +31.2¢ per $1, max drawdown 0.20 vs 0.23).</p>
    </div>
  );
}

function Collapsible({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="mt-4">
      <button type="button" onClick={() => setOpen((x) => !x)} aria-expanded={open} className="flex w-full items-center justify-between py-2 text-left">
        <span className="text-subhead font-semibold">{title}</span>
        <span className="text-[#64748b] transition-transform duration-base ease-soft" style={{ transform: open ? 'rotate(90deg)' : 'none' }}><Icon d={I.chevron} /></span>
      </button>
      <div className={`hz-drawer${open ? ' is-open' : ''}`}><div>{children}</div></div>
    </section>
  );
}

function Row({ title, d, onClick, active }: { title: string; d: Decision; onClick: () => void; active?: boolean }) {
  const v = verdictOf(d);
  const good = v !== 'SKIP';
  return (
    <button type="button" onClick={onClick} className={`hz-row-link hz-rule -mx-2 flex w-[calc(100%+16px)] items-center gap-3 rounded-control px-2 py-3 text-left ${active ? 'bg-[rgba(15,23,42,0.03)]' : ''}`}>
      <span className="min-w-0 flex-1 line-clamp-2 text-body font-medium">{clean(title)}</span>
      <span className="shrink-0 text-footnote font-semibold" style={{ color: good ? UP : MUTED }}>{d.blockedBy ? 'One per event' : v === 'WAIT' ? 'Later' : good ? priceWord(d) : 'Skip'}</span>
    </button>
  );
}

// ---------- Bet tab: this market, or tonight's best ----------

/** Never a blank card: when Polymarket's prices can't be fetched, say so and when they last were. */
function Unreachable({ onRetry }: { onRetry: () => void }) {
  const [last, setLast] = useState<number>();
  useEffect(() => { void gammaLastOk().then(setLast); }, []);
  return (
    <div className="px-4 pt-3">
      <div className="hz-card rounded-panel p-4">
        <p className="text-subhead font-semibold text-[#0f172a]">Polymarket isn't reachable right now.</p>
        <p className="mt-1 text-footnote text-[#64748b]">{last ? `Last checked ${hhmm(last)}.` : 'Check your connection.'}</p>
        <button type="button" onClick={onRetry} className="hz-chip mt-3 rounded-control px-4 py-2 text-body font-semibold">Try again</button>
      </div>
    </div>
  );
}

export function MarketBet({ model, a, slug, tabId, onDetails }: { model: Model; a?: Account; slug: string; tabId?: number; onDetails: () => void }) {
  const [ev, setEv] = useState<{ title: string; legs: Leg[] } | 'loading' | 'error'>('loading');
  const [pick, setPick] = useState(0);
  const [picked, setPicked] = useState(false);
  const [held, setHeld] = useState<WalletPos[]>([]);
  const load = useCallback(() => { setEv('loading'); setPick(0); setPicked(false); decideEvent(model, slug).then((e) => { gammaOk(); setEv(e); }).catch(() => setEv('error')); }, [model, slug]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { void heldOnEvent(slug).then(setHeld); }, [slug]);
  if (ev === 'loading') return <div className="px-4 pt-3"><Thinking steps={[]} fallback="Reading this market" /><div className="hz-skeleton mt-4 h-[230px] rounded-panel" /></div>;
  if (ev === 'error') return <Unreachable onRetry={load} />;
  const band = model.tradable;
  const legs = ev.legs.filter((l) => l.decision && l.marketSlug && l.decision.price >= band[0] && l.decision.price <= band[1])
    .sort((x, y) => verdictRank[verdictOf(y.decision!)] - verdictRank[verdictOf(x.decision!)] || y.decision!.netEdge - x.decision!.netEdge);
  if (!legs.length) {
    return (
      <div className="px-4 pb-6 pt-3">
        <p className="text-footnote text-[#64748b]">{ev.title}</p>
        <h1 className="hz-display mt-1 text-[28px] leading-tight">Nothing to bet on here</h1>
        <p className="mt-2 text-body text-[#475569]">These outcomes are too close to certain, or not trading right now.</p>
      </div>
    );
  }
  // If the wallet holds one of these outcomes, open on it (its HOLD/SELL card) unless the user picked another.
  const heldIx = picked ? -1 : legs.findIndex((l) => held.some((h) => h.slug === l.marketSlug && (h.size ?? 0) > 0));
  const best = legs[heldIx >= 0 ? heldIx : Math.min(pick, legs.length - 1)];
  const titleOf = (l: Leg) => (legs.length > 1 ? clean(l.label) : clean(l.question));
  return (
    <div className="px-4 pb-6 pt-3">
      <p className="mb-2 text-footnote font-medium text-[#64748b] [overflow-wrap:anywhere]">{ev.title}</p>
      <BetCard key={best.marketSlug} model={model} a={a} marketSlug={best.marketSlug!} title={titleOf(best)} d={best.decision!} tabId={tabId} onDetails={onDetails} />
      {legs.length > 1 ? (
        <Collapsible title="Other outcomes">
          {legs.map((l, k) => <Row key={l.marketSlug} title={titleOf(l)} d={l.decision!} active={l === best} onClick={() => { setPick(k); setPicked(true); }} />)}
        </Collapsible>
      ) : null}
      <TrustLine />
    </div>
  );
}

export function Tonight({ model, a, tabId, url, title, onDetails }: { model: Model; a?: Account; tabId?: number; url?: string; title?: string; onDetails: () => void }) {
  const [st, setSt] = useState<{ picks: MarketPick[] } | 'loading' | 'error'>('loading');
  const [pick, setPick] = useState(0);
  const [about, setAbout] = useState<{ q: string; rows: ScanRow[] }>();
  const run = useCallback(() => { setSt('loading'); setPick(0); scanMarkets(model, 'all', 24, 20).then((r) => { gammaOk(); return r; }).then((r) => setSt({ picks: r.picks.filter((p) => verdictOf(p.decision) !== 'SKIP').slice(0, 12) })).catch(() => setSt('error')); }, [model]);
  useEffect(() => { run(); }, [run]);
  useEffect(() => {
    const s = url && /^https?:/.test(url) && !/polymarket\.com/.test(url) ? subjectOf(title, url) : undefined;
    setAbout(undefined);
    if (s) searchMarkets(model, s.query, 5).then((rows) => setAbout({ q: s.query, rows })).catch(() => {});
  }, [model, url, title]);
  if (st === 'loading') return <div className="px-4 pt-3" aria-busy><Thinking steps={[]} fallback="Looking at tonight's markets" /><div className="hz-skeleton mt-4 h-[230px] rounded-panel" /></div>;
  if (st === 'error') return <Unreachable onRetry={run} />;
  const best = st.picks[Math.min(pick, Math.max(0, st.picks.length - 1))];
  const open = (u: string) => { if (tabId !== undefined) void chrome.tabs.update(tabId, { url: u }); else void chrome.tabs.create({ url: u }); };
  return (
    <div className="px-4 pb-6 pt-3">
      {best ? (
        <>
          <p className="mb-2 text-footnote font-medium text-[#64748b]">Tonight's best bet</p>
          <BetCard key={best.marketSlug} model={model} a={a} marketSlug={best.marketSlug} title={best.question} d={best.decision} tabId={tabId} onDetails={onDetails} />
          {st.picks.length > 1 ? (
            <Collapsible title="More good bets">
              {st.picks.map((p, k) => <Row key={p.marketSlug} title={p.question} d={p.decision} active={k === pick} onClick={() => setPick(k)} />)}
            </Collapsible>
          ) : null}
        </>
      ) : (
        <div className="hz-card rounded-panel p-5">
          <h1 className="hz-display text-[26px] leading-tight">No good bets right now</h1>
          <p className="mt-2 text-body text-[#334155]">Horizon would wait. Check back later tonight.</p>
        </div>
      )}
      {about?.rows.length ? (
        <Collapsible title={`About ${about.q}`}>
          {about.rows.map((r) => <Row key={r.question + r.slug} title={r.question} d={r.decision} onClick={() => open(r.url)} />)}
        </Collapsible>
      ) : null}
      <TrustLine />
    </div>
  );
}

// ---------- My decisions: this install's journal ----------

const STATUS_RANK: Record<Entry['status'], number> = { shown: 0, set_up: 1, skipped: 2, placed: 3 };
const STATUS_WORD: Record<Entry['status'], string> = { shown: 'Shown', set_up: 'Set up', skipped: 'Skipped', placed: 'Placed' };

export function MyDecisions({ model }: { model: Model }) {
  const paperOn = usePaper();
  const [view, setView] = useState<'real' | 'paper'>(paperOn ? 'paper' : 'real');
  return (
    <>
      <div className="px-4 pt-4">
        <div role="tablist" className="hz-seg inline-grid grid-cols-2 rounded-control p-[3px]">
          {(['real', 'paper'] as const).map((k) => (
            <button key={k} role="tab" aria-selected={view === k} type="button" onClick={() => setView(k)}
              className={`rounded-[9px] px-4 py-[5px] text-footnote font-semibold ${view === k ? 'hz-seg-on text-[#0f172a]' : 'text-[#64748b]'}`}>{k === 'real' ? 'Real' : 'Paper'}</button>
          ))}
        </div>
      </div>
      {view === 'paper' ? <PaperBook model={model} /> : <RealDecisions model={model} />}
    </>
  );
}

/** The paper book: positions at the live ask + fee, marked to the mid, settled at $1/$0 by Gamma. */
function PaperBook({ model }: { model: Model }) {
  const [a, setA] = useState<Account>();
  const [sure, setSure] = useState(false);
  useEffect(() => { void getAccount('paper').then(setA); return onAccount(setA, 'paper'); }, []);
  const openKey = a?.positions.filter((p) => p.status === 'open').map((p) => p.marketSlug).join() ?? '';
  useEffect(() => {
    if (!openKey) return;
    const tick = async () => refresh(await quotes(model, openKey.split(',')), 'paper');
    void tick();
    const t = setInterval(() => void tick(), 30000);
    return () => clearInterval(t);
  }, [model, openKey]);
  if (!a) return null;
  const open = a.positions.filter((p) => p.status === 'open'), done = a.positions.filter((p) => p.status !== 'open');
  const marked = open.reduce((s2, p) => s2 + p.shares * (p.mark ?? p.avgPrice) - p.stake, 0);
  const settled = done.reduce((s2, p) => s2 + (p.pnl ?? 0), 0);
  const staked = open.reduce((s2, p) => s2 + p.stake, 0);
  const cash = a.bankroll - staked + settled + open.reduce((s2, p) => s2 + (p.pnl ?? 0), 0);
  const sign = (x: number) => `${x >= 0.005 ? '+' : x <= -0.005 ? '−' : ''}${money(Math.abs(x))}`;
  return (
    <div className="px-4 pb-6 pt-4">
      <h1 className="hz-display flex items-center gap-2 text-[32px] leading-none">Paper book <PaperBadge /></h1>
      <p className="mt-2 text-body text-[#475569]">Practice money: {money(a.bankroll)} to start. Nothing here was sent to Polymarket.</p>
      <div className="mt-4 grid grid-cols-3 gap-2 text-center">
        {[['Cash', money(cash), INK], ['Open, marked', sign(marked), marked >= 0 ? UP : DOWN], ['Settled', sign(settled), settled >= 0 ? UP : DOWN]].map(([k, v, col]) => (
          <div key={k} className="hz-card rounded-card px-2 py-2.5"><p className="text-caption text-[#64748b]">{k}</p><p className="text-subhead font-semibold tabular-nums" style={{ color: col }}>{v}</p></div>
        ))}
      </div>
      {a.positions.length ? (
        <ul className="mt-4">
          {a.positions.slice(0, 100).map((p) => {
            const pl = p.status === 'open' ? p.shares * (p.mark ?? p.avgPrice) - p.stake : (p.pnl ?? 0);
            return (
              <li key={p.id} className="hz-rule flex items-center gap-3 py-3">
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-2 block text-body font-medium">{clean(p.question)}</span>
                  <span className="flex items-center gap-1.5 text-caption text-[#64748b]"><PaperBadge /> {money(p.stake)} on {p.side === 'YES' ? 'Yes' : 'No'} at {Math.round(p.avgPrice * 100)}¢ · {p.status === 'open' ? 'open' : p.status === 'settled' ? (p.exitPrice === 1 ? 'won' : 'lost') : 'closed'}{p.by === 'agent' ? ' · agent' : ''}</span>
                </span>
                <span className="shrink-0 text-footnote font-semibold tabular-nums" style={{ color: Math.abs(pl) < 0.005 ? MUTED : pl > 0 ? UP : DOWN }}>{sign(pl)}</span>
              </li>
            );
          })}
        </ul>
      ) : <p className="mt-4 text-body text-[#64748b]">No paper bets yet. Turn on Paper trading in settings, then press a Paper bet button or ask the agent.</p>}
      <button type="button" onClick={() => { if (!sure) { setSure(true); return; } setSure(false); void resetPaper(1000); }}
        className="hz-chip mt-6 rounded-control px-4 py-2 text-footnote font-semibold" style={sure ? { color: DOWN } : undefined}>{sure ? 'Tap again to clear the paper book' : 'Reset paper book ($1,000)'}</button>
    </div>
  );
}

function RealDecisions({ model }: { model: Model }) {
  const [log0, setLog] = useState<Entry[]>([]);
  const log = log0.filter((e) => e.source !== 'paper');
  const [id, setId] = useState<string>();
  const [res, setRes] = useState<Map<string, Quote>>(new Map());
  useEffect(() => { void localJournal().then(setLog); void installId().then(setId); return onJournal(setLog); }, []);
  // One row per market + side: its furthest status, first time shown.
  const rows = [...log.filter((e) => e.side).reduce((m, e) => {
    const k = `${e.slug}:${e.side}`;
    const cur = m.get(k);
    if (!cur || STATUS_RANK[e.status] > STATUS_RANK[cur.status]) m.set(k, { ...e, ts: cur?.ts && cur.ts < e.ts ? cur.ts : e.ts });
    return m;
  }, new Map<string, Entry>()).values()].sort((x, y) => (STATUS_RANK[y.status] - STATUS_RANK[x.status]) || y.ts.localeCompare(x.ts));
  const slugs = rows.map((r) => r.slug).slice(0, 60).join();
  useEffect(() => { if (slugs) void quotes(model, slugs.split(',')).then(setRes); }, [model, slugs]);
  /** Result per $1 staked at the price shown: +(1/p − 1) if right, −1 if wrong. */
  const perDollar = (e: Entry) => {
    const q = res.get(e.slug);
    if (!q?.closed || q.settled === undefined || !e.side) return undefined;
    const p = e.side === 'YES' ? e.price : 1 - e.price;
    return (q.settled === 1) === (e.side === 'YES') ? 1 / p - 1 : -1;
  };
  const resolved = rows.map(perDollar).filter((x): x is number => x !== undefined);
  return (
    <div className="px-4 pb-6 pt-4">
      <h1 className="hz-display text-[32px] leading-none">My decisions</h1>
      <MeStrip />
      <p className="mt-2 text-body text-[#475569]">
        {rows.length ? `${rows.length} decision${rows.length === 1 ? '' : 's'} so far${resolved.length ? `, ${resolved.length} resolved: ${resolved.reduce((s, x) => s + x, 0) >= 0 ? '+' : '−'}${money(Math.abs(resolved.reduce((s, x) => s + x, 0)))} per $1 each` : ''}.${resolved.length < 30 ? ' Few decisions yet: too early to judge.' : ''}` : 'Every bet Horizon shows you lands here, with the result once the market ends.'}
      </p>
      {rows.length ? (
        <ul className="mt-4">
          {rows.slice(0, 80).map((e) => {
            const r = perDollar(e);
            return (
              <li key={`${e.slug}:${e.side}`} className="hz-rule flex items-center gap-3 py-3">
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-2 block text-body font-medium">{clean(e.question)}</span>
                  <span className="block text-caption text-[#64748b]">{e.side === 'YES' ? 'Yes' : 'No'} at {Math.round((e.side === 'YES' ? e.price : 1 - e.price) * 100)}¢ · {STATUS_WORD[e.status]}{e.source === 'agent' ? ' · from the agent' : ''}</span>
                </span>
                <span className="shrink-0 text-right text-footnote font-semibold" style={{ color: r === undefined ? MUTED : r >= 0 ? UP : DOWN }}>
                  {r === undefined ? 'Open' : `${r >= 0 ? '+' : '−'}${money(Math.abs(r))}`}
                  {r !== undefined ? <span className="block text-caption font-normal text-[#64748b]">per $1</span> : null}
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}
      {id ? (
        <a href={webUrl(id)} target="_blank" rel="noreferrer" className="mt-6 inline-flex items-center gap-1 text-footnote font-medium text-[#0f172a] underline decoration-[rgba(15,23,42,0.2)] underline-offset-[3px]">
          My decisions on the web <Icon d={I.external} size={12} />
        </a>
      ) : null}
    </div>
  );
}

// ---------- settings: only the budget ----------

export function Settings({ a, onClose }: { a?: Account; onClose: () => void }) {
  const [v, setV] = useState(String(a?.bankroll ?? 1000));
  const save = () => { const n = Number(v); if (n >= 1) void setBankroll(n).then(onClose); };
  return (
    <div className="hz-enter px-4 pb-6 pt-3">
      <button type="button" onClick={onClose} className="inline-flex items-center gap-1 text-footnote font-medium text-[#64748b] hover:text-[#0f172a]"><Icon d={I.back} size={14} /> Back</button>
      <h1 className="hz-display mt-3 text-[32px] leading-none">Your budget</h1>
      <p className="mt-2 text-body text-[#475569]">Horizon sizes every bet from this, never more than 5% of it at once.</p>
      <form onSubmit={(e) => { e.preventDefault(); save(); }} className="mt-5 flex gap-2">
        <span className="hz-composer flex flex-1 items-center rounded-control px-3">
          <span className="text-subhead text-[#64748b]">$</span>
          <input type="number" min={1} value={v} onChange={(e) => setV(e.target.value)} aria-label="Budget in dollars" className="min-w-0 flex-1 bg-transparent px-1 py-2.5 text-subhead outline-none" />
        </span>
        <button type="submit" className="hz-cta rounded-control bg-[#0f172a] px-5 text-body font-semibold text-white">Save</button>
      </form>
      <WalletField />
      <PaperToggle />
    </div>
  );
}

/** Optional public wallet address, so the results page can read the user's positions. */
function WalletField() {
  const [v, setV] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string }>();
  useEffect(() => { void getWallet().then((w) => setV(w ?? '')); }, []);
  const save = async () => {
    const w = v.trim();
    if (w && !WALLET_RE.test(w)) { setMsg({ ok: false, text: 'That is not a wallet address: it starts with 0x and has 40 more letters and digits.' }); return; }
    await setWallet(w || undefined);
    setMsg({ ok: true, text: w ? 'Saved.' : 'Removed.' });
  };
  return (
    <div className="mt-8">
      <h2 className="text-subhead font-semibold">Your Polymarket wallet <span className="font-normal text-[#64748b]">(optional)</span></h2>
      <p className="mt-1 text-footnote text-[#64748b]">Public address, read-only. Used only to read your public positions. Never your keys.</p>
      <form onSubmit={(e) => { e.preventDefault(); void save(); }} className="mt-3 flex gap-2">
        <span className="hz-composer flex min-w-0 flex-1 items-center rounded-control px-3">
          <input value={v} onChange={(e) => { setV(e.target.value); setMsg(undefined); }} placeholder="0x…" spellCheck={false} aria-label="Polymarket wallet address"
            className="min-w-0 flex-1 bg-transparent py-2.5 font-mono text-footnote outline-none" />
        </span>
        <button type="submit" className="hz-chip rounded-control px-4 text-body font-semibold">Save</button>
      </form>
      {msg ? <p className="mt-1.5 text-caption" style={{ color: msg.ok ? UP : DOWN }}>{msg.text}</p> : null}
      <SellAlertsToggle hasWallet={WALLET_RE.test(v.trim())} />
    </div>
  );
}

/** Practice mode for the team: bets go to the paper book, never to Polymarket's ticket. Off by default. */
function PaperToggle() {
  const on = usePaper();
  return (
    <label className="mt-8 flex items-center justify-between gap-3">
      <span>
        <span className="flex items-center gap-2 text-body font-medium text-[#0f172a]">Paper trading {on ? <PaperBadge /> : null}</span>
        <span className="block text-caption text-[#64748b]">Practice with $1,000 of paper money at live prices and fees. Nothing goes to Polymarket.</span>
      </span>
      <button type="button" role="switch" aria-checked={on} aria-label="Paper trading" onClick={() => void setPaper(!on)}
        className="relative h-6 w-10 shrink-0 rounded-full transition-ui duration-fast" style={{ background: on ? '#0f172a' : 'rgba(15,23,42,0.15)' }}>
        <span className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform duration-fast" style={{ left: 2, transform: on ? 'translateX(16px)' : 'none' }} />
      </button>
    </label>
  );
}

/** "Tell me when it's time to sell": on by default once a wallet is set (background checks every 15 min). */
function SellAlertsToggle({ hasWallet }: { hasWallet: boolean }) {
  const [on, setOn] = useState<boolean>();
  useEffect(() => { void chrome.storage.local.get('horizonSellAlerts').then((r) => setOn(r.horizonSellAlerts === undefined ? undefined : !!r.horizonSellAlerts)); }, []);
  const value = hasWallet && (on ?? true);
  return (
    <label className={`mt-4 flex items-center justify-between gap-3 ${hasWallet ? '' : 'opacity-50'}`}>
      <span>
        <span className="block text-body font-medium text-[#0f172a]">Tell me when it's time to sell</span>
        <span className="block text-caption text-[#64748b]">Checks your positions every 15 minutes. You still press Sell yourself.</span>
      </span>
      <button type="button" role="switch" aria-checked={value} disabled={!hasWallet}
        onClick={() => { const next = !value; setOn(next); void chrome.storage.local.set({ horizonSellAlerts: next }); }}
        className="relative h-6 w-10 shrink-0 rounded-full transition-ui duration-fast" style={{ background: value ? '#0f172a' : 'rgba(15,23,42,0.15)' }}>
        <span className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform duration-fast" style={{ left: 2, transform: value ? 'translateX(16px)' : 'none' }} />
      </button>
    </label>
  );
}

/** "You're up $X" from /api/me (hidden if the endpoint is not live) + a link to the results page. */
function MeStrip() {
  const [me, setMe] = useState<Me>();
  useEffect(() => { void fetchMe().then(setMe); }, []);
  return (
    <div className="mt-3 flex items-center justify-between gap-3">
      {me ? (
        <span className="min-w-0">
          <span className="block text-subhead font-semibold" style={{ color: me.pnl === undefined || Math.abs(me.pnl) < 0.005 ? INK : me.pnl > 0 ? UP : DOWN }}>{me.summary}</span>
          {me.label ? <span className="block text-caption text-[#94a3b8]">{me.label}</span> : null}
        </span>
      ) : <span />}
      <button type="button" onClick={() => void openMyResults()} className="hz-chip inline-flex shrink-0 items-center gap-1 rounded-control px-3.5 py-1.5 text-footnote font-semibold">
        Open my results <Icon d={I.external} size={12} />
      </button>
    </div>
  );
}

// ---------- the agent ----------

export type Run = { task: string; steps: Step[]; answer?: string; busy: boolean; plan: PlanItem[]; mode?: string };

export function useAgent(model: Model | undefined, tabId: number | undefined) {
  const [run, setRun] = useState<Run>();
  const [llm, setLlm] = useState<boolean>();
  const sig = useRef({ stop: false });
  useEffect(() => { void llmAvailable().then(setLlm); }, []);
  const go = useCallback(async (task: string) => {
    if (!model || !task.trim()) return;
    sig.current = { stop: false };
    const steps: Step[] = [];
    const push = (s: Step) => { const i = steps.findIndex((x) => x.id === s.id); if (i >= 0) steps[i] = s; else steps.push(s); setRun((r) => (r ? { ...r, steps: [...steps] } : r)); };
    setRun({ task, steps: [], busy: true, plan: [] });
    const ctx: Ctx = { model, tabId, onStep: push, signal: sig.current, plan: [] };
    let answer: string | undefined, mode = 'Horizon';
    try {
      // Gemini first, re-checked every run (it may have been down when the panel opened), one retry on a blip.
      if (llm || (await llmAvailable())) {
        answer = await planWithLLM(ctx, task);
        if (answer === undefined && !ctx.signal.stop) { await new Promise((r) => setTimeout(r, 1500)); answer = await planWithLLM(ctx, task); }
        if (answer !== undefined) mode = 'Horizon with Gemini';
      }
      if (answer === undefined) answer = await planFromWords(ctx, task);
    } catch (e) { answer = `Stopped: ${(e as Error).message ?? e}`; }
    if (sig.current.stop) { answer = 'Stopped.'; ctx.plan = []; }
    // Main-line legs first: they set up reliably; sub-tab legs (exact score, halves...) go last.
    const later = (x: PlanItem) => !!x.q.decision && verdictOf(x.q.decision) === 'WAIT';
    ctx.plan = [...ctx.plan.filter((x) => !later(x) && !subTabOf(x.q)), ...ctx.plan.filter((x) => !later(x) && subTabOf(x.q)), ...ctx.plan.filter(later)];
    for (const item of ctx.plan) journalOf(item, 'agent', 'shown');
    // The model's words only when they are plain and on-message; with a plan, one line of ours.
    if (answer && (isPaper() ? /\b(demo|simulat)/i : /\b(demo|balance|portfolio|simulat|paper)/i).test(answer)) answer = ctx.plan.length ? undefined : 'Nothing to set up right now.';
    if (ctx.plan.length) {
      const n = ctx.plan.length, buys = ctx.plan.every((x) => x.kind === 'buy');
      answer = buys ? `Here ${n === 1 ? 'is 1 good bet' : `are ${n} good bets`}.` : `Here ${n === 1 ? 'is 1 change' : `are ${n} changes`}.`;
    }
    setRun((r) => (r ? { ...r, answer, mode, busy: false, plan: [...ctx.plan] } : r));
  }, [model, tabId, llm]);
  const stop = () => { sig.current.stop = true; };
  return { run, go, stop, clear: () => setRun(undefined) };
}

/** The plan as a list: decision, size, one plain reason. The top few are set up live on the page. */
function PlanList({ model, tabId, plan: plan0, budget }: { model: Model; tabId?: number; plan: PlanItem[]; budget: number }) {
  // The user can change any amount; a row picks up its new amount when it is set up.
  const [amounts, setAmounts] = useState<Record<number, number>>({});
  const plan = plan0.map((p, k) => (p.kind === 'buy' && amounts[k] !== undefined ? { ...p, amount: amounts[k] } : p));
  const isLater = (x: PlanItem) => !!x.q.decision && verdictOf(x.q.decision) === 'WAIT';
  const paper = isPaper();
  // Paper: every bet that is due now goes into the paper book; real: the top 3 main-line bets are set up on the page.
  const LIVE = Math.min(3, plan.filter((x) => !subTabOf(x.q) && !isLater(x)).length);
  const firstLater = plan.findIndex(isLater);
  const [liveDone, setLiveDone] = useState(LIVE === 0);
  const [one, setOne] = useState<number>();
  const total = plan.reduce((s, p) => s + (p.kind === 'buy' ? p.amount : 0), 0);
  return (
    <div className="mt-4">
      <div className="hz-card hz-enter rounded-panel px-4 pb-2 pt-4">
        <p className="hz-display text-[26px] leading-[1.1]">{plan.length} {plan.every((p) => p.kind === 'buy') ? `bet${plan.length === 1 ? '' : 's'} · ${money(total)}` : `change${plan.length === 1 ? '' : 's'}`}</p>
        <ul className="mt-2">
          {plan.map((p, k) => {
            const d = p.q.decision;
            return (
              <li key={k} className="hz-rule py-2.5">
                {k === firstLater ? <p className="mb-1.5 text-footnote font-semibold text-[#64748b]">Later tonight / tomorrow</p> : null}
                <div className="flex items-start justify-between gap-3">
                  <span className="min-w-0 text-body font-medium leading-snug">{clean(p.name)}</span>
                  {p.kind === 'buy' ? (
                    <span className="flex shrink-0 items-center gap-1.5">
                      <AmountControl compact value={p.amount} max={budget} onChange={(v) => setAmounts((x) => ({ ...x, [k]: v }))} label={`Amount for bet ${k + 1}`} />
                      <span className="text-footnote font-semibold">{p.side === 'YES' ? 'Yes' : 'No'}</span>
                    </span>
                  ) : <span className="shrink-0 text-body font-semibold">{p.fraction >= 0.999 ? 'Sell all' : 'Sell part'}</span>}
                </div>
                {p.kind === 'buy' && p.suggested !== undefined ? (
                  <p className="mt-0.5 text-caption text-[#94a3b8]">{d && d.kelly * budget < 1 ? <>Horizon suggests {money(Math.floor(d.kelly * budget * 100) / 100)} · Polymarket minimum is $1</> : <>Horizon suggests {money(p.suggested)}</>}{p.amount > p.suggested + 0.005 ? <span className="text-[#64748b]"> · above Horizon's suggestion</span> : null}</p>
                ) : null}
                {d ? <p className="mt-0.5 text-caption text-[#64748b]">Market {pct(d.price)} · Horizon {pct(d.q)}. {reasonOf(d)}</p> : null}
                {isLater(p) && d ? <p className="mt-1 inline-flex items-center gap-1.5 text-caption font-medium text-[#475569]"><Icon d={I.clock} size={12} /> {bestTime(d.hours)}</p> : null}
                {k >= LIVE && liveDone && one !== k && !isLater(p) ? (subTabOf(p.q) ? (
                  <a href={`https://polymarket.com/event/${p.q.eventSlug}`} target="_blank" rel="noreferrer" className="hz-chip mt-1.5 inline-flex items-center gap-1 rounded-control px-3 py-1 text-footnote font-semibold">Open <Icon d={I.external} size={12} /></a>
                ) : (
                  <button type="button" onClick={() => setOne(k)} className="hz-chip mt-1.5 rounded-control px-3 py-1 text-footnote font-semibold">Set up</button>
                )) : null}
                {one === k ? <Doer model={model} tabId={tabId} items={[p]} source="agent" onFinish={() => setOne(undefined)} /> : null}
              </li>
            );
          })}
        </ul>
      </div>
      {!liveDone && LIVE > 0 ? (
        <div className="mt-4">
          <p className="text-footnote font-medium text-[#64748b]">{paper ? `Paper mode: walking the top ${LIVE} on Polymarket, then one press adds them to your paper book` : `Setting up the top ${Math.min(LIVE, plan.length)} on Polymarket${plan.length > LIVE ? '. The rest stay in the list.' : ''}`}</p>
          <Doer model={model} tabId={tabId} items={plan.slice(0, LIVE)} source="agent" onFinish={() => setLiveDone(true)} />
        </div>
      ) : <p className="mt-3 text-footnote text-[#64748b]">Saved in My decisions.{plan.length > LIVE ? ' Tap Set up on any other bet.' : ''}</p>}
    </div>
  );
}

export function AgentRun({ model, tabId, run, onBack, budget = 1000 }: { model: Model; tabId?: number; run: Run; onBack: () => void; budget?: number }) {
  const endRef = useRef<HTMLDivElement>(null);
  // Scroll only the panel's own scroller, never the document (which would slide under the header).
  useEffect(() => {
    const el = endRef.current, box = el?.closest('.overflow-y-auto') as HTMLElement | null;
    if (box) box.scrollTo({ top: box.scrollHeight, behavior: 'smooth' });
  }, [run.steps.length, run.answer, run.busy]);
  return (
    <div className="space-y-4 px-4 pb-6 pt-4">
      {!run.busy ? <button type="button" onClick={onBack} className="inline-flex items-center gap-1 text-footnote font-medium text-[#64748b] hover:text-[#0f172a]"><Icon d={I.back} size={14} /> Back</button> : null}
      <UserMessage text={run.task} />
      <AssistantMessage text={!run.busy ? run.answer : undefined} fresh>
        {run.busy ? <div><Thinking steps={run.steps} fallback="Thinking" /></div> : null}
        {run.steps.length ? (
          <div className="hz-card rounded-panel px-3.5 pb-3 pt-1">
            <Steps steps={run.steps} />
          </div>
        ) : null}
        {!run.busy && run.plan.length ? <PlanList model={model} tabId={tabId} plan={run.plan} budget={budget} /> : null}
      </AssistantMessage>
      <div ref={endRef} />
    </div>
  );
}

const CHIPS = ['Set up my 3 best bets tonight', 'Best sports bet tonight', 'Find 10 good bets this week'];

export function Composer({ busy, ready, onSend, onStop, showChips }: { busy: boolean; ready: boolean; onSend: (t: string) => void; onStop: () => void; showChips: boolean }) {
  const [text, setText] = useState('');
  const can = ready && !busy && !!text.trim();
  const send = (t: string) => { if (!ready || busy || !t.trim()) return; onSend(t); setText(''); };
  return (
    <div className="px-3 pb-3 pt-2">
      {showChips ? (
        <div className="-mx-3 mb-2 flex gap-1.5 overflow-x-auto px-3 pb-1 [scrollbar-width:none] [mask-image:linear-gradient(to_right,#000_85%,transparent)]">
          {CHIPS.map((c) => <button key={c} type="button" onClick={() => send(c)} className="hz-chip shrink-0 rounded-full px-3 py-[6px] text-footnote font-medium text-[#334155]">{c}</button>)}
        </div>
      ) : null}
      <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="hz-composer flex items-center gap-2 rounded-panel py-1.5 pl-4 pr-1.5">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Tell Horizon what to do…" aria-label="Tell Horizon what to do"
          className="min-w-0 flex-1 bg-transparent py-2 text-subhead text-[#0f172a] outline-none" />
        {busy ? (
          <button type="button" onClick={onStop} aria-label="Stop" title="Stop" className="hz-chip flex h-9 w-9 shrink-0 items-center justify-center rounded-full" style={{ color: DOWN }}>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" aria-hidden><rect x="4" y="4" width="16" height="16" rx="3" /></svg>
          </button>
        ) : (
          <button type="submit" disabled={!can} aria-label="Send" className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-ui duration-fast ease-soft active:scale-90 ${can ? 'bg-[#0f172a] text-white shadow-[0_1px_6px_rgba(0,0,0,0.18)]' : 'hz-chip text-[rgba(15,23,42,0.3)]'}`}>
            <Icon d={I.up} size={17} stroke={2.2} />
          </button>
        )}
      </form>
    </div>
  );
}
