/**
 * Enterprise history view — renders a list of past enhanced prompts.
 * Exposes TV.enterpriseHistoryView.mount(container, { onSelectPrompt, onBack }).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  /**
   * Mount the history view into `container`.
   * @param {HTMLElement} container
   * @param {{ onSelectPrompt: function, onBack: function }} callbacks
   */
  function mount(container, callbacks) {
    if (!container) return;
    container.innerHTML = "";
    const wrap = document.createElement("div");
    wrap.className = "ent-history-view";
    wrap.innerHTML = `
      <div class="ent-history-header">
        <button type="button" class="ent-link ent-link--btn" id="entHistBack">← Back</button>
        <h3 class="ent-history-title">Prompt History</h3>
      </div>
      <div class="ent-history-list" id="entHistList">
        <p class="ent-history-status">Loading…</p>
      </div>
    `;
    container.appendChild(wrap);

    wrap.querySelector("#entHistBack").addEventListener("click", () => {
      if (callbacks && typeof callbacks.onBack === "function") callbacks.onBack();
    });

    // Fetch history via background handler.
    chrome.runtime.sendMessage({ action: "TV_ENTERPRISE_GET_HISTORY" }, (response) => {
      const list = wrap.querySelector("#entHistList");
      if (!list) return;
      if (chrome.runtime.lastError || !response || !response.success) {
        list.innerHTML = `<p class="ent-history-status">Could not load history. Try again later.</p>`;
        return;
      }
      const prompts = (response.data && response.data.prompts) || [];
      if (!prompts.length) {
        list.innerHTML = `<p class="ent-history-status">No history yet. Enhance a prompt to get started.</p>`;
        return;
      }
      list.innerHTML = "";
      prompts.forEach(function (p) {
        const text   = p.originalPrompt || p.enhanced_prompt || p.enhancedPrompt || "";
        const date   = p.createdAt || p.created_at || "";
        const preview = text.slice(0, 90) + (text.length > 90 ? "…" : "");
        const dateStr = date ? new Date(date).toLocaleDateString() : "";
        const item = document.createElement("button");
        item.type = "button";
        item.className = "ent-history-item";
        item.innerHTML =
          `<span class="ent-history-item-text">${_esc(preview)}</span>` +
          (dateStr ? `<span class="ent-history-item-date">${_esc(dateStr)}</span>` : "");
        item.addEventListener("click", function () {
          if (callbacks && typeof callbacks.onSelectPrompt === "function") {
            callbacks.onSelectPrompt(text);
          }
        });
        list.appendChild(item);
      });
    });
  }

  function _esc(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  root.TV.enterpriseHistoryView = { mount };
})();
