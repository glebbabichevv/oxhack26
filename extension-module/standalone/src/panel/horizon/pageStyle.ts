/**
 * Horizon's look for the kept browser-use overlays on the page, without editing the content
 * layer: the overlay draws with inline styles (orange for agent actions), and a stylesheet
 * inserted from the panel with !important wins over them. Ink while acting, green for a moment
 * on success, rose on failure (html[data-hz-state] is the only thing the panel writes).
 */
const CSS = `
.argos-agent-highlight {
  border: 2px solid #111113 !important;
  background: rgba(17, 17, 19, 0.035) !important;
  border-radius: 8px !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.9), 0 8px 22px -8px rgba(17, 17, 19, 0.35) !important;
  transition: border-color 200ms ease, box-shadow 200ms ease !important;
}
.argos-agent-highlight-label {
  background: #111113 !important; color: #fff !important; font-size: 0 !important;
  border-radius: 6px 6px 0 0 !important; padding: 2px 8px !important;
  font-family: system-ui, -apple-system, sans-serif !important; box-shadow: none !important;
}
.argos-agent-highlight-label::after { content: 'Horizon'; font-size: 11px; font-weight: 600; letter-spacing: 0.01em; }
.argos-highlight-selected { border-color: #111113 !important; }
html[data-hz-state="ok"] .argos-agent-highlight, html[data-hz-state="ok"] .argos-highlight-selected { border-color: #15803d !important; box-shadow: 0 0 0 1px rgba(255,255,255,0.9), 0 8px 22px -8px rgba(21,128,61,0.45) !important; }
html[data-hz-state="ok"] .argos-agent-highlight-label { background: #15803d !important; }
html[data-hz-state="fail"] .argos-agent-highlight, html[data-hz-state="fail"] .argos-highlight-selected { border-color: #e11d48 !important; box-shadow: 0 0 0 1px rgba(255,255,255,0.9), 0 8px 22px -8px rgba(225,29,72,0.45) !important; }
html[data-hz-state="fail"] .argos-agent-highlight-label { background: #e11d48 !important; }
`;

/**
 * Insert the stylesheet unless this very document already has it. Checked inside the page
 * (html[data-hz-styled]) every time, because a reload keeps the URL but starts a new document.
 * Called before every page action, so the overlay can never draw in its own orange.
 */
export async function stylePage(tabId: number) {
  try {
    const [r] = await chrome.scripting.executeScript({ target: { tabId, frameIds: [0] }, func: () => document.documentElement.hasAttribute('data-hz-styled') });
    if (r?.result) return;
    await chrome.scripting.insertCSS({ target: { tabId, frameIds: [0] }, css: CSS });
    await chrome.scripting.executeScript({ target: { tabId, frameIds: [0] }, func: () => { document.documentElement.setAttribute('data-hz-styled', ''); } });
  } catch { /* restricted page or tab gone: nothing to style */ }
}

/** 'act' | 'ok' | 'fail' | '' on <html data-hz-state>; ok/fail clear themselves. */
export async function markPage(tabId: number, state: 'act' | 'ok' | 'fail' | '') {
  try {
    await chrome.scripting.executeScript({ target: { tabId, frameIds: [0] }, args: [state], func: (s: string) => {
      const h = document.documentElement;
      if (s) h.setAttribute('data-hz-state', s); else h.removeAttribute('data-hz-state');
      if (s === 'ok' || s === 'fail') setTimeout(() => { if (h.getAttribute('data-hz-state') === s) h.removeAttribute('data-hz-state'); }, 1600);
    } });
  } catch { /* cosmetic only */ }
}
