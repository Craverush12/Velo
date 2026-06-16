/**
 * Extracted conversation summary store (service worker context).
 *
 * Mirrors a compact summary of each successful ContextEngine sync into
 * chrome.storage.local so the side panel can react without reading the
 * AI tab's page localStorage.
 *
 * Storage shape (keys defined in core/storage-keys.js):
 *
 *   velocity_last_extracted_summary: {
 *     platform, chatId, sessionId, messageCount, title, url, syncedAt
 *   }
 *
 *   velocity_extracted_by_platform: {
 *     chatgpt: { ...summary },
 *     claude:  { ...summary },
 *     gemini:  { ...summary }
 *   }
 *
 * The actual full conversation JSON still lives in page localStorage on the
 * AI host tab (velocity_chatgpt_session etc.) — same as Extension/Extension-new.
 *
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  function getKeys() {
    return root.TV.STORAGE_KEYS || {};
  }

  function summaryKey() {
    return getKeys().LAST_EXTRACTED_SUMMARY || "velocity_last_extracted_summary";
  }

  function platformMapKey() {
    return getKeys().EXTRACTED_BY_PLATFORM || "velocity_extracted_by_platform";
  }

  function buildSummary(contextPayload) {
    const conv = (contextPayload.conversations && contextPayload.conversations[0]) || {};
    const messages = Array.isArray(conv.messages) ? conv.messages : [];
    return {
      platform: contextPayload.platform || "unknown",
      sessionId: contextPayload.sessionId || "",
      chatId: conv.chatId || contextPayload.sessionId || "",
      title: conv.title || "Chat Conversation",
      url: conv.url || "",
      messageCount: messages.length,
      extractorVersion: contextPayload.extractorVersion || "",
      syncedAt: Date.now(),
    };
  }

  async function recordExtraction(contextPayload) {
    if (!contextPayload || !chrome?.storage?.local) return null;
    const summary = buildSummary(contextPayload);

    try {
      const existing = await chrome.storage.local.get([platformMapKey()]);
      const byPlatform = (existing && existing[platformMapKey()]) || {};
      byPlatform[summary.platform] = summary;

      await chrome.storage.local.set({
        [summaryKey()]: summary,
        [platformMapKey()]: byPlatform,
      });

      console.log("[TV_ESSENCE] 📦 Mirror saved to chrome.storage.local", summary);
      return summary;
    } catch (error) {
      console.warn("[TV_ESSENCE] Could not write extracted summary mirror:", error);
      return null;
    }
  }

  async function getLastExtraction() {
    if (!chrome?.storage?.local) return null;
    try {
      const result = await chrome.storage.local.get([summaryKey()]);
      return (result && result[summaryKey()]) || null;
    } catch (error) {
      return null;
    }
  }

  async function getExtractionByPlatform(platform) {
    if (!chrome?.storage?.local) return null;
    try {
      const result = await chrome.storage.local.get([platformMapKey()]);
      const map = (result && result[platformMapKey()]) || {};
      return platform ? map[platform] || null : map;
    } catch (error) {
      return null;
    }
  }

  async function clear() {
    if (!chrome?.storage?.local) return;
    try {
      await chrome.storage.local.remove([summaryKey(), platformMapKey()]);
    } catch (error) {
      /* ignore */
    }
  }

  root.TV.extractedConversationStore = {
    recordExtraction,
    getLastExtraction,
    getExtractionByPlatform,
    clear,
  };
})();
