/**
 * Service worker: side panel behavior + auth (login-bridge, tokens, messaging).
 * Loads shared modules via importScripts (no ES modules).
 */
importScripts(
  "core/storage-keys.js",
  "core/sidebar-flow.js",
  "utils/chrome-storage.js",
  "utils/local-storage-sync-lite.js",
  "utils/token-manager.js",
  "utils/thinkvelocity-urls.js",
  "utils/host-context.js",
  "utils/prompt-display-title.js",
  "utils/subscription-access.js",
  "utils/usage-access.js"
);
try {
  importScripts("features/consumer-enhance-flow.js");
} catch (e) {
  console.error("[Sidebar_extension] consumer-enhance-flow.js failed to load:", e);
}
try {
  importScripts("features/consumer-clarify-refine.js");
} catch (e) {
  console.error("[Sidebar_extension] consumer-clarify-refine.js failed to load:", e);
}
try {
  importScripts("features/consumer-library-fetch.js");
} catch (e) {
  console.error("[Sidebar_extension] consumer-library-fetch.js failed to load:", e);
}
try {
  importScripts("features/extension-context-api.js");
} catch (e) {
  console.error("[Sidebar_extension] extension-context-api.js failed to load:", e);
}
try {
  importScripts("features/offscreen-voice-bridge.js");
} catch (e) {
  console.error("[Sidebar_extension] offscreen-voice-bridge.js failed to load:", e);
}
try {
  importScripts("utils/prompt-format.js");
  importScripts("utils/platform-prompt-actions.js");
  importScripts("features/consumer-platform-inject.js");
} catch (e) {
  console.error("[Sidebar_extension] consumer-platform-inject failed to load:", e);
}
try {
  importScripts("features/extracted-conversation-store.js");
} catch (e) {
  console.error("[Sidebar_extension] extracted-conversation-store.js failed to load:", e);
}
try {
  importScripts("features/essence-context-engine.js");
} catch (e) {
  console.error("[Sidebar_extension] essence-context-engine.js failed to load:", e);
}
try {
  importScripts("features/side-panel-lifecycle.js");
} catch (e) {
  console.error("[Sidebar_extension] side-panel-lifecycle.js failed to load:", e);
}
try {
  importScripts("features/enterprise-enhance-flow.js");
} catch (e) {
  console.error("[Sidebar_extension] enterprise-enhance-flow.js failed to load:", e);
}

// ── Enterprise in-memory mode cache ─────────────────────────────────────────
// Cached on service-worker boot to avoid async storage I/O on every API call.
let _activeMode = "consumer";
(function initActiveMode() {
  const TV = globalThis.TV;
  const key = TV && TV.STORAGE_KEYS && TV.STORAGE_KEYS.SIDEBAR_FLOW
    ? TV.STORAGE_KEYS.SIDEBAR_FLOW : "velocity_sidebar_flow";
  chrome.storage.local.get([key], (r) => {
    if (chrome.runtime.lastError) return;
    _activeMode =
      TV && typeof TV.normalizeSidebarFlow === "function"
        ? TV.normalizeSidebarFlow(r[key])
        : (r[key] === "enterprise" ? "enterprise" : "consumer");
    if (TV && TV.tokenManager) TV.tokenManager.getActiveMode = () => _activeMode;
  });
  if (TV && TV.tokenManager) TV.tokenManager.getActiveMode = () => _activeMode;
})();

/** Injected into the active tab; self-contained (aligned with Extension-new/background.js). */
function pageContextExtractFn() {
  const url = location.href;
  const title = document.title || "";
  const html = document.documentElement.outerHTML || "";
  
  return {
    url,
    title,
    html,
    language: document.documentElement.getAttribute("lang") || "",
    fetchedAt: new Date().toISOString(),
  };
}

function canExtractPageContextFromUrl(url) {
  if (!url || typeof url !== "string") return false;
  if (/^(chrome|edge|about|chrome-extension|devtools|file):/i.test(url)) return false;
  if (/^view-source:/i.test(url)) return false;
  if (url.includes("chrome.google.com/webstore")) return false;
  return /^https?:\/\//i.test(url);
}

async function configureSidePanelBehavior() {
  if (!chrome.sidePanel || !chrome.sidePanel.setPanelBehavior) {
    return;
  }
  try {
    await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  } catch (error) {
    console.warn("[Sidebar_extension] setPanelBehavior failed:", error);
  }
}

function buildLoginUrl(path) {
  const TV = globalThis.TV;
  if (TV && TV.thinkvelocityUrls) {
    return TV.thinkvelocityUrls.buildThinkVelocityUrl(path, {
      platform: "sidebar",
      content: "sidebar_auth_login",
    });
  }
  return new URL(path, "https://thinkvelocity.in").toString();
}

function isOffscreenVoiceReplySenderAllowed(sender) {
  if (!sender || sender.id !== chrome.runtime.id) return false;
  const urlStr = sender.url || "";
  if (!urlStr.includes("offscreen-voice.html")) return false;
  try {
    const u = new URL(urlStr);
    return u.protocol === "chrome-extension:" && u.hostname === chrome.runtime.id;
  } catch (e) {
    return false;
  }
}

function isAuthMessageSenderAllowed(sender) {
  if (!sender) return false;
  if (sender.id != null && sender.id !== chrome.runtime.id) {
    return false;
  }
  const origin = sender.origin || "";
  if (origin.startsWith(`chrome-extension://${chrome.runtime.id}`)) {
    return true;
  }
  const urlStr = sender.url || sender.tab?.url || "";
  try {
    const u = new URL(urlStr);
    if (u.protocol === "chrome-extension:" && u.hostname === chrome.runtime.id) {
      return true;
    }
    if (u.hostname === "thinkvelocity.in" || u.hostname.endsWith(".thinkvelocity.in")) {
      return true;
    }
    if (u.hostname === "localhost" && u.port === "3002") {
      return true;
    }
  } catch (e) {
    return false;
  }
  return false;
}

function isHostPlatformContentScriptSender(sender) {
  if (!sender || sender.id !== chrome.runtime.id) return false;
  const urlStr = sender.url || sender.tab?.url || "";
  try {
    const u = new URL(urlStr);
    if (u.protocol !== "https:") return false;
    const host = u.hostname;
    const allowed = [
      "chat.openai.com",
      "chatgpt.com",
      "claude.ai",
      "gemini.google.com",
      "chat.mistral.ai",
      "gamma.app",
      "bolt.new",
      "grok.com",
      "suno.com",
      "lovable.dev",
      "replit.com",
      "v0.dev",
      "v0.app",
      "perplexity.ai",
      "hera.video",
      "labs.google",
      "kimi.com",
      "app.emergent.sh",
      "emergent.sh",
    ];
    return allowed.some((h) => host === h || host.endsWith("." + h));
  } catch (e) {
    return false;
  }
}

async function openSidePanelForSender(sender) {
  if (!chrome.sidePanel || typeof chrome.sidePanel.open !== "function") {
    throw new Error("Side panel API unavailable");
  }
  const windowId = sender.tab && sender.tab.windowId;
  if (windowId != null) {
    await chrome.sidePanel.open({ windowId });
    return;
  }
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const tab = tabs && tabs[0];
  if (tab && tab.windowId != null) {
    await chrome.sidePanel.open({ windowId: tab.windowId });
    return;
  }
  throw new Error("Could not resolve window for side panel");
}

/**
 * Synchronous starter for chrome.sidePanel.open(). Must be invoked inside the
 * same synchronous turn as the incoming runtime message so the user-gesture
 * context survives. Returns a promise the caller can await later. If the
 * window id is not available on `sender.tab`, we fall back to an async
 * tabs.query — that path will likely fail Chrome's gesture check, but it
 * preserves the prior behaviour as a best-effort path.
 */
function beginOpenSidePanelForSender(sender) {
  if (!chrome.sidePanel || typeof chrome.sidePanel.open !== "function") {
    return Promise.reject(new Error("Side panel API unavailable"));
  }
  const windowId = sender && sender.tab && sender.tab.windowId;
  if (windowId != null) {
    return chrome.sidePanel.open({ windowId });
  }
  return (async () => {
    const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    const tab = tabs && tabs[0];
    if (tab && tab.windowId != null) {
      return chrome.sidePanel.open({ windowId: tab.windowId });
    }
    throw new Error("Could not resolve window for side panel");
  })();
}

async function reopenSidePanelAfterLogin(sender) {
  if (!chrome.sidePanel || typeof chrome.sidePanel.open !== "function") {
    return;
  }
  // Try the tab that submitted the auth message first.
  let windowId = sender && sender.tab && sender.tab.windowId;
  if (windowId == null) {
    try {
      const focused = await chrome.windows.getLastFocused({ populate: false });
      if (focused && focused.id != null) windowId = focused.id;
    } catch (_) {}
  }
  if (windowId == null) {
    try {
      const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      const tab = tabs && tabs[0];
      if (tab && tab.windowId != null) windowId = tab.windowId;
    } catch (_) {}
  }
  if (windowId == null) return;
  try {
    await chrome.sidePanel.open({ windowId });
  } catch (e) {
    // sidePanel.open() requires a user gesture; if Chrome rejected the call
    // (older builds, race with focus changes, etc.), fall back to action
    // click behaviour — `setPanelBehavior` already auto-opens on click.
    console.warn("[Sidebar_extension] sidePanel.open after login failed:", e);
  }
}

function reply(sendResponse, requestId, success, data, error) {
  const out = { success, requestId: requestId || null };
  if (success) {
    out.data = data;
  } else {
    if (error && typeof error === "object" && error.message) {
      out.error = {
        code: error.code || "ERROR",
        message: error.message,
        retryable: Boolean(error.retryable),
        guardrail: error.guardrail || null,
      };
    } else {
      out.error = {
        code: "ERROR",
        message: String(error || "error"),
        retryable: false,
      };
    }
  }
  sendResponse(out);
}

const SUB_STATUS_CACHE_MS = 15 * 60 * 1000;

async function readCachedUserStatus() {
  const TV = globalThis.TV;
  const keys = TV.STORAGE_KEYS;
  const cached = await TV.chromeStorage.get([
    keys.SUBSCRIPTION_STATUS,
    keys.SUBSCRIPTION_STATUS_AT,
    keys.REMAINING_USAGE,
    keys.USAGE_LIMIT,
  ]);
  const cachedAt = Number(cached[keys.SUBSCRIPTION_STATUS_AT]) || 0;
  const fresh = Boolean(cached[keys.SUBSCRIPTION_STATUS]) && Date.now() - cachedAt < SUB_STATUS_CACHE_MS;
  return {
    fresh,
    cachedAt,
    subscriptionStatus: cached[keys.SUBSCRIPTION_STATUS] || "free",
    remainingUsage:
      cached[keys.REMAINING_USAGE] !== undefined && cached[keys.REMAINING_USAGE] !== null
        ? Number(cached[keys.REMAINING_USAGE])
        : null,
    usageLimit:
      cached[keys.USAGE_LIMIT] !== undefined && cached[keys.USAGE_LIMIT] !== null
        ? Number(cached[keys.USAGE_LIMIT])
        : null,
  };
}

async function fetchUserStatus(userId, accessToken, options) {
  const TV = globalThis.TV;
  const keys = TV.STORAGE_KEYS;
  const force = Boolean(options && options.force);
  const cached = await readCachedUserStatus();

  if (!userId || !accessToken) {
    return {
      subscriptionStatus: cached.subscriptionStatus || "free",
      remainingUsage: cached.remainingUsage,
      usageLimit: cached.usageLimit,
    };
  }

  if (cached.fresh && !force) {
    return {
      subscriptionStatus: cached.subscriptionStatus,
      remainingUsage: cached.remainingUsage,
      usageLimit: cached.usageLimit,
    };
  }

  try {
    const base = await TV.tokenManager.getApiBase();
    const res = await fetch(`${base}/status/${encodeURIComponent(userId)}`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
    });
    if (!res.ok) {
      return {
        subscriptionStatus: cached.subscriptionStatus || "free",
        remainingUsage: cached.remainingUsage,
        usageLimit: cached.usageLimit,
      };
    }
    const json = await res.json();
    const data = json && json.success && json.data ? json.data : null;
    const usage =
      TV.usageAccess && typeof TV.usageAccess.buildUsageFieldsFromStatusData === "function"
        ? TV.usageAccess.buildUsageFieldsFromStatusData(data || {})
        : {
            status: data && data.status ? String(data.status) : "free",
            remainingUsage: data && data.remainingUsage !== undefined ? data.remainingUsage : 0,
            usageLimit: data && data.usageLimit !== undefined ? data.usageLimit : 10,
          };
    await TV.chromeStorage.set({
      [keys.SUBSCRIPTION_STATUS]: usage.status,
      [keys.REMAINING_USAGE]: usage.remainingUsage,
      [keys.USAGE_LIMIT]: usage.usageLimit,
      [keys.SUBSCRIPTION_STATUS_AT]: Date.now(),
    });
    if (TV.localStorageSync && typeof TV.localStorageSync.syncChromeStorageToLocalStorage === "function") {
      try {
        await TV.localStorageSync.syncChromeStorageToLocalStorage();
      } catch (_) {}
    }
    return {
      subscriptionStatus: usage.status,
      remainingUsage: usage.remainingUsage,
      usageLimit: usage.usageLimit,
    };
  } catch (_) {
    return {
      subscriptionStatus: cached.subscriptionStatus || "free",
      remainingUsage: cached.remainingUsage,
      usageLimit: cached.usageLimit,
    };
  }
}

async function decrementStoredUsage() {
  const TV = globalThis.TV;
  const keys = TV.STORAGE_KEYS;
  const data = await TV.chromeStorage.get([keys.REMAINING_USAGE, keys.SUBSCRIPTION_STATUS]);
  if (data[keys.REMAINING_USAGE] === undefined || data[keys.REMAINING_USAGE] === null) {
    return null;
  }
  const next =
    TV.usageAccess && typeof TV.usageAccess.decrementRemainingUsage === "function"
      ? TV.usageAccess.decrementRemainingUsage(data[keys.REMAINING_USAGE])
      : Math.max(0, Number(data[keys.REMAINING_USAGE] || 0) - 1);
  await TV.chromeStorage.set({ [keys.REMAINING_USAGE]: next });
  if (TV.localStorageSync && typeof TV.localStorageSync.syncChromeStorageToLocalStorage === "function") {
    try {
      await TV.localStorageSync.syncChromeStorageToLocalStorage();
    } catch (_) {}
  }
  return next;
}

async function getAuthSnapshotPayload(options) {
  const TV = globalThis.TV;
  const keys = TV.STORAGE_KEYS;
  const data = await TV.chromeStorage.get([
    keys.USER_ID,
    keys.USER_EMAIL,
    keys.USER_NAME,
    keys.SIDEBAR_FLOW,
    "accessToken",
    "refreshToken",
  ]);
  const hasAccess = Boolean(data.accessToken);
  const hasRefresh = Boolean(data.refreshToken);
  const isLoggedIn = hasAccess || hasRefresh;
  let subscriptionStatus = "free";
  let remainingUsage = null;
  let usageLimit = null;
  let isProUser = false;
  if (isLoggedIn && data.userId && data.accessToken) {
    const statusPayload = await fetchUserStatus(data.userId, data.accessToken, options || {});
    subscriptionStatus = statusPayload.subscriptionStatus || "free";
    remainingUsage = statusPayload.remainingUsage;
    usageLimit = statusPayload.usageLimit;
    if (TV.subscriptionAccess && typeof TV.subscriptionAccess.hasProGoldChrome === "function") {
      isProUser = TV.subscriptionAccess.hasProGoldChrome(subscriptionStatus);
    }
  }
  const snapshot = {
    isLoggedIn,
    userId: data.userId || "",
    userEmail: data.userEmail || "",
    userName: data.userName || "",
    sidebarFlow: TV.normalizeSidebarFlow(data[keys.SIDEBAR_FLOW]),
    subscriptionStatus,
    remainingUsage,
    usageLimit,
    isProUser,
  };
  snapshot.isUsageExhausted =
    TV.usageAccess && typeof TV.usageAccess.isUsageExhausted === "function"
      ? TV.usageAccess.isUsageExhausted(snapshot)
      : false;
  return snapshot;
}

// Page Chrome opens when the user removes the extension from chrome://extensions.
// Re-applied on every service-worker boot so the URL survives manifest updates.
const UNINSTALL_FEEDBACK_URL =
  "https://thinkvelocity.in/reviews/?utm_source=chrome_extension&utm_medium=uninstall";

function configureUninstallUrl() {
  try {
    if (!chrome.runtime || typeof chrome.runtime.setUninstallURL !== "function") return;
    chrome.runtime.setUninstallURL(UNINSTALL_FEEDBACK_URL, () => {
      const err = chrome.runtime.lastError;
      if (err) console.warn("[background] setUninstallURL failed:", err.message);
    });
  } catch (e) {
    console.warn("[background] setUninstallURL threw:", e);
  }
}

configureSidePanelBehavior();
configureUninstallUrl();
chrome.runtime.onInstalled.addListener((details) => {
  configureSidePanelBehavior();
  configureUninstallUrl();
  if (details && details.reason === "install") {
    // Welcome flow: open ChatGPT directly and let the in-page popup
    // (button/js/injection-popups.js) render the tutorial overlay on top of
    // the host page. The coachmark next to the floating V button is kept as
    // a complementary nudge after the user dismisses the tutorial.
    try {
      chrome.storage.local.set({
        velocity_show_install_tutorial_popup: true,
        velocity_show_post_install_popup: true,
      });
    } catch (e) {
      console.warn("[background] failed to set post-install popup flags:", e);
    }
    openInstallWelcomeTutorial();
  }
});
chrome.runtime.onStartup.addListener(() => {
  configureSidePanelBehavior();
  configureUninstallUrl();
});

function openInstallWelcomeTutorial() {
  try {
    chrome.tabs.create({ url: "https://chatgpt.com/", active: true });
  } catch (e) {
    console.warn("[background] failed to open ChatGPT for install welcome:", e);
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const TV = globalThis.TV;
  if (!message || typeof message.action !== "string") {
    reply(sendResponse, null, false, null, {
      code: "INVALID_MESSAGE",
      message: "Missing action",
      retryable: false,
    });
    return false;
  }

  const action = message.action.trim();
  if (action !== message.action) {
    message = { ...message, action };
  }

  if (action === "TV_OFFSCREEN_VOICE_SW_REPLY") {
    if (!isOffscreenVoiceReplySenderAllowed(sender)) {
      return false;
    }
    if (TV.offscreenVoiceBridge && typeof TV.offscreenVoiceBridge.handleSwReply === "function") {
      TV.offscreenVoiceBridge.handleSwReply(message);
    }
    return false;
  }

  /** Essence sync from AI host content scripts (bridge → background). */
  if (action === "handleMessagesExtracted") {
    if (!isHostPlatformContentScriptSender(sender)) {
      reply(sendResponse, message.requestId, false, null, {
        code: "UNAUTHORIZED_SENDER",
        message: "Unauthorized message sender",
        retryable: false,
      });
      return false;
    }
    sendResponse({ success: true });
    return false;
  }

  if (action === "processConversationContext") {
    if (!isHostPlatformContentScriptSender(sender)) {
      reply(sendResponse, message.requestId, false, null, {
        code: "UNAUTHORIZED_SENDER",
        message: "Unauthorized message sender",
        retryable: false,
      });
      return false;
    }
    if (!TV.essenceContextEngine || typeof TV.essenceContextEngine.processConversationContext !== "function") {
      sendResponse({
        success: false,
        error: "Essence module not loaded",
      });
      return false;
    }
    TV.essenceContextEngine.processConversationContext(message, sendResponse);
    return true;
  }

  if (action === "TV_OPEN_SIDE_PANEL") {
    if (!isAuthMessageSenderAllowed(sender) && !isHostPlatformContentScriptSender(sender)) {
      reply(sendResponse, message.requestId, false, null, {
        code: "UNAUTHORIZED_SENDER",
        message: "Unauthorized message sender",
        retryable: false,
      });
      return false;
    }
    // IMPORTANT: chrome.sidePanel.open() requires an active user-gesture
    // context. The first `await` in this handler consumes that gesture, so we
    // must kick off the open call synchronously (before any awaited work)
    // and only `await` its promise afterwards. Storage writes happen in
    // parallel so they do not push the open call past the gesture window.
    const requestId = message.requestId || null;
    const payload = message.payload && typeof message.payload === "object" ? message.payload : {};
    const prompt = typeof payload.prompt === "string" ? payload.prompt.trim() : "";
    let platform = typeof payload.platform === "string" ? payload.platform.trim() : "";
    if (!platform && sender.tab && sender.tab.url && TV.hostContext) {
      const detected = TV.hostContext.detectHostFromUrl(sender.tab.url);
      if (detected) platform = detected.hostKey;
    }
    const targetRaw = typeof payload.target === "string" ? payload.target.trim().toLowerCase() : "enhance";
    const target =
      targetRaw === "library" || targetRaw === "voice" || targetRaw === "enhance" ? targetRaw : "enhance";

    let openPromise;
    try {
      openPromise = beginOpenSidePanelForSender(sender);
    } catch (error) {
      console.error("[Velocity Sidebar] TV_OPEN_SIDE_PANEL begin failed:", error);
      reply(sendResponse, requestId, false, null, {
        code: "SIDE_PANEL_OPEN_FAILED",
        message: error.message || String(error),
        retryable: false,
      });
      return false;
    }

    const patch = {
      velocity_button_pending_at: Date.now(),
      velocity_button_nav_target: target,
    };
    if (prompt) {
      patch.velocity_button_pending_prompt = prompt;
      patch.velocity_button_pending_platform = platform;
    }
    // Session hand-off bundle from the in-page Improve modal. When the modal
    // sends along the already-enhanced result we persist it here so the side
    // panel can render the Output view directly — no re-enhance, no usage tick.
    const originalText =
      typeof payload.original === "string" ? payload.original.trim() : "";
    const enhancedText =
      typeof payload.enhanced === "string" ? payload.enhanced.trim() : "";
    const sessionMode =
      typeof payload.mode === "string" ? payload.mode.trim() : "";
    if (originalText) patch.velocity_button_pending_original = originalText;
    if (enhancedText) patch.velocity_button_pending_enhanced = enhancedText;
    if (sessionMode) patch.velocity_button_pending_mode = sessionMode;
    if (platform) {
      patch.velocity_active_host_platform = platform;
    }

    (async () => {
      try {
        await Promise.all([openPromise, chrome.storage.local.set(patch)]);
        console.log("[Velocity Sidebar] TV_OPEN_SIDE_PANEL ok", {
          target,
          platform: platform || "(none)",
          promptLen: prompt.length,
        });
        reply(sendResponse, requestId, true, { opened: true }, null);
      } catch (error) {
        console.error("[Velocity Sidebar] TV_OPEN_SIDE_PANEL failed:", error);
        reply(sendResponse, requestId, false, null, {
          code: "SIDE_PANEL_OPEN_FAILED",
          message: error.message || String(error),
          retryable: false,
        });
      }
    })();
    return true;
  }

  if (action === "TV_OPEN_HOSTED_PAGE") {
    const requestId = message.requestId || null;
    if (!isAuthMessageSenderAllowed(sender) && !isHostPlatformContentScriptSender(sender)) {
      reply(sendResponse, requestId, false, null, {
        code: "UNAUTHORIZED_SENDER",
        message: "Unauthorized message sender",
        retryable: false,
      });
      return false;
    }
    try {
      const path = message.payload && message.payload.path;
      if (!TV.thinkvelocityUrls.isSafeHostedPath(path)) {
        reply(sendResponse, requestId, false, null, {
          code: "INVALID_PATH",
          message: "Invalid or disallowed path",
          retryable: false,
        });
        return false;
      }
      const url = TV.thinkvelocityUrls.buildThinkVelocityUrl(path, {
        platform: (message.payload && message.payload.platform) || "sidebar",
        campaign: (message.payload && message.payload.utmCampaign) || "platform_tracking",
        content: (message.payload && message.payload.utmContent) || "sidebar_navigation",
      });
      chrome.tabs.create({ url }, () => {
        reply(sendResponse, requestId, true, { opened: true, url }, null);
      });
    } catch (error) {
      reply(sendResponse, requestId, false, null, {
        code: "OPEN_TAB_FAILED",
        message: error.message || String(error),
        retryable: true,
      });
    }
    return true;
  }

  if (action === "TV_FETCH_PACKAGED_RESOURCE") {
    if (!isHostPlatformContentScriptSender(sender)) {
      reply(sendResponse, message.requestId, false, null, {
        code: "UNAUTHORIZED_SENDER",
        message: "Unauthorized message sender",
        retryable: false,
      });
      return false;
    }
    (async () => {
      const rid = message.requestId || null;
      try {
        const path = String((message.payload && message.payload.path) || "");
        const allowed = [
          "assets/Extension videos/tutorialvideo_step1.mp4",
          "assets/Extension videos/tutorialvideo_step2.mp4",
          "assets/Extension videos/tutorialvideo_step3.mp4",
        ];
        if (allowed.indexOf(path) === -1) {
          reply(sendResponse, rid, false, null, {
            code: "PATH_NOT_ALLOWED",
            message: "Resource not whitelisted",
            retryable: false,
          });
          return;
        }
        const res = await fetch(chrome.runtime.getURL(path));
        if (!res.ok) {
          reply(sendResponse, rid, false, null, {
            code: "FETCH_FAILED",
            message: "HTTP " + res.status,
            retryable: true,
          });
          return;
        }
        const buf = await res.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let binary = "";
        const CHUNK = 0x8000;
        for (let i = 0; i < bytes.length; i += CHUNK) {
          binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
        }
        const mime = res.headers.get("content-type") || "video/mp4";
        reply(sendResponse, rid, true, { base64: btoa(binary), mime, size: bytes.length }, null);
      } catch (error) {
        reply(sendResponse, rid, false, null, {
          code: "FETCH_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  const hostInjectionActions =
    isHostPlatformContentScriptSender(sender) &&
    [
      "TV_CONSUMER_ENHANCE",
      "TV_CONSUMER_CLARIFY",
      "TV_CONSUMER_REFINE",
      "TV_AUTH_GET_SNAPSHOT",
      "TV_AUTH_OPEN_LOGIN",
      "TV_CONSUMER_LIST_ENHANCED_PROMPTS",
      "TV_FETCH_PACKAGED_RESOURCE",
    ].includes(action);

  if (!isAuthMessageSenderAllowed(sender) && !hostInjectionActions) {
    reply(sendResponse, message.requestId, false, null, {
      code: "UNAUTHORIZED_SENDER",
      message: "Unauthorized message sender",
      retryable: false,
    });
    return false;
  }

  const requestId = message.requestId || null;

  if (action === "storeUserData") {
    (async () => {
      try {
        const tokenPayload = {};
        if (message.token) tokenPayload.accessToken = message.token;
        if (message.refreshToken) tokenPayload.refreshToken = message.refreshToken;
        if (Object.keys(tokenPayload).length) {
          await TV.tokenManager.storeAuthTokens(tokenPayload);
        }
        const profilePatch = {
          userName: message.userName,
          userId: message.userId,
          userEmail: message.userEmail,
          FreeUser: false,
          showLoginWelcome: false,
        };
        const flowRaw = message.sidebarFlow != null ? message.sidebarFlow : message.appFlow;
        if (flowRaw != null && String(flowRaw).trim() !== "") {
          profilePatch[TV.STORAGE_KEYS.SIDEBAR_FLOW] = TV.normalizeSidebarFlow(flowRaw);
        }
        await TV.chromeStorage.set(profilePatch);
        await TV.localStorageSync.syncChromeStorageToLocalStorage();
        if (message.userId && (message.token || message.accessToken)) {
          const accessToken =
            message.token || message.accessToken || (await TV.tokenManager.ensureFreshAccessToken(false));
          if (accessToken) {
            await fetchUserStatus(message.userId, accessToken, { force: true });
          }
        }
        reply(sendResponse, requestId, true, { stored: true }, null);
        // After a successful sign-in via the hosted page, automatically
        // reopen the side panel that the welcome view closed when the user
        // tapped Sign up / Login. This runs in the user-gesture context of
        // the incoming runtime message, so chrome.sidePanel.open is allowed.
        reopenSidePanelAfterLogin(sender).catch((err) => {
          console.warn("[Sidebar_extension] reopenSidePanelAfterLogin failed:", err);
        });
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "STORE_USER_FAILED",
          message: error.message || String(error),
          retryable: false,
        });
      }
    })();
    return true;
  }

  if (action === "clearUserData") {
    (async () => {
      try {
        await TV.tokenManager.clearAuthTokens();
        await TV.chromeStorage.remove([
          "accessToken",
          "refreshToken",
          "accessTokenExpiresAt",
          "refreshTokenExpiresAt",
          TV.STORAGE_KEYS.USER_NAME,
          TV.STORAGE_KEYS.USER_ID,
          TV.STORAGE_KEYS.USER_EMAIL,
          TV.STORAGE_KEYS.FREE_USER,
          TV.STORAGE_KEYS.SIDEBAR_FLOW,
          TV.STORAGE_KEYS.SUBSCRIPTION_STATUS,
          TV.STORAGE_KEYS.SUBSCRIPTION_STATUS_AT,
          TV.STORAGE_KEYS.REMAINING_USAGE,
          TV.STORAGE_KEYS.USAGE_LIMIT,
        ]);
        reply(sendResponse, requestId, true, { cleared: true }, null);
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "CLEAR_USER_FAILED",
          message: error.message || String(error),
          retryable: false,
        });
      }
    })();
    return true;
  }

  if (action === "TV_AUTH_GET_SNAPSHOT") {
    (async () => {
      try {
        const force = Boolean(message.payload && message.payload.force);
        const data = await getAuthSnapshotPayload({ force });
        reply(sendResponse, requestId, true, data, null);
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "SNAPSHOT_FAILED",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_AUTH_LOGOUT") {
    (async () => {
      try {
        await TV.tokenManager.clearAuthTokens();
        await TV.chromeStorage.remove([
          "accessToken",
          "refreshToken",
          "accessTokenExpiresAt",
          "refreshTokenExpiresAt",
          TV.STORAGE_KEYS.USER_NAME,
          TV.STORAGE_KEYS.USER_ID,
          TV.STORAGE_KEYS.USER_EMAIL,
          TV.STORAGE_KEYS.FREE_USER,
          TV.STORAGE_KEYS.SIDEBAR_FLOW,
          TV.STORAGE_KEYS.SUBSCRIPTION_STATUS,
          TV.STORAGE_KEYS.SUBSCRIPTION_STATUS_AT,
          TV.STORAGE_KEYS.REMAINING_USAGE,
          TV.STORAGE_KEYS.USAGE_LIMIT,
        ]);
        const data = await getAuthSnapshotPayload();
        reply(sendResponse, requestId, true, data, null);
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "LOGOUT_FAILED",
          message: error.message || String(error),
          retryable: false,
        });
      }
    })();
    return true;
  }

  if (action === "TV_AUTH_OPEN_LOGIN") {
    (async () => {
      try {
        const raw =
          (message.payload && message.payload.intendedSidebarFlow) ||
          message.intendedSidebarFlow;
        if (raw != null && String(raw).trim() !== "") {
          await TV.chromeStorage.set({
            [TV.STORAGE_KEYS.SIDEBAR_FLOW]: TV.normalizeSidebarFlow(raw),
          });
        }
        chrome.tabs.create({ url: buildLoginUrl("/login") }, () => {
          reply(sendResponse, requestId, true, { opened: true }, null);
        });
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "OPEN_TAB_FAILED",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONSUMER_ENHANCE") {
    (async () => {
      try {
        if (!TV.consumerEnhanceFlow || typeof TV.consumerEnhanceFlow.runEnhance !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "ENHANCE_MODULE_MISSING",
            message:
              "Enhance module did not load. Reload the extension and ensure features/consumer-enhance-flow.js is present.",
            retryable: false,
          });
          return;
        }
        const payload = message.payload || {};
        const prompt = payload.prompt;
        const mode = payload.mode || "standard";
        if (!prompt || typeof prompt !== "string" || !prompt.trim()) {
          reply(sendResponse, requestId, false, null, {
            code: "INVALID_PROMPT",
            message: "Prompt is required",
            retryable: false,
          });
          return;
        }
        const keys = TV.STORAGE_KEYS;
        const authRow = await TV.chromeStorage.get([keys.USER_ID, "accessToken"]);
        const enhanceUserId = authRow[keys.USER_ID] || "";
        const enhanceToken = authRow.accessToken || "";
        if (enhanceUserId && enhanceToken) {
          const usageSnap = await fetchUserStatus(enhanceUserId, enhanceToken, { force: true });
          const gateSnap = {
            isLoggedIn: true,
            subscriptionStatus: usageSnap.subscriptionStatus,
            remainingUsage: usageSnap.remainingUsage,
          };
          if (TV.usageAccess && typeof TV.usageAccess.isUsageExhausted === "function") {
            if (TV.usageAccess.isUsageExhausted(gateSnap)) {
              reply(sendResponse, requestId, false, null, {
                code: "USAGE_EXHAUSTED",
                message: "You have run out of free prompts. Upgrade to Pro for unlimited access.",
                retryable: false,
              });
              return;
            }
          }
        }
        const result = await TV.consumerEnhanceFlow.runEnhance({
          prompt: prompt.trim(),
          mode,
          platform: "extension",
        });
        if (result.success) {
          if (enhanceUserId && enhanceToken) {
            await decrementStoredUsage();
          }
          reply(sendResponse, requestId, true, result.data || {}, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "ENHANCE_FAILED",
            message: result.error || "Enhancement failed",
            retryable: false,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "ENHANCE_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONSUMER_LIST_COLLECTIONS") {
    (async () => {
      try {
        if (!TV.consumerLibraryFetch || typeof TV.consumerLibraryFetch.listCollections !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "LIBRARY_MODULE_MISSING",
            message: "Library module did not load.",
            retryable: false,
          });
          return;
        }
        const result = await TV.consumerLibraryFetch.listCollections();
        if (result.success) {
          reply(sendResponse, requestId, true, result.data || {}, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "COLLECTIONS_FAILED",
            message: result.error || "Failed to load collections",
            retryable: true,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "COLLECTIONS_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONSUMER_LIST_ENHANCED_PROMPTS") {
    (async () => {
      try {
        if (!TV.consumerLibraryFetch || typeof TV.consumerLibraryFetch.listEnhancedPrompts !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "LIBRARY_MODULE_MISSING",
            message: "Library module did not load.",
            retryable: false,
          });
          return;
        }
        const payload = message.payload || {};
        const result = await TV.consumerLibraryFetch.listEnhancedPrompts(payload.page, payload.limit);
        if (result.success) {
          reply(sendResponse, requestId, true, result.data || {}, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "PROMPTS_FAILED",
            message: result.error || "Failed to load prompts",
            retryable: true,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "PROMPTS_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONSUMER_CREATE_COLLECTION") {
    (async () => {
      try {
        if (!TV.consumerLibraryFetch || typeof TV.consumerLibraryFetch.createCollection !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "LIBRARY_MODULE_MISSING",
            message: "Library module did not load.",
            retryable: false,
          });
          return;
        }
        const payload = message.payload || {};
        const name = payload.name;
        if (!name || typeof name !== "string" || !String(name).trim()) {
          reply(sendResponse, requestId, false, null, {
            code: "INVALID_NAME",
            message: "Collection name is required",
            retryable: false,
          });
          return;
        }
        const result = await TV.consumerLibraryFetch.createCollection(String(name).trim());
        if (result.success) {
          reply(sendResponse, requestId, true, result.data || {}, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "CREATE_COLLECTION_FAILED",
            message: result.error || "Failed to create collection",
            retryable: false,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "CREATE_COLLECTION_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONSUMER_LIST_MEMORIES") {
    (async () => {
      try {
        if (!TV.consumerLibraryFetch || typeof TV.consumerLibraryFetch.listMemories !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "LIBRARY_MODULE_MISSING",
            message: "Library module did not load.",
            retryable: false,
          });
          return;
        }
        const payload = message.payload || {};
        const result = await TV.consumerLibraryFetch.listMemories(payload.page, payload.limit);
        if (result.success) {
          reply(sendResponse, requestId, true, result.data || {}, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "MEMORIES_FAILED",
            message: result.error || "Failed to load memories",
            retryable: true,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "MEMORIES_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONSUMER_UPDATE_MEMORY") {
    (async () => {
      try {
        if (!TV.consumerLibraryFetch || typeof TV.consumerLibraryFetch.updateMemoryEssence !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "LIBRARY_MODULE_MISSING",
            message: "Library module did not load.",
            retryable: false,
          });
          return;
        }
        const result = await TV.consumerLibraryFetch.updateMemoryEssence(message.payload || {});
        if (result.success) {
          reply(sendResponse, requestId, true, result.data || {}, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "MEMORY_UPDATE_FAILED",
            message: result.error || "Failed to update memory",
            retryable: true,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "MEMORY_UPDATE_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONSUMER_DELETE_MEMORY") {
    (async () => {
      try {
        if (!TV.consumerLibraryFetch || typeof TV.consumerLibraryFetch.deleteMemoryEssence !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "LIBRARY_MODULE_MISSING",
            message: "Library module did not load.",
            retryable: false,
          });
          return;
        }
        const result = await TV.consumerLibraryFetch.deleteMemoryEssence(message.payload || {});
        if (result.success) {
          reply(sendResponse, requestId, true, result.data || {}, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "MEMORY_DELETE_FAILED",
            message: result.error || "Failed to delete memory",
            retryable: true,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "MEMORY_DELETE_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONSUMER_CREATE_MEMORY") {
    (async () => {
      try {
        if (!TV.consumerLibraryFetch || typeof TV.consumerLibraryFetch.createMemoryEssence !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "LIBRARY_MODULE_MISSING",
            message: "Library module did not load.",
            retryable: false,
          });
          return;
        }
        const result = await TV.consumerLibraryFetch.createMemoryEssence(message.payload || {});
        if (result.success) {
          reply(sendResponse, requestId, true, result.data || {}, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "MEMORY_CREATE_FAILED",
            message: result.error || "Failed to create memory",
            retryable: true,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "MEMORY_CREATE_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_EXTRACT_PAGE_CONTEXT") {
    (async () => {
      try {
        let tabId = message.payload && message.payload.tabId;
        if (tabId == null) {
          const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
          tabId = tabs[0] && tabs[0].id;
        }
        if (tabId == null) {
          reply(sendResponse, requestId, false, null, {
            code: "NO_TAB",
            message: "No active tab",
            retryable: false,
          });
          return;
        }
        const tab = await chrome.tabs.get(tabId);
        if (!canExtractPageContextFromUrl(tab.url || "")) {
          reply(sendResponse, requestId, false, null, {
            code: "URL_NOT_ALLOWED",
            message: "This page cannot be accessed. Open a regular http(s) page and try again.",
            retryable: false,
          });
          return;
        }
        const [injected] = await chrome.scripting.executeScript({
          target: { tabId },
          func: pageContextExtractFn,
        });
        const data = injected && injected.result;
        if (!data) {
          reply(sendResponse, requestId, false, null, {
            code: "NO_DATA",
            message: "No data returned from page",
            retryable: false,
          });
          return;
        }
        
        const extractUrl = "https://api.thinkvelocity.in/extract/html";
        
        const response = await fetch(extractUrl, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({html: data.html || ""})
        });
        
        if (!response.ok) {
            throw new Error(`Failed to extract page context via API: ${response.statusText}`);
        }
        
        const jsonResult = await response.json();
        data.extractedText = jsonResult.markdown || "";
        delete data.html; // remove HTML so we don't send huge payloads to the UI
        
        reply(sendResponse, requestId, true, data, null);
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "EXTRACT_FAILED",
          message: "try after sometime",
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONTEXT_CAPTURE") {
    (async () => {
      try {
        if (!TV.extensionContextApi || typeof TV.extensionContextApi.postContextCapture !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "CONTEXT_API_MISSING",
            message: "Context capture module did not load.",
            retryable: false,
          });
          return;
        }
        const payload = (message.payload && message.payload.body) || message.payload || {};
        const result = await TV.extensionContextApi.postContextCapture(payload);
        if (result.success) {
          reply(sendResponse, requestId, true, result.data || {}, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "CONTEXT_CAPTURE_FAILED",
            message: result.error || "Capture failed",
            retryable: true,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "CONTEXT_CAPTURE_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONSUMER_CLARIFY") {
    (async () => {
      try {
        if (!TV.consumerClarifyRefine || typeof TV.consumerClarifyRefine.clarify !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "CLARIFY_MODULE_MISSING",
            message: "Clarify module did not load.",
            retryable: false,
          });
          return;
        }
        const payload = message.payload || {};
        const result = await TV.consumerClarifyRefine.clarify(payload.original, payload.enhanced);
        if (result.success) {
          reply(sendResponse, requestId, true, result.data || {}, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "CLARIFY_FAILED",
            message: result.error || "Clarify failed",
            retryable: true,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "CLARIFY_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONSUMER_REFINE") {
    (async () => {
      try {
        if (!TV.consumerClarifyRefine || typeof TV.consumerClarifyRefine.refine !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "REFINE_MODULE_MISSING",
            message: "Refine module did not load.",
            retryable: false,
          });
          return;
        }
        const payload = message.payload || {};
        const result = await TV.consumerClarifyRefine.refine(
          payload.original,
          payload.enhanced,
          payload.qaArray
        );
        if (result.success) {
          reply(sendResponse, requestId, true, result.data || {}, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "REFINE_FAILED",
            message: result.error || "Refine failed",
            retryable: true,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "REFINE_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_GET_ACTIVE_HOST_CONTEXT") {
    (async () => {
      try {
        const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
        const tab = tabs && tabs[0];
        const url = (tab && tab.url) || "";
        let ctx =
          TV.hostContext && typeof TV.hostContext.detectHostFromUrl === "function"
            ? TV.hostContext.detectHostFromUrl(url)
            : null;
        if (!ctx) {
          const stored = await chrome.storage.local.get(["velocity_active_host_platform"]);
          const key = String(stored.velocity_active_host_platform || "").trim();
          if (key && TV.hostContext && TV.hostContext.HOST_RULES) {
            const rule = TV.hostContext.HOST_RULES.find((r) => r.hostKey === key);
            if (rule) {
              ctx = {
                hostKey: rule.hostKey,
                aiType: rule.aiType,
                openInKey: rule.openInKey,
                label: rule.label,
                platformFeedId: `pl-${rule.aiType}`,
              };
            }
          }
        } else {
          await chrome.storage.local.set({ velocity_active_host_platform: ctx.hostKey }).catch(() => {});
        }
        reply(sendResponse, requestId, true, { context: ctx, tabUrl: url || null }, null);
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "HOST_CONTEXT_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONSUMER_INSERT_ACTIVE_TAB") {
    (async () => {
      try {
        if (!TV.consumerPlatformInject || typeof TV.consumerPlatformInject.injectActiveTab !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "INJECT_MODULE_MISSING",
            message: "Platform inject module did not load.",
            retryable: false,
          });
          return;
        }
        const payload = message.payload || {};
        const prompt = payload.prompt;
        if (!prompt || typeof prompt !== "string" || !prompt.trim()) {
          reply(sendResponse, requestId, false, null, {
            code: "INVALID_PROMPT",
            message: "Prompt is required",
            retryable: false,
          });
          return;
        }
        // The gold insert glow is a Pro-tier flourish; the side panel passes
        // `isPro` from its auth snapshot so the content-script animation only
        // runs for paying users.
        const isPro = Boolean(payload.isPro);
        const result = await TV.consumerPlatformInject.injectActiveTab(prompt, { isPro });
        if (result.success) {
          reply(sendResponse, requestId, true, result, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "INSERT_FAILED",
            message: result.error || "Insert failed",
            retryable: false,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "INSERT_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONSUMER_OPEN_IN_PLATFORM") {
    (async () => {
      try {
        if (!TV.consumerPlatformInject || typeof TV.consumerPlatformInject.openInPlatform !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "OPEN_IN_MODULE_MISSING",
            message: "Platform open module did not load.",
            retryable: false,
          });
          return;
        }
        const payload = message.payload || {};
        const prompt = payload.prompt;
        const platformKey = payload.platformKey || payload.platform || "openai";
        if (!prompt || typeof prompt !== "string" || !prompt.trim()) {
          reply(sendResponse, requestId, false, null, {
            code: "INVALID_PROMPT",
            message: "Prompt is required",
            retryable: false,
          });
          return;
        }
        const isPro = Boolean(payload.isPro);
        const result = await TV.consumerPlatformInject.openInPlatform(prompt, platformKey, { isPro });
        if (result.success) {
          reply(sendResponse, requestId, true, result, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "OPEN_IN_FAILED",
            message: result.error || "Open in failed",
            retryable: false,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "OPEN_IN_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONSUMER_FEEDBACK") {
    (async () => {
      try {
        if (!TV.consumerClarifyRefine || typeof TV.consumerClarifyRefine.sendFeedback !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "FEEDBACK_MODULE_MISSING",
            message: "Feedback module did not load.",
            retryable: false,
          });
          return;
        }
        const payload = message.payload || {};
        const result = await TV.consumerClarifyRefine.sendFeedback(
          payload.promptId,
          payload.feedback,
          payload.mode,
          payload.isRefine
        );
        if (result.success) {
          reply(sendResponse, requestId, true, result.data || {}, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "FEEDBACK_FAILED",
            message: result.error || "Feedback failed",
            retryable: false,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "FEEDBACK_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_CONSUMER_SUBMIT_FEEDBACK") {
    (async () => {
      try {
        if (!TV.consumerClarifyRefine || typeof TV.consumerClarifyRefine.submitWrittenFeedback !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "FEEDBACK_MODULE_MISSING",
            message: "Feedback module did not load.",
            retryable: false,
          });
          return;
        }
        const payload = message.payload || {};
        const result = await TV.consumerClarifyRefine.submitWrittenFeedback(
          payload.feedback,
          payload.reason,
          payload.source
        );
        if (result.success) {
          reply(sendResponse, requestId, true, result.data || {}, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: "FEEDBACK_FAILED",
            message: result.error || "Feedback failed",
            retryable: false,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "FEEDBACK_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_QUERY_SIDE_PANEL_STATE") {
    // Host-platform content scripts query this on mount so the launcher pill
    // can sync its glow with the current side-panel state without waiting for
    // the next open/close transition broadcast.
    if (!isHostPlatformContentScriptSender(sender)) {
      reply(sendResponse, message.requestId, false, null, {
        code: "UNAUTHORIZED_SENDER",
        message: "Unauthorized message sender",
        retryable: false,
      });
      return false;
    }
    const open =
      TV.sidePanelLifecycle && typeof TV.sidePanelLifecycle.isPanelOpen === "function"
        ? Boolean(TV.sidePanelLifecycle.isPanelOpen())
        : false;
    reply(sendResponse, message.requestId, true, { open }, null);
    return false;
  }

  if (action === "TV_OFFSCREEN_VOICE_START") {
    if (!TV.offscreenVoiceBridge || typeof TV.offscreenVoiceBridge.panelStart !== "function") {
      reply(sendResponse, requestId, false, null, {
        code: "VOICE_BRIDGE_MISSING",
        message: "Voice capture module did not load.",
        retryable: false,
      });
      return false;
    }
    const rid = message.requestId || null;
    (async () => {
      try {
        await TV.offscreenVoiceBridge.panelStart(rid, sendResponse, reply);
      } catch (error) {
        reply(sendResponse, rid, false, null, {
          code: "VOICE_START_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_OFFSCREEN_VOICE_STOP") {
    if (!TV.offscreenVoiceBridge || typeof TV.offscreenVoiceBridge.panelStop !== "function") {
      reply(sendResponse, requestId, false, null, {
        code: "VOICE_BRIDGE_MISSING",
        message: "Voice capture module did not load.",
        retryable: false,
      });
      return false;
    }
    const rid = message.requestId || null;
    (async () => {
      try {
        await TV.offscreenVoiceBridge.panelStop(rid, sendResponse, reply, message.payload || {});
      } catch (error) {
        reply(sendResponse, rid, false, null, {
          code: "VOICE_STOP_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_ENTERPRISE_LOGIN_SUCCESS") {
    (async () => {
      try {
        const p = message.payload || {};
        const SK = TV.STORAGE_KEYS;
        const expiresIn = Number(p.expiresIn) || 900;
        const user = p.user || {};
        if (!p.accessToken || typeof p.accessToken !== "string" ||
            !p.refreshToken || typeof p.refreshToken !== "string") {
          reply(sendResponse, requestId, false, null, {
            code: "ENT_LOGIN_INVALID_PAYLOAD",
            message: "Login payload missing accessToken or refreshToken",
            retryable: false,
          });
          return;
        }
        await TV.chromeStorage.set({
          [SK.ENT_ACCESS_TOKEN]:  p.accessToken,
          [SK.ENT_REFRESH_TOKEN]: p.refreshToken,
          [SK.ENT_ACCESS_EXP]:    Date.now() + expiresIn * 1000,
          [SK.ENT_USER_ID]:       user.id || "",
          [SK.ENT_ENTERPRISE_ID]: user.enterpriseId || "",
          [SK.ENT_USER_NAME]:     user.name || "",
          [SK.ENT_USER_EMAIL]:    user.email || "",
          [SK.ENT_ROLE_TYPES]:    user.roleTypes || [],
          [SK.SIDEBAR_FLOW]:      "enterprise",
        });
        const conTokens = await TV.chromeStorage.get(["accessToken", "refreshToken"]);
        const hasConsumer = Boolean(conTokens.accessToken || conTokens.refreshToken);
        _activeMode = "enterprise";
        if (TV.tokenManager) TV.tokenManager.getActiveMode = () => _activeMode;
        const sessionState =
          TV.computeSessionState && typeof TV.computeSessionState === "function"
            ? TV.computeSessionState(hasConsumer, true)
            : "enterprise_only";
        reply(sendResponse, requestId, true, { sessionState }, null);
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "ENT_LOGIN_STORE_FAILED",
          message: error.message || String(error),
          retryable: false,
        });
      }
    })();
    return true;
  }

  if (action === "TV_ENTERPRISE_LOGOUT") {
    (async () => {
      try {
        const SK = TV.STORAGE_KEYS;
        try {
          const stored = await TV.tokenManager.getEntStoredTokens();
          if (stored.accessToken && stored.refreshToken) {
            await fetch("https://velocityenterprise.toteminteractive.in/backend/auth/logout", {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${stored.accessToken}`,
              },
              body: JSON.stringify({ refreshToken: stored.refreshToken }),
            });
          }
        } catch (_) {}
        await TV.tokenManager.clearEnterpriseTokens();
        const newFlow = "consumer";
        await TV.chromeStorage.set({ [SK.SIDEBAR_FLOW]: newFlow });
        _activeMode = newFlow;
        if (TV.tokenManager) TV.tokenManager.getActiveMode = () => _activeMode;
        reply(sendResponse, requestId, true, { loggedOut: true, newFlow }, null);
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "ENT_LOGOUT_FAILED",
          message: error.message || String(error),
          retryable: false,
        });
      }
    })();
    return true;
  }

  if (action === "TV_ENTERPRISE_MODE_SWITCH") {
    (async () => {
      try {
        const rawFlow = message.payload && message.payload.flow;
        if (rawFlow !== "consumer" && rawFlow !== "enterprise") {
          reply(sendResponse, requestId, false, null, {
            code: "ENT_MODE_SWITCH_INVALID_FLOW",
            message: "flow must be 'consumer' or 'enterprise'",
            retryable: false,
          });
          return;
        }
        const targetFlow = rawFlow;
        if (targetFlow === "enterprise") {
          const entTokens = await TV.tokenManager.getEntStoredTokens();
          if (!entTokens.accessToken && !entTokens.refreshToken) {
            reply(sendResponse, requestId, false, null, {
              code: "ENT_MODE_SWITCH_NO_TOKENS",
              message: "Cannot switch to enterprise mode: no enterprise session found",
              retryable: false,
            });
            return;
          }
        }
        await TV.chromeStorage.set({ [TV.STORAGE_KEYS.SIDEBAR_FLOW]: targetFlow });
        _activeMode = targetFlow;
        if (TV.tokenManager) TV.tokenManager.getActiveMode = () => _activeMode;
        reply(sendResponse, requestId, true, { flow: targetFlow }, null);
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "ENT_MODE_SWITCH_FAILED",
          message: error.message || String(error),
          retryable: false,
        });
      }
    })();
    return true;
  }

  if (action === "TV_ENTERPRISE_GET_TOKEN") {
    (async () => {
      try {
        const accessToken = await TV.tokenManager.ensureFreshEnterpriseToken();
        const SK = TV.STORAGE_KEYS;
        const stored = await TV.chromeStorage.get([SK.ENT_ENTERPRISE_ID, SK.ENT_USER_ID]);
        reply(sendResponse, requestId, true, {
          accessToken,
          enterpriseId: stored[SK.ENT_ENTERPRISE_ID] || "",
          userId:       stored[SK.ENT_USER_ID]       || "",
        }, null);
      } catch (err) {
        reply(sendResponse, requestId, false, null, {
          code:      err.message === "ENT_NO_TOKENS" ? "ENT_NO_TOKENS" : "ENT_TOKEN_ERROR",
          message:   err.message || "Failed to get enterprise token",
          retryable: false,
        });
      }
    })();
    return true;
  }

  if (action === "TV_ENTERPRISE_GET_HISTORY") {
    (async () => {
      try {
        const accessToken = await TV.tokenManager.ensureFreshEnterpriseToken();
        const SK = TV.STORAGE_KEYS;
        const stored = await TV.chromeStorage.get([SK.ENT_USER_ID]);
        const userId = stored[SK.ENT_USER_ID] || "";
        if (!userId) {
          reply(sendResponse, requestId, false, null, {
            code: "ENT_NO_USER_ID", message: "No user ID in storage", retryable: false,
          });
          return;
        }
        const res = await fetch(
          `https://velocityenterprise.toteminteractive.in/backend/prompt/enhanced-prompts/user/${encodeURIComponent(userId)}?limit=20`,
          { headers: { Authorization: `Bearer ${accessToken}` } }
        );
        if (!res.ok) {
          const msg = await res.text().catch(() => "");
          reply(sendResponse, requestId, false, null, {
            code: "ENT_HISTORY_FAILED", message: `${res.status} ${msg}`, retryable: res.status >= 500,
          });
          return;
        }
        const body = await res.json();
        const prompts = Array.isArray(body) ? body : (body.data || body.prompts || []);
        reply(sendResponse, requestId, true, { prompts }, null);
      } catch (err) {
        reply(sendResponse, requestId, false, null, {
          code: "ENT_HISTORY_ERROR", message: err.message || String(err), retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_ENTERPRISE_CHECK_APPROVAL") {
    (async () => {
      try {
        const SK = TV.STORAGE_KEYS;
        const stored = await TV.chromeStorage.get([SK.ENT_PENDING_APPROVAL]);
        const pending = stored[SK.ENT_PENDING_APPROVAL];
        if (!pending) {
          reply(sendResponse, requestId, true, { status: "NONE" }, null);
          return;
        }
        if (!pending.queueId) {
          // Stored without a queueId — cannot check; report as pending.
          reply(sendResponse, requestId, true, { status: "PENDING" }, null);
          return;
        }
        const accessToken = await TV.tokenManager.ensureFreshEnterpriseToken();
        const res = await fetch(
          `https://velocityenterprise.toteminteractive.in/backend/guardrail/approvals/${encodeURIComponent(pending.queueId)}`,
          { headers: { Authorization: `Bearer ${accessToken}` } }
        );
        if (!res.ok) {
          const msg = await res.text().catch(() => "");
          reply(sendResponse, requestId, false, null, {
            code: "ENT_APPROVAL_CHECK_FAILED", message: `${res.status} ${msg}`, retryable: true,
          });
          return;
        }
        const data = await res.json();
        const status = (data.status || "PENDING").toUpperCase();
        // Clear storage when the decision is final.
        if (status === "APPROVED" || status === "REJECTED") {
          await TV.chromeStorage.remove(SK.ENT_PENDING_APPROVAL);
        }
        reply(sendResponse, requestId, true, {
          status,
          originalPrompt: pending.promptExcerpt || "",
        }, null);
      } catch (err) {
        reply(sendResponse, requestId, false, null, {
          code: "ENT_APPROVAL_CHECK_ERROR", message: err.message || String(err), retryable: true,
        });
      }
    })();
    return true;
  }

  if (action === "TV_ENTERPRISE_ENHANCE") {
    (async () => {
      try {
        if (!TV.enterpriseEnhanceFlow || typeof TV.enterpriseEnhanceFlow.run !== "function") {
          reply(sendResponse, requestId, false, null, {
            code: "ENT_ENHANCE_MODULE_MISSING",
            message: "Enterprise enhance module did not load. Reload the extension.",
            retryable: false,
          });
          return;
        }
        const payload = message.payload || {};
        const prompt = payload.prompt;
        if (!prompt || typeof prompt !== "string" || !prompt.trim()) {
          reply(sendResponse, requestId, false, null, {
            code: "INVALID_PROMPT",
            message: "Prompt is required",
            retryable: false,
          });
          return;
        }
        const opts = {};
        if (payload.skipGuardrail) opts.skipGuardrail = true;
        if (typeof payload.useRedacted === "string") opts.useRedacted = payload.useRedacted;

        // guardrailOnly: skip SSE, return guardrail decision only (panel streams directly).
        if (payload.guardrailOnly) {
          if (typeof TV.enterpriseEnhanceFlow.runGuardrailOnly !== "function") {
            reply(sendResponse, requestId, false, null, {
              code: "ENT_ENHANCE_MODULE_MISSING",
              message: "runGuardrailOnly not available. Reload extension.",
              retryable: false,
            });
            return;
          }
          const grResult = await TV.enterpriseEnhanceFlow.runGuardrailOnly(prompt.trim(), opts);
          if (grResult.success) {
            reply(sendResponse, requestId, true, { guardrailPassed: true }, null);
          } else {
            reply(sendResponse, requestId, false, null, {
              code:      grResult.code || "ENT_ENHANCE_FAILED",
              message:   grResult.error || "Enhancement failed",
              guardrail: grResult.guardrail || null,
              retryable: false,
            });
          }
          return;
        }

        const result = await TV.enterpriseEnhanceFlow.run(prompt.trim(), opts);
        if (result.success) {
          reply(sendResponse, requestId, true, result.data, null);
        } else {
          reply(sendResponse, requestId, false, null, {
            code: result.code || "ENT_ENHANCE_FAILED",
            message: result.error || "Enhancement failed",
            guardrail: result.guardrail || null,
            retryable: false,
          });
        }
      } catch (error) {
        reply(sendResponse, requestId, false, null, {
          code: "ENT_ENHANCE_ERROR",
          message: error.message || String(error),
          retryable: true,
        });
      }
    })();
    return true;
  }

  reply(sendResponse, requestId, false, null, {
    code: "UNKNOWN_ACTION",
    message: `Unknown action: ${action}`,
    retryable: false,
  });
  return false;
});

chrome.commands.onCommand.addListener(async (command) => {
  if (command === 'enhance_selected_text') {
    try {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      const activeTab = tabs[0];
      if (!activeTab || !activeTab.id) return;
      
      const [{ result }] = await chrome.scripting.executeScript({
        target: { tabId: activeTab.id },
        func: () => window.getSelection().toString().trim()
      });
      
      if (!result) return;

      await chrome.scripting.executeScript({
        target: { tabId: activeTab.id },
        func: () => typeof globalThis.VelocityInjectionModal !== 'undefined'
      }).then(async ([{ result: isLoaded }]) => {
        if (!isLoaded) {
          await chrome.scripting.insertCSS({
            target: { tabId: activeTab.id },
            files: [
              'button/css/velocity-theme.css',
              'button/css/injection-modal.css',
              'button/css/injection-popups.css'
            ]
          });
          await chrome.scripting.executeScript({
            target: { tabId: activeTab.id },
            files: [
              'content/velocity-host-debug.js',
              'features/thought-process-loader.js',
              'features/injection-pro-theme.js',
              'utils/prompt-format.js',
              'panel/consumer/structured-prompt-dom.js',
              'button/js/injection-popups.js',
              'button/js/injection-modal.js'
            ]
          });
        }
        
        await chrome.scripting.executeScript({
          target: { tabId: activeTab.id },
          func: (promptText) => {
            if (globalThis.VelocityInjectionModal) {
              globalThis.VelocityInjectionModal.open({ prompt: promptText });
            }
          },
          args: [result]
        });
      });
    } catch (err) {
      console.warn('[Velocity] hotkey enhancement failed:', err);
    }
  }
});

