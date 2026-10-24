/**
 * Personal results: the site's /me page and GET /api/me for this install (and, if the user gave
 * one, their public Polymarket wallet address: read-only, never keys). If /api/me is not live,
 * summaries are simply absent.
 */
import { API, SITE, installId } from './journal';

const WALLET_KEY = 'horizonWallet';
export const WALLET_RE = /^0x[0-9a-fA-F]{40}$/;

export async function getWallet(): Promise<string | undefined> {
  const r = await chrome.storage.local.get(WALLET_KEY).catch(() => ({} as Record<string, unknown>));
  const w = r[WALLET_KEY];
  return typeof w === 'string' && WALLET_RE.test(w) ? w : undefined;
}
export async function setWallet(w: string | undefined) {
  if (w && WALLET_RE.test(w)) await chrome.storage.local.set({ [WALLET_KEY]: w });
  else await chrome.storage.local.remove(WALLET_KEY);
}

const qs = (id: string, wallet?: string) => new URLSearchParams({ id, ...(wallet ? { wallet } : {}) }).toString();
export async function meUrl() {
  const [id, wallet] = [await installId(), await getWallet()];
  return `${SITE}/me?${qs(id, wallet)}`;
}

export type Me = { pnl?: number; summary?: string };
const num = (x: unknown) => (typeof x === 'number' && Number.isFinite(x) ? x : undefined);

/** One-line result from /api/me, tolerant of the exact field names; undefined if not available. */
export async function fetchMe(): Promise<Me | undefined> {
  try {
    const [id, wallet] = [await installId(), await getWallet()];
    const p = new URLSearchParams({ install_id: id, ...(wallet ? { wallet } : {}) });
    const r = await fetch(`${API}/api/me?${p}`, { signal: AbortSignal.timeout(5000) });
    if (!r.ok) return undefined;
    const j = await r.json() as Record<string, any>;
    const pnl = num(j.pnl_usd) ?? num(j.pnl) ?? num(j.total_pnl) ?? num(j.result_usd) ?? num(j.summary?.pnl_usd) ?? num(j.summary?.pnl) ?? num(j.totals?.pnl_usd) ?? num(j.totals?.pnl);
    const summary = typeof j.summary === 'string' ? j.summary : typeof j.headline === 'string' ? j.headline : typeof j.text === 'string' ? j.text : undefined;
    return pnl === undefined && !summary ? undefined : { pnl, summary };
  } catch { return undefined; }
}

export const upDown = (pnl: number) => (Math.abs(pnl) < 0.005 ? "You're even" : `You're ${pnl > 0 ? 'up' : 'down'} $${Math.abs(pnl).toFixed(2).replace(/\.00$/, '')}`);

export async function openMyResults() {
  await chrome.tabs.create({ url: await meUrl() });
}
