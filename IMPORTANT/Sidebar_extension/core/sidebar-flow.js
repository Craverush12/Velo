/**
 * Side panel product line: consumer vs enterprise (different UI + APIs later).
 * Persisted under TV.STORAGE_KEYS.SIDEBAR_FLOW.
 * - **Consumer** = B2C reference UI (`panel/consumer/`). Opening login from that panel sets this to `consumer`.
 * - **Enterprise** = B2B shell (`panel/enterprise/`). Opening login from there sets `enterprise`.
 * Website can also set `sidebarFlow` on `storeUserData` or `localStorage.velocitySidebarFlow` via login-bridge.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  root.TV.SidebarFlow = {
    CONSUMER: "consumer",
    ENTERPRISE: "enterprise",
  };

  /**
   * @param {unknown} raw
   * @returns {"consumer"|"enterprise"}
   */
  root.TV.normalizeSidebarFlow = function normalizeSidebarFlow(raw) {
    const v = (raw == null ? "" : String(raw)).toLowerCase().trim();
    if (v === root.TV.SidebarFlow.ENTERPRISE || v === "org" || v === "b2b") {
      return root.TV.SidebarFlow.ENTERPRISE;
    }
    return root.TV.SidebarFlow.CONSUMER;
  };

  /**
   * Four-state session machine. `SWITCHING` is transient in-memory only —
   * never persisted to chrome.storage. All other states may be derived from
   * storage and are recalculated on each service-worker startup.
   */
  root.TV.EntSessionState = {
    CONSUMER_ONLY:    "consumer_only",
    ENTERPRISE_ONLY:  "enterprise_only",
    BOTH_ACTIVE:      "both_active",
    SWITCHING:        "switching",
  };

  /**
   * Derive the current session state from which token sets exist.
   * @param {boolean} hasConsumerSession  consumer accessToken or refreshToken present
   * @param {boolean} hasEnterpriseSession enterprise ent_accessToken or ent_refreshToken present
   * @returns {"consumer_only"|"enterprise_only"|"both_active"}
   */
  root.TV.computeSessionState = function computeSessionState(hasConsumerSession, hasEnterpriseSession) {
    if (hasConsumerSession && hasEnterpriseSession) return root.TV.EntSessionState.BOTH_ACTIVE;
    if (hasEnterpriseSession)                       return root.TV.EntSessionState.ENTERPRISE_ONLY;
    return root.TV.EntSessionState.CONSUMER_ONLY;
  };
})();
