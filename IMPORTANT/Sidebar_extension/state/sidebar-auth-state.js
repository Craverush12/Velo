/**
 * Side panel auth UI state: cache + subscribe; server truth lives in background + chrome.storage.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  let snapshot = {
    isLoggedIn: false,
    userId: "",
    userEmail: "",
    userName: "",
    subscriptionStatus: "free",
    remainingUsage: null,
    usageLimit: null,
    isUsageExhausted: false,
    isProUser: false,
    /** @type {string} mirrors TV.SidebarFlow; default until snapshot loads */
    sidebarFlow: "consumer",
    loading: true,
    error: null,
  };
  const listeners = [];

  function notify() {
    listeners.forEach((fn) => {
      try {
        fn({ ...snapshot });
      } catch (e) {}
    });
  }

  function sendAuthMessage(action, payload) {
    const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ action, payload: payload || {}, requestId }, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        resolve(response);
      });
    });
  }

  function applyUsageExhaustedFlag(next) {
    const acc = root.TV && root.TV.usageAccess;
    if (acc && typeof acc.isUsageExhausted === "function") {
      next.isUsageExhausted = acc.isUsageExhausted(next);
    } else {
      next.isUsageExhausted = Boolean(
        next.isLoggedIn &&
          next.remainingUsage !== undefined &&
          next.remainingUsage !== null &&
          Number(next.remainingUsage) <= 0
      );
    }
    return next;
  }

  root.TV.sidebarAuthState = {
    getSnapshot() {
      return { ...snapshot };
    },

    subscribe(fn) {
      listeners.push(fn);
      return () => {
        const i = listeners.indexOf(fn);
        if (i >= 0) listeners.splice(i, 1);
      };
    },

    async refresh(options) {
      const o = options || {};
      snapshot.loading = true;
      snapshot.error = null;
      notify();
      try {
        const response = await sendAuthMessage("TV_AUTH_GET_SNAPSHOT", {
          force: Boolean(o.force),
        });
        if (response && response.success && response.data) {
          snapshot = applyUsageExhaustedFlag({
            ...snapshot,
            ...response.data,
            loading: false,
            error: null,
          });
        } else {
          const err = response && response.error;
          snapshot.loading = false;
          snapshot.error =
            (err && err.message) || (typeof err === "string" ? err : "Failed to load auth state");
        }
      } catch (e) {
        snapshot.loading = false;
        snapshot.error = e.message || String(e);
      }
      notify();
      return { ...snapshot };
    },

    async logout() {
      snapshot.loading = true;
      notify();
      try {
        const response = await sendAuthMessage("TV_AUTH_LOGOUT", {});
        if (response && response.success && response.data) {
          snapshot = applyUsageExhaustedFlag({
            ...snapshot,
            ...response.data,
            loading: false,
            error: null,
          });
        } else {
          snapshot.loading = false;
          snapshot.error = "Logout failed";
        }
      } catch (e) {
        snapshot.loading = false;
        snapshot.error = e.message || String(e);
      }
      notify();
      return { ...snapshot };
    },

    /**
     * Opens ThinkVelocity login in a new tab and records which side-panel line the user is
     * entering (consumer = B2C reference UI; enterprise = B2B shell). Defaults to **consumer**.
     * @param {{ intendedSidebarFlow?: string }} [options]
     */
    async openLoginTab(options) {
      const o = options || {};
      const rootTv = typeof globalThis !== "undefined" ? globalThis.TV : null;
      const fallback =
        rootTv && rootTv.SidebarFlow ? rootTv.SidebarFlow.CONSUMER : "consumer";
      const intended =
        o.intendedSidebarFlow != null && String(o.intendedSidebarFlow).trim() !== ""
          ? o.intendedSidebarFlow
          : fallback;
      await sendAuthMessage("TV_AUTH_OPEN_LOGIN", { intendedSidebarFlow: intended });
    },

    /**
     * Open a path on thinkvelocity.in in a new tab (tracked URL; same pattern as Extension-new).
     * @param {string} path - e.g. "/profile?tab=profile"
     * @param {string} [utmContent] - utm_content value
     */
    async openHostedPage(path, utmContent) {
      return sendAuthMessage("TV_OPEN_HOSTED_PAGE", {
        path,
        utmContent: utmContent || "sidebar_navigation",
        platform: "sidebar",
      });
    },

    /** Optimistic local decrement after a successful enhance (mirrors chat `consumeOneUsageLocally`). */
    consumeOneUsageLocally() {
      if (!snapshot.isLoggedIn) return { ...snapshot };
      if (snapshot.remainingUsage === undefined || snapshot.remainingUsage === null) {
        return { ...snapshot };
      }
      const acc = root.TV && root.TV.usageAccess;
      const nextRemaining =
        acc && typeof acc.decrementRemainingUsage === "function"
          ? acc.decrementRemainingUsage(snapshot.remainingUsage)
          : Math.max(0, Number(snapshot.remainingUsage || 0) - 1);
      snapshot = applyUsageExhaustedFlag({
        ...snapshot,
        remainingUsage: nextRemaining,
      });
      notify();
      return { ...snapshot };
    },

    canConsumeUsage() {
      const acc = root.TV && root.TV.usageAccess;
      if (acc && typeof acc.canConsumeUsage === "function") {
        return acc.canConsumeUsage(snapshot);
      }
      return !snapshot.isUsageExhausted;
    },
  };
})();
