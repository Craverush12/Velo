/**
 * Routes consumer voice capture through an offscreen document (USER_MEDIA).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : self;
  root.TV = root.TV || {};

  const OFFSCREEN_PATH = "offscreen/offscreen-voice.html";
  const pendingStart = new Map();
  const pendingStop = new Map();

  function defer() {
    let resolve;
    let reject;
    const promise = new Promise((res, rej) => {
      resolve = res;
      reject = rej;
    });
    return { promise, resolve, reject };
  }

  async function tryCloseOffscreen() {
    if (!chrome.offscreen || !chrome.offscreen.closeDocument) return;
    try {
      await chrome.offscreen.closeDocument();
    } catch (_) {
      /* no document */
    }
  }

  async function ensureOffscreenVoiceDoc() {
    if (!chrome.offscreen || typeof chrome.offscreen.createDocument !== "function") {
      throw new Error("Offscreen API is not available.");
    }
    const hasFn = chrome.offscreen.hasDocument;
    if (typeof hasFn === "function") {
      const has = await hasFn.call(chrome.offscreen);
      if (has) {
        await tryCloseOffscreen();
      }
    }
    await chrome.offscreen.createDocument({
      url: OFFSCREEN_PATH,
      reasons: ["USER_MEDIA"],
      justification: "Record voice from the sidebar for speech-to-text transcription.",
    });
  }

  function forwardToOffscreen(message) {
    return chrome.runtime.sendMessage({
      ...message,
      __tvOffscreenTarget: "offscreen-voice",
    });
  }

  /**
   * @param {object} message
   * @returns {boolean} true if consumed
   */
  function handleSwReply(message) {
    if (!message || message.action !== "TV_OFFSCREEN_VOICE_SW_REPLY") return false;
    const requestId = message.requestId;
    if (!requestId) return false;

    if (message.data && message.data.started) {
      const d = pendingStart.get(requestId);
      if (!d) return false;
      if (d.timeoutId) clearTimeout(d.timeoutId);
      pendingStart.delete(requestId);
      d.resolve(message);
      return true;
    }

    if (message.data && (message.data.base64 != null || message.data.cancelled)) {
      const d = pendingStop.get(requestId);
      if (!d) return false;
      if (d.timeoutId) clearTimeout(d.timeoutId);
      pendingStop.delete(requestId);
      d.resolve(message);
      return true;
    }

    if (pendingStart.has(requestId)) {
      const d = pendingStart.get(requestId);
      if (d.timeoutId) clearTimeout(d.timeoutId);
      pendingStart.delete(requestId);
      d.resolve(message);
      return true;
    }

    if (pendingStop.has(requestId)) {
      const d = pendingStop.get(requestId);
      if (d.timeoutId) clearTimeout(d.timeoutId);
      pendingStop.delete(requestId);
      d.resolve(message);
      return true;
    }

    return false;
  }

  /**
   * @param {(sendResponse: function, requestId: string|null, success: boolean, data: *, error: *) => void} reply
   */
  async function panelStart(requestId, sendResponse, reply) {
    if (!requestId || typeof requestId !== "string") {
      reply(sendResponse, null, false, null, {
        code: "INVALID_REQUEST",
        message: "requestId is required",
        retryable: false,
      });
      return;
    }

    const d = defer();
    const timeoutId = setTimeout(() => {
      if (!pendingStart.has(requestId)) return;
      pendingStart.delete(requestId);
      d.reject(new Error("Timed out waiting to start voice capture."));
    }, 20000);
    pendingStart.set(requestId, { ...d, timeoutId });

    try {
      await ensureOffscreenVoiceDoc();
      await forwardToOffscreen({
        action: "TV_OFFSCREEN_VOICE_START",
        requestId,
        payload: { timesliceMs: 250 },
      });
      const result = await d.promise;
      if (result.success && result.data && result.data.started) {
        reply(sendResponse, requestId, true, { started: true }, null);
        return;
      }
      await tryCloseOffscreen();
      const err = result.error || {};
      reply(sendResponse, requestId, false, null, {
        code: err.code || "START_FAILED",
        message: err.message || "Could not start recording",
        retryable: Boolean(err.retryable),
      });
    } catch (error) {
      if (pendingStart.has(requestId)) {
        const p = pendingStart.get(requestId);
        if (p.timeoutId) clearTimeout(p.timeoutId);
        pendingStart.delete(requestId);
      }
      await tryCloseOffscreen();
      reply(sendResponse, requestId, false, null, {
        code: "START_FAILED",
        message: error && error.message ? error.message : String(error),
        retryable: true,
      });
    }
  }

  /**
   * @param {(sendResponse: function, requestId: string|null, success: boolean, data: *, error: *) => void} reply
   */
  async function panelStop(requestId, sendResponse, reply, payload) {
    if (!requestId || typeof requestId !== "string") {
      reply(sendResponse, null, false, null, {
        code: "INVALID_REQUEST",
        message: "requestId is required",
        retryable: false,
      });
      return;
    }

    const d = defer();
    const timeoutId = setTimeout(() => {
      if (!pendingStop.has(requestId)) return;
      pendingStop.delete(requestId);
      d.reject(new Error("Timed out waiting for voice capture to finish."));
    }, 180000);
    pendingStop.set(requestId, { ...d, timeoutId });

    try {
      await forwardToOffscreen({
        action: "TV_OFFSCREEN_VOICE_STOP",
        requestId,
        payload: { cancelOnly: Boolean(payload && payload.cancelOnly) },
      });
      const result = await d.promise;
      await tryCloseOffscreen();

      if (result.success && result.data && result.data.cancelled) {
        reply(sendResponse, requestId, true, { cancelled: true }, null);
        return;
      }

      if (result.success && result.data && result.data.base64 != null) {
        reply(sendResponse, requestId, true, result.data, null);
        return;
      }

      const err = result.error || {};
      reply(sendResponse, requestId, false, null, {
        code: err.code || "STOP_FAILED",
        message: err.message || "Recording failed",
        retryable: Boolean(err.retryable),
      });
    } catch (error) {
      if (pendingStop.has(requestId)) {
        const p = pendingStop.get(requestId);
        if (p.timeoutId) clearTimeout(p.timeoutId);
        pendingStop.delete(requestId);
      }
      await tryCloseOffscreen();
      reply(sendResponse, requestId, false, null, {
        code: "STOP_FAILED",
        message: error && error.message ? error.message : String(error),
        retryable: true,
      });
    }
  }

  root.TV.offscreenVoiceBridge = {
    handleSwReply,
    panelStart,
    panelStop,
  };
})();
