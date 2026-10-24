/**
 * The family-friendly layer: demo account header, one-tap bets, "Tonight", "My bets", settings,
 * and the agent command box with its live step list. Demo money on live Polymarket prices.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { Decision, Model } from './horizon';
import {
  equity, getAccount, lossToday, onAccount, outlook, placeBet, pWinOf, quotes, refresh, resetAccount, sell, setLossLimit, suggested,
  type Account, type Position, type Quote, type Side,
} from './demo';
import { llmAvailable, parseCommand, runLLM, scanMarkets, showOnPage, type Ctx, type Pick, type Step } from './agent';
import { cents, pct, when } from './HorizonCard';

export const UP = '#15803d';
export const DOWN = '#e11d48';
export const MARKET = '#a1a1aa';
export const INK = '#111113';

export const money = (x: number, cents2 = false) => {
  const a = Math.abs(x);
  const s = !cents2 && a >= 100 ? Math.round(a).toLocaleString() : a.toFixed(2);
  return `${x < 0 ? '−' : ''}$${s}`;
};
export const signed = (x: number) => `${x >= 0 ? '+' : '−'}${money(Math.abs(x))}`;
const hueOf = (x: number) => (x > 0.005 ? UP : x < -0.005 ? DOWN : INK);
const cleanLabel = (l: string) => l.replace(/\s*\(.*\)\s*$/, '').replace(/\?$/, '').trim();

// ---------- account hook ----------

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
    const tick = async () => { const qs = await quotes(model, openKey.split(',')); if (!dead) await refresh(model, qs); };
    void tick();
    const t = setInterval(() => void tick(), 30000);
    return () => { dead = true; clearInterval(t); };
  }, [model, openKey]);
}

// ---------- header ----------

export function AccountBar({ a, onSettings }: { a?: Account; onSettings: () => void }) {
  const eq = a ? equity(a) : 1000;
  const pnl = a ? eq - a.start : 0;
  return (
    <div className="flex items-center justify-between gap-3 px-4 pb-2 pt-3">
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="text-[22px] font-semibold leading-none">{money(eq)}</span>
          <span className="text-[13px] font-semibold" style={{ color: hueOf(pnl) }}>{signed(pnl)}</span>
        </div>
        <div className="mt-1 text-[11px] text-[#71717a]">Demo money · live Polymarket prices</div>
      </div>
      <button type="button" onClick={onSettings} aria-label="Settings" className="shrink-0 rounded-full border border-black/[0.1] px-3 py-1.5 text-[12px] font-medium text-[#3f3f46]">
        Settings
      </button>
    </div>
  );
}

export type TabName = 'tonight' | 'market' | 'bets';
export function Tabs({ tab, setTab, openCount }: { tab: TabName; setTab: (t: TabName) => void; openCount: number }) {
  const items: [TabName, string][] = [['tonight', 'Tonight'], ['market', 'This market'], ['bets', openCount ? `My bets · ${openCount}` : 'My bets']];
  return (
    <div role="tablist" className="mx-4 mb-1 grid grid-cols-3 rounded-[12px] bg-black/[0.05] p-1">
      {items.map(([k, label]) => (
        <button key={k} role="tab" aria-selected={tab === k} type="button" onClick={() => setTab(k)}
          className={`rounded-[9px] py-1.5 text-[12.5px] font-semibold transition-colors ${tab === k ? 'bg-white text-[#111113] shadow-[0_1px_2px_rgba(0,0,0,0.08)]' : 'text-[#71717a]'}`}>
          {label}
        </button>
      ))}
    </div>
  );
}

// ---------- the plain-words call + one-tap bet ----------

export function PlainCall({ d }: { d: Decision }) {
  const side = d.action === 'BUY_YES' ? 'YES' : d.action === 'BUY_NO' ? 'NO' : undefined;
  return (
    <div>
      <div className="flex items-end gap-6">
        <div>
          <div className="text-[11px] font-medium text-[#71717a]">Market says</div>
          <div className="text-[28px] font-semibold leading-none" style={{ color: MARKET }}>{pct(d.price)}</div>
        </div>
        <div>
          <div className="text-[11px] font-medium text-[#71717a]">Horizon thinks</div>
          <div className="text-[28px] font-semibold leading-none" style={{ color: INK }}>{pct(d.q)}</div>
        </div>
      </div>
      <p className="mt-1.5 text-[13.5px] font-medium leading-snug" style={{ color: side === 'YES' ? UP : side === 'NO' ? DOWN : '#52525b' }}>
        {side === 'YES' ? `More likely than the price says → good bet on YES`
          : side === 'NO' ? `Less likely than the price says → good bet on NO`
          : `Too close to call after costs → Horizon would skip it`}
      </p>
    </div>
  );
}

function Details({ d, a }: { d: Decision; a?: Account }) {
  return (
    <div className="mt-2 rounded-[10px] bg-black/[0.035] px-3 py-2 text-[12px] leading-relaxed text-[#3f3f46]">
      <div>Horizon range <b>{pct(d.lo)}–{pct(d.hi)}</b> (10–90% of 40 refits)</div>
      <div>Advantage after costs <b>{(d.netEdge * 100).toFixed(1)}¢</b> per $1 share (cost {cents(d.cost)})</div>
      <div>Suggested bet <b>{(d.kelly * 100).toFixed(1)}%</b> of balance (¼ Kelly, max 5%){a ? ` = ${money(suggested(a, d), true)}` : ''}</div>
      <div>{when(d.hours)} to the end · {d.domain.replace('_', ' ')}</div>
      <div className="mt-1 text-[11px] text-[#71717a]">{d.reason}</div>
    </div>
  );
}

/** "Bet $X on YES" with −/+; places a demo bet at the live ask. Optional "Show on Polymarket". */
export function BetBox({ model, a, marketSlug, d, tabId, label }: {
  model: Model; a?: Account; marketSlug: string; d: Decision; tabId?: number; label: string;
}) {
  const side: Side | undefined = d.action === 'BUY_YES' ? 'YES' : d.action === 'BUY_NO' ? 'NO' : undefined;
  const sug = a ? suggested(a, d) : 0;
  const [amt, setAmt] = useState<number>();
  const [msg, setMsg] = useState<{ ok: boolean; text: string }>();
  const [busy, setBusy] = useState<'bet' | 'show'>();
  const [details, setDetails] = useState(false);
  const value = amt ?? Math.max(1, Math.round(sug));
  const stepBy = value >= 50 ? 10 : value >= 20 ? 5 : 1;
  const over = value > sug + 0.5;
  const hue = side === 'YES' ? UP : DOWN;
  const open = a?.positions.find((p) => p.status === 'open' && p.marketSlug === marketSlug);

  const bet = async () => {
    if (!side) return;
    setBusy('bet'); setMsg(undefined);
    const q = (await quotes(model, [marketSlug])).get(marketSlug);
    if (!q) { setBusy(undefined); setMsg({ ok: false, text: 'Could not get a live price. Try again.' }); return; }
    const r = await placeBet(model, q, side, value, 'you', over);
    setBusy(undefined);
    setMsg(r.ok ? { ok: true, text: `Done: ${money(r.position.stake, true)} on ${side} at ${Math.round(r.position.avgPrice * 100)}¢. See My bets.` } : { ok: false, text: r.error });
  };
  const show = async () => {
    if (!side) return;
    setBusy('show'); setMsg(undefined);
    const q = (await quotes(model, [marketSlug])).get(marketSlug);
    const steps: Step[] = [];
    const ctx: Ctx = { model, tabId, signal: { stop: false }, onStep: (s) => { const i = steps.findIndex((x) => x.id === s.id); if (i >= 0) steps[i] = s; else steps.push(s); } };
    const r = q ? await showOnPage(ctx, q, side, value) : { ok: false };
    setBusy(undefined);
    setMsg(r.ok ? { ok: true, text: 'Filled in on Polymarket for you to see. Horizon never presses Trade.' } : { ok: false, text: `Could not show it on the page${steps[steps.length - 1]?.detail ? `: ${steps[steps.length - 1].detail}` : ''}.` });
  };

  return (
    <div className="mt-2.5">
      {side ? (
        <>
          <div className="flex items-stretch gap-2">
            <div className="flex items-center rounded-[12px] border border-black/[0.12]">
              <button type="button" aria-label="Less" onClick={() => setAmt(Math.max(1, value - stepBy))} className="h-11 w-9 text-[18px] font-semibold text-[#3f3f46]">−</button>
              <span className="min-w-[44px] text-center text-[14px] font-semibold">${value}</span>
              <button type="button" aria-label="More" onClick={() => setAmt(Math.min(Math.floor(a?.cash ?? 1000), value + stepBy))} className="h-11 w-9 text-[18px] font-semibold text-[#3f3f46]">+</button>
            </div>
            <button type="button" onClick={() => void bet()} disabled={!!busy}
              className="h-11 flex-1 rounded-[12px] text-[14.5px] font-semibold text-white transition-opacity disabled:opacity-60"
              style={{ background: hue }}>
              {busy === 'bet' ? 'Placing…' : `Bet $${value} on ${side}`}
            </button>
          </div>
          <div className="mt-1.5 flex items-center justify-between text-[11.5px] text-[#71717a]">
            <span>{over ? <span style={{ color: DOWN }}>More than Horizon suggests ({money(sug, true)})</span> : `Suggested bet ${money(sug, true)}`}{open ? ` · you hold ${money(open.stake, true)}` : ''}</span>
            <span className="flex gap-3">
              {tabId !== undefined ? <button type="button" onClick={() => void show()} disabled={!!busy} className="font-semibold text-[#111113] underline decoration-black/20 underline-offset-2">{busy === 'show' ? 'Showing…' : 'Show on Polymarket'}</button> : null}
              <button type="button" onClick={() => setDetails((x) => !x)} className="font-semibold text-[#111113]">{details ? 'Less' : 'Details'}</button>
            </span>
          </div>
        </>
      ) : (
        <div className="flex justify-end text-[11.5px]"><button type="button" onClick={() => setDetails((x) => !x)} className="font-semibold text-[#111113]">{details ? 'Less' : 'Details'}</button></div>
      )}
      {msg ? <p className="mt-1.5 text-[12px] font-medium leading-snug" style={{ color: msg.ok ? UP : DOWN }}>{msg.text}</p> : null}
      {details ? <Details d={d} a={a} /> : null}
      <span className="sr-only">{label}</span>
    </div>
  );
}

// ---------- Tonight ----------

export function Tonight({ model, a, tabId }: { model: Model; a?: Account; tabId?: number }) {
  const [st, setSt] = useState<{ picks: Pick[]; scanned: number } | 'loading' | 'error'>('loading');
  const run = useCallback(() => { setSt('loading'); scanMarkets(model, 'all', 24, 12).then(setSt).catch(() => setSt('error')); }, [model]);
  useEffect(() => { run(); }, [run]);
  return (
    <div className="px-4 pb-4 pt-2">
      <h1 className="hz-serif text-[24px] font-medium leading-tight">Best bets tonight</h1>
      <p className="mt-1 text-[12.5px] leading-snug text-[#676e7e]">Markets that end in the next 24 hours where Horizon's probability beats the price, after the spread. Best first.</p>
      {st === 'loading' ? (
        <div className="mt-3 space-y-3" aria-busy>{[0, 1, 2].map((i) => <div key={i} className="h-28 animate-pulse rounded-[12px] bg-black/[0.04]" />)}</div>
      ) : st === 'error' ? (
        <p className="mt-3 text-[13px] text-[#676e7e]">Could not reach Polymarket. <button type="button" onClick={run} className="font-semibold text-[#111113] underline">Retry</button></p>
      ) : st.picks.length ? (
        <>
          {st.picks.map((p) => (
            <div key={p.marketSlug} className="hz-rule py-3.5">
              <a href={`https://polymarket.com/event/${p.eventSlug}`} target="_blank" rel="noreferrer" className="block text-[14px] font-semibold leading-snug [overflow-wrap:anywhere]">{p.question}</a>
              <div className="mb-2 mt-0.5 text-[11.5px] text-[#71717a]">ends in {when(p.decision.hours)}</div>
              <PlainCall d={p.decision} />
              <BetBox model={model} a={a} marketSlug={p.marketSlug} d={p.decision} tabId={tabId} label={p.question} />
            </div>
          ))}
          <p className="mt-2 text-[11px] text-[#71717a]">{st.scanned.toLocaleString()} most-traded markets ending within 24h checked. <button type="button" onClick={run} className="font-semibold text-[#111113]">Refresh</button></p>
        </>
      ) : (
        <p className="mt-3 text-[13px] text-[#676e7e]">Nothing ending in the next 24h beats the price after costs. Horizon would rather wait.</p>
      )}
    </div>
  );
}

// ---------- My bets ----------

const valueNow = (p: Position) => p.shares * (p.mark ?? p.avgPrice);

export function MyBets({ model, a }: { model: Model; a?: Account }) {
  const [od, setOd] = useState<{ ev: number; pDown: number }>();
  const open = a?.positions.filter((p) => p.status === 'open') ?? [];
  const done = a?.positions.filter((p) => p.status !== 'open') ?? [];
  const sig = open.map((p) => `${p.id}:${p.stake.toFixed(2)}:${(p.mark ?? 0).toFixed(3)}`).join();
  useEffect(() => {
    if (!open.length) { setOd(undefined); return; }
    setOd(outlook(open.map((p) => ({ shares: p.shares, stake: p.stake, value: valueNow(p), pWin: p.qAtOpen }))));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig]);
  if (!a) return null;
  const eq = equity(a);
  const inPlay = open.reduce((s, p) => s + p.stake, 0);
  const unreal = open.reduce((s, p) => s + valueNow(p) - p.stake, 0);
  const realized = done.reduce((s, p) => s + (p.pnl ?? 0), 0);
  const lt = lossToday(a);
  const close = async (p: Position, f = 1) => {
    const q = (await quotes(model, [p.marketSlug])).get(p.marketSlug);
    if (q) await sell(model, q, p.id, f);
  };
  return (
    <div className="px-4 pb-4 pt-2">
      <div className="grid grid-cols-3 gap-3">
        <Stat label="Balance" value={money(eq)} />
        <Stat label="In play" value={money(inPlay)} />
        <Stat label="Profit so far" value={signed(eq - a.start)} color={hueOf(eq - a.start)} />
      </div>
      {open.length && od ? (
        <p className="mt-3 rounded-[10px] bg-black/[0.035] px-3 py-2 text-[12.5px] leading-snug text-[#3f3f46]">
          If Horizon's probabilities are right, your open bets are worth <b style={{ color: hueOf(od.ev) }}>{signed(od.ev)}</b> on average from here, with a <b>{Math.round(od.pDown * 100)}%</b> chance they end down. Not a promise.
        </p>
      ) : null}
      <p className="mt-2 text-[11.5px] text-[#71717a]">Today {lt.loss > 0 ? `down ${money(lt.loss)}` : 'not down'} · stop at {money(lt.limit)} (daily limit {Math.round(a.lossLimitPct * 100)}%){lt.hit ? ' · limit reached, no new bets today' : ''}</p>

      <h2 className="hz-eyebrow mt-4">Open · {open.length}</h2>
      {open.length ? open.map((p) => {
        const v = valueNow(p), pl = v - p.stake;
        return (
          <div key={p.id} className="hz-rule py-3">
            <div className="flex items-start justify-between gap-3">
              <a href={`https://polymarket.com/event/${p.eventSlug}`} target="_blank" rel="noreferrer" className="min-w-0 text-[13.5px] font-semibold leading-snug [overflow-wrap:anywhere]">{p.question}</a>
              <span className="shrink-0 text-right">
                <span className="block text-[15px] font-semibold" style={{ color: hueOf(pl) }}>{signed(pl)}</span>
                <span className="block text-[11px] text-[#71717a]">now {money(v, true)}</span>
              </span>
            </div>
            <div className="mt-1 text-[12px] text-[#52525b]">
              <b style={{ color: p.side === 'YES' ? UP : DOWN }}>{p.side}</b> · {money(p.stake, true)} at {Math.round(p.avgPrice * 100)}¢ · price now {Math.round((p.mark ?? p.avgPrice) * 100)}¢ · pays {money(p.shares, true)} if right{p.by === 'agent' ? ' · by agent' : ''}
            </div>
            <div className="mt-2 flex gap-2">
              <button type="button" onClick={() => void close(p, 0.5)} className="rounded-[9px] border border-black/[0.12] px-3 py-1 text-[12px] font-semibold">Halve</button>
              <button type="button" onClick={() => void close(p)} className="rounded-[9px] border border-black/[0.12] px-3 py-1 text-[12px] font-semibold">Close</button>
            </div>
          </div>
        );
      }) : <p className="mt-2 text-[13px] text-[#676e7e]">No open bets. Tap a “Bet” button, or ask Horizon below.</p>}

      {done.length ? (
        <>
          <h2 className="hz-eyebrow mt-5">Finished · {signed(realized)}</h2>
          {done.slice(0, 30).map((p) => (
            <div key={p.id} className="hz-rule flex items-start justify-between gap-3 py-2 text-[12.5px]">
              <span className="min-w-0 leading-snug text-[#3f3f46]">{p.side} · {p.question}<span className="block text-[11px] text-[#71717a]">{p.status === 'settled' ? (p.exitPrice === 1 ? 'resolved: right' : 'resolved: wrong') : 'closed early'}</span></span>
              <b className="shrink-0" style={{ color: hueOf(p.pnl ?? 0) }}>{signed(p.pnl ?? 0)}</b>
            </div>
          ))}
        </>
      ) : null}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="text-[11px] font-medium text-[#71717a]">{label}</div>
      <div className="text-[19px] font-semibold leading-tight" style={{ color: color ?? INK }}>{value}</div>
    </div>
  );
}

// ---------- settings ----------

export function Settings({ a, onClose }: { a?: Account; onClose: () => void }) {
  const [start, setStart] = useState(String(a?.start ?? 1000));
  const [limit, setLimit] = useState(String(Math.round((a?.lossLimitPct ?? 0.2) * 100)));
  const [sure, setSure] = useState(false);
  return (
    <div className="px-4 pb-4 pt-2">
      <div className="flex items-center justify-between">
        <h1 className="hz-serif text-[22px] font-medium">Settings</h1>
        <button type="button" onClick={onClose} className="text-[13px] font-semibold">Done</button>
      </div>
      <label className="mt-4 block text-[12.5px] font-medium text-[#3f3f46]">Starting demo balance ($)
        <input type="number" min={10} max={1000000} value={start} onChange={(e) => setStart(e.target.value)} className="mt-1 block w-full rounded-[10px] border border-black/[0.12] px-3 py-2 text-[15px]" />
      </label>
      <button type="button" onClick={() => { if (!sure) { setSure(true); return; } const n = Number(start); if (n >= 10) void resetAccount(n).then(onClose); }}
        className="mt-2 w-full rounded-[10px] py-2 text-[13px] font-semibold" style={{ background: sure ? DOWN : 'rgba(0,0,0,0.05)', color: sure ? '#fff' : INK }}>
        {sure ? 'Tap again: clear all bets and start over' : 'Reset demo account'}
      </button>
      <label className="mt-4 block text-[12.5px] font-medium text-[#3f3f46]">Daily loss limit (% of the day's starting balance)
        <input type="number" min={1} max={100} value={limit} onChange={(e) => setLimit(e.target.value)} onBlur={() => { const n = Number(limit); if (n >= 1 && n <= 100) void setLossLimit(n / 100); }}
          className="mt-1 block w-full rounded-[10px] border border-black/[0.12] px-3 py-2 text-[15px]" />
      </label>
      <p className="mt-1 text-[11.5px] text-[#71717a]">When today's losses reach this, neither you nor the agent can open new bets until tomorrow.</p>
      <div className="mt-5 rounded-[10px] bg-black/[0.035] px-3 py-2.5 text-[12px] leading-relaxed text-[#3f3f46]">
        <b>18+ only.</b> This is a demo: the money is pretend, the prices and results are real Polymarket data. Horizon never places a real order, never connects a wallet and never presses Polymarket's Trade button. Its probabilities come from an out-of-time backtest and can be wrong.
      </div>
    </div>
  );
}

// ---------- agent: command box + live step list ----------

const CHIPS = ['Place my 20 best bets tonight', 'Lower all stakes by half', 'Close everything that lost its edge', 'Bet $50 on the best sports market'];

export function Agent({ model, tabId, onActivity }: { model?: Model; tabId?: number; onActivity: () => void }) {
  const [text, setText] = useState('');
  const [run, setRun] = useState<{ task: string; steps: Step[]; answer?: string; mode?: string; busy: boolean }>();
  const [llm, setLlm] = useState<boolean>();
  const sig = useRef({ stop: false });
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => { void llmAvailable().then(setLlm); }, []);
  useEffect(() => { listRef.current?.scrollTo({ top: listRef.current.scrollHeight }); }, [run?.steps.length, run?.answer]);

  const go = async (task: string) => {
    if (!model || !task.trim() || run?.busy) return;
    sig.current = { stop: false };
    const steps: Step[] = [];
    const push = (s: Step) => {
      const i = steps.findIndex((x) => x.id === s.id);
      if (i >= 0) steps[i] = s; else steps.push(s);
      setRun((r) => (r ? { ...r, steps: [...steps] } : r));
    };
    setRun({ task, steps: [], busy: true });
    setText('');
    onActivity();
    const ctx: Ctx = { model, tabId, onStep: push, signal: sig.current };
    let answer: string | undefined, mode = 'Built-in planner';
    try {
      if (llm) { answer = await runLLM(ctx, task); if (answer !== undefined) mode = 'Gemini'; }
      if (answer === undefined) {
        const plan = parseCommand(task);
        if ('error' in plan) answer = plan.error;
        else { push({ id: -1, text: `Plan: ${plan.summary}`, status: 'info' }); answer = await plan.run(ctx); }
      }
    } catch (e) { answer = `Stopped: ${(e as Error).message ?? e}`; }
    setRun((r) => (r ? { ...r, answer, mode, busy: false } : r));
  };

  return (
    <div className="border-t border-black/[0.08] bg-white shadow-[0_-8px_24px_-16px_rgba(17,17,19,0.25)]">
      {run ? (
        <div ref={listRef} className="max-h-[42vh] overflow-y-auto px-4 pt-2.5">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 text-[12.5px] font-semibold leading-snug">“{run.task}”</div>
            {run.busy
              ? <button type="button" onClick={() => { sig.current.stop = true; }} className="shrink-0 text-[12px] font-semibold" style={{ color: DOWN }}>Stop</button>
              : <button type="button" onClick={() => setRun(undefined)} aria-label="Hide" className="shrink-0 text-[12px] font-semibold text-[#71717a]">Hide</button>}
          </div>
          <ol className="mt-1.5 space-y-1" aria-live="polite">
            {run.steps.map((s) => (
              <li key={s.id} className="flex gap-2 text-[12px] leading-snug">
                <span className="mt-[3px] inline-block h-2 w-2 shrink-0 rounded-full" style={{
                  background: s.status === 'ok' ? UP : s.status === 'fail' ? DOWN : s.status === 'info' ? INK : MARKET,
                  animation: s.status === 'run' ? 'pulse 1s ease-in-out infinite' : undefined }} />
                <span className="min-w-0">
                  <span className={s.status === 'info' ? 'font-semibold' : ''}>{s.text}</span>
                  {s.detail ? <span className="block text-[11px] text-[#71717a]">{s.detail}</span> : null}
                </span>
              </li>
            ))}
            {run.busy && !run.steps.length ? <li className="text-[12px] text-[#71717a]">Thinking…</li> : null}
          </ol>
          {run.answer ? <p className="mt-2 pb-1 text-[13px] font-medium leading-snug">{run.answer}</p> : null}
          {run.mode && !run.busy ? <p className="pb-1 text-[10.5px] text-[#a1a1aa]">{run.mode} · every bet checked by Horizon's model · demo money</p> : null}
        </div>
      ) : null}
      {!run ? (
        <div className="flex gap-1.5 overflow-x-auto px-4 pt-2.5 [scrollbar-width:none]">
          {CHIPS.map((c) => (
            <button key={c} type="button" onClick={() => void go(c)} className="shrink-0 rounded-full border border-black/[0.12] px-2.5 py-1 text-[11.5px] font-medium text-[#3f3f46]">{c}</button>
          ))}
        </div>
      ) : null}
      <form onSubmit={(e) => { e.preventDefault(); void go(text); }} className="flex gap-2 px-4 pb-3 pt-2">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Tell Horizon what to do…" aria-label="Tell Horizon what to do"
          className="min-w-0 flex-1 rounded-[12px] border border-black/[0.14] px-3 py-2.5 text-[14px] outline-none focus:border-[#111113]" />
        <button type="submit" disabled={!text.trim() || run?.busy || !model} className="rounded-[12px] bg-[#111113] px-4 text-[13.5px] font-semibold text-white disabled:opacity-40">Go</button>
      </form>
    </div>
  );
}

export { pWinOf };
export type { Quote };
