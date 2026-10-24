/**
 * Horizon card: on a Polymarket event page, shows Horizon's calibrated probability, the call
 * and the edge after the spread for every yes/no leg. Computed in the panel from the fitted
 * coefficients (GET /api/model, cached, with a bundled fallback) and live Gamma prices.
 * Source of truth for the maths: oxhack26/extension-module/horizon.ts (parity-checked vs Python).
 */
import { useCallback, useEffect, useState } from 'react';
import { decideEvent, type Decision, type Leg, type Model } from './horizon';
import fallbackModel from './model.fallback.json';

const MODEL_URL = 'https://oxhack26-production.up.railway.app/api/model';
const SITE_URL = 'https://web-production-c7376.up.railway.app';
const UP = '#15803d';
const DOWN = '#e11d48';

export function slugFrom(url?: string) {
  // polymarket.com/event/<slug>, /<lang>/event/<slug>, and sports pages, which Polymarket
  // redirects to /sports/<league>/<slug> (e.g. /sports/laliga/lal-bar-rea-2026-10-25).
  let u: URL;
  try { u = new URL(url ?? ''); } catch { return undefined; }
  if (!/(^|\.)polymarket\.com$/.test(u.hostname)) return undefined;
  const parts = u.pathname.split('/').filter(Boolean);
  const i = parts.indexOf('event');
  if (i >= 0) return parts[i + 1];
  if (parts[0] === 'sports' && parts.length >= 3 && /\d/.test(parts[parts.length - 1])) return parts[parts.length - 1];
  return undefined;
}

export async function loadModel(): Promise<Model> {
  try {
    const res = await fetch(MODEL_URL, { signal: AbortSignal.timeout(2500) });
    if (!res.ok) throw new Error(String(res.status));
    const m = (await res.json()) as Model;
    chrome.storage.local.set({ horizonModel: m });
    return m;
  } catch {
    const { horizonModel } = await chrome.storage.local.get('horizonModel');
    return (horizonModel as Model) ?? (fallbackModel as unknown as Model);
  }
}

export const pct = (x: number) => `${Math.round(x * 100)}%`;
export const cents = (x: number) => `${Math.round(x * 100)}¢`;
export const when = (h: number) => (h >= 48 ? `${Math.round(h / 24)}d` : `${Math.max(1, Math.round(h))}h`);

/** ' (12 closed, 3 without a book)': why legs are missing, so an empty card is not a mystery. */
function skipNote(legs: Leg[]) {
  const n = new Map<string, number>();
  for (const l of legs) if (l.skip) n.set(l.skip, (n.get(l.skip) ?? 0) + 1);
  const short: Record<string, string> = { 'not a yes/no market': 'not yes/no', closed: 'closed', 'no two-sided order book': 'without a book', 'past its end date': 'past their end date' };
  const parts = [...n].map(([k, v]) => `${v} ${short[k] ?? k}`);
  return parts.length ? ` (${parts.join(', ')})` : '';
}

export function Chip({ d }: { d: Decision }) {
  const style = d.action === 'BUY_YES' ? { color: UP, background: 'rgba(21,128,61,0.10)' }
    : d.action === 'BUY_NO' ? { color: DOWN, background: 'rgba(225,29,72,0.10)' }
    : { color: '#676e7e', background: 'rgba(15,23,42,0.05)' };
  const label = d.action === 'BUY_YES' ? 'Buy YES' : d.action === 'BUY_NO' ? 'Buy NO' : 'No trade';
  return <span className="shrink-0 rounded-full px-2 py-[2px] text-[11px] font-semibold" style={style}>{label}</span>;
}

/** Market price tick, Horizon q dot, the model's interval as a band, the gap in the call's hue. */
function Track({ d }: { d: Decision }) {
  const x = (v: number) => `${Math.min(Math.max(v, 0), 1) * 100}%`;
  const gap = d.action === 'BUY_YES' ? UP : d.action === 'BUY_NO' ? DOWN : '#a1a1aa';
  return (
    <div className="relative mt-1.5 h-3 w-full" aria-hidden>
      <div className="absolute inset-x-0 top-1/2 h-px bg-black/[0.08]" />
      <div className="absolute top-1/2 h-2 -translate-y-1/2 rounded-full bg-black/[0.06]" style={{ left: x(d.lo), right: `calc(100% - ${x(d.hi)})` }} />
      <div className="absolute top-1/2 h-[3px] -translate-y-1/2 rounded-full" style={{ background: gap, left: x(Math.min(d.price, d.q)), right: `calc(100% - ${x(Math.max(d.price, d.q))})` }} />
      <div className="absolute top-1/2 h-3 w-[2px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#a1a1aa]" style={{ left: x(d.price) }} />
      <div className="absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border-[1.5px] border-white bg-[#111113]" style={{ left: x(d.q) }} />
    </div>
  );
}

function Row({ leg, band }: { leg: Leg; band: [number, number] }) {
  const d = leg.decision!;
  const outOfBand = d.price < band[0] || d.price > band[1];
  return (
    <div className="border-t border-black/[0.06] py-2.5 first:border-t-0" title={d.reason}>
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0 text-[13px] font-medium leading-snug text-[#0a0a0a]">{leg.question}</span>
        <Chip d={d} />
      </div>
      <div className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-[12px] tabular-nums text-[#676e7e] [&>span]:whitespace-nowrap">
        <span>market <b className="font-semibold text-[#0a0a0a]">{cents(d.price)}</b></span>
        {outOfBand
          ? <span className="!whitespace-normal">outside {pct(band[0])}–{pct(band[1])}: a {cents(d.cost)} cost exceeds any edge</span>
          : <span>Horizon <b className="font-semibold text-[#0a0a0a]">{pct(d.q)}</b> <span className="text-[#71717a]">({pct(d.lo)}–{pct(d.hi)})</span></span>}
        {d.action !== 'NO_TRADE'
          ? <span>edge <b className="font-semibold" style={{ color: d.action === 'BUY_YES' ? UP : DOWN }}>{(d.netEdge * 100).toFixed(1)}¢</b> · stake {(d.kelly * 100).toFixed(1)}%</span>
          : null}
      </div>
      {outOfBand ? null : <Track d={d} />}
    </div>
  );
}

// When to act: in the backtest, return per $1 trade after costs was highest 12–24h before the
// scheduled end (≈14–15%, vs ≈7% at 3d and ≈4–5% at 7d–30d), after dropping stale prices and
// markets whose event was already over. The window is shown in the reader's local time.
const WINDOW_H: [number, number] = [24, 12];
export function When({ hours }: { hours: number }) {
  const far = hours - WINDOW_H[0] > 6 * 24; // a weekday alone is ambiguous beyond a week
  const at = (h: number) => new Date(Date.now() + (hours - h) * 3.6e6)
    .toLocaleString(undefined, far
      ? { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }
      : { weekday: 'short', hour: '2-digit', minute: '2-digit' });
  const text = hours > WINDOW_H[0]
    ? <>Best window: <b className="font-semibold text-[#0a0a0a]">{at(WINDOW_H[0])} – {at(WINDOW_H[1])}</b> (12–24h before the end), when the edge per trade was ~2× the 3-day one.</>
    : hours > WINDOW_H[1]
      ? <><b className="font-semibold" style={{ color: UP }}>In the best window now</b>: 12–24h before the end, where the edge per trade was largest.</>
      : <>Under 12h to the end: the edge per trade stayed high, but books thin out; check the spread.</>;
  return (
    <div className="mt-2.5 rounded-control bg-black/[0.035] px-2.5 py-2 text-[12px] leading-snug text-[#3f3f46]">
      <span className="text-[#71717a]">{when(hours)} to resolution · </span>{text}
    </div>
  );
}

export function HorizonCard() {
  const [slug, setSlug] = useState<string>();
  const [state, setState] = useState<{ title: string; legs: Leg[]; model: Model } | 'loading' | 'error'>();
  const [notFound, setNotFound] = useState(false);
  const [open, setOpen] = useState(true);
  const [showAll, setShowAll] = useState(false);

  // Follow the active tab.
  useEffect(() => {
    const sync = async () => {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      setSlug(slugFrom(tab?.url));
    };
    void sync();
    const onActivated = () => void sync();
    const onUpdated = (_: number, info: chrome.tabs.TabChangeInfo, tab: chrome.tabs.Tab) => { if (tab.active && (info.url || info.status === 'complete')) void sync(); };
    chrome.tabs.onActivated.addListener(onActivated);
    chrome.tabs.onUpdated.addListener(onUpdated);
    return () => { chrome.tabs.onActivated.removeListener(onActivated); chrome.tabs.onUpdated.removeListener(onUpdated); };
  }, []);

  const load = useCallback(async (s: string) => {
    setState('loading');
    setNotFound(false);
    try {
      const model = await loadModel();
      const ev = await decideEvent(model, s);
      setState({ ...ev, model });
    } catch (e) {
      setNotFound(e instanceof Error && e.message === 'event not found');
      setState('error');
    }
  }, []);

  useEffect(() => { setShowAll(false); if (slug) void load(slug); else setState(undefined); }, [slug, load]);

  if (!slug || !state) return null;

  const legs = state !== 'loading' && state !== 'error'
    ? [...state.legs.filter((l) => l.decision)].sort((a, b) =>
      Number(b.decision!.action !== 'NO_TRADE') - Number(a.decision!.action !== 'NO_TRADE') || b.decision!.netEdge - a.decision!.netEdge)
    : [];
  const shown = showAll ? legs : legs.slice(0, 4);
  const hoursNow = legs[0]?.decision?.hours;

  return (
    <div className="relative z-[75] mx-3 mt-3 rounded-card border border-black/[0.08] bg-white shadow-[0_12px_32px_-18px_rgba(15,23,42,0.25)]">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full items-baseline justify-between gap-2 px-3.5 pt-3 pb-2 text-left">
        <span className="min-w-0">
          <span className="block text-[11px] font-semibold tracking-[0.02em] text-[#71717a]">Horizon · calibrated for time to resolution</span>
          <span className="mt-0.5 block truncate text-[15px] text-[#0a0a0a]" style={{ fontFamily: "'Playfair Display', 'Cormorant Garamond', Georgia, serif" }}>
            {state === 'loading' ? 'Reading the market…' : state === 'error' ? (notFound ? 'Event not found on Polymarket' : 'Horizon unavailable') : state.title}
          </span>
        </span>
        <span className="shrink-0 text-[12px] text-[#71717a]">{open ? 'Hide' : 'Show'}</span>
      </button>
      {open ? (
        <div className="px-3.5 pb-3">
          {state === 'loading' ? <div className="h-16 animate-pulse rounded-control bg-black/[0.04]" /> : null}
          {state === 'error' ? (
            <>
            <p className="pb-2 text-[12px] leading-snug text-[#676e7e]">{notFound ? 'Gamma has no event with this address yet.' : 'Could not reach Polymarket prices.'}</p>
            <button type="button" onClick={() => void load(slug)} className="w-full rounded-control bg-black/[0.05] py-2 text-[13px] font-medium">Retry</button>
            </>
          ) : null}
          {state !== 'loading' && state !== 'error' ? (
            legs.length ? (
              <>
                {shown.map((l, i) => <Row key={i} leg={l} band={state.model.tradable} />)}
                {legs.length > 4 ? (
                  <button type="button" onClick={() => setShowAll((s) => !s)} className="mt-1 w-full rounded-control bg-black/[0.04] py-1.5 text-[12px] font-medium text-[#111113]">
                    {showAll ? 'Show fewer' : `Show all ${legs.length}`}
                  </button>
                ) : null}
                {hoursNow !== undefined ? <When hours={hoursNow} /> : null}
                <p className="mt-2 text-[11px] leading-snug text-[#71717a]">
                  Averages from the out-of-time backtest, not a forecast for this market.{' '}
                  <a href={SITE_URL} target="_blank" rel="noreferrer" className="underline decoration-black/20 underline-offset-2">How we measured it</a>
                </p>
              </>
            ) : <p className="py-2 text-[13px] leading-snug text-[#676e7e]">No open yes/no market with a two-sided book on this page{skipNote(state.legs)}.</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
