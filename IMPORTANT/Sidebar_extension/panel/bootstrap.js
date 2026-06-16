/**
 * Side panel entry: picks `panel/consumer/sidebar.html` vs `panel/enterprise/sidebar.html`
 * from chrome.storage (TV.STORAGE_KEYS.SIDEBAR_FLOW).
 */
(function () {
  const TV = typeof globalThis !== "undefined" ? globalThis.TV : null;
  const key =
    TV && TV.STORAGE_KEYS && TV.STORAGE_KEYS.SIDEBAR_FLOW
      ? TV.STORAGE_KEYS.SIDEBAR_FLOW
      : "velocity_sidebar_flow";
  const normalize =
    TV && typeof TV.normalizeSidebarFlow === "function"
      ? TV.normalizeSidebarFlow.bind(TV)
      : function (raw) {
          const v = (raw == null ? "" : String(raw)).toLowerCase().trim();
          return v === "enterprise" ? "enterprise" : "consumer";
        };

  chrome.storage.local.get([key], (result) => {
    if (chrome.runtime.lastError) {
      const el = document.getElementById("bootMsg");
      if (el) el.textContent = "Could not read storage.";
      return;
    }
    const flow = normalize(result[key]);
    const url = chrome.runtime.getURL(`panel/${flow}/sidebar.html`);
    window.location.replace(url);
  });
})();
