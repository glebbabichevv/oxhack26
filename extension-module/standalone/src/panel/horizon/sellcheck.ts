/**
 * Sell notifications (runs in the background service worker every 15 min). For a public wallet
 * address the user gave (read only), each open Polymarket position is priced with the SAME code the
 * panel uses: decideEvent (COH, one bet per event) for Horizon's q and cost, quotes() + caution()
 * to skip events in progress and markets smaller than anything Horizon was tested on. When what the
 * market pays for the side held is at least Horizon's value of it plus the cost (the panel's SELL
 * rule), a notification says so. Clicking it opens the market; the panel's position card offers
 * "Set up sale", and the human presses Sell. Nothing here trades.
 */
import { decideEvent, type Decision, type Leg, type Model } from './horizon';
import { caution, quotes, type Quote } from './ledger';
import fallbackModel from './model.fallback.json';

const MODEL_URL = 'https://oxhack26-production.up.railway.app/api/model';
const WALLET_KEY = 'horizonWallet';
export const ALERTS_KEY = 'horizonSellAlerts';
const SENT_KEY = 'horizonSellSent';
const MAX_PER_RUN = 3;

export type WalletPos = { eventSlug?: string; slug?: string; conditionId?: string; outcome?: string; size?: number; title?: string };
export type Signal = { key: string; eventSlug: string; title: string; message: string };

const c = (x: number) => `${Math.round(x * 100)}¢`;

/** The panel's rule for one held position: SELL when the market pays >= Horizon's value + cost. Pure. */
export function sellSignal(pos: WalletPos, leg: Pick<Leg, 'label' | 'bid' | 'ask'> & { decision?: Decision }, quote?: Pick<Quote, 'volume' | 'startsAt' | 'endDate'>, now = Date.now()): Signal | undefined {
  const d = leg.decision;
  if (!d || leg.bid === undefined || leg.ask === undefined) return undefined;
  if (quote && caution(quote, now)) return undefined; // in progress, or smaller than any tested market
  const side = /^no$/i.test(pos.outcome ?? '') ? 'NO' : 'YES';
  const pays = side === 'YES' ? leg.bid : 1 - leg.ask;
  const worth = side === 'YES' ? d.q : 1 - d.q;
  if (!(pays >= worth + d.cost)) return undefined;
  const outcome = `${leg.label}${side === 'NO' ? ' (No)' : ''}`;
  return {
    key: `${pos.conditionId ?? pos.slug}:${side}:${Math.round(pays * 100)}`,
    eventSlug: pos.eventSlug ?? '',
    title: `Time to sell: ${outcome}`,
    message: `Market pays ${c(pays)}, Horizon values it at ${c(worth)}.`,
  };
}

async function loadModel(): Promise<Model> {
  try {
    const r = await fetch(MODEL_URL, { signal: AbortSignal.timeout(5000) });
    if (!r.ok) throw new Error(String(r.status));
    const m = (await r.json()) as Model;
    void chrome.storage.local.set({ horizonModel: m });
    return m;
  } catch {
    const { horizonModel } = await chrome.storage.local.get('horizonModel');
    return (horizonModel as Model) ?? (fallbackModel as unknown as Model);
  }
}

/** Whether alerts are on: the setting, or by default on exactly when a wallet is set. */
export async function alertsOn(): Promise<{ on: boolean; wallet?: string }> {
  const r = await chrome.storage.local.get([WALLET_KEY, ALERTS_KEY]);
  const wallet = typeof r[WALLET_KEY] === 'string' && /^0x[0-9a-fA-F]{40}$/.test(r[WALLET_KEY]) ? (r[WALLET_KEY] as string) : undefined;
  const on = !!wallet && (r[ALERTS_KEY] === undefined ? true : !!r[ALERTS_KEY]);
  return { on, wallet };
}

/** One run: read positions, price them, notify (at most 3, once per position and price level). */
export async function runSellCheck(): Promise<Signal[]> {
  const { on, wallet } = await alertsOn();
  if (!on || !wallet) return [];
  const pos = await fetch(`https://data-api.polymarket.com/positions?user=${wallet}&sizeThreshold=0.1&limit=500`, { signal: AbortSignal.timeout(8000) })
    .then((r) => (r.ok ? r.json() : [])).catch(() => []) as WalletPos[];
  if (!pos.length) return [];
  const model = await loadModel();
  const sent = new Set<string>(((await chrome.storage.local.get(SENT_KEY))[SENT_KEY] as string[] | undefined) ?? []);
  const qs = await quotes(model, pos.map((p) => p.slug ?? '').filter(Boolean)).catch(() => new Map<string, Quote>());
  const events = new Map<string, Leg[]>();
  const out: Signal[] = [];
  for (const p of pos) {
    if (out.length >= MAX_PER_RUN || !p.eventSlug) continue;
    if (!events.has(p.eventSlug)) events.set(p.eventSlug, await decideEvent(model, p.eventSlug).then((e) => e.legs).catch(() => []));
    const leg = events.get(p.eventSlug)!.find((l) => l.marketSlug === p.slug);
    const s = leg ? sellSignal(p, leg, p.slug ? qs.get(p.slug) : undefined) : undefined;
    if (!s || sent.has(s.key)) continue;
    sent.add(s.key);
    out.push(s);
  }
  for (const s of out) {
    chrome.notifications.create(`hz-sell|${s.eventSlug}|${s.key}`, { type: 'basic', iconUrl: 'icons/icon128.png', title: s.title, message: s.message, priority: 1 });
  }
  if (out.length) await chrome.storage.local.set({ [SENT_KEY]: [...sent].slice(-300) });
  return out;
}
