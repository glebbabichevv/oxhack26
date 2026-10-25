/**
 * Horizon side panel. First run: a one-screen welcome. Then two tabs: Bet (this market's best
 * outcome, or tonight's best bet elsewhere: one line, one button) and My decisions (journal). Numbers, the
 * time curve and the backtest live behind "Details". The agent composer sits at the bottom; its
 * run (thinking orb, live steps, one confirmation) takes over the content area.
 * All maths is horizon.ts (parity-checked against the Python model); prices come from Gamma.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { decide, decideEvent, type Decision, type Leg, type Model } from './horizon';
import { When, cents, loadModel, pct, slugFrom, when } from './HorizonCard';
import { migrate, type Account } from './ledger';
import { pageDrive } from './agent';
import { AgentRun, Composer, Header, MarketBet, MyDecisions, Settings, Tabs, Tonight, Welcome, useAccount, useAgent, useMarking, type TabName } from './Play';
import { flush } from './journal';
import { initPaper } from './paper';
import { fillTicket } from './agent';
import { quotes } from './ledger';
import { apiJSON, hhmm } from './net';
import { stylePage } from './pageStyle';
import { Md } from './argos/Message';
import './horizon-mode.css';

const API = 'https://oxhack26-production.up.railway.app';
const SITE_URL = 'https://web-production-c7376.up.railway.app';
const UP = '#15803d';
const DOWN = '#e11d48';
const MARKET = '#a1a1aa';
const INK = '#0f172a';
const WELCOME_KEY = 'horizonWelcomed';

// ---------- the active tab ----------

function useActiveTab() {
  const [tab, setTab] = useState<{ id?: number; url?: string; title?: string }>({});
  useEffect(() => {
    const sync = async () => {
      const [t] = await chrome.tabs.query({ active: true, currentWindow: true });
      setTab((prev) => (prev.id === t?.id && prev.url === t?.url && prev.title === t?.title ? prev : { id: t?.id, url: t?.url, title: t?.title }));
    };
    void sync();
    const onActivated = () => void sync();
    const onUpdated = (_: number, info: chrome.tabs.TabChangeInfo, t: chrome.tabs.Tab) => { if (t.active && (info.url || info.status === 'complete')) void sync(); };
    chrome.tabs.onActivated.addListener(onActivated);
    chrome.tabs.onUpdated.addListener(onUpdated);
    return () => { chrome.tabs.onActivated.removeListener(onActivated); chrome.tabs.onUpdated.removeListener(onUpdated); };
  }, []);
  return tab;
}

// ---------- the app ----------

export function HorizonApp() {
  const account = useAccount();
  const tab = useActiveTab();
  const slug = slugFrom(tab.url);
  const [view, setView] = useState<TabName>('bet');
  const [screen, setScreen] = useState<'main' | 'settings' | 'details'>('main');
  const [welcome, setWelcome] = useState<boolean>();
  const [model, setModel] = useState<Model>();
  const agent = useAgent(model, tab.id);
  const scroller = useRef<HTMLDivElement>(null);
  // Test hook for the fill matrix (dev builds only): fill one ticket on the active tab, never presses Trade.
  useEffect(() => {
    if (!import.meta.env.DEV) return;
    (window as unknown as Record<string, unknown>).__hzFill = async (marketSlug: string, side: 'YES' | 'NO', amount: number) => {
      const m = await loadModel();
      const q = (await quotes(m, [marketSlug])).get(marketSlug);
      if (!q) return { ok: false, error: 'no quote' };
      const [t] = await chrome.tabs.query({ active: true, currentWindow: true });
      const steps: string[] = [];
      const t0 = Date.now();
      let r = await fillTicket({ model: m, tabId: t?.id, onStep: (st) => { if (st.status !== 'run') steps.push(`${st.status}:${st.text}`); } }, q, side, amount, 'buy');
      if (!r.ok) r = await fillTicket({ model: m, tabId: t?.id, onStep: (st) => { if (st.status !== 'run') steps.push(`retry ${st.status}:${st.text}`); } }, q, side, amount, 'buy', true);
      return { ...r, ms: Date.now() - t0, steps };
    };
  }, []);
  useEffect(() => { void initPaper(); void migrate(); void loadModel().then(setModel); void flush(); }, []);
  useEffect(() => { void chrome.storage.local.get(WELCOME_KEY).then((r) => setWelcome(!r[WELCOME_KEY])).catch(() => setWelcome(false)); }, []);
  const dismiss = () => { setWelcome(false); setView('bet'); void chrome.storage.local.set({ [WELCOME_KEY]: true }); };
  // Landing on a Polymarket market shows its bet (unless Horizon itself is steering the tab).
  const lastSlug = useRef<string | undefined>(undefined);
  useEffect(() => { if (slug && slug !== lastSlug.current && !pageDrive.active) { setView('bet'); setScreen('main'); } lastSlug.current = slug; }, [slug]);
  useEffect(() => { scroller.current?.scrollTo({ top: 0 }); }, [view, screen]);
  useMarking(model, account);
  // Restyle the page overlay whenever the panel's tab finishes loading a Polymarket page.
  useEffect(() => {
    const l = (id: number, info: chrome.tabs.TabChangeInfo, t: chrome.tabs.Tab) => {
      if (id === tab.id && info.status === 'complete' && /polymarket\.com/.test(t.url ?? '')) void stylePage(id);
    };
    chrome.tabs.onUpdated.addListener(l);
    if (tab.id !== undefined && /polymarket\.com/.test(tab.url ?? '')) void stylePage(tab.id);
    return () => chrome.tabs.onUpdated.removeListener(l);
  }, [tab.id, tab.url]);
  const go = (t: TabName) => { agent.clear(); setScreen('main'); setView(t); };
  const showRun = !!agent.run && screen === 'main' && !welcome;
  return (
    <div className="hz-mode hz-ambient flex h-full flex-col">
      {welcome ? null : <Header onSettings={() => { agent.clear(); setScreen((x) => (x === 'settings' ? 'main' : 'settings')); }} />}
      {welcome || screen !== 'main' ? null : <Tabs tab={showRun ? undefined : view} setTab={go} />}
      <div ref={scroller} className="relative min-h-0 flex-1 overflow-y-auto">
        {welcome ? <Welcome onGo={dismiss} />
          : screen === 'settings' ? <Settings a={account} onClose={() => setScreen('main')} />
          : screen === 'details' ? <Details model={model} slug={slug} a={account} onBack={() => setScreen('main')} />
          : !model ? null
          : showRun ? <AgentRun model={model} tabId={tab.id} run={agent.run!} onBack={agent.clear} budget={account?.bankroll ?? 1000} />
          : view === 'decisions' ? <MyDecisions model={model} />
          : slug ? <MarketBet model={model} a={account} slug={slug} tabId={tab.id} onDetails={() => setScreen('details')} />
          : <Tonight model={model} a={account} tabId={tab.id} url={tab.url} title={tab.title} onDetails={() => setScreen('details')} />}
      </div>
      {welcome === false ? (
        <Composer busy={!!agent.run?.busy} ready={!!model} showChips={!agent.run}
          onSend={(t) => { setScreen('main'); void agent.go(t); }} onStop={agent.stop} />
      ) : null}
    </div>
  );
}

// ---------- helpers ----------

const cleanLabel = (l: string) => l.replace(/\s*\(.*\)\s*$/, '').replace(/\?$/, '').trim();

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(340);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

// ---------- Details: the full analysis, one tap away ----------

/** The model and the decision rule, in the same notation as backend/model.py. */
const MATH = String.raw`Horizon corrects the market price $p$ for the time left $h$ (hours to the scheduled end):

$$q = \sigma\!\left(\beta_0 + \beta_1\,\operatorname{logit} p + \beta_2 \log\tfrac{h}{24} + \beta_3\,\operatorname{logit} p \cdot \log\tfrac{h}{24}\right)$$

Its range $[q_{10}, q_{90}]$ comes from 40 refits on resampled events. With cost $c$ = half the spread (at least 1¢) plus Polymarket's fee, it backs **Yes** only if $q_{10} > p + c$ and **No** only if $q_{90} < p - c$, and stakes a quarter of the Kelly fraction:

$$f = \min\!\left(\tfrac14 \cdot \frac{q_{10} - (p + c)}{1 - (p + c)},\; 5\%\right)$$

Across the outcomes of one event, Horizon's probabilities are scaled to sum to 100%, and it backs at most one outcome per event.`;

function Details({ model, slug, a, onBack }: { model?: Model; slug?: string; a?: Account; onBack: () => void }) {
  const [ev, setEv] = useState<{ title: string; legs: Leg[] }>();
  useEffect(() => { if (model && slug) decideEvent(model, slug).then(setEv).catch(() => setEv(undefined)); }, [model, slug]);
  const band = (model?.tradable ?? [0.03, 0.97]) as [number, number];
  const legs = (ev?.legs ?? []).filter((l) => l.decision).sort((x, y) => y.decision!.netEdge - x.decision!.netEdge);
  const top = legs.find((l) => l.decision!.price >= band[0] && l.decision!.price <= band[1]);
  const bankroll = a?.bankroll ?? 1000;
  return (
    <div className="hz-enter px-4 pb-6 pt-3">
      <button type="button" onClick={onBack} className="inline-flex items-center gap-1 text-footnote font-medium text-[#64748b] hover:text-[#0f172a]">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M15 6l-6 6 6 6" /></svg> Back
      </button>
      <h1 className="hz-display mt-2 text-[30px] leading-[1.08]">{ev?.title ?? 'How Horizon decides'}</h1>
      <Md className="mt-2" text={MATH} />
      {legs.length ? (
        <section className="mt-4">
          {legs.map((l) => {
            const d = l.decision!;
            const out = d.price < band[0] || d.price > band[1];
            return (
              <div key={l.marketSlug ?? l.label} className="hz-rule py-2.5 text-footnote">
                <div className="font-semibold text-[#0f172a]">{cleanLabel(l.label)}</div>
                {out ? <div className="text-[#64748b]">Market {pct(d.price)}: outside {pct(band[0])}–{pct(band[1])}, not traded.</div> : (
                  <div className="text-[#475569]">
                    Market {pct(d.price)} · Horizon {pct(d.q)} (range {pct(d.lo)}–{pct(d.hi)}) · {d.blockedBy ? `one bet per event: ${cleanLabel(d.blockedBy)} has the larger edge` : d.wait ? `advantage ${(d.netEdge * 100).toFixed(1)}¢ after ${(d.cost * 100).toFixed(1)}¢ costs · wait: enter within 24h of the end` : d.action === 'NO_TRADE' ? 'no trade' : `advantage ${(d.netEdge * 100).toFixed(1)}¢ after ${(d.cost * 100).toFixed(1)}¢ costs · suggested ${(d.kelly * 100).toFixed(1)}% = $${(d.kelly * bankroll).toFixed(2)}`}
                    {d.action !== 'NO_TRADE' ? <Scale d={d} /> : null}
                  </div>
                )}
              </div>
            );
          })}
        </section>
      ) : null}
      {top && model ? (
        <section className="hz-rule mt-5 pt-4">
          <h2 className="hz-display text-[22px] leading-snug">When to bet on {cleanLabel(top.label)}</h2>
          <p className="mt-0.5 text-footnote text-[#64748b]">How Horizon reads this price as the end nears, if the price holds.</p>
          <TimeCurve key={`${slug}-${top.question}`} model={model} d={top.decision!} />
          <When hours={top.decision!.hours} />
        </section>
      ) : null}
      <Credentials />
    </div>
  );
}

/** Zoomed scale: market tick (grey), Horizon dot (ink), the 10–90% interval as a band, labelled ticks. */
function Scale({ d }: { d: Decision }) {
  const lo0 = Math.min(d.price, d.lo), hi0 = Math.max(d.price, d.hi);
  const pad = Math.max(0.03, (hi0 - lo0) * 0.6);
  const step = hi0 - lo0 + 2 * pad > 0.3 ? 0.1 : 0.05;
  const a = Math.max(0, Math.floor((lo0 - pad) / step) * step);
  const b = Math.min(1, Math.ceil((hi0 + pad) / step) * step);
  const x = (v: number) => `${((v - a) / (b - a)) * 100}%`;
  const ticks: number[] = [];
  for (let t = a; t <= b + 1e-9; t += step) ticks.push(Math.round(t * 100) / 100);
  const gap = d.action === 'BUY_YES' ? UP : d.action === 'BUY_NO' ? DOWN : MARKET;
  return (
    <div className="mt-2.5" aria-label={`market ${cents(d.price)}, Horizon ${pct(d.q)}, range ${pct(d.lo)} to ${pct(d.hi)}`}>
      <div className="relative h-4">
        <div className="absolute inset-x-0 top-1/2 h-px bg-black/[0.1]" />
        <div className="absolute top-1/2 h-2.5 -translate-y-1/2 rounded-full bg-black/[0.07]" style={{ left: x(d.lo), width: `calc(${x(d.hi)} - ${x(d.lo)})`, minWidth: 3 }} />
        <div className="absolute top-1/2 h-[3px] -translate-y-1/2" style={{ background: gap, left: x(Math.min(d.price, d.q)), width: `calc(${x(Math.max(d.price, d.q))} - ${x(Math.min(d.price, d.q))})` }} />
        <div className="absolute top-1/2 h-4 w-[2px] -translate-x-1/2 -translate-y-1/2" style={{ left: x(d.price), background: MARKET }} />
        <div className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white" style={{ left: x(d.q), background: INK }} />
      </div>
      <div className="relative mt-0.5 h-3.5 text-[10px] text-[#a1a1aa]">
        {ticks.map((t, i) => (
          <span key={t} className="absolute" style={{ left: x(t), transform: i === 0 ? 'none' : i === ticks.length - 1 ? 'translateX(-100%)' : 'translateX(-50%)' }}>{Math.round(t * 100)}%</span>
        ))}
      </div>
      <div className="mt-0.5 text-[11px] text-[#71717a]">Horizon range {pct(d.lo)}–{pct(d.hi)} (10–90% of 40 bootstrap fits)</div>
    </div>
  );
}

// ---------- c. the time curve ----------

const H_MAX = 720, H_MIN = 12;
const MARKS = [720, 168, 72, 24, 12];

function TimeCurve({ model, d }: { model: Model; d: Decision }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const H = 170, padL = 8, padR = 8, padT = 22, padB = 34;
  const iw = Math.max(120, w - padL - padR), ih = H - padT - padB;
  const lx = (h: number) => padL + ((Math.log(H_MAX) - Math.log(Math.min(Math.max(h, H_MIN), H_MAX))) / (Math.log(H_MAX) - Math.log(H_MIN))) * iw;

  const samples = useMemo(() => Array.from({ length: 41 }, (_, i) => H_MAX * Math.pow(H_MIN / H_MAX, i / 40))
    .map((h) => ({ h, q: decide(model, d.price, h, d.domain, d.cost * 2).q })), [model, d]);
  const qs = samples.map((s) => s.q);
  const lo = Math.min(d.price, ...qs), hi = Math.max(d.price, ...qs);
  const pad = Math.max(0.015, (hi - lo) * 0.35);
  const ya = Math.max(0, lo - pad), yb = Math.min(1, hi + pad);
  const y = (v: number) => padT + (1 - (v - ya) / (yb - ya)) * ih;

  const line = samples.map((s, i) => `${i ? 'L' : 'M'}${lx(s.h).toFixed(1)},${y(s.q).toFixed(1)}`).join(' ');
  const gapArea = `${line} L${lx(H_MIN).toFixed(1)},${y(d.price).toFixed(1)} L${lx(H_MAX).toFixed(1)},${y(d.price).toFixed(1)} Z`;
  const up = samples[samples.length - 1].q >= d.price;
  const end = Date.now() + d.hours * 3.6e6;
  const fmt = (h: number) => {
    const t = new Date(end - h * 3.6e6);
    return h > 6 * 24 || d.hours > 7 * 24
      ? t.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
      : t.toLocaleString(undefined, { weekday: 'short', hour: 'numeric' });
  };
  const nowX = lx(d.hours);
  const qEnd = samples[samples.length - 1].q, qStart = samples[0].q;
  const nowQ = decide(model, d.price, d.hours, d.domain, d.cost * 2).q;

  return (
    <div ref={ref} className="mt-2 w-full">
      <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`} role="img"
        aria-label={`If the price holds at ${cents(d.price)}, Horizon reads it as ${pct(qStart)} 30 days out and ${pct(qEnd)} 12 hours out.`}>
        {/* best window: 24h → 12h before the end */}
        <rect x={lx(24)} y={padT - 6} width={lx(12) - lx(24)} height={ih + 6} fill="rgba(21,128,61,0.07)" />
        <text x={(lx(24) + lx(12)) / 2} y={padT - 10} textAnchor="middle" fontSize="9.5" fill={UP} fontWeight={600}>best window</text>
        {/* gap */}
        <path d={gapArea} fill={up ? 'rgba(21,128,61,0.10)' : 'rgba(225,29,72,0.10)'} className="hz-fade" />
        {/* market price, held */}
        <line x1={lx(H_MAX)} x2={lx(H_MIN)} y1={y(d.price)} y2={y(d.price)} stroke={MARKET} strokeWidth={1.5} strokeDasharray="4 4" />
        {/* Horizon */}
        <path d={line} fill="none" stroke={INK} strokeWidth={2} strokeLinecap="round" pathLength={1} className="hz-draw" />
        {/* now */}
        <g>
            <line x1={nowX} x2={nowX} y1={padT - 4} y2={padT + ih} stroke={INK} strokeOpacity={0.35} strokeWidth={1} />
            <circle cx={nowX} cy={y(nowQ)} r={3.5} fill={INK} stroke="#fff" strokeWidth={1.5} />
            <text x={nowX > padL + iw - 30 ? padL + iw : Math.max(nowX, padL + 14)} y={padT + ih + 30} textAnchor={nowX > padL + iw - 30 ? 'end' : 'middle'} fontSize="9.5" fontWeight={700} fill={INK}>{d.hours < H_MIN ? `now · ${when(d.hours)} left` : 'now'}</text>
          </g>
        {/* x axis: horizons + local time */}
        <line x1={padL} x2={padL + iw} y1={padT + ih} y2={padT + ih} stroke="rgba(17,17,19,0.12)" />
        {MARKS.map((h, i) => (
          <g key={h} fontSize="9.5" fill="#71717a" textAnchor={i === 0 ? 'start' : i === MARKS.length - 1 ? 'end' : 'middle'}>
            <text x={lx(h)} y={padT + ih + 11} fontWeight={600}>{when(h)}</text>
            {h >= 72 ? <text x={lx(h)} y={padT + ih + 21} fill="#a1a1aa">{fmt(h)}</text> : null}
          </g>
        ))}
        {/* end labels */}
        <text x={padL + iw} y={y(qEnd) + (up ? -6 : 13)} textAnchor="end" fontSize="11" fontWeight={700} fill={INK} className="hz-fade">Horizon {pct(qEnd)}</text>
        <text x={padL} y={y(d.price) + (up ? 13 : -6)} fontSize="11" fontWeight={600} fill={MARKET}>market {cents(d.price)}</text>
      </svg>
    </div>
  );
}

// ---------- f. credentials ----------

type Creds = { cachedAt?: number; ret: number; ci: [number, number]; nTrades: number; brierModel: number; brierMarket: number; nTest: number; sha: string; sealedAt: string };
const FALLBACK_CREDS: Creds = { ret: 0.31, ci: [0.23, 0.40], nTrades: 1899, brierModel: 0.1297, brierMarket: 0.1305, nTest: 10579,
  sha: '31d2510c13ee29c0a4c9ac26aa498b7ca1cffca58d4bf553f6d5bfd5acb73326', sealedAt: '2026-10-24T15:31:30+00:00' };
let credsCache: Creds | undefined;

function Credentials() {
  const [c, setC] = useState<Creds>(credsCache ?? FALLBACK_CREDS);
  useEffect(() => {
    if (credsCache) return;
    void Promise.allSettled([apiJSON<any>('/api/backtest'), apiJSON<any>('/api/capsule')]).then(([btg, capg]) => {
      const next: Creds = { ...FALLBACK_CREDS };
      const bt = btg.status === 'fulfilled' ? { status: 'fulfilled' as const, value: btg.value.data } : btg;
      const cap = capg.status === 'fulfilled' ? { status: 'fulfilled' as const, value: capg.value.data } : capg;
      const times = [btg, capg].map((g) => (g.status === 'fulfilled' ? g.value.cachedAt : undefined)).filter((x): x is number => !!x);
      if (times.length) next.cachedAt = Math.min(...times);
      if (bt.status === 'fulfilled') {
        const b = bt.value;
        const h = b?.headline;
        if (typeof h?.per_dollar === 'number') { next.ret = h.per_dollar; if (Array.isArray(h.per_dollar_ci)) next.ci = h.per_dollar_ci; }
        if (typeof h?.n_trades === 'number') next.nTrades = h.n_trades;
        if (typeof b?.overall?.brier_model === 'number') { next.brierModel = b.overall.brier_model; next.brierMarket = b.overall.brier_market; }
        if (typeof b?.n_test_markets === 'number') next.nTest = b.n_test_markets;
      }
      if (cap.status === 'fulfilled' && cap.value?.seals?.[0]?.sha256) {
        next.sha = cap.value.seals[0].sha256;
        next.sealedAt = cap.value.seals[0].sealed_at;
      }
      credsCache = next;
      setC(next);
    });
  }, []);
  const p = (x: number) => `${x >= 0 ? '+' : '−'}${Math.round(Math.abs(x) * 100)}¢`;
  const sealed = new Date(c.sealedAt).toLocaleString('en-GB', { timeZone: 'Europe/London', weekday: 'short', hour: '2-digit', minute: '2-digit' });
  return (
    <footer className="hz-rule mt-6 pt-4 text-footnote text-[#475569]">
      <h2 className="mb-1 text-body font-semibold text-[#0f172a]">How we know it works</h2>
      <p>
        Tested on <b className="font-semibold text-[#0f172a]">{c.nTest.toLocaleString()}</b> past markets it had never seen: it predicted them better than the market price,
        and its rule made <b className="font-semibold" style={{ color: UP }}>{p(c.ret)} per $1</b> staked after spreads and Polymarket's fees over {c.nTrades.toLocaleString()} bets (90% range {p(c.ci[0])} to {p(c.ci[1])}), mostly on sports. Crypto and markets a month out showed no edge.
      </p>
      <p className="mt-1 text-caption text-[#64748b]">
        Brier {c.brierModel.toFixed(4)} vs market {c.brierMarket.toFixed(4)}. Predictions sealed before the results: <a href={`${SITE_URL}/#sealed`} target="_blank" rel="noreferrer" className="font-mono text-[#0f172a] underline decoration-black/20 underline-offset-2">{c.sha.slice(0, 8)}…{c.sha.slice(-4)}</a> (Seal 1, {sealed} London).
      </p>
      {c.cachedAt ? <p className="mt-1 text-caption text-[#94a3b8]">Offline copy · cached at {hhmm(c.cachedAt)}</p> : null}
    </footer>
  );
}
