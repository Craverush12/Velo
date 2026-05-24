/**
 * Enterprise enhance view — renders guardrail outcome overlays.
 * Exposes TV.enterpriseEnhanceView.showOutcome(container, outcome).
 * Returns Promise<{ action: "proceed"|"cancel", redactedPrompt?: string }>.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  /**
   * Render a guardrail outcome overlay in `container` and wait for user action.
   *
   * @param {HTMLElement} container   - element to render into (clears on resolve/reject)
   * @param {object} outcomeData
   * @param {string} outcomeData.code - ENT_GUARDRAIL_WARN | ENT_GUARDRAIL_CONFIRM |
   *                                    ENT_GUARDRAIL_REDACT | ENT_GUARDRAIL_BLOCK |
   *                                    ENT_GUARDRAIL_APPROVAL
   * @param {object} outcomeData.guardrail - raw guardrail response from server
   * @returns {Promise<{ action: "proceed"|"cancel", redactedPrompt?: string }>}
   *   BLOCK and APPROVAL always resolve with action = "cancel" (terminal — no proceed).
   */
  function showOutcome(container, outcomeData) {
    return new Promise((resolve) => {
      container.innerHTML = "";
      const { code, guardrail } = outcomeData;
      const g = guardrail || {};
      const violations = Array.isArray(g.violations) ? g.violations : [];
      const violationText = violations.length
        ? violations.map((v) => v.description || v.rule || String(v)).join("; ")
        : "Policy violation detected.";

      const overlay = document.createElement("div");
      overlay.className = "ent-guardrail-overlay";

      function done(action, extra) {
        container.innerHTML = "";
        resolve(Object.assign({ action }, extra || {}));
      }

      if (code === "ENT_GUARDRAIL_WARN") {
        overlay.innerHTML = `
          <div class="ent-guardrail-card ent-guardrail-card--warn">
            <div class="ent-guardrail-icon">⚠</div>
            <h3 class="ent-guardrail-title">Warning</h3>
            <p class="ent-guardrail-body">${_esc(violationText)}</p>
            <p class="ent-guardrail-sub">You can still proceed, but this prompt may violate policy.</p>
            <div class="ent-guardrail-actions">
              <button class="ent-btn ent-btn--ghost" id="entGrCancel">Cancel</button>
              <button class="ent-btn ent-btn--primary" id="entGrProceed">Proceed anyway</button>
            </div>
          </div>`;
        container.appendChild(overlay);
        overlay.querySelector("#entGrProceed").addEventListener("click", () => done("proceed"));
        overlay.querySelector("#entGrCancel").addEventListener("click", () => done("cancel"));

      } else if (code === "ENT_GUARDRAIL_CONFIRM") {
        overlay.innerHTML = `
          <div class="ent-guardrail-card ent-guardrail-card--confirm">
            <div class="ent-guardrail-icon">🔒</div>
            <h3 class="ent-guardrail-title">Confirmation required</h3>
            <p class="ent-guardrail-body">${_esc(violationText)}</p>
            <p class="ent-guardrail-sub">Please confirm you want to send this prompt.</p>
            <div class="ent-guardrail-actions">
              <button class="ent-btn ent-btn--ghost" id="entGrCancel">Cancel</button>
              <button class="ent-btn ent-btn--primary" id="entGrConfirm">Confirm</button>
            </div>
          </div>`;
        container.appendChild(overlay);
        overlay.querySelector("#entGrConfirm").addEventListener("click", () => done("proceed"));
        overlay.querySelector("#entGrCancel").addEventListener("click", () => done("cancel"));

      } else if (code === "ENT_GUARDRAIL_REDACT") {
        const redacted = g.redactedPrompt || "";
        overlay.innerHTML = `
          <div class="ent-guardrail-card ent-guardrail-card--redact">
            <div class="ent-guardrail-icon">✂</div>
            <h3 class="ent-guardrail-title">Sensitive content removed</h3>
            <p class="ent-guardrail-sub">The following redacted version will be enhanced:</p>
            <div class="ent-redacted-preview">${_esc(redacted || "(redacted prompt)")}</div>
            <div class="ent-guardrail-actions">
              <button class="ent-btn ent-btn--ghost" id="entGrCancel">Cancel</button>
              <button class="ent-btn ent-btn--primary" id="entGrEnhance">Enhance with redacted</button>
            </div>
          </div>`;
        container.appendChild(overlay);
        overlay.querySelector("#entGrEnhance").addEventListener("click", () =>
          done("proceed", { redactedPrompt: redacted })
        );
        overlay.querySelector("#entGrCancel").addEventListener("click", () => done("cancel"));

      } else if (code === "ENT_GUARDRAIL_BLOCK") {
        overlay.innerHTML = `
          <div class="ent-guardrail-card ent-guardrail-card--block">
            <div class="ent-guardrail-icon">🚫</div>
            <h3 class="ent-guardrail-title">Prompt blocked</h3>
            <p class="ent-guardrail-body">${_esc(violationText)}</p>
            <p class="ent-guardrail-sub">This prompt violates company policy and cannot be enhanced.</p>
            <div class="ent-guardrail-actions">
              <button class="ent-btn ent-btn--primary" id="entGrBack">Back to composer</button>
            </div>
          </div>`;
        container.appendChild(overlay);
        overlay.querySelector("#entGrBack").addEventListener("click", () => done("cancel"));

      } else if (code === "ENT_GUARDRAIL_APPROVAL") {
        overlay.innerHTML = `
          <div class="ent-guardrail-card ent-guardrail-card--approval">
            <div class="ent-guardrail-icon">📋</div>
            <h3 class="ent-guardrail-title">Sent for admin review</h3>
            <p class="ent-guardrail-sub">
              Your prompt requires administrator approval before it can be enhanced.
              You will be notified when it is reviewed.
            </p>
            <div class="ent-guardrail-actions">
              <button class="ent-btn ent-btn--primary" id="entGrBack">Back to composer</button>
            </div>
          </div>`;
        container.appendChild(overlay);
        overlay.querySelector("#entGrBack").addEventListener("click", () => done("cancel"));

      } else {
        // Unknown guardrail code — show generic error.
        overlay.innerHTML = `
          <div class="ent-guardrail-card ent-guardrail-card--block">
            <h3 class="ent-guardrail-title">Cannot enhance</h3>
            <p class="ent-guardrail-body">${_esc(code)}</p>
            <div class="ent-guardrail-actions">
              <button class="ent-btn ent-btn--primary" id="entGrBack">Back</button>
            </div>
          </div>`;
        container.appendChild(overlay);
        overlay.querySelector("#entGrBack").addEventListener("click", () => done("cancel"));
      }
    });
  }

  function _esc(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  root.TV.enterpriseEnhanceView = { showOutcome };
})();
