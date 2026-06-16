/**
 * Side-panel lifecycle tracker (service worker).
 *
 * Responsibility:
 *   Track whether at least one Velocity side panel is currently open. The side
 *   panel opens a long-lived `chrome.runtime.connect` port on init; this module
 *   counts active ports and broadcasts the open/close transitions to every
 *   host-platform tab so on-page UI (e.g. the floating launcher pill) can
 *   react — for example, suppressing its glow while the panel is visible and
 *   resuming it once the panel closes.
 *
 * Boundaries (per extension-architecture-js-only skill):
 *   - Background-only. Pure in-memory state, no storage writes.
 *   - Single global namespace: `globalThis.TV.sidePanelLifecycle`.
 *   - Messaging stays inside one action: `TV_SIDE_PANEL_STATE` (broadcast +
 *     query response). The connect port carries a single name only.
 */
(function () {
  "use strict";

  const root = typeof globalThis !== "undefined" ? globalThis : self;
  root.TV = root.TV || {};

  const PORT_NAME = "velocity-side-panel-lifecycle";
  const BROADCAST_ACTION = "TV_SIDE_PANEL_STATE";
  /**
   * Mirrored in `chrome.storage.local` so launchers that mount AFTER the
   * panel opens (e.g. host-tab navigations, late content-script injection)
   * can pick up the current state via `chrome.storage.onChanged` even if the
   * runtime broadcast missed them. Session storage isn't available to MV3
   * content scripts, so `local` is the lowest-common-denominator surface.
   */
  const STORAGE_KEY = "velocity_side_panel_open";

  /** Hosts that get the broadcast — must stay in sync with content_scripts in manifest.json. */
  const HOST_TAB_PATTERNS = [
    "https://chat.openai.com/*",
    "https://chatgpt.com/*",
    "https://claude.ai/*",
    "https://gemini.google.com/*",
    "https://chat.mistral.ai/*",
    "https://gamma.app/*",
    "https://bolt.new/*",
    "https://grok.com/*",
    "https://www.grok.com/*",
    "https://suno.com/*",
    "https://www.suno.com/*",
    "https://lovable.dev/*",
    "https://www.lovable.dev/*",
    "https://replit.com/*",
    "https://www.replit.com/*",
    "https://v0.dev/*",
    "https://v0.app/*",
    "https://perplexity.ai/*",
    "https://www.perplexity.ai/*",
    "https://hera.video/*",
    "https://www.hera.video/*",
    "https://labs.google/*",
    "https://kimi.com/*",
    "https://www.kimi.com/*",
    "https://app.emergent.sh/*",
    "https://emergent.sh/*",
  ];

  let openCount = 0;

  function isPanelOpen() {
    return openCount > 0;
  }

  function writeStorage(open) {
    if (!chrome || !chrome.storage || !chrome.storage.local) return;
    try {
      chrome.storage.local.set({ [STORAGE_KEY]: Boolean(open) }, () => {
        void chrome.runtime.lastError;
      });
    } catch (_) {
      /* storage not available — broadcast still tries */
    }
  }

  function broadcastState(open) {
    writeStorage(open);
    if (!chrome || !chrome.tabs || typeof chrome.tabs.query !== "function") return;
    const message = { action: BROADCAST_ACTION, payload: { open: Boolean(open) } };
    try {
      chrome.tabs.query({ url: HOST_TAB_PATTERNS }, (tabs) => {
        if (chrome.runtime.lastError || !Array.isArray(tabs)) return;
        tabs.forEach((tab) => {
          if (!tab || tab.id == null) return;
          try {
            chrome.tabs.sendMessage(tab.id, message, () => {
              void chrome.runtime.lastError;
            });
          } catch (_) {
            /* tab gone or no receiver — safe to drop */
          }
        });
      });
    } catch (_) {
      /* chrome.tabs not available in this context */
    }
  }

  function handleConnect(port) {
    if (!port || port.name !== PORT_NAME) return false;
    const wasOpen = isPanelOpen();
    openCount += 1;
    if (!wasOpen) broadcastState(true);

    port.onDisconnect.addListener(() => {
      openCount = Math.max(0, openCount - 1);
      if (!isPanelOpen()) broadcastState(false);
    });
    return true;
  }

  if (chrome && chrome.runtime && chrome.runtime.onConnect) {
    chrome.runtime.onConnect.addListener(handleConnect);
  }

  // On service-worker (re)spawn the in-memory `openCount` resets to 0 — any
  // panels that were open before the SW eviction will reconnect their ports
  // shortly, but until they do the storage flag should not falsely say the
  // panel is open. Clear it eagerly so the launcher pill doesn't get stuck
  // in the suppressed state.
  writeStorage(false);

  root.TV.sidePanelLifecycle = {
    PORT_NAME,
    BROADCAST_ACTION,
    STORAGE_KEY,
    isPanelOpen,
    broadcastState,
  };
})();
