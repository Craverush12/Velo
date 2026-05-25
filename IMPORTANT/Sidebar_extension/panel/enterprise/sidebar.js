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

  // ── Enhance flow ────────────────────────────────────────────────────────────
  async function runEnhance(promptText, opts) {
    showView("LOADING", "Checking policy…");
    try {
      opts = opts || {};
      const payload = Object.assign({ prompt: promptText }, opts);
      const response = await new Promise((resolve) => {
        chrome.runtime.sendMessage({ action: "TV_ENTERPRISE_ENHANCE", payload }, (r) => {
          if (chrome.runtime.lastError) {
            resolve({ success: false, error: { message: chrome.runtime.lastError.message } });
            return;
          }
          resolve(r);
        });
      });

      if (response && response.success) {
        // Enhancement complete.
        const data = response.data || {};
        if (outputText) outputText.textContent = data.enhancedText || "";
        if (outputArea) outputArea.style.display = "";
        showView("MAIN");
        return;
      }

      // Failure — check if it's a guardrail outcome.
      const code = response && response.error && response.error.code;
      const isGuardrail = code && code.startsWith("ENT_GUARDRAIL_");

      if (!isGuardrail) {
        if (code === "ENT_NO_TOKENS") {
          // Tokens expired — save the prompt and route to login.
          _pendingPromptAfterReauth = promptText;
          showAuth();
          return;
        }
        alert(response && response.error ? response.error.message : "Enhancement failed.");
        showMain(await readStorage());
        return;
      }

      // Show guardrail overlay.
      showView("GUARDRAIL");
      const outcomeData = { code, guardrail: response.error && response.error.guardrail };
      const userDecision = await TV.enterpriseEnhanceView.showOutcome(viewGuardrail, outcomeData);

      if (userDecision.action === "cancel") {
        showMain(await readStorage());
        return;
      }

      // User chose to proceed.
      if (code === "ENT_GUARDRAIL_WARN" || code === "ENT_GUARDRAIL_CONFIRM") {
        await runEnhance(promptText, { skipGuardrail: true });
      } else if (code === "ENT_GUARDRAIL_REDACT") {
        await runEnhance(promptText, { skipGuardrail: true, useRedacted: userDecision.redactedPrompt });
      }
    } catch (err) {
      console.error("[sidebar-enterprise] runEnhance error:", err);
      alert("Extension error. Please reload.");
      showMain(await readStorage());
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

  if (btnHistory) {
    btnHistory.addEventListener("click", () => {
      if (!TV.enterpriseHistoryView) return;
      showView("HISTORY");
      TV.enterpriseHistoryView.mount(viewHistory, {
        onBack: () => showMain({}),
        onSelectPrompt: (text) => {
          if (entPrompt) entPrompt.value = text;
          showMain({});
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
