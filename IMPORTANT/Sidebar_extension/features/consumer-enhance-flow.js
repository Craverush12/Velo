/**
 * Consumer enhance flow — mirrors Extension-new paths:
 * - POST backend-V1-D/prompt/user-prompt (API #1)
 * - Optional quality analyze (dev/test API)
 * - POST thinkvelocity.in/dev/test/enhance/stream (SSE data: lines)
 * - Intent/domain merged from stream payload when present (same fields as v-chat finalData)
 * - POST backend-V1-D/prompt/enhanced-prompt (API #2) when UUID prompt_id exists
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const BACKEND_URL = "https://thinkvelocity.in/backend-V1-D";
  const _API_BASE = "https://api.thinkvelocity.in";
  const ENHANCE_STREAM_URL = `${_API_BASE}/dev/test/enhance/stream`;
  const QUALITY_URL = `${_API_BASE}/dev/test/api/v1/quality/analyze-prompt`;
  const PERSONALIZATION_BASE = "https://thinkvelocity.in/backend-V1-D/api/personalization";
  const LOCAL_ANNOTATE_URL = "http://localhost:8000/enhance/annotate";

  function isValidUUID(v) {
    return (
      typeof v === "string" &&
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v)
    );
  }

  function modeToApi(mode) {
    const m = (mode || "standard").toLowerCase();
    const map = { standard: "flash", flash: "flash", best: "best", build: "build", media: "media", research: "research" };
    return map[m] !== undefined ? map[m] : m || "flash";
  }

  function complexityOf(text) {
    if (!text) return "simple";
    const len = text.length;
    const words = text.split(/\s+/).filter(Boolean).length;
    if (len < 100 || words < 20) return "simple";
    if (len > 500 || words > 100) return "complex";
    return "medium";
  }

  async function getAuthUser() {
    const TV = root.TV;
    let accessToken = "";
    try {
      accessToken = await TV.tokenManager.ensureFreshAccessToken(false);
    } catch (e) {
      // `ensureFreshAccessToken` throws `NO_TOKENS` for a fully signed-out
      // user. That's not an error here — `runEnhance` has its own guest path.
      // Treat any auth-state failure as "no token" and fall through.
      accessToken = "";
    }
    const data = await TV.chromeStorage.get([TV.STORAGE_KEYS.USER_ID]);
    return { userId: data[TV.STORAGE_KEYS.USER_ID] || "", accessToken: accessToken || "" };
  }

  /**
   * Anonymous (signed-out) callers get exactly **one** free enhancement,
   * tracked via `chrome.storage.local` under `STORAGE_KEYS.GUEST_FREE_USED`.
   * The popup modal reads the same flag to flip back to the sign-in wall
   * on subsequent attempts.
   */
  async function isGuestFreeUsed() {
    try {
      const key = root.TV.STORAGE_KEYS.GUEST_FREE_USED;
      const data = await root.TV.chromeStorage.get([key]);
      return Boolean(data && data[key]);
    } catch (e) {
      return false;
    }
  }

  async function markGuestFreeUsed() {
    try {
      const key = root.TV.STORAGE_KEYS.GUEST_FREE_USED;
      await root.TV.chromeStorage.set({ [key]: true });
    } catch (e) {
      // Best-effort; never fail the enhance result on a storage write.
    }
  }

  async function analyzeQuality(prompt) {
    try {
      const res = await fetch(QUALITY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      const text = await res.text();
      let json;
      try {
        json = JSON.parse(text);
      } catch (e) {
        return { domain: "", intent: "", intent_description: "", raw: null };
      }
      if (res.ok && json.status === "success") {
        const meta = json.metadata || {};
        return {
          domain: meta.domain || "",
          intent: meta.intent || "",
          intent_description: meta.intent_description || meta.description || "",
          raw: json,
        };
      }
    } catch (e) {}
    return { domain: "", intent: "", intent_description: "", raw: null };
  }

  async function saveUserPrompt(userPrompt, platform) {
    const { userId, accessToken } = await getAuthUser();
    if (!accessToken || !userId) {
      return { success: false, error: "Not signed in" };
    }
    const url = `${BACKEND_URL}/prompt/user-prompt`;
    const res = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        user_id: userId,
        user_prompt: userPrompt,
        platform: platform || "Extension",
        source: "extension_sidebar_consumer",
      }),
    });
    const result = await res.json().catch(() => ({}));
    if (!res.ok) {
      return { success: false, error: result.message || result.error || `HTTP ${res.status}` };
    }
    const promptId =
      result.data?.prompt_id ?? result.data?.id ?? result.prompt_id ?? result.data?.promptId ?? null;
    return { success: true, data: { ...(result.data || {}), prompt_id: promptId } };
  }

  async function fetchPersonalizationPrefs(userId, bearer) {
    try {
      const res = await fetch(`${PERSONALIZATION_BASE}/${userId}`, {
        method: "GET",
        headers: { Accept: "application/json", Authorization: `Bearer ${bearer}` },
      });
      if (!res.ok) return {};
      const json = await res.json();
      const d = json.data || {};
      const prefs = {};
      if (d.preferredName) prefs.preferredName = d.preferredName;
      if (d.professionalWorld) prefs.professionalWorld = d.professionalWorld;
      if (d.velocityTraits) prefs.velocityTraits = d.velocityTraits;
      if (d.personalLife) prefs.personalLife = d.personalLife;
      if (d.hobbies) prefs.hobbies = d.hobbies;
      if (d.primaryModel) prefs.primaryModel = d.primaryModel;
      return prefs;
    } catch (e) {
      return {};
    }
  }

  function pickIntentDomainFromLayer(p) {
    if (!p || typeof p !== "object") {
      return { domain: "", intent: "" };
    }
    const intent =
      (p.intent_analysis &&
        typeof p.intent_analysis.intent === "string" &&
        p.intent_analysis.intent.trim()) ||
      (p.computed_fields &&
        typeof p.computed_fields.intent === "string" &&
        p.computed_fields.intent.trim()) ||
      (typeof p.intent === "string" && p.intent.trim()) ||
      "";
    const domain =
      (p.domain_analysis &&
        typeof p.domain_analysis.domain === "string" &&
        p.domain_analysis.domain.trim()) ||
      (p.computed_fields &&
        typeof p.computed_fields.domain === "string" &&
        p.computed_fields.domain.trim()) ||
      (typeof p.domain === "string" && p.domain.trim()) ||
      "";
    return { domain: domain || "", intent: intent || "" };
  }

  /** Same field resolution as v-chat saveEnhancedPrompt / enhance finalData */
  function extractQualityFromEnhancePayload(payload) {
    if (!payload || typeof payload !== "object") {
      return { domain: "", intent: "" };
    }
    const top = pickIntentDomainFromLayer(payload);
    if (top.domain || top.intent) return top;
    if (payload.data && typeof payload.data === "object") {
      return pickIntentDomainFromLayer(payload.data);
    }
    return { domain: "", intent: "" };
  }

  function mergeQualityForSession(preEnhance, enhancePayload) {
    const fromStream = extractQualityFromEnhancePayload(enhancePayload || {});
    const pre = preEnhance || {};
    return {
      domain: (fromStream.domain || pre.domain || "").trim(),
      intent: (fromStream.intent || pre.intent || "").trim(),
      intent_description: (pre.intent_description || "").trim(),
    };
  }

  async function buildRequestBody(userPrompt, selectedStyle, userData, quality, prefs) {
    const finalMode = modeToApi(selectedStyle);
    const body = {
      prompt: userPrompt,
      chat_history: ["", "", ""],
      context: { mode: finalMode },
      target_ai: "",
      domain: quality.domain || "",
      user_id: userData.userId,
      auth_token: userData.accessToken,
      intent: quality.intent || "",
      intent_description: quality.intent_description || "",
    };
    if (prefs && Object.keys(prefs).length) {
      body.user_context = { preferences: prefs };
    }
    return body;
  }

  async function processStream(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let accumulated = "";
    let buffer = "";
    /** Last SSE object that carried intent/domain (some streams emit analysis before "complete") */
    let latestPayloadWithQuality = null;

    function consumeLine(line) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) return null;
      const jsonPart = trimmed.slice("data:".length).trimStart();
      if (!jsonPart || jsonPart === "[DONE]") return null;
      try {
        const data = JSON.parse(jsonPart);
        if (data.type === "content" && data.chunk) {
          accumulated += data.chunk;
        }
        const q = extractQualityFromEnhancePayload(data);
        if (q.domain || q.intent) {
          latestPayloadWithQuality = data;
        }
        if (
          data.type === "complete" ||
          data.status === "completed" ||
          data.status === "complete"
        ) {
          const nested = (data.data && typeof data.data === "object") ? data.data : null;
          const segs = Array.isArray(data.annotated_segments)
            ? data.annotated_segments
            : nested && Array.isArray(nested.annotated_segments)
              ? nested.annotated_segments
              : [];
          const enhancedText =
            data.enhanced_prompt ||
            (nested && nested.enhanced_prompt) ||
            accumulated;
          return {
            success: true,
            enhanced_prompt: enhancedText,
            annotated_segments: segs,
            performance: data.performance,
            metadata: data.metadata,
            completePayload: data,
          };
        }
      } catch (e) {}
      return null;
    }

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        const doneObj = consumeLine(line);
        if (doneObj) return doneObj;
      }
    }
    if (buffer.trim()) {
      const doneObj = consumeLine(buffer);
      if (doneObj) return doneObj;
    }
    if (accumulated) {
      return {
        success: true,
        enhanced_prompt: accumulated,
        annotated_segments: [],
        performance: null,
        metadata: null,
        completePayload: latestPayloadWithQuality,
      };
    }
    return { success: false, error: "Empty enhancement response" };
  }

  async function useService(userId, accessToken) {
    try {
      await fetch(`${BACKEND_URL}/status/${userId}/use`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
      });
    } catch (e) {
      // Billing tick is best-effort; never fail the enhance flow
    }
  }

  async function saveEnhancedPrompt(enhancedText, promptId, mode, domain, intent) {
    if (!isValidUUID(promptId)) {
      return { success: false, skipped: true };
    }
    const { accessToken } = await getAuthUser();
    if (!accessToken) return { success: false, error: "No token" };
    const apiMode = modeToApi(mode);
    const body = {
      prompt_id: promptId,
      enhanced_prompt: enhancedText,
      conversation_id: null,
      mode: apiMode,
      user_status: null,
      processing_time: null,
      intent: intent || "",
      llm_used: "",
      complexity: complexityOf(enhancedText),
      domain: domain || "",
      metadata: null,
      input_token: null,
      output_token: null,
      total_token: null,
    };
    const res = await fetch(`${BACKEND_URL}/prompt/enhanced-prompt`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    const result = await res.json().catch(() => ({}));
    if (!res.ok) {
      return { success: false, error: result.message || `HTTP ${res.status}` };
    }
    return { success: true, data: result.data };
  }

  /**
   * Call the local ThinkVelocity server's /enhance/annotate endpoint to
   * generate annotated_segments for an already-enhanced prompt.
   * Returns an array of segment objects, or [] on any failure.
   * Never throws — wrapped in try/catch so it never breaks the enhance flow.
   */
  async function fetchLocalAnnotations(enhancedPrompt, originalPrompt) {
    try {
      const res = await fetch(LOCAL_ANNOTATE_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enhanced_prompt: enhancedPrompt,
          original_prompt: originalPrompt || "",
        }),
        // Short timeout — if local server is down, fail fast and silently
        signal: AbortSignal.timeout ? AbortSignal.timeout(8000) : undefined,
      });
      if (!res.ok) return [];
      const json = await res.json();
      const segs = json && Array.isArray(json.annotated_segments) ? json.annotated_segments : [];
      return segs;
    } catch (e) {
      // Local server may be offline — this is always best-effort
      return [];
    }
  }

  async function runEnhance(opts) {
    const prompt = (opts && opts.prompt) || "";
    const mode = (opts && opts.mode) || "standard";
    const platform = (opts && opts.platform) || "extension";
    if (!prompt.trim()) {
      return { success: false, error: "Prompt is required" };
    }

    try {
      const { userId, accessToken } = await getAuthUser();
      const isGuest = !accessToken || !userId;

      if (isGuest) {
        const guestUsed = await isGuestFreeUsed();
        if (guestUsed) {
          return { success: false, error: "Sign in on thinkvelocity.in first." };
        }
      }

      const quality = await analyzeQuality(prompt);

      let promptId = null;
      if (!isGuest) {
        const save1 = await saveUserPrompt(prompt, platform);
        if (save1.success) {
          promptId = save1.data?.prompt_id || null;
          if (!isValidUUID(promptId)) {
            promptId = null;
          }
        }
      }

      const prefs = isGuest ? {} : await fetchPersonalizationPrefs(userId, accessToken);
      const userData = { userId: userId || "", accessToken: accessToken || "" };
      const requestBody = await buildRequestBody(prompt, mode, userData, quality, prefs);

      const headers = { "Content-Type": "application/json" };
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
      const res = await fetch(ENHANCE_STREAM_URL, {
        method: "POST",
        headers,
        body: JSON.stringify(requestBody),
      });

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        return { success: false, error: `Enhance HTTP ${res.status}: ${t.slice(0, 200)}` };
      }

      const streamResult = await processStream(res);
      if (!streamResult.success) {
        return { success: false, error: streamResult.error || "Stream failed" };
      }

      const enhanced = streamResult.enhanced_prompt || "";
      const payloadForQuality = streamResult.completePayload || streamResult.metadata || null;
      const mergedQuality = mergeQualityForSession(quality, payloadForQuality);

      if (!isGuest && promptId) {
        await saveEnhancedPrompt(enhanced, promptId, mode, mergedQuality.domain, mergedQuality.intent);
      }

      if (isGuest) {
        // Burn the one-shot free entitlement once we have a confirmed result.
        await markGuestFreeUsed();
      } else {
        // Billing tick — fire-and-forget, never blocks enhance result.
        void useService(userId, accessToken);
      }

      // If the remote stream returned no annotated_segments, fetch them from
      // the local ThinkVelocity server.  This call is wrapped in try/catch
      // inside fetchLocalAnnotations — it never breaks the enhance result.
      let annotatedSegments = streamResult.annotated_segments || [];
      if (annotatedSegments.length === 0 && enhanced) {
        annotatedSegments = await fetchLocalAnnotations(enhanced, prompt);
      }

      return {
        success: true,
        data: {
          enhanced_prompt: enhanced,
          annotated_segments: annotatedSegments,
          prompt_id: promptId,
          quality: mergedQuality,
          is_guest: isGuest,
        },
      };
    } catch (err) {
      return { success: false, error: err.message || String(err) };
    }
  }

  root.TV.consumerEnhanceFlow = { runEnhance, fetchLocalAnnotations };
})();
