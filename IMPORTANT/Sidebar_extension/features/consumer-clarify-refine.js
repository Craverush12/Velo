/**
 * Clarify and refine flow — matches Extension-new/Button/js/api.js.
 * clarify:  POST /refine/prepare             { original_prompt, user_id, previous_enhanced_prompt? }
 * refine:   POST /refine/finalize             { original_prompt, clarification_qa, neuro_state, context_patterns }
 * API #3:   POST /backend-V1-D/prompt/refine-prompt
 * feedback: POST /backend-V1-D/prompt/insert-feedback
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const _API_BASE       = "https://api.thinkvelocity.in";
  const BACKEND_URL     = "https://thinkvelocity.in/backend-V1-D";
  const PREPARE_URL     = `${_API_BASE}/refine/prepare`;
  const FINALIZE_URL    = `${_API_BASE}/refine/finalize`;
  const REFINE_SAVE_URL = `${BACKEND_URL}/prompt/refine-prompt`;
  const FEEDBACK_URL    = `${BACKEND_URL}/prompt/insert-feedback`;
  const REVIEWS_URL     = `${BACKEND_URL}/reviews`;

  /** State carried from the most recent prepare call into the finalize call. */
  let _prepareState = { neuro_state: null, context_patterns: [] };

  async function getAuth() {
    const TV = root.TV;
    const accessToken = await TV.tokenManager.ensureFreshAccessToken(false);
    const data = await TV.chromeStorage.get([TV.STORAGE_KEYS.USER_ID]);
    return {
      userId: data[TV.STORAGE_KEYS.USER_ID] || "free-trial",
      accessToken: accessToken || "free-trial",
    };
  }

  // Normalise prepare/clarify response into [{ id, question, options }]
  function normaliseQuestions(json) {
    // New format: { questions: [{ id, question, options }] }
    const newList = json.questions || (json.data && json.data.questions);
    if (Array.isArray(newList) && newList.length && typeof newList[0].question === "string") {
      return newList.map((q, i) => ({
        id: q.id != null ? q.id : i,
        question: q.question || "",
        options: Array.isArray(q.options) ? q.options : [],
      }));
    }

    // Legacy format A: { mcq_questions: [{ question_text, answer_options }] }
    const mcqList = json.mcq_questions || (json.data && json.data.mcq_questions);
    if (Array.isArray(mcqList) && mcqList.length) {
      return mcqList.map((q, i) => ({
        id: q.question_id || i,
        question: q.question_text || q.question || "",
        options: Array.isArray(q.answer_options) ? q.answer_options : [],
      }));
    }

    // Legacy format B: { questions: ["q1","q2"], options: [["a","b"],["c","d"]] }
    const rawQs   = (json.data && json.data.questions) || [];
    const rawOpts = (json.data && json.data.options)   || null;
    if (Array.isArray(rawQs) && rawQs.length && typeof rawQs[0] === "string" && Array.isArray(rawOpts)) {
      return rawQs.map((text, i) => ({
        id: i,
        question: text,
        options: Array.isArray(rawOpts[i]) ? rawOpts[i] : [],
      }));
    }

    return [];
  }

  async function clarify(original, enhanced) {
    const promptText = String(original || "").trim();
    if (!promptText) {
      return { success: false, error: "Prompt is required" };
    }

    // Reset prepare state so a stale neuro_state is never sent on a subsequent refine.
    _prepareState = { neuro_state: null, context_patterns: [] };

    try {
      const { userId, accessToken } = await getAuth();
      const body = {
        original_prompt: promptText,
        user_id: userId,
      };
      const enhancedText = String(enhanced || "").trim();
      if (enhancedText) {
        body.previous_enhanced_prompt = enhancedText;
      }

      const headers = { "Content-Type": "application/json" };
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

      const res = await fetch(PREPARE_URL, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        return { success: false, error: json.message || json.detail || json.error || `HTTP ${res.status}` };
      }

      // Persist prepare context for the upcoming finalize call.
      _prepareState = {
        neuro_state:      json.neuro_state      || null,
        context_patterns: json.context_patterns || [],
      };

      const questions = normaliseQuestions(json);
      return { success: true, data: { questions } };
    } catch (err) {
      return { success: false, error: err.message || String(err) };
    }
  }

  // API #3 — fire-and-forget after a successful refine
  async function saveRefinedPrompt(refinedPrompt, qaArray, refineTokens) {
    try {
      const { accessToken } = await getAuth();
      const stored = await root.TV.chromeStorage.get([
        "velocityCurrentPromptId",
        "velocityCurrentEnhancedPromptId",
        "clarifyInputToken",
        "clarifyOutputToken",
        "clarifyTotalToken",
      ]);

      const promptId      = stored.velocityCurrentPromptId || null;
      const enhancedPromptId = stored.velocityCurrentEnhancedPromptId || null;
      if (!promptId || !enhancedPromptId) return;

      // Combine clarify + refine tokens
      const clarifyIn  = stored.clarifyInputToken  || 0;
      const clarifyOut = stored.clarifyOutputToken || 0;
      const clarifyTot = stored.clarifyTotalToken  || 0;
      const refineIn   = refineTokens.input_tokens  || 0;
      const refineOut  = refineTokens.output_tokens || 0;
      const refineTot  = refineTokens.total_tokens  || 0;

      const body = {
        prompt_id:          promptId,
        enhanced_prompt_id: enhancedPromptId,
        refined_prompt:     refinedPrompt,
        refine_question_1:  (qaArray[0] && qaArray[0].question) || null,
        refine_answer_1:    (qaArray[0] && qaArray[0].answer)   || null,
        refine_question_2:  (qaArray[1] && qaArray[1].question) || null,
        refine_answer_2:    (qaArray[1] && qaArray[1].answer)   || null,
        input_token:  (clarifyIn  + refineIn)  || null,
        output_token: (clarifyOut + refineOut) || null,
        total_token:  (clarifyTot + refineTot) || null,
      };

      const res = await fetch(REFINE_SAVE_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify(body),
      });
      const result = await res.json().catch(() => ({}));
      if (res.ok && result.data && result.data.refine_id) {
        await root.TV.chromeStorage.set({
          velocityCurrentRefinedPromptId: result.data.refine_id,
        }).catch(() => {});
      }
    } catch (e) {
      console.warn("[consumer-clarify-refine] saveRefinedPrompt error:", e);
    }
  }

  async function refine(original, enhanced, qaArray) {
    const promptToRefine = String(enhanced || original || "").trim();
    if (!promptToRefine) {
      return { success: false, error: "A prompt is required to refine" };
    }
    try {
      const { userId, accessToken } = await getAuth();
      const body = {
        original_prompt:          String(original || "").trim() || promptToRefine,
        previous_enhanced_prompt: String(enhanced || "").trim() || null,
        clarification_qa:         Array.isArray(qaArray) ? qaArray : [],
        user_id:                  userId,
        neuro_state:              _prepareState.neuro_state    || null,
        context_patterns:         _prepareState.context_patterns || [],
      };

      const headers = { "Content-Type": "application/json" };
      if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

      const res = await fetch(FINALIZE_URL, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        return { success: false, error: json.message || json.detail || json.error || `HTTP ${res.status}` };
      }

      // New API returns refined_prompt; fall back to enhanced_prompt for safety.
      const refined =
        json.refined_prompt  ||
        (json.data && (json.data.refined_prompt || json.data.enhanced_prompt)) ||
        json.enhanced_prompt ||
        "";

      // Token counts are not returned by the new API; pass nulls so saveRefinedPrompt
      // still fires (it guards on promptId, not tokens).
      const refineTokens = {};

      // API #3 — persist refined prompt (fire-and-forget; never blocks the UI)
      void saveRefinedPrompt(refined, Array.isArray(qaArray) ? qaArray : [], refineTokens);

      return { success: true, data: { refined_prompt: refined } };
    } catch (err) {
      return { success: false, error: err.message || String(err) };
    }
  }

  async function sendFeedback(promptId, feedback, mode) {
    if (!promptId || !feedback) {
      return { success: false, error: "promptId and feedback are required" };
    }
    try {
      const { userId, accessToken } = await getAuth();
      const res = await fetch(FEEDBACK_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        },
        body: JSON.stringify({
          prompt_id: promptId,
          feedback,
          mode: mode || "standard",
          user_id: userId || "",
        }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        return { success: false, error: json.message || json.error || `HTTP ${res.status}` };
      }
      return { success: true, data: json.data || {} };
    } catch (err) {
      return { success: false, error: err.message || String(err) };
    }
  }

  async function submitWrittenFeedback(feedbackText, reason, source) {
    const text = typeof feedbackText === "string" ? feedbackText.trim() : "";
    const chosenReason = (typeof reason === "string" && reason.trim()) ? reason.trim() : "Other";
    if (!text) {
      return { success: false, error: "Feedback text is required" };
    }
    try {
      const { userId, accessToken } = await getAuth();
      const formData = new FormData();
      formData.append("user_id", userId || 0);
      formData.append("selectedReason", chosenReason);
      formData.append("feedback", text);
      formData.append("source", source || "sidebar-extension");

      const res = await fetch(REVIEWS_URL, {
        method: "POST",
        headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined,
        body: formData,
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        return { success: false, error: json.message || json.error || `HTTP ${res.status}` };
      }
      return { success: true, data: json.data || json || {} };
    } catch (err) {
      return { success: false, error: err.message || String(err) };
    }
  }

  root.TV.consumerClarifyRefine = { clarify, refine, sendFeedback, submitWrittenFeedback };
})();
