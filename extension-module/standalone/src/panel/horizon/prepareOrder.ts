/**
 * "Prepare order": Horizon decides, the browser-use layer acts. Drives the open Polymarket
 * event page through the content script's existing EXECUTE_ACTION ops (find → click → fill_input),
 * exactly as the agent would. It selects the leg and the outcome and types the stake, then STOPS:
 * it never clicks Trade/Buy/confirm and never touches a wallet.
 */

export type PrepareStep = { step: string; ok: boolean; detail?: string };
export type PrepareResult = { ok: boolean; steps: PrepareStep[] };

type Hit = { role: string; name: string; ref: string; state: string };

async function send(tabId: number, action: Record<string, unknown>): Promise<any> {
  return chrome.tabs.sendMessage(tabId, { type: 'EXECUTE_ACTION', action }, { frameId: 0 });
}

/** The content script is declared for every page, but a tab opened before install has none yet. */
async function ensureContentScript(tabId: number) {
  try {
    await send(tabId, { op: 'find', payload: { description: 'Polymarket' } });
  } catch {
    await chrome.scripting.executeScript({ target: { tabId, frameIds: [0] }, files: ['content.js'] });
    await new Promise((r) => setTimeout(r, 300));
  }
}

async function find(tabId: number, description: string): Promise<Hit[]> {
  const r = await send(tabId, { op: 'find', payload: { description } });
  if (!r?.success || typeof r.result !== 'string') return [];
  return [...r.result.matchAll(/^- (\S+) "([^"]*)" \[ref=(e\d+)\](?: \(([^)]*)\))?/gm)]
    .map((m) => ({ role: m[1], name: m[2], ref: m[3], state: m[4] ?? '' }));
}

async function click(tabId: number, ref: string) {
  const r = await send(tabId, { op: 'click', target: { selector: ref } });
  return !!r?.success;
}

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const NEVER = /^(trade|buy|confirm|place order|sign up|log in)\b/i; // never a target, whatever matches

export async function prepareOrder(opts: {
  tabId: number; eventSlug: string; marketSlug?: string; label: string; legCount: number;
  side: 'YES' | 'NO'; amount: number; bid?: number; ask?: number;
}): Promise<PrepareResult> {
  const { tabId, eventSlug, marketSlug, label, legCount, side, amount, bid, ask } = opts;
  const steps: PrepareStep[] = [];
  await ensureContentScript(tabId);

  // 1. The leg. Sports pages: a moneyline button named by the slug suffix ("DRAW 16¢", "BAR 60¢").
  //    Other multi-market pages: the row named by the leg. Single-market pages: nothing to pick.
  if (legCount > 1) {
    const suffix = marketSlug?.startsWith(`${eventSlug}-`) ? marketSlug.slice(eventSlug.length + 1) : '';
    let picked = false;
    if (suffix && /^[a-z]{2,6}$/.test(suffix)) {
      const hits = await find(tabId, `${suffix} button`);
      const hit = hits.find((h) => h.role === 'button' && new RegExp(`^${esc(suffix)}(\\s|\\d|$)`, 'i').test(h.name));
      if (hit) picked = await click(tabId, hit.ref);
    }
    if (!picked && bid !== undefined && ask !== undefined) {
      // Multi-outcome pages list a "Buy Yes 24¢" / "Buy No 77¢" button per row, priced at the ask.
      // Click it only if exactly one button carries this leg's price.
      const c = (x: number) => `${Number((x * 100).toFixed(1))}¢`;
      const name = side === 'YES' ? `Buy Yes ${c(ask)}` : `Buy No ${c(1 - bid)}`;
      const hits = (await find(tabId, `${name} button`)).filter((h) => h.role === 'button' && h.name.replace(/\s+/g, ' ') === name);
      if (hits.length === 1) picked = await click(tabId, hits[0].ref);
    }
    if (!picked) {
      const hits = await find(tabId, label);
      const hit = hits.find((h) => ['button', 'link', 'row', 'radio', 'option', 'tab'].includes(h.role)
        && h.name.toLowerCase().includes(label.toLowerCase()) && !NEVER.test(h.name));
      if (hit) picked = await click(tabId, hit.ref);
    }
    steps.push({ step: `Select “${label}”`, ok: picked, detail: picked ? undefined : 'could not find this market on the page' });
    if (!picked) return { ok: false, steps };
    await new Promise((r) => setTimeout(r, 400));
  }

  // 2. The outcome in the order ticket: a radio "Yes 16¢" / "No 85¢".
  const word = side === 'YES' ? 'Yes' : 'No';
  const want = new RegExp(`^${word}\\b`, 'i');
  let radios = (await find(tabId, `${word} radio`)).filter((h) => h.role === 'radio' && want.test(h.name));
  let outcomeOk = radios.some((h) => /checked/.test(h.state));
  if (!outcomeOk && radios[0]) {
    await click(tabId, radios[0].ref);
    radios = (await find(tabId, `${word} radio`)).filter((h) => h.role === 'radio' && want.test(h.name));
    outcomeOk = radios.some((h) => /checked/.test(h.state));
  }
  steps.push({ step: `Outcome ${word}`, ok: outcomeOk, detail: outcomeOk ? radios[0]?.name.replace(/\s+\d+$/, '') : 'order ticket not found' });
  if (!outcomeOk) return { ok: false, steps };

  // 3. The stake. Then stop: the Trade button is the user's.
  const value = amount >= 10 ? String(Math.round(amount)) : amount.toFixed(2);
  const r = await send(tabId, { op: 'fill_input', target: { selector: '#market-order-amount-input', text: 'Amount' }, payload: { value } });
  steps.push({ step: `Amount $${value}`, ok: !!r?.success, detail: r?.success ? undefined : (r?.error ?? 'amount field not found') });
  return { ok: steps.every((s) => s.ok), steps };
}

/** Fallback when the page resists: highlight the leg if possible and put the amount on the clipboard. */
export async function fallbackHint(tabId: number, label: string, amount: number) {
  try { await send(tabId, { op: 'highlight', target: { text: label } }); } catch { /* visual only */ }
  try { await navigator.clipboard.writeText(amount.toFixed(2)); return true; } catch { return false; }
}
