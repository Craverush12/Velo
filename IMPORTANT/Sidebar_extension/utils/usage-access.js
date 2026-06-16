/**
 * Free-tier usage helpers (aligned with Vel-Next chat `canConsumeUsageNow`).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  function normalizeStatus(raw) {
    if (root.TV.subscriptionAccess && typeof root.TV.subscriptionAccess.normalizeSubscriptionStatus === "function") {
      return root.TV.subscriptionAccess.normalizeSubscriptionStatus(raw);
    }
    if (raw == null || raw === undefined) return "";
    return String(raw).trim().toLowerCase().replace(/-/g, "_");
  }

  function parseUsageCount(raw, fallback) {
    const n = Number(raw);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(0, n);
  }

  /** Paid Pro plan — API should keep remainingUsage > 0; still gate on count like chat page. */
  function isPaidProPlan(subscriptionStatus) {
    return normalizeStatus(subscriptionStatus) === "pro";
  }

  function isUsageExhausted(snapshot) {
    const s = snapshot || {};
    if (!s.isLoggedIn) return false;
    if (isPaidProPlan(s.subscriptionStatus)) return false;
    const remaining = s.remainingUsage;
    if (remaining === undefined || remaining === null) return false;
    return parseUsageCount(remaining, 0) <= 0;
  }

  function canConsumeUsage(snapshot) {
    if (!snapshot || !snapshot.isLoggedIn) return true;
    return !isUsageExhausted(snapshot);
  }

  function decrementRemainingUsage(remainingUsage) {
    return Math.max(0, parseUsageCount(remainingUsage, 0) - 1);
  }

  function buildUsageFieldsFromStatusData(data) {
    const status =
      data && data.status != null && data.status !== undefined ? String(data.status) : "free";
    const usageLimit = parseUsageCount(
      data && data.usageLimit !== undefined ? data.usageLimit : undefined,
      10
    );
    const remainingUsage = parseUsageCount(
      data && data.remainingUsage !== undefined ? data.remainingUsage : undefined,
      usageLimit
    );
    return { status, usageLimit, remainingUsage };
  }

  root.TV.usageAccess = {
    normalizeStatus,
    parseUsageCount,
    isPaidProPlan,
    isUsageExhausted,
    canConsumeUsage,
    decrementRemainingUsage,
    buildUsageFieldsFromStatusData,
  };
})();
