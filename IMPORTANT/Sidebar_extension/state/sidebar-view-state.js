/**
 * Side-panel view-state persistence (consumer surface).
 *
 * Single source of truth for "which screen was the user on?" — Home / Prompt
 * Library / Collections / Memory / Session(output|suggestions|context|versions).
 * Persisted to `chrome.storage.local` so the panel can rehydrate after it has
 * been closed and reopened (or after the welcome → login → reopen flow).
 *
 * Storage key: `tv_sidebar_consumer_view_state`
 * Shape:
 *   {
 *     v: 1,
 *     updatedAt: <ms>,
 *     panel: "home" | "library" | "collections" | "memory" | "session",
 *     sessionTab: "output" | "suggestions" | "context" | "versions",
 *     session: { ...minimal serializable session fields } | null,
 *     composerInput: string,
 *   }
 *
 * Only used by the consumer side panel today; enterprise has its own flow.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const STORAGE_KEY = "tv_sidebar_consumer_view_state";
  const SCHEMA_VERSION = 1;
  const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

  const VALID_PANELS = new Set([
    "home",
    "library",
    "collections",
    "memory",
    "session",
  ]);
  const VALID_SESSION_TABS = new Set([
    "output",
    "suggestions",
    "context",
    "versions",
  ]);

  /** In-memory mirror of the persisted shape so synchronous reads work. */
  let cached = null;
  let writeTimer = null;
  let pendingPatch = null;

  function emptyState() {
    return {
      v: SCHEMA_VERSION,
      updatedAt: 0,
      panel: "home",
      sessionTab: "output",
      session: null,
      composerInput: "",
    };
  }

  function isStorageAvailable() {
    return typeof chrome !== "undefined" && chrome.storage && chrome.storage.local;
  }

  function sanitizeSession(raw) {
    if (!raw || typeof raw !== "object") return null;
    // Keep only JSON-friendly primitives; strip anything that can't survive
    // structured clone (functions, DOM refs, blobs, etc.).
    try {
      const cloned = JSON.parse(JSON.stringify(raw));
      if (!cloned || typeof cloned !== "object") return null;
      // We require at least one of these to consider a saved session real.
      const hasContent =
        (typeof cloned.original === "string" && cloned.original.trim() !== "") ||
        (typeof cloned.enhanced === "string" && cloned.enhanced.trim() !== "") ||
        (typeof cloned.displayPrompt === "string" && cloned.displayPrompt.trim() !== "");
      return hasContent ? cloned : null;
    } catch (_) {
      return null;
    }
  }

  function sanitize(state) {
    const next = { ...emptyState(), ...(state || {}) };
    next.v = SCHEMA_VERSION;
    if (!VALID_PANELS.has(next.panel)) next.panel = "home";
    if (!VALID_SESSION_TABS.has(next.sessionTab)) next.sessionTab = "output";
    next.session = sanitizeSession(next.session);
    if (next.panel === "session" && !next.session) {
      // A session panel without session data isn't useful.
      next.panel = "home";
    }
    next.composerInput = typeof next.composerInput === "string" ? next.composerInput : "";
    next.updatedAt = Number(next.updatedAt) || 0;
    return next;
  }

  async function loadFromStorage() {
    if (!isStorageAvailable()) return emptyState();
    return new Promise((resolve) => {
      try {
        chrome.storage.local.get([STORAGE_KEY], (items) => {
          if (chrome.runtime && chrome.runtime.lastError) {
            console.warn(
              "[sidebar-view-state] load failed:",
              chrome.runtime.lastError.message
            );
            resolve(emptyState());
            return;
          }
          const raw = items && items[STORAGE_KEY];
          if (!raw || typeof raw !== "object") {
            resolve(emptyState());
            return;
          }
          const next = sanitize(raw);
          if (next.updatedAt && Date.now() - next.updatedAt > MAX_AGE_MS) {
            // Stale snapshot — drop the session payload but keep the panel
            // intent so users don't get dumped back into an old enhance.
            next.session = null;
            if (next.panel === "session") next.panel = "home";
          }
          resolve(next);
        });
      } catch (e) {
        console.warn("[sidebar-view-state] load threw:", e);
        resolve(emptyState());
      }
    });
  }

  function writeNow() {
    writeTimer = null;
    if (!pendingPatch) return;
    const merged = sanitize({ ...(cached || emptyState()), ...pendingPatch });
    merged.updatedAt = Date.now();
    cached = merged;
    pendingPatch = null;
    if (!isStorageAvailable()) return;
    try {
      chrome.storage.local.set({ [STORAGE_KEY]: merged }, () => {
        if (chrome.runtime && chrome.runtime.lastError) {
          console.warn(
            "[sidebar-view-state] save failed:",
            chrome.runtime.lastError.message
          );
        }
      });
    } catch (e) {
      console.warn("[sidebar-view-state] save threw:", e);
    }
  }

  function scheduleWrite(delayMs) {
    if (writeTimer != null) return;
    writeTimer = setTimeout(writeNow, Math.max(0, Number(delayMs) || 0));
  }

  /**
   * Merge a partial patch into the cached state and persist it. Coalesces
   * rapid calls (e.g. typing into the composer) into a single storage write.
   * @param {Partial<object>} patch
   * @param {{immediate?: boolean}} [opts]
   */
  function save(patch, opts) {
    if (!patch || typeof patch !== "object") return;
    pendingPatch = { ...(pendingPatch || {}), ...patch };
    if (opts && opts.immediate) {
      if (writeTimer != null) {
        clearTimeout(writeTimer);
        writeTimer = null;
      }
      writeNow();
    } else {
      scheduleWrite(180);
    }
  }

  /**
   * Synchronous read of the last loaded/cached state. Call `init()` first;
   * before that, returns an empty default.
   */
  function getSnapshot() {
    return cached ? { ...cached } : emptyState();
  }

  async function init() {
    cached = await loadFromStorage();
    return getSnapshot();
  }

  function clear() {
    cached = emptyState();
    pendingPatch = null;
    if (writeTimer != null) {
      clearTimeout(writeTimer);
      writeTimer = null;
    }
    if (!isStorageAvailable()) return;
    try {
      chrome.storage.local.remove([STORAGE_KEY], () => {
        if (chrome.runtime && chrome.runtime.lastError) {
          console.warn(
            "[sidebar-view-state] clear failed:",
            chrome.runtime.lastError.message
          );
        }
      });
    } catch (e) {
      console.warn("[sidebar-view-state] clear threw:", e);
    }
  }

  root.TV.sidebarViewState = {
    STORAGE_KEY,
    init,
    save,
    getSnapshot,
    clear,
    VALID_PANELS,
    VALID_SESSION_TABS,
  };
})();
