/**
 * Paper trading (practice for the team, off by default): bets are recorded in the separate
 * 'paper' book at the live ask plus Polymarket's taker fee, never on Polymarket's ticket.
 */
import { useEffect, useState } from 'react';

const KEY = 'horizonPaperMode';
let on = false;
const subs = new Set<(v: boolean) => void>();

export async function initPaper() {
  const r = await chrome.storage.local.get(KEY).catch(() => ({} as Record<string, unknown>));
  on = !!r[KEY];
  subs.forEach((f) => f(on));
  chrome.storage.onChanged.addListener((c, area) => { if (area === 'local' && KEY in c) { on = !!c[KEY].newValue; subs.forEach((f) => f(on)); } });
}
export const isPaper = () => on;
export async function setPaper(v: boolean) { on = v; subs.forEach((f) => f(on)); await chrome.storage.local.set({ [KEY]: v }); }
export function usePaper() {
  const [v, setV] = useState(on);
  useEffect(() => { subs.add(setV); setV(on); return () => { subs.delete(setV); }; }, []);
  return v;
}
