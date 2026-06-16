/**
 * Offscreen document: getUserMedia + MediaRecorder (USER_MEDIA reason).
 * Communicates with the service worker via chrome.runtime.sendMessage.
 */
(function () {
  let stream = null;
  let recorder = null;
  const chunks = [];
  let activeRequestId = null;
  let skipUpload = false;

  function pickMimeType() {
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
      "audio/ogg",
    ];
    if (!window.MediaRecorder || !window.MediaRecorder.isTypeSupported) return undefined;
    if (window.MediaRecorder.isTypeSupported(candidates[0])) return candidates[0];
    return candidates.find((t) => window.MediaRecorder.isTypeSupported(t));
  }

  function releaseStream() {
    try {
      if (stream) stream.getTracks().forEach((t) => t.stop());
    } catch (_) {}
    stream = null;
  }

  function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const dataUrl = reader.result;
        if (typeof dataUrl !== "string" || !dataUrl.includes(",")) {
          reject(new Error("Failed to read audio"));
          return;
        }
        resolve(dataUrl.split(",")[1]);
      };
      reader.onerror = () => reject(reader.error || new Error("read failed"));
      reader.readAsDataURL(blob);
    });
  }

  function sendToSw(payload) {
    try {
      chrome.runtime.sendMessage(payload);
    } catch (e) {
      console.warn("[offscreen-voice] sendToSw:", e);
    }
  }

  async function startRecording(requestId, timesliceMs) {
    if (activeRequestId && activeRequestId !== requestId) {
      sendToSw({
        action: "TV_OFFSCREEN_VOICE_SW_REPLY",
        requestId,
        success: false,
        error: { code: "BUSY", message: "Another recording is active", retryable: true },
      });
      return;
    }
    activeRequestId = requestId;
    skipUpload = false;
    chunks.length = 0;
    releaseStream();

    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = pickMimeType();
      const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorder = rec;

      rec.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunks.push(e.data);
      };

      rec.onerror = () => {
        releaseStream();
        recorder = null;
        activeRequestId = null;
        sendToSw({
          action: "TV_OFFSCREEN_VOICE_SW_REPLY",
          requestId,
          success: false,
          error: { code: "RECORDER_ERROR", message: "Could not capture voice.", retryable: true },
        });
      };

      rec.onstop = async () => {
        const req = requestId;
        const shouldSkip = skipUpload;
        skipUpload = false;
        const mime = rec.mimeType || (chunks[0] && chunks[0].type) || "audio/webm";
        const parts = chunks.splice(0, chunks.length);
        releaseStream();
        recorder = null;
        activeRequestId = null;

        if (shouldSkip) {
          sendToSw({
            action: "TV_OFFSCREEN_VOICE_SW_REPLY",
            requestId: req,
            success: true,
            data: { cancelled: true },
          });
          return;
        }

        if (!parts.length) {
          sendToSw({
            action: "TV_OFFSCREEN_VOICE_SW_REPLY",
            requestId: req,
            success: false,
            error: { code: "NO_AUDIO", message: "No audio captured.", retryable: true },
          });
          return;
        }

        try {
          const blob = new Blob(parts, { type: mime });
          const base64 = await blobToBase64(blob);
          sendToSw({
            action: "TV_OFFSCREEN_VOICE_SW_REPLY",
            requestId: req,
            success: true,
            data: { base64, mimeType: mime },
          });
        } catch (err) {
          sendToSw({
            action: "TV_OFFSCREEN_VOICE_SW_REPLY",
            requestId: req,
            success: false,
            error: {
              code: "ENCODE_FAILED",
              message: err && err.message ? err.message : "Could not read recording.",
              retryable: true,
            },
          });
        }
      };

      const slice = typeof timesliceMs === "number" && timesliceMs > 0 ? timesliceMs : 250;
      rec.start(slice);
      sendToSw({
        action: "TV_OFFSCREEN_VOICE_SW_REPLY",
        requestId,
        success: true,
        data: { started: true },
      });
    } catch (err) {
      console.warn("[offscreen-voice] getUserMedia:", err);
      releaseStream();
      recorder = null;
      activeRequestId = null;
      const name = err && err.name ? String(err.name) : "Error";
      sendToSw({
        action: "TV_OFFSCREEN_VOICE_SW_REPLY",
        requestId,
        success: false,
        error: {
          code: name,
          message:
            name === "NotAllowedError"
              ? "Microphone access was blocked. Allow the microphone for this extension in Chrome site settings."
              : name === "NotFoundError"
                ? "No microphone was found."
                : `Could not access microphone (${name}).`,
          retryable: name === "NotReadableError" || name === "AbortError",
        },
      });
    }
  }

  function stopRecording(requestId, cancelOnly) {
    if (activeRequestId !== requestId) {
      sendToSw({
        action: "TV_OFFSCREEN_VOICE_SW_REPLY",
        requestId,
        success: false,
        error: { code: "NO_SESSION", message: "No active recording for this request.", retryable: false },
      });
      return;
    }
    skipUpload = Boolean(cancelOnly);
    try {
      if (recorder && recorder.state !== "inactive") recorder.stop();
    } catch (e) {
      skipUpload = true;
      releaseStream();
      recorder = null;
      activeRequestId = null;
      sendToSw({
        action: "TV_OFFSCREEN_VOICE_SW_REPLY",
        requestId,
        success: false,
        error: { code: "STOP_FAILED", message: e && e.message ? e.message : "Stop failed", retryable: true },
      });
    }
  }

  chrome.runtime.onMessage.addListener((message) => {
    if (!message || typeof message.action !== "string") return;
    if (message.__tvOffscreenTarget !== "offscreen-voice") return;

    const requestId = message.requestId || null;
    if (message.action === "TV_OFFSCREEN_VOICE_START") {
      const payload = message.payload || {};
      startRecording(requestId, payload.timesliceMs);
      return;
    }
    if (message.action === "TV_OFFSCREEN_VOICE_STOP") {
      const payload = message.payload || {};
      stopRecording(requestId, payload.cancelOnly);
    }
  });
})();
