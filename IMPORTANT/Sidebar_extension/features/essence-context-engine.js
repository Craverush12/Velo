/**
 * ContextEngine bulk sync from AI host tabs (ChatGPT, Claude, Gemini).
 * Handles processConversationContext from content/context-engine-bridge.js.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const CONTEXT_ENGINE_URL =
    "https://thinkvelocity.in/context-engine/api/process-context";
  const MAX_RETRIES = 3;
  const BASE_DELAY_MS = 1000;
  const FETCH_TIMEOUT_MS = 30000;

  function normalizePlatform(platform) {
    if (!platform) return "chatgpt";
    const normalized = String(platform).toLowerCase().trim();
    const map = { openai: "chatgpt", anthropic: "claude", google: "gemini" };
    return map[normalized] || normalized;
  }

  // ContextEngine's ExtensionSyncRequest schema declares accessTokenExpiresAt
  // as a string. chrome.storage.local stores it as an epoch-ms number (e.g.
  // 1779268855000), which Pydantic rejects with:
  //   "Input should be a valid string [type=string_type, input_value=...,
  //    input_type=int]"
  // Coerce numeric timestamps to ISO-8601 strings; pass strings through; null
  // when missing or invalid.
  function normalizeAccessTokenExpiresAt(value) {
    if (value == null) return null;
    if (typeof value === "string") {
      const trimmed = value.trim();
      return trimmed === "" ? null : trimmed;
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      try {
        return new Date(value).toISOString();
      } catch (e) {
        return String(value);
      }
    }
    return null;
  }

  function buildContextPayload(extractedData, userPatch) {
    const userId =
      userPatch.user_id ||
      extractedData.userId ||
      extractedData.user?.user_id ||
      extractedData.user_id ||
      "unknown_user";
    const userData = extractedData.user || {};
    const rawAccessTokenExpiresAt =
      userPatch.accessTokenExpiresAt ||
      userData.accessTokenExpiresAt ||
      null;

    return {
      sessionId:
        extractedData.sessionId || extractedData.session_id || "unknown_session",
      sessionStartedAt: Date.now(),
      exportedAt: Date.now(),
      platform: normalizePlatform(extractedData.platform),
      extractorVersion: extractedData.extractorVersion || "3.1.4",
      user: {
        user_id: userId,
        usage_left: userData.usage_left || extractedData.usage_left || 100,
        accessToken:
          userPatch.accessToken ||
          userData.accessToken ||
          userData.authToken ||
          null,
        accessTokenExpiresAt: normalizeAccessTokenExpiresAt(rawAccessTokenExpiresAt),
      },
      stats: extractedData.stats || {},
      conversations: [
        {
          chatId:
            extractedData.sessionId || extractedData.session_id || "unknown_session",
          title: extractedData.title || "Chat Conversation",
          url: extractedData.url || "",
          messages: (extractedData.messages || []).map((msg, index) => ({
            role: msg.role,
            content: msg.content,
            timestamp:
              typeof msg.timestamp === "string"
                ? msg.timestamp
                : msg.timestamp
                  ? new Date(msg.timestamp).toISOString()
                  : new Date().toISOString(),
            index,
            contentType: msg.contentType || "plain",
            images: msg.images || [],
            codeBlocks: msg.codeBlocks || [],
          })),
          model: extractedData.model || "gpt-4",
          updatedAt: Date.now(),
        },
      ],
    };
  }

  async function loadAuthPatch() {
    const patch = {};
    try {
      const stored = await chrome.storage.local.get([
        "userId",
        "accessToken",
        "accessTokenExpiresAt",
      ]);
      if (stored.userId != null && String(stored.userId).trim() !== "") {
        patch.user_id = String(stored.userId).trim();
      }
      if (stored.accessToken) {
        patch.accessToken = stored.accessToken;
        patch.accessTokenExpiresAt = stored.accessTokenExpiresAt || null;
      } else if (root.TV.tokenManager) {
        const tokens = await root.TV.tokenManager.getStoredTokens();
        if (tokens && tokens.accessToken) {
          patch.accessToken = tokens.accessToken;
          patch.accessTokenExpiresAt = tokens.accessTokenExpiresAt || null;
        }
      }
    } catch (e) {
      console.warn("[TV_ESSENCE] Could not load auth patch:", e);
    }
    return patch;
  }

  async function postContextEngine(contextPayload) {
    let lastError = null;
    let response = null;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

        response = await fetch(CONTEXT_ENGINE_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(contextPayload),
          signal: controller.signal,
        });

        clearTimeout(timeoutId);

        if (response.ok) break;

        const errorText = await response.text().catch(() => "Unknown error");
        lastError = new Error(`HTTP ${response.status}: ${errorText}`);

        if (
          response.status >= 400 &&
          response.status < 500 &&
          response.status !== 429
        ) {
          break;
        }

        if (attempt === MAX_RETRIES) break;

        const delay = BASE_DELAY_MS * Math.pow(2, attempt);
        await new Promise((r) => setTimeout(r, delay));
      } catch (fetchError) {
        lastError = fetchError;
        if (fetchError.name === "AbortError" || attempt === MAX_RETRIES) break;
        const delay = BASE_DELAY_MS * Math.pow(2, attempt);
        await new Promise((r) => setTimeout(r, delay));
      }
    }

    if (!response || !response.ok) {
      throw lastError || new Error("ContextEngine request failed");
    }

    return response.json();
  }

  async function markEssenceStored(sessionId) {
    const keys = root.TV.STORAGE_KEYS || {};
    const atKey = keys.ESSENCE_LAST_STORED_AT || "velocity_essence_last_stored_at";
    const sessionKey = keys.ESSENCE_LAST_SESSION || "velocity_essence_last_session";
    await chrome.storage.local.set({
      [atKey]: Date.now(),
      [sessionKey]: sessionId || "",
    });
  }

  async function processConversationContext(message, sendResponse) {
    try {
      const extractedData = message.extractedData;
      if (!extractedData) {
        sendResponse({ success: false, error: "No extracted data provided" });
        return;
      }

      const authPatch = await loadAuthPatch();
      const contextPayload = buildContextPayload(extractedData, authPatch);

      if (
        !contextPayload.user.user_id ||
        contextPayload.user.user_id === "unknown_user"
      ) {
        console.warn(
          "[TV_ESSENCE] Skipping sync — user not signed in (unknown_user)"
        );
        sendResponse({
          success: false,
          error: "Sign in to ThinkVelocity to save memory from this chat",
        });
        return;
      }

      const messages = contextPayload.conversations[0].messages;
      if (!messages || messages.length === 0) {
        console.warn("[TV_ESSENCE] No messages in payload");
        sendResponse({ success: false, error: "No messages to process" });
        return;
      }

      const result = await postContextEngine(contextPayload);
      await markEssenceStored(contextPayload.sessionId);
      if (root.TV.extractedConversationStore?.recordExtraction) {
        await root.TV.extractedConversationStore.recordExtraction(contextPayload);
      }
      console.log("[TV_ESSENCE] ✅ Context stored", {
        sessionId: contextPayload.sessionId,
        platform: contextPayload.platform,
        messageCount: messages.length,
      });

      sendResponse({ success: true, contextResult: result });
    } catch (error) {
      console.error("[TV_ESSENCE] Processing failed:", error);
      sendResponse({
        success: false,
        error: error.message || "Unknown error occurred",
      });
    }
  }

  root.TV.essenceContextEngine = {
    processConversationContext,
  };
})();
