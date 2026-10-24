/**
 * Horizon background: opens the side panel from the toolbar button, and every 15 minutes checks
 * the user's public Polymarket positions (if they gave a wallet address and left alerts on) for
 * the panel's SELL rule, raising a notification. Page reading and actions run in the content
 * script (the kept browser-use layer), driven from the panel; nothing here trades.
 */
import { runSellCheck, sellSignal } from '../panel/horizon/sellcheck';

const ALARM = 'hz-sell-check';
const setup = () => {
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
  void chrome.alarms.create(ALARM, { periodInMinutes: 15, delayInMinutes: 1 });
};
chrome.runtime.onInstalled.addListener(setup);
chrome.runtime.onStartup.addListener(setup);

chrome.alarms.onAlarm.addListener((a) => { if (a.name === ALARM) void runSellCheck().catch(() => {}); });

// Click: open the market; the panel's position card shows SELL and "Set up sale" (the human presses Sell).
chrome.notifications.onClicked.addListener((id) => {
  if (!id.startsWith('hz-sell|')) return;
  const eventSlug = id.split('|')[1];
  void chrome.tabs.create({ url: `https://polymarket.com/event/${eventSlug}` }).then((tab) => {
    if (tab.id !== undefined) void chrome.sidePanel.open({ tabId: tab.id }).catch(() => {});
  });
  chrome.notifications.clear(id);
});

// For tests and the panel: the pure rule, and a manual run.
(self as unknown as Record<string, unknown>).hzSellSignal = sellSignal;
(self as unknown as Record<string, unknown>).hzRunSellCheck = runSellCheck;
