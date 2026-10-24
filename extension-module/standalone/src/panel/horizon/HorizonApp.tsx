/**
 * Horizon: the whole side panel is an analysis instrument for the active Polymarket event:
 * verdict, every yes/no leg on a scale, the time curve (Horizon's q if the price holds), the best
 * window, tonight's edges elsewhere, and the backtest + sealed-capsule credentials. "Prepare order"
 * drives the page through the browser-use layer (select leg + outcome, type the stake) and stops
 * before confirm.
 * All maths is horizon.ts (parity-checked against the Python model); prices come from Gamma.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { decide, decideEvent, domainOf, scanTag, searchMarkets, subjectOf, type Decision, type Leg, type Model, type ScanRow } from './horizon';
import { Chip, When, cents, loadModel, pct, slugFrom, when } from './HorizonCard';
import { fallbackHint, prepareOrder, type PrepareResult } from './prepareOrder';
import './horizon-mode.css';

const API = 'https://horizon-api-iota.vercel.app';
const SITE_URL = 'https://horizon-two-gilt.vercel.app';
const UP = '#15803d';
const DOWN = '#e11d48';
const MARKET = '#a1a1aa';
const INK = '#111113';
const BANKROLL_KEY = 'horizonBankroll';

// ---------- state: bankroll and the active tab ----------

function useBankroll(): [number, (v: number) => void] {
  const [v, setV] = useState(1000);
  useEffect(() => {
    void chrome.storage.local.get(BANKROLL_KEY).then((r) => { const n = Number(r[BANKROLL_KEY]); if (n > 0) setV(n); }).catch(() => {});
  }, []);
  const set = useCallback((n: number) => { setV(n); void chrome.storage.local.set({ [BANKROLL_KEY]: n }); }, []);
  return [v, set];
}

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
  const [bankroll, setBankroll] = useBankroll();
  return (
    <div className="hz-mode flex h-full flex-col bg-white">
      <div className="flex items-center justify-between gap-3 border-b border-black/[0.08] px-4 py-2.5">
        <span className="flex items-center gap-2">
          <img src="icons/icon48.png" alt="" className="h-[18px] w-[18px] rounded-[5px]" />
          <span className="hz-serif text-[16px] font-semibold tracking-[-0.01em]">Horizon</span>
          <span className="hidden text-[11px] text-[#71717a] min-[420px]:inline">prediction-market analyst</span>
        </span>
        <label className="flex shrink-0 items-center gap-1 whitespace-nowrap text-[11px] text-[#71717a]" title="Your bankroll: ¼-Kelly stakes are sized from it. Stored only in this browser.">
          bankroll $
          <input
            type="number" min={1} step={100} value={bankroll}
            onChange={(e) => { const n = Number(e.target.value); if (n > 0) setBankroll(n); }}
            className="w-[64px] border-b border-black/[0.15] bg-transparent text-right text-[12px] font-semibold text-[#111113] outline-none focus:border-[#111113]"
          />
        </label>
      </div>
      <HorizonAnalysis bankroll={bankroll} />
    </div>
  );
}

// ---------- helpers ----------

const cleanLabel = (l: string) => l.replace(/\s*\(.*\)\s*$/, '').replace(/\?$/, '').trim();
const signedCents = (x: number) => `${x >= 0 ? '+' : '−'}${(Math.abs(x) * 100).toFixed(1)}¢`;
const TAG_FOR_DOMAIN: Record<string, string> = {
  sports: 'sports', crypto: 'crypto', politics: 'politics', geopolitics: 'geopolitics',
  culture: 'culture', economics: 'economy', science_tech: 'tech', other: 'sports',
};

function verdict(legs: Leg[], band: [number, number]) {
  const top = legs[0]?.decision;
  if (!top) return 'Nothing to price on this page.';
  const name = cleanLabel(legs[0].label);
  if (top.action === 'BUY_YES') return `${name} is underpriced: ${cents(top.price)} vs Horizon ${pct(top.q)}.`;
  if (top.action === 'BUY_NO') return `${name} is overpriced: ${cents(top.price)} vs Horizon ${pct(top.q)}.`;
  if (legs.every((l) => l.decision!.price < band[0] || l.decision!.price > band[1])) return 'Too close to certain to trade.';
  return 'No edge here after the spread.';
}

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

// ---------- the analysis view ----------

type EventState = { title: string; legs: Leg[]; tags: string[]; model: Model } | 'loading' | 'error' | 'notfound';

function HorizonAnalysis({ bankroll }: { bankroll: number }) {
  const tab = useActiveTab();
  const slug = slugFrom(tab.url);
  const [model, setModel] = useState<Model>();
  const [ev, setEv] = useState<EventState>('loading');
  const [showAll, setShowAll] = useState(false);

  useEffect(() => { void loadModel().then(setModel); }, []);

  const load = useCallback(async (s: string) => {
    setEv('loading');
    try {
      const m = await loadModel();
      setEv({ ...(await decideEvent(m, s)), model: m });
    } catch (e) {
      setEv(e instanceof Error && e.message === 'event not found' ? 'notfound' : 'error');
    }
  }, []);
  useEffect(() => { setShowAll(false); if (slug) void load(slug); }, [slug, load]);

  const data = typeof ev === 'object' ? ev : undefined;
  const legs = useMemo(() => (data ? data.legs.filter((l) => l.decision).sort((a, b) =>
    Number(b.decision!.action !== 'NO_TRADE') - Number(a.decision!.action !== 'NO_TRADE') || b.decision!.netEdge - a.decision!.netEdge) : []), [data]);
  const band = (model?.tradable ?? [0.03, 0.97]) as [number, number];
  const top = legs.find((l) => { const d = l.decision!; return d.price >= band[0] && d.price <= band[1]; });
  const scanTagSlug = data && legs[0] ? TAG_FOR_DOMAIN[domainOf(data.model, data.tags)] ?? 'sports' : 'sports';
  const shown = showAll ? legs : legs.slice(0, 5);

  return (
    <div className="hz-mode relative z-[75] min-h-0 flex-1 overflow-y-auto bg-white">
      <div className="px-4 pb-6 pt-4">
        {/* a. Headline + verdict */}
        {!slug ? (
          model ? <PageBridge model={model} url={tab.url} title={tab.title} tabId={tab.id} /> : null
        ) : ev === 'loading' ? (
          <header aria-busy>
            <div className="hz-eyebrow">Reading the market</div>
            <div className="mt-2 h-7 w-4/5 animate-pulse rounded bg-black/[0.05]" />
            <div className="mt-2 h-4 w-3/5 animate-pulse rounded bg-black/[0.04]" />
            <div className="mt-6 h-24 animate-pulse rounded bg-black/[0.035]" />
          </header>
        ) : ev === 'error' || ev === 'notfound' ? (
          <header>
            <div className="hz-eyebrow">Horizon</div>
            <h1 className="hz-serif mt-1 text-[24px] font-medium leading-tight">{ev === 'notfound' ? 'Event not found on Polymarket' : 'Horizon unavailable'}</h1>
            <p className="mt-1.5 text-[13px] text-[#676e7e]">{ev === 'notfound' ? 'Gamma has no event with this address yet.' : 'Could not reach Polymarket prices.'}</p>
            <button type="button" onClick={() => void load(slug)} className="mt-3 w-full rounded-[11px] bg-black/[0.05] py-2 text-[13px] font-medium">Retry</button>
          </header>
        ) : data ? (
          <header>
            <div className="hz-eyebrow">{legs.length ? `${legs.length} yes/no market${legs.length === 1 ? '' : 's'} · ${when(legs[0].decision!.hours)} to the end` : 'Horizon'}</div>
            <h1 className="hz-serif mt-1 text-[26px] font-medium leading-[1.12]">{data.title}</h1>
            <p className="mt-2 text-[15px] font-medium leading-snug" style={{ color: legs[0]?.decision?.action === 'BUY_YES' ? UP : legs[0]?.decision?.action === 'BUY_NO' ? DOWN : INK }}>
              {verdict(legs, band)}
            </p>
          </header>
        ) : null}

        {/* b. Legs */}
        {data && legs.length ? (
          <section className="mt-4">
            {shown.map((l, i) => <LegRow key={`${slug}-${i}`} leg={l} band={band} bankroll={bankroll} tabId={tab.id} eventSlug={slug!} legCount={legs.length} />)}
            {legs.length > 5 ? (
              <button type="button" onClick={() => setShowAll((s) => !s)} className="hz-rule w-full pt-2.5 text-left text-[12px] font-semibold text-[#111113]">
                {showAll ? 'Show fewer' : `Show all ${legs.length} markets`}
              </button>
            ) : null}
          </section>
        ) : data ? (
          <p className="mt-3 text-[13px] text-[#676e7e]">No open yes/no market with a two-sided book on this page.</p>
        ) : null}

        {/* c. Time curve + d. best window */}
        {data && top && model ? (
          <section className="hz-rule mt-5 pt-4">
            <div className="hz-eyebrow">Time · {cleanLabel(top.label)}</div>
            <h2 className="hz-serif mt-1 text-[18px] font-medium leading-snug">How Horizon reads this price as the end nears</h2>
            <TimeCurve key={`${slug}-${top.question}`} model={model} d={top.decision!} />
            <p className="mt-1 text-[11px] leading-snug text-[#71717a]">Model view if the price holds; averages, not a forecast.</p>
            <When hours={top.decision!.hours} />
          </section>
        ) : null}

        {/* e. Tonight's edges */}
        {model ? <TonightsEdges model={model} tag={scanTagSlug} tabId={tab.id} currentSlug={slug} /> : null}

        {/* f. Credentials */}
        <Credentials />
      </div>
    </div>
  );
}

// ---------- b. one leg ----------

function LegRow({ leg, band, bankroll, tabId, eventSlug, legCount }: {
  leg: Leg; band: [number, number]; bankroll: number; tabId?: number; eventSlug: string; legCount: number;
}) {
  const d = leg.decision!;
  const outOfBand = d.price < band[0] || d.price > band[1];
  const hue = d.action === 'BUY_YES' ? UP : d.action === 'BUY_NO' ? DOWN : INK;
  return (
    <div className="hz-rule py-3" title={d.reason}>
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0 text-[13px] font-semibold leading-snug" title={leg.question}>{cleanLabel(leg.label)}</span>
        <Chip d={d} />
      </div>
      {outOfBand ? (
        <p className="mt-1 text-[12px] text-[#676e7e]">Market {cents(d.price)} · outside {pct(band[0])}–{pct(band[1])}: a {cents(d.cost)} cost exceeds any edge.</p>
      ) : (
        <>
          <div className="mt-1.5 flex items-end gap-5">
            <div>
              <div className="text-[10.5px] font-medium text-[#71717a]">Market</div>
              <div className="text-[24px] font-semibold leading-none" style={{ color: MARKET }}>{cents(d.price)}</div>
            </div>
            <div>
              <div className="text-[10.5px] font-medium text-[#71717a]">Horizon</div>
              <div className="text-[24px] font-semibold leading-none" style={{ color: INK }}>{pct(d.q)}</div>
            </div>
            <div className="ml-auto text-right text-[12px] leading-tight text-[#676e7e]">
              {d.action !== 'NO_TRADE' ? (
                <>
                  <div>edge <b className="font-semibold" style={{ color: hue }}>{signedCents(d.netEdge)}</b> after spread</div>
                  <div>¼ Kelly <b className="font-semibold text-[#111113]">${stake(d.kelly * bankroll)}</b> ({(d.kelly * 100).toFixed(1)}%)</div>
                </>
              ) : (
                <div className="max-w-[150px]">gap inside uncertainty + {cents(d.cost)} cost</div>
              )}
            </div>
          </div>
          <Scale d={d} />
          {d.action !== 'NO_TRADE' && tabId !== undefined ? (
            <Prepare leg={leg} d={d} bankroll={bankroll} tabId={tabId} eventSlug={eventSlug} legCount={legCount} />
          ) : null}
        </>
      )}
    </div>
  );
}

const stake = (x: number) => (x >= 10 ? Math.round(x).toLocaleString() : x.toFixed(2));

/** Horizon decides, the browser-use layer acts: pick leg + outcome, type the stake, stop before confirm. */
function Prepare({ leg, d, bankroll, tabId, eventSlug, legCount }: {
  leg: Leg; d: Decision; bankroll: number; tabId: number; eventSlug: string; legCount: number;
}) {
  const [st, setSt] = useState<'idle' | 'running' | PrepareResult>('idle');
  const [copied, setCopied] = useState(false);
  const side = d.action === 'BUY_YES' ? 'YES' : 'NO';
  const amount = d.kelly * bankroll;
  const run = async () => {
    setSt('running');
    setCopied(false);
    try {
      const r = await prepareOrder({ tabId, eventSlug, marketSlug: leg.marketSlug, label: cleanLabel(leg.label), legCount, side, amount, bid: leg.bid, ask: leg.ask });
      setSt(r);
      if (!r.ok) setCopied(await fallbackHint(tabId, cleanLabel(leg.label), amount));
    } catch (e) {
      setSt({ ok: false, steps: [{ step: 'Reach the page', ok: false, detail: e instanceof Error ? e.message : String(e) }] });
      setCopied(await fallbackHint(tabId, cleanLabel(leg.label), amount));
    }
  };
  const hue = side === 'YES' ? UP : DOWN;
  return (
    <div className="mt-2.5">
      <button type="button" onClick={() => void run()} disabled={st === 'running'}
        className="w-full rounded-[10px] border py-1.5 text-[12.5px] font-semibold transition-colors disabled:opacity-60"
        style={{ borderColor: hue, color: hue }}>
        {st === 'running' ? 'Preparing on the page…' : `Prepare order · Buy ${side} $${stake(amount)}`}
      </button>
      {typeof st === 'object' ? (
        st.ok ? (
          <p className="mt-1.5 text-[12px] leading-snug text-[#3f3f46]">
            <b className="font-semibold" style={{ color: hue }}>Order prepared:</b> Buy {side} {cleanLabel(leg.label)}, ${stake(amount)} ({(d.kelly * 100).toFixed(1)}% of ${bankroll.toLocaleString()}). Review and confirm on Polymarket; Horizon never clicks Trade.
          </p>
        ) : (
          <p className="mt-1.5 text-[12px] leading-snug text-[#676e7e]">
            Could not prepare it on the page ({st.steps.filter((s) => !s.ok).map((s) => `${s.step}: ${s.detail ?? 'failed'}`).join('; ')}).{' '}
            {copied ? `Amount $${amount.toFixed(2)} copied; pick Buy ${side} yourself.` : `Enter $${amount.toFixed(2)} and Buy ${side} yourself.`}
          </p>
        )
      ) : null}
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

// ---------- bridge: markets about any page ----------

function PageBridge({ model, url, title, tabId }: { model: Model; url?: string; title?: string; tabId?: number }) {
  const onPolymarket = !!url && /^https:\/\/([a-z0-9-]+\.)?polymarket\.com\//.test(url);
  const subject = useMemo(() => (url && /^https?:/.test(url) && !onPolymarket ? subjectOf(title, url) : undefined), [url, title, onPolymarket]);
  const [rows, setRows] = useState<ScanRow[] | 'loading' | 'error'>('loading');
  const run = useCallback(() => {
    if (!subject) return;
    setRows('loading');
    searchMarkets(model, subject.query, 6).then(setRows).catch(() => setRows('error'));
  }, [model, subject]);
  useEffect(() => { run(); }, [run]);
  const open = (u: string) => { if (tabId !== undefined) void chrome.tabs.update(tabId, { url: u }); else void chrome.tabs.create({ url: u }); };

  if (!subject) {
    return (
      <header>
        <div className="hz-eyebrow">Horizon</div>
        <h1 className="hz-serif mt-1 text-[26px] font-medium leading-[1.12]">Open a Polymarket market</h1>
        <p className="mt-2 text-[14px] leading-snug text-[#3f3f46]">
          On a polymarket.com event page, Horizon prices every yes/no leg for its time to resolution. On any other page it looks for markets about what you are reading. Meanwhile, here is where it sees edge in the next 24 hours.
        </p>
      </header>
    );
  }
  const list = typeof rows === 'object' ? rows : [];
  const crypto = subject.crypto || list.some((r) => r.decision.domain === 'crypto');
  return (
    <header>
      <div className="hz-eyebrow">From this page · {subject.query}</div>
      <h1 className="hz-serif mt-1 text-[26px] font-medium leading-[1.12]">
        {rows === 'loading' || list.length ? <>Markets about {subject.query}</> : <>No open prediction markets about this page</>}
      </h1>
      <p className="mt-2 text-[12.5px] leading-snug text-[#676e7e]">
        Horizon's model is validated on Polymarket prices only{crypto ? '; on crypto markets our backtest shows no lift, so treat these calls as unproven.' : '. Tap a market to open its full analysis.'}
      </p>
      {rows === 'loading' ? (
        <div className="mt-3 space-y-2" aria-busy>{[0, 1, 2].map((i) => <div key={i} className="h-10 animate-pulse rounded bg-black/[0.04]" />)}</div>
      ) : rows === 'error' ? (
        <p className="mt-3 text-[13px] text-[#676e7e]">Search failed. <button type="button" onClick={run} className="font-semibold text-[#111113] underline decoration-black/20 underline-offset-2">Retry</button></p>
      ) : list.length ? (
        <div className="mt-3">
          {list.map((r) => <EdgeRow key={r.question + r.slug} r={r} onOpen={open} />)}
        </div>
      ) : null}
    </header>
  );
}

function EdgeRow({ r, onOpen }: { r: ScanRow; onOpen: (url: string) => void }) {
  const d = r.decision;
  const hue = d.action === 'BUY_YES' ? UP : d.action === 'BUY_NO' ? DOWN : INK;
  return (
    <button type="button" onClick={() => onOpen(r.url)} title={d.reason}
      className="hz-row-link hz-rule -mx-1 flex w-[calc(100%+8px)] items-center gap-3 px-1 py-2 text-left">
      <span className="min-w-0 flex-1">
        <span className="line-clamp-2 block text-[13px] font-medium leading-snug">{r.question}</span>
        <span className="block text-[11.5px] text-[#71717a]">
          <span style={{ color: MARKET }}>{cents(d.price)}</span> → <span className="font-semibold text-[#111113]">{pct(d.q)}</span> · {when(d.hours)} left
        </span>
      </span>
      <span className="shrink-0 text-right">
        <span className="block text-[13px] font-semibold" style={{ color: hue }}>{d.action === 'NO_TRADE' ? '—' : signedCents(d.netEdge)}</span>
        <span className="block text-[10.5px] text-[#71717a]">{d.action === 'BUY_YES' ? 'buy YES' : d.action === 'BUY_NO' ? 'buy NO' : 'no trade'}</span>
      </span>
    </button>
  );
}

// ---------- e. tonight's edges ----------

function TonightsEdges({ model, tag, tabId, currentSlug }: { model: Model; tag: string; tabId?: number; currentSlug?: string }) {
  const [state, setState] = useState<{ rows: ScanRow[]; scanned: number; trades: number } | 'loading' | 'error'>('loading');
  const run = useCallback(() => {
    setState('loading');
    scanTag(model, tag, 24, 6).then(setState).catch(() => setState('error'));
  }, [model, tag]);
  useEffect(() => { run(); }, [run]);
  const rows = typeof state === 'object' ? state.rows.filter((r) => r.slug !== currentSlug).slice(0, 5) : [];
  const open = (url: string) => {
    if (tabId !== undefined) void chrome.tabs.update(tabId, { url });
    else void chrome.tabs.create({ url });
  };
  return (
    <section className="hz-rule mt-5 pt-4">
      <div className="hz-eyebrow">Tonight's edges · {tag} · next 24h</div>
      <h2 className="hz-serif mt-1 text-[18px] font-medium leading-snug">Where else Horizon would act</h2>
      {state === 'loading' ? (
        <div className="mt-2 space-y-2" aria-busy>{[0, 1, 2].map((i) => <div key={i} className="h-9 animate-pulse rounded bg-black/[0.04]" />)}</div>
      ) : state === 'error' ? (
        <p className="mt-2 text-[13px] text-[#676e7e]">Scan failed. <button type="button" onClick={run} className="font-semibold text-[#111113] underline decoration-black/20 underline-offset-2">Retry</button></p>
      ) : rows.length ? (
        <>
          <div className="mt-2">
            {rows.map((r) => <EdgeRow key={r.question + r.slug} r={r} onOpen={open} />)}
          </div>
          <p className="mt-1.5 text-[11px] text-[#71717a]">{state.scanned.toLocaleString()} most-traded {tag} markets ending within 24h scanned, {state.trades} clear the cost and uncertainty bar. Tap to open.</p>
        </>
      ) : (
        <p className="mt-2 text-[13px] text-[#676e7e]">No open {tag} market ending in the next 24h clears the bar.</p>
      )}
    </section>
  );
}

// ---------- f. credentials ----------

type Creds = { ret: number; ci: [number, number]; brierModel: number; brierMarket: number; nTest: number; sha: string; sealedAt: string };
const FALLBACK_CREDS: Creds = { ret: 3.0447, ci: [1.84, 4.4], brierModel: 0.1297, brierMarket: 0.1305, nTest: 10579,
  sha: '31d2510c13ee29c0a4c9ac26aa498b7ca1cffca58d4bf553f6d5bfd5acb73326', sealedAt: '2026-10-24T15:31:30+00:00' };
let credsCache: Creds | undefined;

function Credentials() {
  const [c, setC] = useState<Creds>(credsCache ?? FALLBACK_CREDS);
  useEffect(() => {
    if (credsCache) return;
    const get = (p: string) => fetch(`${API}${p}`, { signal: AbortSignal.timeout(4000) }).then((r) => (r.ok ? r.json() : Promise.reject()));
    void Promise.allSettled([get('/api/backtest'), get('/api/capsule')]).then(([bt, cap]) => {
      const next = { ...FALLBACK_CREDS };
      if (bt.status === 'fulfilled') {
        const b = bt.value;
        if (typeof b?.with_costs?.return === 'number') next.ret = b.with_costs.return;
        if (Array.isArray(b?.return_ci)) next.ci = b.return_ci;
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
  const p = (x: number) => `+${Math.round(x * 100)}%`;
  const sealed = new Date(c.sealedAt).toLocaleString('en-GB', { timeZone: 'Europe/London', weekday: 'short', hour: '2-digit', minute: '2-digit' });
  return (
    <footer className="hz-rule mt-6 pt-3 text-[11.5px] leading-relaxed text-[#676e7e]">
      <div className="hz-eyebrow mb-1">How we know</div>
      <p>
        Out-of-time backtest on <b className="font-semibold text-[#111113]">{c.nTest.toLocaleString()}</b> markets:{' '}
        <b className="font-semibold" style={{ color: UP }}>{p(c.ret)}</b> of bankroll after costs (90% CI {p(c.ci[0])} to {p(c.ci[1])}),
        Brier <b className="font-semibold text-[#111113]">{c.brierModel.toFixed(4)}</b> vs market {c.brierMarket.toFixed(4)}.
      </p>
      <p className="mt-1">
        Sealed predictions: <a href={`${SITE_URL}/#sealed`} target="_blank" rel="noreferrer" className="font-mono text-[11px] text-[#111113] underline decoration-black/20 underline-offset-2">{c.sha.slice(0, 8)}…{c.sha.slice(-4)}</a>{' '}
        (Seal 1, {sealed} London).
      </p>
    </footer>
  );
}
