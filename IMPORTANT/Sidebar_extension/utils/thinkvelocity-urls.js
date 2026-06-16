/**
 * Tracked ThinkVelocity URLs — same query contract as Extension-new/background.js
 * (`buildTrackedThinkVelocityUrl`). Used for profile, library, etc.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  function sanitizeTrackingValue(value, fallback) {
    if (!value || typeof value !== "string") return fallback;
    const cleaned = value.trim().toLowerCase().replace(/[^a-z0-9_-]/g, "_");
    return cleaned || fallback;
  }

  /**
   * @param {string} path - Absolute path on thinkvelocity.in, e.g. "/profile?tab=profile"
   * @param {{ platform?: string, campaign?: string, content?: string }} options
   */
  function buildThinkVelocityUrl(path, options) {
    const opt = options || {};
    const platform = opt.platform != null ? opt.platform : "unknown";
    const campaign = opt.campaign != null ? opt.campaign : "platform_tracking";
    const content = opt.content != null ? opt.content : "extension_navigation";

    const url = new URL(path, "https://thinkvelocity.in");
    url.searchParams.set("source", "extension");
    url.searchParams.set("utm_source", "extension");
    url.searchParams.set("utm_medium", "chrome_extension");
    url.searchParams.set("utm_campaign", sanitizeTrackingValue(campaign, "platform_tracking"));
    url.searchParams.set("utm_term", sanitizeTrackingValue(platform, "unknown"));
    url.searchParams.set("utm_content", sanitizeTrackingValue(content, "extension_navigation"));
    url.searchParams.set("tv_platform", sanitizeTrackingValue(platform, "unknown"));
    return url.toString();
  }

  /**
   * @param {string} path - Must start with "/" and must not start with "//" (open redirect guard).
   */
  function isSafeHostedPath(path) {
    if (!path || typeof path !== "string") return false;
    if (!path.startsWith("/")) return false;
    if (path.startsWith("//")) return false;
    if (path.length > 512) return false;
    if (/[\s<>"'`]/.test(path)) return false;
    return true;
  }

  root.TV.thinkvelocityUrls = {
    buildThinkVelocityUrl,
    isSafeHostedPath,
  };
})();
