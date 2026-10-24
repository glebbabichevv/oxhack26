/**
 * Horizon background: opens the side panel from the toolbar button. Page reading and actions
 * run in the content script (the kept browser-use layer), driven from the panel via
 * chrome.tabs.sendMessage; this worker makes no network requests.
 */
chrome.runtime.onInstalled.addListener(() => {
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
});
chrome.runtime.onStartup.addListener(() => {
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
});
