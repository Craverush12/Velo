/**
 * Subscription tier helpers (aligned with Vel-Next enhancementModeAccess.js).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const PRO_STATUSES = new Set([
    "pro",
    "freetrial",
    "free_trial",
    "pro_trial",
    "protrial",
  ]);

  function normalizeSubscriptionStatus(raw) {
    if (raw == null || raw === undefined) return "";
    return String(raw).trim().toLowerCase().replace(/-/g, "_");
  }

  function hasProGoldChrome(subscriptionStatus) {
    const s = normalizeSubscriptionStatus(subscriptionStatus);
    return s ? PRO_STATUSES.has(s) : false;
  }

  function isPaidProPlan(subscriptionStatus) {
    return normalizeSubscriptionStatus(subscriptionStatus) === "pro";
  }

  function canUseProEnhancementModes(subscriptionStatus) {
    return hasProGoldChrome(subscriptionStatus);
  }

  /** Maps API mode values to allowed mode when subscription is free. */
  function clampEnhancementModeForSubscription(apiMode, subscriptionStatus) {
    if (canUseProEnhancementModes(subscriptionStatus)) return apiMode || "standard";
    const m = String(apiMode || "standard").toLowerCase();
    if (m === "media" || m === "best") return "standard";
    return m || "standard";
  }

  function getSubscriptionTierMeta(subscriptionStatus) {
    const s = normalizeSubscriptionStatus(subscriptionStatus);
    const isGold = hasProGoldChrome(subscriptionStatus);
    const isPaid = isPaidProPlan(subscriptionStatus);
    let theme = "guest";
    let label = "";
    let profileTitle = "Velocity";
    if (s === "pro") {
      theme = "pro";
      label = "Pro";
      profileTitle = "Velocity Pro";
    } else if (s === "freetrial" || s === "free_trial" || s === "pro_trial" || s === "protrial") {
      theme = "pro";
      label = "Pro trial";
      profileTitle = "Velocity Pro trial";
    } else if (s === "free" || s) {
      theme = "free";
      label = s === "free" ? "Free" : "";
      profileTitle = "Velocity Free";
    }
    return {
      status: s,
      theme,
      label,
      profileTitle,
      isGoldChrome: isGold,
      isPaidPro: isPaid,
      canUseProModes: isGold,
    };
  }

  function canAccessLibraryPrompt(prompt, isProUser) {
    if (!prompt || !prompt.isProOnly) return true;
    return Boolean(isProUser);
  }

  /** Text safe to place in composer / send to enhance — empty when Pro-locked. */
  function getUsablePromptText(prompt, isProUser) {
    if (!canAccessLibraryPrompt(prompt, isProUser)) return "";
    return String((prompt && (prompt.prompt || prompt.short_prompt)) || "").trim();
  }

  /** Strip prompt bodies so locked Pro content is not left in DOM/state. */
  function sanitizePromptForViewer(prompt, isProUser) {
    if (!prompt || canAccessLibraryPrompt(prompt, isProUser)) return prompt;
    return {
      ...prompt,
      prompt: "",
      short_prompt: "",
    };
  }

  root.TV.subscriptionAccess = {
    normalizeSubscriptionStatus,
    hasProGoldChrome,
    isPaidProPlan,
    canUseProEnhancementModes,
    clampEnhancementModeForSubscription,
    getSubscriptionTierMeta,
    canAccessLibraryPrompt,
    getUsablePromptText,
    sanitizePromptForViewer,
  };
})();
