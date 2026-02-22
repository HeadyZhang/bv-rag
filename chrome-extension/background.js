/**
 * BV Maritime Extension — Background Service Worker
 *
 * Manages context menus, API dispatch, side panel communication,
 * and defect cache synchronization.
 */

// ── Context menus ──

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'bv-fill-en',
    title: 'BV AI: Convert to standard English',
    contexts: ['selection'],
  });
  chrome.contextMenus.create({
    id: 'bv-fill-zh',
    title: 'BV AI: Convert to standard Chinese',
    contexts: ['selection'],
  });
  chrome.contextMenus.create({
    id: 'bv-explain',
    title: 'BV AI: Explain in Chinese',
    contexts: ['selection'],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (!tab?.id || !info.selectionText) return;

  if (info.menuItemId === 'bv-fill-en') {
    chrome.tabs.sendMessage(tab.id, {
      type: 'FILL_REQUEST',
      selectedText: info.selectionText,
      targetLang: 'en',
    });
  } else if (info.menuItemId === 'bv-fill-zh') {
    chrome.tabs.sendMessage(tab.id, {
      type: 'FILL_REQUEST',
      selectedText: info.selectionText,
      targetLang: 'zh',
    });
  } else if (info.menuItemId === 'bv-explain') {
    // Open side panel and send explain request
    try {
      await chrome.sidePanel.open({ tabId: tab.id });
    } catch (e) {
      // Side panel may already be open
    }
    // Give side panel time to load, then send explanation
    setTimeout(() => {
      chrome.runtime.sendMessage({
        type: 'EXPLAIN_TEXT',
        selectedText: info.selectionText,
        tabId: tab.id,
      });
    }, 500);
  }
});

// ── Message routing ──

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'SHOW_EXPLANATION') {
    // Forward to side panel
    chrome.runtime.sendMessage({
      type: 'EXPLAIN_TEXT',
      selectedText: msg.selectedText,
    });
    sendResponse({ ok: true });
  }

  if (msg.type === 'GET_SETTINGS') {
    chrome.storage.sync.get(['apiBaseUrl'], (result) => {
      sendResponse({
        apiBaseUrl: result.apiBaseUrl || 'http://localhost:8000',
      });
    });
    return true; // async response
  }

  if (msg.type === 'SAVE_SETTINGS') {
    chrome.storage.sync.set({ apiBaseUrl: msg.apiBaseUrl }, () => {
      sendResponse({ ok: true });
    });
    return true;
  }
});

// ── Startup ──

chrome.runtime.onInstalled.addListener(async () => {
  // Set side panel behavior
  try {
    await chrome.sidePanel.setOptions({
      enabled: true,
    });
  } catch (e) {
    // Older Chrome versions may not support this
  }
});
