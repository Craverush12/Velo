/**
 * Host-page debug logging for Sidebar_extension (ChatGPT, Claude, Gemini, etc.).
 * Always prints boot line; verbose logs when localStorage.velocity_sidebar_debug === "1".
 * @global VelocitySidebarDebug
 */
(function () {
  "use strict";

  const PREFIX = "[Velocity Sidebar]";
  const STORAGE_KEY = "velocity_sidebar_debug";

  function isVerbose() {
    try {
      return localStorage.getItem(STORAGE_KEY) === "1";
    } catch (_) {
      return false;
    }
  }

  function logAlways() {
    console.log.apply(console, [PREFIX].concat(Array.prototype.slice.call(arguments)));
  }

  function logVerbose() {
    if (!isVerbose()) return;
    console.log.apply(console, [PREFIX].concat(Array.prototype.slice.call(arguments)));
  }

  function warn() {
    console.warn.apply(console, [PREFIX].concat(Array.prototype.slice.call(arguments)));
  }

  function logError() {
    console.error.apply(console, [PREFIX].concat(Array.prototype.slice.call(arguments)));
  }

  globalThis.VelocitySidebarDebug = {
    PREFIX,
    STORAGE_KEY,
    isVerbose,
    log: logVerbose,
    boot: logAlways,
    warn,
    error: logError,
    enableVerbose() {
      try {
        localStorage.setItem(STORAGE_KEY, "1");
        logAlways("Verbose debug enabled — reload the page");
      } catch (e) {
        warn("Could not enable debug:", e);
      }
    },
    logRuntimeMessage(action, response, err) {
      if (err) {
        logError(action + " failed:", err.message || err);
        return;
      }
      if (isVerbose()) {
        logVerbose(action + " ok", response);
      } else if (response && response.success === false) {
        logError(action + " rejected:", response);
      }
    },
  };

  logAlways(
    "content script loaded on",
    location.hostname,
    "— open this tab's DevTools → Console (not the extension service worker).",
    "Verbose:",
    "localStorage.setItem('" + STORAGE_KEY + "', '1') then reload."
  );
})();
