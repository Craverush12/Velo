/**
 * Single source of truth for chrome.storage.local keys used by auth.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};
  root.TV.STORAGE_KEYS = {
    ACCESS_TOKEN: "accessToken",
    REFRESH_TOKEN: "refreshToken",
    ACCESS_EXP: "accessTokenExpiresAt",
    REFRESH_EXP: "refreshTokenExpiresAt",
    USER_NAME: "userName",
    USER_ID: "userId",
    USER_EMAIL: "userEmail",
    FREE_USER: "FreeUser",
    SUBSCRIPTION_STATUS: "subscriptionStatus",
    SUBSCRIPTION_STATUS_AT: "subscriptionStatusFetchedAt",
    REMAINING_USAGE: "remainingUsage",
    USAGE_LIMIT: "usageLimit",
    ENVIRONMENT: "environment",
    API_BASE: "apiBase",
    /**
     * One-shot anonymous enhancement entitlement. Set to `true` the first time
     * an unauthenticated caller successfully completes an enhance via the
     * injected popup modal. Read by both `features/consumer-enhance-flow.js`
     * (background) and `button/js/injection-modal.js` (content script) to
     * decide whether to allow the call or render the sign-in wall instead.
     */
    GUEST_FREE_USED: "velocity_guest_free_used",
    /** Which side-panel flow to load: `consumer` | `enterprise` (see `core/sidebar-flow.js`). */
    SIDEBAR_FLOW: "velocity_sidebar_flow",
    /** Set when ContextEngine successfully stores essence (ms timestamp). */
    ESSENCE_LAST_STORED_AT: "velocity_essence_last_stored_at",
    ESSENCE_LAST_SESSION: "velocity_essence_last_session",
    /**
     * chrome.storage.local mirror of the most recent successful extraction.
     * Shape: { platform, chatId, sessionId, messageCount, title, url, syncedAt }
     * Allows the side panel to read recent extraction info without crawling page localStorage.
     */
    LAST_EXTRACTED_SUMMARY: "velocity_last_extracted_summary",
    /**
     * Per-platform mirror keyed by host: chatgpt | claude | gemini.
     * Shape: { [platform]: { chatId, sessionId, messageCount, title, url, syncedAt } }
     */
    EXTRACTED_BY_PLATFORM: "velocity_extracted_by_platform",
    // ── Enterprise (B2B) session ──────────────────────────────────────────────
    /** JWT issued by /backend/auth/login (15-min expiry). */
    ENT_ACCESS_TOKEN: "ent_accessToken",
    ENT_REFRESH_TOKEN: "ent_refreshToken",
    /** ms timestamp: Date.now() + expiresIn * 1000. */
    ENT_ACCESS_EXP: "ent_accessTokenExpiresAt",
    ENT_USER_ID: "ent_userId",
    ENT_ENTERPRISE_ID: "ent_enterpriseId",
    ENT_USER_NAME: "ent_userName",
    ENT_USER_EMAIL: "ent_userEmail",
    ENT_ROLE_TYPES: "ent_roleTypes",
    /**
     * Persisted when guardrail returns REQUIRE_APPROVAL.
     * Shape: { queueId: string, promptExcerpt: string, submittedAt: number } | null
     */
    ENT_PENDING_APPROVAL: "ent_pendingApproval",
    /**
     * Page-localStorage keys that the in-tab extractors write to (MAIN world).
     * Listed here for reference; they are not chrome.storage keys.
     */
    PAGE_LOCAL_KEYS: {
      CHATGPT_SESSION: "velocity_chatgpt_session",
      CLAUDE_SESSION: "velocity_Claude_session",
      GEMINI_SESSION: "velocity_gemini_session",
      SMART_TRIGGER_STATE: "smartTriggerState",
    },
  };
})();
