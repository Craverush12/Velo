/**
 * Essence capture bootstrap (Sidebar_extension).
 * Loaded after platform extractor + essence-smart-trigger on ChatGPT / Claude / Gemini.
 * Extractors auto-track DOM when CONFIG.AUTO_TRACK is true.
 */
(function () {
  "use strict";

  var platform = "unknown";
  if (window.VelocityChatGPTExtractor) platform = "chatgpt";
  else if (window.VelocityClaudeExtractor) platform = "claude";
  else if (window.VelocityGeminiExtractor) platform = "gemini";

  var d = globalThis.VelocitySidebarDebug;
  if (d) {
    d.boot("essence pipeline ready", { platform: platform });
  } else {
    console.log(
      "[Velocity Sidebar] essence extractors on",
      platform,
      "(MAIN world)"
    );
  }

  if (platform !== "unknown") {
    try {
      window.postMessage(
        {
          type: "VELOCITY_ESSENCE_READY",
          platform,
          at: Date.now(),
        },
        "*"
      );
    } catch (e) {
      /* ignore */
    }
  }
})();
