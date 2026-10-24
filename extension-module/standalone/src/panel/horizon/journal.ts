/**
 * Decision Journal client. Every decision Horizon shows (a card's verdict, an agent plan item, a
 * ticket it set up, the user's "I placed it" / "Skip") is kept locally and POSTed to
 * /api/journal under an anonymous install id. If the server is down or the endpoint is not
 * there yet, entries queue in chrome.storage.local and are retried later; the UI never waits.
 */
import type { Decision } from './horizon';

export const API = 'https://horizon-api-iota.vercel.app';
export const SITE = 'https://horizon-two-gilt.vercel.app';
const ID_KEY = 'horizonInstallId';
const LOG_KEY = 'horizonJournal';
const QUEUE_KEY = 'horizonJournalQueue';

export type Status = 'shown' | 'set_up' | 'placed' | 'skipped';
export type Entry = {
  install_id: string; ts: string; market_id: string; slug: string; question: string; side: 'YES' | 'NO' | null;
  price: number; q: number; q_low: number; q_high: number; action: Decision['action']; stake_usd: number;
  kelly_fraction: number; source: 'card' | 'agent'; status: Status;
};

let idCache: string | undefined;
export async function installId(): Promise<string> {
  if (idCache) return idCache;
  const r = await chrome.storage.local.get(ID_KEY).catch(() => ({} as Record<string, unknown>));
  let id = r[ID_KEY] as string | undefined;
  if (!id) { id = crypto.randomUUID(); await chrome.storage.local.set({ [ID_KEY]: id }).catch(() => {}); }
  idCache = id;
  return id;
}
export const webUrl = (id: string) => `${SITE}/journal?me=${encodeURIComponent(id)}`;

async function post(entries: Entry[]): Promise<boolean> {
  try {
    const r = await fetch(`${API}/api/journal`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(entries.length === 1 ? entries[0] : { entries }), signal: AbortSignal.timeout(5000) });
    return r.ok;
  } catch { return false; }
}

let flushing = false;
/** Retry queued entries (one by one, oldest first); stops at the first failure. */
export async function flush() {
  if (flushing) return;
  flushing = true;
  try {
    const r = await chrome.storage.local.get(QUEUE_KEY);
    const queue = (r[QUEUE_KEY] as Entry[] | undefined) ?? [];
    let sent = 0;
    for (const e of queue) { if (!(await post([e]))) break; sent++; }
    if (sent) {
      const r2 = await chrome.storage.local.get(QUEUE_KEY);
      await chrome.storage.local.set({ [QUEUE_KEY]: ((r2[QUEUE_KEY] as Entry[] | undefined) ?? []).slice(sent) });
    }
  } catch { /* try again later */ } finally { flushing = false; }
}

const seenShown = new Set<string>();

/** Record one decision. "shown" is logged once per market+side per panel session. */
export async function record(x: {
  marketId?: string; slug: string; question: string; d: Decision; stake: number; source: 'card' | 'agent'; status: Status;
}) {
  const side = x.d.action === 'BUY_YES' ? 'YES' : x.d.action === 'BUY_NO' ? 'NO' : null;
  const key = `${x.slug}:${side}`;
  if (x.status === 'shown') { if (seenShown.has(key)) return; seenShown.add(key); }
  const e: Entry = {
    install_id: await installId(), ts: new Date().toISOString(), market_id: x.marketId ?? '', slug: x.slug, question: x.question, side,
    price: +x.d.price.toFixed(4), q: +x.d.q.toFixed(4), q_low: +x.d.lo.toFixed(4), q_high: +x.d.hi.toFixed(4), action: x.d.action,
    stake_usd: +x.stake.toFixed(2), kelly_fraction: +x.d.kelly.toFixed(5), source: x.source, status: x.status,
  };
  try {
    const r = await chrome.storage.local.get(LOG_KEY);
    const log = ((r[LOG_KEY] as Entry[] | undefined) ?? []);
    log.unshift(e);
    await chrome.storage.local.set({ [LOG_KEY]: log.slice(0, 500) });
  } catch { /* local copy is best effort */ }
  void (async () => {
    if (await post([e])) { void flush(); return; }
    const r = await chrome.storage.local.get(QUEUE_KEY).catch(() => ({} as Record<string, unknown>));
    const queue = ((r[QUEUE_KEY] as Entry[] | undefined) ?? []);
    queue.push(e);
    await chrome.storage.local.set({ [QUEUE_KEY]: queue.slice(-1000) }).catch(() => {});
  })();
}

export async function localJournal(): Promise<Entry[]> {
  const r = await chrome.storage.local.get(LOG_KEY).catch(() => ({} as Record<string, unknown>));
  return (r[LOG_KEY] as Entry[] | undefined) ?? [];
}
export function onJournal(cb: (e: Entry[]) => void) {
  const l = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
    if (area === 'local' && changes[LOG_KEY]?.newValue) cb(changes[LOG_KEY].newValue as Entry[]);
  };
  chrome.storage.onChanged.addListener(l);
  return () => chrome.storage.onChanged.removeListener(l);
}
