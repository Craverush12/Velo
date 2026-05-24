/**
 * Enterprise enhance pipeline (service-worker module, loaded via importScripts).
 * Exposes TV.enterpriseEnhanceFlow.run(prompt, opts).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const ENT_BASE = "https://velocityenterprise.toteminteractive.in";

  /**
   * Read the guardrail decision for a prompt.
   * @param {string} prompt
   * @param {string} accessToken
   * @param {string} enterpriseId
   * @returns {Promise<{allowed,decision,queueId,violations,redactedPrompt}>}
   */
  async function checkGuardrail(prompt, accessToken, enterpriseId) {
    const res = await fetch(`${ENT_BASE}/backend/guardrail/check-prompt`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ prompt, contentType: "CHAT_PROMPT", enterpriseId }),
    });
    if (!res.ok) {
      const msg = await res.text().catch(() => "");
      throw new Error(`Guardrail check failed: ${res.status} ${msg}`);
    }
    return res.json();
  }

  /**
   * Call the enterprise enhance SSE endpoint and accumulate the full text.
   * @param {string} prompt
   * @param {string} accessToken
   * @param {string} enterpriseId
   * @param {string} userId
   * @returns {Promise<string>} the full enhanced text
   */
  async function streamEnhance(prompt, accessToken, enterpriseId, userId) {
    const res = await fetch(`${ENT_BASE}/prompt/enhance/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ prompt, enterpriseId, userId }),
    });
    if (!res.ok) {
      const msg = await res.text().catch(() => "");
      throw new Error(`Enterprise enhance failed: ${res.status} ${msg}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let accumulated = "";
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        const jsonPart = trimmed.slice("data:".length).trimStart();
        if (!jsonPart || jsonPart === "[DONE]") continue;
        try {
          const data = JSON.parse(jsonPart);
          if (data.type === "content" && data.chunk) accumulated += data.chunk;
          if (data.type === "complete" && data.enhanced_prompt) {
            accumulated = data.enhanced_prompt;
          }
        } catch (_) {}
      }
    }
    if (buffer.trim()) {
      try {
        const data = JSON.parse(buffer.trim().replace(/^data:\s*/, ""));
        if (data.type === "complete" && data.enhanced_prompt) accumulated = data.enhanced_prompt;
      } catch (_) {}
    }
    return accumulated.trim();
  }

  /**
   * Main entry point.
   *
   * opts.skipGuardrail = true  →  skip guardrail check (user already acknowledged),
   *                                used when panel re-calls after WARN/CONFIRM/REDACT.
   * opts.useRedacted = string  →  enhance this text instead of original prompt
   *                                (used after REDACT outcome).
   *
   * Returns:
   *   { success: true, data: { enhancedText, guardrail: null } }
   *   { success: false, code: "ENT_GUARDRAIL_WARN", guardrail: {...} }
   *   { success: false, code: "ENT_GUARDRAIL_CONFIRM", guardrail: {...} }
   *   { success: false, code: "ENT_GUARDRAIL_REDACT", guardrail: {...} }
   *   { success: false, code: "ENT_GUARDRAIL_BLOCK", guardrail: {...} }
   *   { success: false, code: "ENT_GUARDRAIL_APPROVAL", guardrail: {...} }
   *   { success: false, code: "ENT_NO_TOKENS" | "ENT_ENHANCE_ERROR", error: "..." }
   */
  async function run(prompt, opts) {
    const TV = root.TV;
    opts = opts || {};

    let accessToken;
    try {
      accessToken = await TV.tokenManager.ensureFreshEnterpriseToken();
    } catch (err) {
      return { success: false, code: err.message || "ENT_NO_TOKENS", error: err.message };
    }

    const SK = TV.STORAGE_KEYS;
    const stored = await TV.chromeStorage.get([SK.ENT_ENTERPRISE_ID, SK.ENT_USER_ID]);
    const enterpriseId = stored[SK.ENT_ENTERPRISE_ID] || "";
    const userId = stored[SK.ENT_USER_ID] || "";

    // Determine the actual prompt text to enhance.
    const promptToEnhance =
      typeof opts.useRedacted === "string" && opts.useRedacted.trim()
        ? opts.useRedacted.trim()
        : prompt;

    // Guardrail check (skip when panel has already obtained acknowledgement).
    if (!opts.skipGuardrail) {
      let guardrail;
      try {
        guardrail = await checkGuardrail(prompt, accessToken, enterpriseId);
      } catch (err) {
        return { success: false, code: "ENT_GUARDRAIL_ERROR", error: err.message };
      }

      const decision = (guardrail.decision || "ALLOW").toUpperCase();

      if (decision === "WARN") {
        return { success: false, code: "ENT_GUARDRAIL_WARN", guardrail };
      }
      if (decision === "REQUIRE_CONFIRMATION") {
        return { success: false, code: "ENT_GUARDRAIL_CONFIRM", guardrail };
      }
      if (decision === "REDACT") {
        return { success: false, code: "ENT_GUARDRAIL_REDACT", guardrail };
      }
      if (decision === "BLOCK") {
        return { success: false, code: "ENT_GUARDRAIL_BLOCK", guardrail };
      }
      if (decision === "REQUIRE_APPROVAL") {
        // Store pending approval so the panel can show a banner on next boot.
        await TV.chromeStorage.set({
          [SK.ENT_PENDING_APPROVAL]: {
            queueId: guardrail.queueId || null,
            promptExcerpt: prompt.slice(0, 120),
            submittedAt: Date.now(),
          },
        });
        return { success: false, code: "ENT_GUARDRAIL_APPROVAL", guardrail };
      }
      // ALLOW falls through to enhance below.
    }

    // Enhance.
    try {
      const enhancedText = await streamEnhance(promptToEnhance, accessToken, enterpriseId, userId);
      return { success: true, data: { enhancedText, guardrail: null } };
    } catch (err) {
      return { success: false, code: "ENT_ENHANCE_ERROR", error: err.message };
    }
  }

  root.TV.enterpriseEnhanceFlow = { run };
})();
