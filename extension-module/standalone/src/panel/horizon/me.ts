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

export type Me = { pnl?: number; summary?: string; label?: string };
const num = (x: unknown) => (typeof x === 'number' && Number.isFinite(x) ? x : undefined);
const money2 = (x: number) => `$${Math.abs(x).toFixed(2)}`;
const signed = (x: number) => (Math.abs(x) < 0.005 ? 'even' : `${x > 0 ? 'up' : 'down'} ${money2(x)}`);

/**
 * The strip from GET /api/me (backend/me.py): the user's real Polymarket positions if a wallet is
 * set and has any; else their self-reported placed bets once resolved; else what following every
 * Horizon call would have made; else "No settled bets yet". Not live (404/5xx) → undefined.
 */
export async function fetchMe(): Promise<Me | undefined> {
  try {
    const [id, wallet] = [await installId(), await getWallet()];
    const p = new URLSearchParams({ install_id: id, ...(wallet ? { wallet } : {}) });
    const r = await fetch(`${API}/api/me?${p}`, { signal: AbortSignal.timeout(6000) });
    if (!r.ok) return undefined;
    const j = await r.json() as Record<string, any>;
    const wt = j.wallet?.totals;
    if (wt && (num(wt.n_open) ?? 0) + (num(wt.n_closed) ?? 0) > 0 && num(wt.total_usd) !== undefined) {
      const x = wt.total_usd as number;
      return { pnl: x, summary: `You're ${signed(x)}`, label: 'from your Polymarket positions' };
    }
    const placed = j.journal?.placed, all = j.journal?.if_followed_all;
    if ((num(placed?.n_resolved) ?? 0) > 0 && num(placed?.pnl_usd) !== undefined) {
      const x = placed.pnl_usd as number;
      return { pnl: x, summary: `You're ${signed(x)}`, label: 'self-reported' };
    }
    if ((num(all?.n_resolved) ?? 0) > 0 && num(all?.pnl_usd) !== undefined) {
      const x = all.pnl_usd as number;
      return { pnl: x, summary: `If you'd followed Horizon: ${signed(x)}` };
    }
    const open = num(placed?.n_open) ?? 0;
    return { summary: `No settled bets yet${open ? ` (${open} open)` : ''}` };
  } catch { return undefined; }
}

export const upDown = (pnl: number) => (Math.abs(pnl) < 0.005 ? "You're even" : `You're ${pnl > 0 ? 'up' : 'down'} $${Math.abs(pnl).toFixed(2).replace(/\.00$/, '')}`);

export async function openMyResults() {
  await chrome.tabs.create({ url: await meUrl() });
}
