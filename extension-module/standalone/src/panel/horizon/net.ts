/**
 * Offline fallback for bad venue Wi-Fi: every good response from our API is kept in
 * chrome.storage.local; when the API can't be reached, the last copy is returned with its time.
 * (Gamma prices are live by nature and are not cached: the panel says when it last reached them.)
 */
import { API } from './journal';

const KEY = (path: string) => `hzc:${path}`;
export type Got<T> = { data: T; cachedAt?: number };

export async function apiJSON<T>(path: string, timeoutMs = 4000): Promise<Got<T>> {
  try {
    const r = await fetch(`${API}${path}`, { signal: AbortSignal.timeout(timeoutMs) });
    if (!r.ok) throw new Error(String(r.status));
    const data = (await r.json()) as T;
    void chrome.storage.local.set({ [KEY(path)]: { t: Date.now(), data } }).catch(() => {});
    return { data };
  } catch (e) {
    const got = await chrome.storage.local.get(KEY(path)).catch(() => ({} as Record<string, unknown>));
    const hit = got[KEY(path)] as { t: number; data: T } | undefined;
    if (hit) return { data: hit.data, cachedAt: hit.t };
    throw e;
  }
}

export const hhmm = (t: number) => new Date(t).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });

// ---------- Gamma reachability ----------

const GAMMA_OK = 'hzGammaOk';
export function gammaOk() { void chrome.storage.local.set({ [GAMMA_OK]: Date.now() }).catch(() => {}); }
export async function gammaLastOk(): Promise<number | undefined> {
  const r = await chrome.storage.local.get(GAMMA_OK).catch(() => ({} as Record<string, unknown>));
  return typeof r[GAMMA_OK] === 'number' ? (r[GAMMA_OK] as number) : undefined;
}
