/**
 * Injection Pro theme — content-script feature.
 *
 * Responsibility:
 *   Mirror the sidebar's Pro/free theme toggle on the on-page injection bar
 *   and the draggable enhancement popup. When the signed-in user is Pro, this
 *   feature toggles a single `is-pro` class on every registered root element.
 *   CSS in `injection-button.css` and `injection-modal.css` scopes gold
 *   accents to that class.
 *
 * Boundaries (per extension-architecture-js-only skill):
 *   - Content-script only. No DOM rendering. No API calls outside the
 *     existing TV_AUTH_GET_SNAPSHOT message contract.
 *   - Storage reads go through a single onChanged listener; nobody writes
 *     here.
 *   - Exposes one global namespace: `globalThis.VelocityInjectionProTheme`.
 */
(function () {
  "use strict";

  const POLL_BACKOFF_MS = 4000;
  const STORAGE_WATCH_KEYS = [
    "accessToken",
    "refreshToken",
    "userId",
    "subscription_status",
    "subscriptionStatus",
    "isProUser",
  ];

  let cachedIsPro = false;
  let initialized = false;
  let inflight = null;
  let lastFetchedAt = 0;
  const registered = new WeakSet();
  const elements = new Set();
  const listeners = new Set();

  function dbg() {
    return globalThis.VelocitySidebarDebug || null;
  }

  function sendSnapshotRequest() {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(
          {
            action: "TV_AUTH_GET_SNAPSHOT",
            requestId: "vipt-" + Date.now(),
            payload: { force: false },
          },
          (res) => {
            const lastError = chrome.runtime.lastError;
            if (lastError || !res || res.success === false) {
              resolve(null);
              return;
            }
            resolve(res.data || null);
          }
        );
      } catch (_) {
        resolve(null);
      }
    });
  }

  function deriveIsProFromSnapshot(snapshot) {
    if (!snapshot || typeof snapshot !== "object") return false;
    if (!snapshot.isLoggedIn) return false;
    return Boolean(snapshot.isProUser);
  }

  function applyClassToAll() {
    elements.forEach((el) => {
      if (!el || !el.isConnected) {
        elements.delete(el);
        return;
      }
      el.classList.toggle("is-pro", cachedIsPro);
    });
  }

  function notifyListeners() {
    listeners.forEach((fn) => {
      try {
        fn(cachedIsPro);
      } catch (e) {
        const d = dbg();
        if (d) d.warn("[injection-pro-theme] listener error:", e);
      }
    });
  }

  function setIsPro(next) {
    const value = Boolean(next);
    if (value === cachedIsPro) {
      // Re-apply anyway — newly registered nodes need the current state.
      applyClassToAll();
      return;
    }
    cachedIsPro = value;
    applyClassToAll();
    notifyListeners();
  }

  async function refresh(options) {
    const opts = options || {};
    const force = Boolean(opts.force);
    if (!force && Date.now() - lastFetchedAt < POLL_BACKOFF_MS && inflight) {
      return inflight;
    }
    if (inflight) return inflight;
    inflight = (async () => {
      try {
        const snapshot = await sendSnapshotRequest();
        lastFetchedAt = Date.now();
        setIsPro(deriveIsProFromSnapshot(snapshot));
      } finally {
        inflight = null;
      }
    })();
    return inflight;
  }

  function watchStorage() {
    if (!chrome || !chrome.storage || !chrome.storage.onChanged) return;
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "local") return;
      const hit = STORAGE_WATCH_KEYS.some((k) => Object.prototype.hasOwnProperty.call(changes, k));
      if (!hit) return;
      void refresh({ force: true });
    });
  }

  function register(el) {
    if (!el || registered.has(el)) return;
    registered.add(el);
    elements.add(el);
    el.classList.toggle("is-pro", cachedIsPro);
  }

  function unregister(el) {
    if (!el) return;
    elements.delete(el);
    registered.delete(el);
    el.classList.remove("is-pro");
  }

  function subscribe(fn) {
    if (typeof fn !== "function") return () => {};
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  function init() {
    if (initialized) return;
    initialized = true;
    watchStorage();
    void refresh({ force: true });
  }

  globalThis.VelocityInjectionProTheme = {
    init,
    register,
    unregister,
    subscribe,
    refresh,
    getIsPro() {
      return cachedIsPro;
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
