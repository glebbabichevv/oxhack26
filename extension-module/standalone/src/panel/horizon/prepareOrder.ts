/**
 * Fill Polymarket's order ticket: Horizon decides, the browser-use layer acts. Drives the open
 * event page through the content script's existing EXECUTE_ACTION ops (find → click → fill_input):
 * selects the leg, the Buy or Sell tab, the outcome, and types the amount. Pressing the final
 * button is a separate step (orders.ts), done only on the user's own Bet / Place click. Never
 * touches a wallet or a login form.
 */

export type PrepareStep = { step: string; ok: boolean; detail?: string };
export type PrepareResult = { ok: boolean; steps: PrepareStep[] };

type Hit = { role: string; name: string; ref: string; state: string; where: string };

export async function send(tabId: number, action: Record<string, unknown>): Promise<any> {
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

export async function find(tabId: number, description: string): Promise<Hit[]> {
  const r = await send(tabId, { op: 'find', payload: { description } });
  if (!r?.success || typeof r.result !== 'string') return [];
  // "- button "Buy Yes 27¢" [ref=e9] (checked) — below the viewport"
  return [...r.result.matchAll(/^- (\S+) "([^"]*)" \[ref=(e\d+)\](?: \(([^)]*)\))?(?: — (.*))?$/gm)]
    .map((m) => ({ role: m[1], name: m[2], ref: m[3], state: m[4] ?? '', where: m[5] ?? '' }));
}

export async function click(tabId: number, ref: string) {
  const r = await send(tabId, { op: 'click', target: { selector: ref } });
  return !!r?.success;
}

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const NEVER = /^(trade|buy|confirm|place order|sign up|log in)\b/i; // never a target, whatever matches

export async function prepareOrder(opts: {
  tabId: number; eventSlug: string; marketSlug?: string; label: string; legCount: number;
  side: 'YES' | 'NO'; amount: number; bid?: number; ask?: number;
  /** Live narration for the panel: called before each page action. */
  onProgress?: (text: string) => void;
  /** 'sell' switches the ticket to Sell; amount is then a number of shares. */
  mode?: 'buy' | 'sell';
}): Promise<PrepareResult> {
  const { tabId, eventSlug, marketSlug, label, legCount, side, amount, bid, ask } = opts;
  const say = opts.onProgress ?? (() => {});
  const steps: PrepareStep[] = [];
  await ensureContentScript(tabId);

  const word = side === 'YES' ? 'Yes' : 'No';
  const c = (x: number) => Number((x * 100).toFixed(1));
  const wantCents = bid !== undefined && ask !== undefined ? c(side === 'YES' ? ask : 1 - bid) : undefined;
  /** The ticket's checked outcome radio ("Yes 27¢ 0"): its price says which leg is selected. */
  const ticketCents = async () => {
    const r = (await find(tabId, `${word} radio`)).filter((h) => h.role === 'radio' && new RegExp(`^${word}\\b`, 'i').test(h.name));
    const m = r[0]?.name.match(/(\d+(?:\.\d+)?)¢/);
    return m ? Number(m[1]) : undefined;
  };
  const sameLeg = async () => {
    if (wantCents === undefined) return true;
    const got = await ticketCents();
    return got !== undefined && Math.abs(got - wantCents) <= 1.5;
  };

  // 1. The leg. Sports pages: a moneyline button named by the slug suffix ("DRAW 16¢", "BAR 60¢").
  //    Multi-outcome pages: each row has "Buy Yes 27¢ / Buy No 74¢" buttons, often far below the
  //    fold: scroll the row into view by its label (search_page scans and scrolls), then click the
  //    in-view button for the chosen side at this leg's price. Single-market pages: nothing to pick.
  //    Afterwards the ticket must show this leg's price, or nothing is typed.
  if (legCount > 1) {
    say(`Choosing ${label}`);
    const suffix = marketSlug?.startsWith(`${eventSlug}-`) ? marketSlug.slice(eventSlug.length + 1) : '';
    const bySuffix = async () => {
      if (!(suffix && /^[a-z][a-z0-9]{1,6}$/.test(suffix))) return false;
      const hits = await find(tabId, `${suffix} button`);
      const hit = hits.find((h) => h.role === 'button' && new RegExp(`^${esc(suffix)}(\\s|\\d|$)`, 'i').test(h.name));
      return hit ? click(tabId, hit.ref) : false;
    };
    const byRow = async () => {
      if (wantCents === undefined) return false;
      await send(tabId, { op: 'search_page', payload: { query: label } }).catch(() => undefined);
      await new Promise((r) => setTimeout(r, 350));
      const name = `Buy ${word} ${wantCents}¢`;
      const hits = (await find(tabId, `${name} button`)).filter((h) => h.role === 'button' && h.name.replace(/\s+/g, ' ') === name);
      const inView = hits.filter((h) => !/viewport/i.test(h.where));
      const hit = inView.length >= 1 ? inView[0] : hits.length === 1 ? hits[0] : undefined;
      return hit ? click(tabId, hit.ref) : false;
    };
    // Sports moneylines are labelled by team abbreviation + price ("COR 45¢", "DRAW 16¢"): try the
    // abbreviations a team name usually gets, then the price alone on such short buttons.
    const bySports = async () => {
      if (side !== 'YES' || wantCents === undefined) return false;
      const words = label.toUpperCase().replace(/[^A-Z0-9 ]/g, ' ').split(/\s+/)
        .filter((w) => w && !['FC', 'SC', 'CF', 'AC', 'CD', 'CA', 'AFC', 'SSC', 'CLUB', 'DE', 'THE', 'RC', 'SV', 'FK', 'SK'].includes(w));
      const abbrs = [...new Set([words[0]?.slice(0, 3), words.map((w) => w[0]).join('').slice(0, 3), words[words.length - 1]?.slice(0, 3), label === 'Draw' ? 'DRAW' : '']
        .filter((x): x is string => !!x && x.length >= 2))];
      const short = (h: Hit) => h.role === 'button' && /^[A-Z][A-Z0-9]{1,4}\s+\d+(\.\d)?¢$/.test(h.name.trim());
      const priceOk = (h: Hit) => { const m = h.name.match(/(\d+(?:\.\d)?)¢/); return !!m && Math.abs(Number(m[1]) - wantCents) <= 1; };
      for (const ab of abbrs) {
        const hit = (await find(tabId, `${ab} button`)).find((h) => short(h) && h.name.toUpperCase().startsWith(`${ab} `) && priceOk(h));
        if (hit) return click(tabId, hit.ref);
      }
      const byPrice = (await find(tabId, `${wantCents}¢ button`)).filter((h) => short(h) && priceOk(h));
      return byPrice.length === 1 ? click(tabId, byPrice[0].ref) : false;
    };
    const byLabel = async () => {
      const hits = await find(tabId, label);
      const hit = hits.find((h) => ['button', 'link', 'row', 'radio', 'option', 'tab'].includes(h.role)
        && h.name.toLowerCase().includes(label.toLowerCase()) && !NEVER.test(h.name));
      return hit ? click(tabId, hit.ref) : false;
    };
    let picked = false;
    for (const attempt of [bySuffix, bySports, byRow, byLabel, byRow]) {
      if (!(await attempt())) continue;
      // The ticket re-renders after the click: give it up to ~2s to show this leg.
      for (let k = 0; k < 6 && !picked; k++) { await new Promise((r) => setTimeout(r, 350)); picked = await sameLeg(); }
      if (picked) break;
    }
    steps.push({ step: `Select “${label}”`, ok: picked, detail: picked ? undefined
      : wantCents !== undefined && (await ticketCents()) !== undefined ? 'wrong outcome selected' : 'could not find this market on the page' });
    if (!picked) return { ok: false, steps };
  }

  // 1b. Sell: switch the ticket to its Sell tab.
  if (opts.mode === 'sell') {
    say('Switching to Sell');
    const hits = (await find(tabId, 'Sell tab')).filter((h) => ['tab', 'button', 'radio'].includes(h.role) && /^sell$/i.test(h.name.trim()));
    const ok = !!hits[0] && await click(tabId, hits[0].ref);
    steps.push({ step: 'Sell tab', ok, detail: ok ? undefined : 'Sell tab not found' });
    if (!ok) return { ok: false, steps };
    await new Promise((r) => setTimeout(r, 300));
  }

  // 2. The outcome in the order ticket: a radio "Yes 16¢" / "No 85¢".
  say(`Picking ${word}`);
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
  if (!(await sameLeg())) { steps.push({ step: 'Check the ticket', ok: false, detail: 'wrong outcome selected' }); return { ok: false, steps }; }

  // 3. The stake. Then stop: the Trade button is the user's.
  const sell = opts.mode === 'sell';
  const value = sell ? amount.toFixed(2) : amount >= 10 ? String(Math.round(amount)) : amount.toFixed(2);
  say(sell ? `Typing ${value} shares` : `Typing $${value}`);
  const r = await send(tabId, { op: 'fill_input', target: { selector: '#market-order-amount-input', text: sell ? 'Shares' : 'Amount' }, payload: { value } });
  steps.push({ step: sell ? `Shares ${value}` : `Amount $${value}`, ok: !!r?.success, detail: r?.success ? undefined : (r?.error ?? 'amount field not found') });
  return { ok: steps.every((s) => s.ok), steps };
}

/** Fallback when the page resists: highlight the leg if possible and put the amount on the clipboard. */
export async function fallbackHint(tabId: number, label: string, amount: number) {
  try { await send(tabId, { op: 'highlight', target: { text: label } }); } catch { /* visual only */ }
  try { await navigator.clipboard.writeText(amount.toFixed(2)); return true; } catch { return false; }
}
