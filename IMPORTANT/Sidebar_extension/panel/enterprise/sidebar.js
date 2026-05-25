/**
 * Enterprise side-panel view state controller.
 * States: LOADING | AUTH | MAIN | GUARDRAIL
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  const TV = root.TV;

  if (!TV || !TV.STORAGE_KEYS || !TV.enterpriseAuthView || !TV.enterpriseEnhanceView) {
    console.error("[sidebar-enterprise] Required modules not loaded.");
    return;
  }

  const SK = TV.STORAGE_KEYS;

  // ── DOM references ──────────────────────────────────────────────────────────
  const viewLoading    = document.getElementById("viewLoading");
  const viewAuth       = document.getElementById("viewAuth");
  const viewMain       = document.getElementById("viewMain");
  const viewGuardrail  = document.getElementById("viewGuardrail");
  const viewHistory    = document.getElementById("viewHistory");
  const btnHistory     = document.getElementById("btnHistory");
  const loadingLabel   = document.getElementById("loadingLabel");

  const mainUserName      = document.getElementById("mainUserName");
  const btnSwitchConsumer = document.getElementById("btnSwitchConsumer");
  const btnLogout         = document.getElementById("btnLogout");
  const pendingBanner     = document.getElementById("pendingBanner");
  const btnDismissPending = document.getElementById("btnDismissPending");
  const btnCheckApproval  = document.getElementById("btnCheckApproval");

  const entPrompt      = document.getElementById("entPrompt");
  const btnEnhance     = document.getElementById("btnEnhance");
  const outputArea     = document.getElementById("outputArea");
  const outputText     = document.getElementById("outputText");
  const btnCopyOutput  = document.getElementById("btnCopyOutput");
  const btnNewPrompt   = document.getElementById("btnNewPrompt");

  // Prompt to restore after re-authentication (set when ENT_NO_TOKENS is hit mid-session).
  let _pendingPromptAfterReauth = null;

  // ── View switching ──────────────────────────────────────────────────────────
  function showView(name, label) {
    [viewLoading, viewAuth, viewMain, viewGuardrail, viewHistory].forEach((v) => {
      if (v) v.style.display = "none";
    });
    const map = { LOADING: viewLoading, AUTH: viewAuth, MAIN: viewMain, GUARDRAIL: viewGuardrail, HISTORY: viewHistory };
    const el = map[name];
    if (el) el.style.display = "";
    if (name === "LOADING" && loadingLabel && label) loadingLabel.textContent = label;
  }

  // ── Boot sequence ───────────────────────────────────────────────────────────
  async function boot() {
    showView("LOADING", "Loading…");
    try {
      const data = await new Promise((resolve, reject) => {
        chrome.storage.local.get([
          SK.ENT_ACCESS_TOKEN, SK.ENT_REFRESH_TOKEN, SK.ENT_ACCESS_EXP,
          SK.ENT_USER_NAME, SK.ENT_USER_EMAIL, SK.ENT_ENTERPRISE_ID,
          SK.ENT_PENDING_APPROVAL,
          "accessToken", "refreshToken",
        ], (r) => {
          if (chrome.runtime.lastError) return reject(chrome.runtime.lastError);
          resolve(r);
        });
      });

      const hasEntAccess  = Boolean(data[SK.ENT_ACCESS_TOKEN]);
      const hasEntRefresh = Boolean(data[SK.ENT_REFRESH_TOKEN]);
      const hasEnt = hasEntAccess || hasEntRefresh;

      if (!hasEnt) {
        showAuth();
        return;
      }

      // Tokens exist → show MAIN view.
      showMain(data);
    } catch (err) {
      console.error("[sidebar-enterprise] boot error:", err);
      showAuth();
    }
  }

  // ── Show AUTH view ──────────────────────────────────────────────────────────
  function showAuth() {
    showView("AUTH");
    TV.enterpriseAuthView.mount(viewAuth, {
      onSuccess: handleLoginSuccess,
      onSwitchToConsumer: switchToConsumer,
    });
  }

  async function handleLoginSuccess(payload) {
    showView("LOADING", "Signing in…");
    chrome.runtime.sendMessage(
      { action: "TV_ENTERPRISE_LOGIN_SUCCESS", payload },
      (response) => {
        if (chrome.runtime.lastError || !response || !response.success) {
          console.error("[sidebar-enterprise] login store failed:", chrome.runtime.lastError || response);
          showAuth();
          return;
        }
        // Reload boot sequence so MAIN view reads fresh storage.
        boot();
      }
    );
  }

  // ── Show MAIN view ──────────────────────────────────────────────────────────
  async function showMain(storageData) {
    // Populate header.
    if (mainUserName) {
      const name  = storageData[SK.ENT_USER_NAME]  || "";
      const email = storageData[SK.ENT_USER_EMAIL] || "";
      mainUserName.textContent = name || email || "";
    }

    // Check if both sessions exist → show mode switcher.
    const hasConsumer = Boolean(storageData["accessToken"] || storageData["refreshToken"]);
    if (btnSwitchConsumer) {
      btnSwitchConsumer.style.display = hasConsumer ? "" : "none";
    }

    // Pending approval banner.
    const pending = storageData[SK.ENT_PENDING_APPROVAL];
    if (pending && pendingBanner) {
      pendingBanner.style.display = "";
    }

    // Reset output area.
    if (outputArea) outputArea.style.display = "none";
    if (outputText) outputText.textContent = "";
    // Restore pending prompt if returning from a re-auth redirect.
    if (entPrompt) {
      entPrompt.value = _pendingPromptAfterReauth || "";
    }
    _pendingPromptAfterReauth = null;

    showView("MAIN");
  }

  // ── Enhance flow (streaming) ────────────────────────────────────────────────
  async function runEnhance(promptText, opts) {
    showView("LOADING", "Checking policy…");
    try {
      opts = opts || {};

      // Phase 1 — guardrail check through background (handles token refresh, storage).
      const grPayload = Object.assign({ prompt: promptText, guardrailOnly: true }, opts);
      const grResponse = await new Promise((resolve) => {
        chrome.runtime.sendMessage({ action: "TV_ENTERPRISE_ENHANCE", payload: grPayload }, (r) => {
          if (chrome.runtime.lastError) {
            resolve({ success: false, error: { message: chrome.runtime.lastError.message } });
            return;
          }
          resolve(r);
        });
      });

      if (!grResponse || !grResponse.success) {
        const code = grResponse && grResponse.error && grResponse.error.code;
        const isGuardrail = code && code.startsWith("ENT_GUARDRAIL_");

        if (!isGuardrail) {
          if (code === "ENT_NO_TOKENS") {
            _pendingPromptAfterReauth = promptText;
            showAuth();
            return;
          }
          alert(grResponse && grResponse.error ? grResponse.error.message : "Enhancement failed.");
          showMain(await readStorage());
          return;
        }

        // Show guardrail overlay.
        showView("GUARDRAIL");
        const outcomeData = { code, guardrail: grResponse.error && grResponse.error.guardrail };
        const userDecision = await TV.enterpriseEnhanceView.showOutcome(viewGuardrail, outcomeData);

        if (userDecision.action === "cancel") {
          showMain(await readStorage());
          return;
        }
        if (code === "ENT_GUARDRAIL_WARN" || code === "ENT_GUARDRAIL_CONFIRM") {
          await runEnhance(promptText, { skipGuardrail: true });
        } else if (code === "ENT_GUARDRAIL_REDACT") {
          await runEnhance(promptText, { skipGuardrail: true, useRedacted: userDecision.redactedPrompt });
        }
        return;
      }

      // Phase 2 — guardrail passed. Get a fresh token and stream SSE directly.
      const tokenResponse = await new Promise((resolve) => {
        chrome.runtime.sendMessage({ action: "TV_ENTERPRISE_GET_TOKEN" }, (r) => {
          if (chrome.runtime.lastError) {
            resolve({ success: false, error: { message: chrome.runtime.lastError.message } });
            return;
          }
          resolve(r);
        });
      });

      if (!tokenResponse || !tokenResponse.success) {
        const tCode = tokenResponse && tokenResponse.error && tokenResponse.error.code;
        if (tCode === "ENT_NO_TOKENS") {
          _pendingPromptAfterReauth = promptText;
          showAuth();
          return;
        }
        alert("Could not get session token. Please reload.");
        showMain(await readStorage());
        return;
      }

      const { accessToken, enterpriseId, userId } = tokenResponse.data;
      const promptToEnhance =
        typeof opts.useRedacted === "string" && opts.useRedacted.trim()
          ? opts.useRedacted.trim()
          : promptText;

      // Show MAIN view immediately with empty output (stream chunks as they arrive).
      if (outputText)  outputText.textContent = "";
      if (outputArea)  outputArea.style.display = "";
      if (btnEnhance)  btnEnhance.disabled = true;
      showView("MAIN");

      const res = await fetch("https://velocityenterprise.toteminteractive.in/prompt/enhance/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ prompt: promptToEnhance, enterpriseId, userId }),
      });

      if (!res.ok) {
        const msg = await res.text().catch(() => "");
        throw new Error(`Enhance failed: ${res.status} ${msg}`);
      }
      if (!res.body) throw new Error("No response body from enhance endpoint");

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";
      let buffer = "";

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop();
          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data:")) continue;
            const jsonPart = trimmed.slice(5).trimStart();
            if (!jsonPart || jsonPart === "[DONE]") continue;
            try {
              const data = JSON.parse(jsonPart);
              if (data.type === "content" && data.chunk) {
                accumulated += data.chunk;
                if (outputText) outputText.textContent = accumulated;
              }
              if (data.type === "complete" && data.enhanced_prompt) {
                accumulated = data.enhanced_prompt;
                if (outputText) outputText.textContent = accumulated;
              }
            } catch (_) {}
          }
        }
        // Flush residual buffer.
        buffer += decoder.decode();
        if (buffer.trim()) {
          for (const line of buffer.split("\n")) {
            const trimmed = line.trim();
            if (!trimmed.startsWith("data:")) continue;
            const jsonPart = trimmed.slice(5).trimStart();
            if (!jsonPart || jsonPart === "[DONE]") continue;
            try {
              const data = JSON.parse(jsonPart);
              if (data.type === "content" && data.chunk) {
                accumulated += data.chunk;
                if (outputText) outputText.textContent = accumulated;
              }
              if (data.type === "complete" && data.enhanced_prompt) {
                accumulated = data.enhanced_prompt;
                if (outputText) outputText.textContent = accumulated;
              }
            } catch (_) {}
          }
        }
      } finally {
        reader.cancel().catch(() => {});
      }

      if (!accumulated.trim()) throw new Error("Empty enhancement response");

    } catch (err) {
      console.error("[sidebar-enterprise] runEnhance error:", err);
      alert("Enhancement failed: " + (err.message || String(err)));
      showMain(await readStorage());
    } finally {
      if (btnEnhance) btnEnhance.disabled = false;
    }
  }

  async function readStorage() {
    return new Promise((resolve) => {
      chrome.storage.local.get([
        SK.ENT_USER_NAME, SK.ENT_USER_EMAIL, SK.ENT_ENTERPRISE_ID,
        SK.ENT_PENDING_APPROVAL, "accessToken", "refreshToken",
      ], (r) => resolve(r || {}));
    });
  }

  // ── Buttons ─────────────────────────────────────────────────────────────────
  if (btnEnhance) {
    btnEnhance.addEventListener("click", () => {
      const prompt = entPrompt && entPrompt.value.trim();
      if (!prompt) return;
      runEnhance(prompt);
    });
  }

  if (btnCopyOutput) {
    btnCopyOutput.addEventListener("click", () => {
      const text = outputText && outputText.textContent;
      if (text) navigator.clipboard.writeText(text).catch(() => {});
      btnCopyOutput.textContent = "Copied!";
      setTimeout(() => { btnCopyOutput.textContent = "Copy"; }, 1500);
    });
  }

  if (btnNewPrompt) {
    btnNewPrompt.addEventListener("click", async () => {
      if (outputArea) outputArea.style.display = "none";
      showMain(await readStorage());
    });
  }

  if (btnLogout) {
    btnLogout.addEventListener("click", () => {
      chrome.runtime.sendMessage({ action: "TV_ENTERPRISE_LOGOUT" }, () => {
        window.location.replace(chrome.runtime.getURL("panel/bootstrap.html"));
      });
    });
  }

  if (btnSwitchConsumer) {
    btnSwitchConsumer.addEventListener("click", () => {
      switchToConsumer();
    });
  }

  if (btnDismissPending) {
    btnDismissPending.addEventListener("click", () => {
      chrome.storage.local.remove(SK.ENT_PENDING_APPROVAL);
      if (pendingBanner) pendingBanner.style.display = "none";
    });
  }

  if (btnCheckApproval) {
    btnCheckApproval.addEventListener("click", () => {
      btnCheckApproval.textContent = "Checking…";
      btnCheckApproval.disabled = true;
      chrome.runtime.sendMessage({ action: "TV_ENTERPRISE_CHECK_APPROVAL" }, (response) => {
        btnCheckApproval.disabled = false;
        if (chrome.runtime.lastError || !response || !response.success) {
          btnCheckApproval.textContent = "Check status";
          alert("Could not check approval status. Try again.");
          return;
        }
        const status = response.data && response.data.status;
        if (status === "APPROVED") {
          if (pendingBanner) pendingBanner.style.display = "none";
          const original = response.data.originalPrompt || "";
          if (original && entPrompt) entPrompt.value = original;
          alert("✅ Your prompt was approved! The text has been restored — enhance it now.");
        } else if (status === "REJECTED") {
          if (pendingBanner) pendingBanner.style.display = "none";
          alert("❌ Your prompt was rejected by the admin.");
        } else if (status === "NONE") {
          if (pendingBanner) pendingBanner.style.display = "none";
          btnCheckApproval.textContent = "Check status";
        } else {
          // Still PENDING.
          btnCheckApproval.textContent = "Still pending…";
          setTimeout(() => { btnCheckApproval.textContent = "Check status"; }, 3000);
        }
      });
    });
  }

  if (btnHistory) {
    btnHistory.addEventListener("click", () => {
      if (!TV.enterpriseHistoryView) return;
      showView("HISTORY");
      TV.enterpriseHistoryView.mount(viewHistory, {
        onBack: async () => showMain(await readStorage()),
        onSelectPrompt: async (text) => {
          if (entPrompt) entPrompt.value = text;
          showMain(await readStorage());
        },
      });
    });
  }

  function switchToConsumer() {
    chrome.runtime.sendMessage(
      { action: "TV_ENTERPRISE_MODE_SWITCH", payload: { flow: "consumer" } },
      () => {
        window.location.replace(chrome.runtime.getURL("panel/bootstrap.html"));
      }
    );
  }

  // ── Lifecycle port (panel open/close detection for host-page launcher pill) ─
  try {
    const lifecyclePort = chrome.runtime.connect({ name: "velocity-side-panel-lifecycle" });
    lifecyclePort.onDisconnect.addListener(() => { void chrome.runtime.lastError; });
  } catch (e) {
    console.warn("[sidebar-enterprise] lifecycle port failed:", e);
  }

  // Start.
  boot();
})();
