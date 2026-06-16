/**
 * Voice capture → POST /transcribe (Extension-new `voice-recorder.js` parity).
 * Uses `navigator.permissions.query({ name: "microphone" })`: if state is `prompt`, opens
 * `panel/consumer/mic-permission.html` in a tab to grant mic (sidebar prompts are unreliable).
 * If `granted`, composer calls `getUserMedia` then `continueWithMediaStream(stream)`.
 * Offscreen capture remains as a fallback when nothing is passed from the UI.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const DEFAULT_TRANSCRIBE_URL = "https://api.thinkvelocity.in/dev/test/transcribe";

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

  /** Mic capture runs in an offscreen document created by the service worker (createDocument is SW-only). */
  function usesServiceWorkerVoiceCapture() {
    return !!(
      typeof chrome !== "undefined" &&
      chrome.runtime &&
      typeof chrome.runtime.sendMessage === "function" &&
      typeof chrome.runtime.id === "string"
    );
  }

  function isCaptureSupported() {
    return !!(
      typeof navigator !== "undefined" &&
      navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === "function" &&
      window.MediaRecorder
    );
  }

  function base64ToBlob(base64, mimeType) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    return new Blob([bytes], { type: mimeType || "audio/webm" });
  }

  function sendRuntimeVoiceMessage(action, requestId, payload) {
    return new Promise((resolve, reject) => {
      try {
        chrome.runtime.sendMessage({ action, requestId, payload: payload || {} }, (raw) => {
          const le = chrome.runtime.lastError;
          if (le) {
            reject(new Error(le.message));
            return;
          }
          if (!raw || raw.success === false) {
            const msg =
              raw && raw.error && raw.error.message ? String(raw.error.message) : "Voice capture request failed";
            reject(new Error(msg));
            return;
          }
          resolve(raw.data || {});
        });
      } catch (e) {
        reject(e);
      }
    });
  }

  /**
   * @param {unknown} err
   * @returns {string}
   */
  function micErrorMessage(err) {
    const name = err && err.name ? String(err.name) : "";
    const detail = err && err.message ? String(err.message).toLowerCase() : "";
    if (name === "NotAllowedError") {
      if (detail.includes("dismiss")) {
        return "The microphone prompt was closed. Tap the mic again and choose Allow, or set Microphone to Allow for this extension (Chrome menu → Extensions → Velocity Sidebar → Details → Site settings).";
      }
      return "Microphone access was denied. Allow the microphone for this extension in Chrome → Extensions → this extension → Site settings → Microphone.";
    }
    if (name === "NotFoundError") {
      return "No microphone was found. Connect a microphone and try again.";
    }
    if (name === "NotReadableError" || name === "AbortError") {
      return "The microphone is in use or unavailable. Close other apps using the mic and try again.";
    }
    return `Could not access microphone (${name || "Error"}).`;
  }

  /**
   * Same as Extension-new `voice-recorder.js`: microphone state for this extension origin.
   * @returns {Promise<'granted'|'denied'|'prompt'>}
   */
  async function checkMicPermission() {
    try {
      const result = await navigator.permissions.query({ name: "microphone" });
      return result.state;
    } catch (_) {
      return "prompt";
    }
  }

  /**
   * Opens a normal tab to request mic (Extension-new pattern — sidebar/popup prompts are unreliable).
   */
  async function openMicPermissionPage() {
    let sourceTab = null;
    try {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      sourceTab = Array.isArray(tabs) && tabs.length ? tabs[0] : null;
    } catch (_) {}

    const params = new URLSearchParams();
    if (sourceTab && Number.isInteger(sourceTab.id)) params.set("returnTabId", String(sourceTab.id));
    if (sourceTab && Number.isInteger(sourceTab.windowId)) params.set("returnWindowId", String(sourceTab.windowId));

    const path = `panel/consumer/mic-permission.html${params.toString() ? `?${params.toString()}` : ""}`;
    const url = chrome.runtime.getURL(path);
    try {
      chrome.tabs.create({
        url,
        active: true,
        ...(sourceTab && Number.isInteger(sourceTab.id) ? { openerTabId: sourceTab.id } : {}),
      });
    } catch (_) {
      try {
        window.open(url, "_blank");
      } catch (__) {}
    }
  }

  async function buildAuthHeaders() {
    const TV = root.TV;
    if (!TV || !TV.tokenManager || typeof TV.tokenManager.ensureFreshAccessToken !== "function") {
      return undefined;
    }
    try {
      const token = await TV.tokenManager.ensureFreshAccessToken(false);
      if (token && typeof token === "string" && token.length > 2) {
        return { Authorization: `Bearer ${token}` };
      }
    } catch (_) {
      /* not signed in or refresh failed */
    }
    return undefined;
  }

  async function transcribeBlob(audioBlob, mime, transcribeUrl, getHeaders, fail) {
    const extension = mime.includes("ogg") ? "ogg" : mime.includes("mp4") ? "mp4" : "webm";
    const formData = new FormData();
    formData.append("audio", audioBlob, `voice-${Date.now()}.${extension}`);

    try {
      const headers = await getHeaders();
      const response = await fetch(transcribeUrl, {
        method: "POST",
        headers: headers || undefined,
        body: formData,
      });

      if (!response.ok) {
        let errorMessage = response.statusText || "Transcription failed";
        try {
          const errJson = await response.json();
          errorMessage = errJson.error || errJson.message || errorMessage;
        } catch {
          try {
            const errorText = await response.text();
            if (errorText) errorMessage = errorText.slice(0, 200);
          } catch (_) {}
        }
        throw new Error(errorMessage);
      }

      const data = await response.json();
      const transcript = data && data.transcript != null ? String(data.transcript).trim() : "";
      if (!transcript) throw new Error("No transcript returned");
      return transcript;
    } catch (err) {
      console.warn("[consumer-voice-transcribe]", err);
      fail(err && err.message ? err.message : "Could not transcribe audio. Please try again.");
      return null;
    }
  }

  /**
   * @param {object} options
   * @param {string} [options.transcribeUrl]
   * @param {() => Promise<HeadersInit|undefined>} [options.getHeaders]
   * @param {(text: string) => void} options.onTranscript
   * @param {(message: string) => void} [options.onError]
   * @param {(state: 'idle'|'recording'|'paused'|'transcribing') => void} [options.onStateChange]
   * @param {number} [options.maxDurationSeconds]
   */
  function createToggleController(options) {
    const transcribeUrl = options.transcribeUrl || DEFAULT_TRANSCRIBE_URL;
    const getHeaders = options.getHeaders || buildAuthHeaders;
    const maxDuration = options.maxDurationSeconds || 120;
    const useOffscreen = usesServiceWorkerVoiceCapture();

    let recorder = null;
    let stream = null;
    /** When false the controller never stops `stream.getTracks()` — the caller (composer-bar)
     *  owns the cached mic stream and reuses it across recordings so Chrome doesn't re-prompt. */
    let ownsStream = true;
    const chunks = [];
    let skipTranscription = false;
    let recording = false;
    let elapsedSeconds = 0;
    let timerInterval = null;
    let timerPaused = false;
    let autoStopFired = false;
    /** True while POST /transcribe is in flight (blocks overlapping mic starts). */
    let transcribing = false;
    /** @type {string|null} */
    let voiceSessionId = null;

    function isRecorderLive() {
      return !!(recorder && (recorder.state === "recording" || recorder.state === "paused"));
    }

    function isVoiceSessionActive() {
      return !!(transcribing || voiceSessionId || recording || isRecorderLive());
    }

    function setState(state) {
      if (typeof options.onStateChange === "function") options.onStateChange(state);
    }

    function stopTimer() {
      if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
      }
    }

    function startTimer() {
      stopTimer();
      timerPaused = false;
      timerInterval = setInterval(() => {
        if (timerPaused) return;
        elapsedSeconds += 1;
        if (elapsedSeconds >= maxDuration && !autoStopFired) {
          autoStopFired = true;
          confirm();
        }
      }, 1000);
    }

    function releaseStream() {
      if (ownsStream) {
        try {
          stream && stream.getTracks().forEach((t) => t.stop());
        } catch (_) {}
      }
      stream = null;
    }

    function fail(msg) {
      if (typeof options.onError === "function") options.onError(msg);
    }

    function resetLocal() {
      recording = false;
      elapsedSeconds = 0;
      autoStopFired = false;
      timerPaused = false;
      stopTimer();
      voiceSessionId = null;
    }

    async function finishWithBlob(audioBlob, mime) {
      transcribing = true;
      setState("transcribing");
      try {
        const transcript = await transcribeBlob(audioBlob, mime, transcribeUrl, getHeaders, fail);
        if (transcript) options.onTranscript(transcript);
      } finally {
        transcribing = false;
        setState("idle");
      }
    }

    async function startRecordingOffscreen() {
      skipTranscription = false;
      elapsedSeconds = 0;
      autoStopFired = false;
      voiceSessionId =
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : `voice-${Date.now()}-${Math.random().toString(36).slice(2)}`;

      try {
        await sendRuntimeVoiceMessage("TV_OFFSCREEN_VOICE_START", voiceSessionId, {});
        recording = true;
        setState("recording");
        startTimer();
      } catch (err) {
        console.warn("[consumer-voice-transcribe] offscreen start:", err);
        fail(err && err.message ? err.message : "Could not access microphone. Allow mic for this extension.");
        resetLocal();
        setState("idle");
        voiceSessionId = null;
      }
    }

    async function stopOffscreenAndMaybeTranscribe(cancelOnly) {
      const session = voiceSessionId;
      voiceSessionId = null;
      skipTranscription = Boolean(cancelOnly);
      stopTimer();
      recording = false;

      if (!session) {
        setState("idle");
        return;
      }

      if (skipTranscription) {
        setState("idle");
        try {
          await sendRuntimeVoiceMessage("TV_OFFSCREEN_VOICE_STOP", session, { cancelOnly: true });
        } catch (e) {
          console.warn("[consumer-voice-transcribe] offscreen cancel:", e);
        }
        return;
      }

      try {
        const data = await sendRuntimeVoiceMessage("TV_OFFSCREEN_VOICE_STOP", session, { cancelOnly: false });
        if (data && data.cancelled) {
          setState("idle");
          return;
        }
        if (!data || data.base64 == null) {
          fail("No audio captured. Please try again.");
          setState("idle");
          return;
        }
        const mime = data.mimeType || "audio/webm";
        const audioBlob = base64ToBlob(data.base64, mime);
        await finishWithBlob(audioBlob, mime);
      } catch (err) {
        console.warn("[consumer-voice-transcribe] offscreen stop:", err);
        fail(err && err.message ? err.message : "Could not capture voice. Please try again.");
        setState("idle");
      }
    }

    /**
     * Call from `getUserMedia(...).then(stream => …)` (same chain as the mic click) so recording starts
     * after the user allows the prompt.
     * @param {MediaStream} mediaStream
     * @param {{ ownsStream?: boolean }} [opts] When `ownsStream` is `false` the controller will not
     *   stop the stream's tracks on cancel/stop/dispose — the caller is responsible for the
     *   stream's lifetime (used to cache the mic grant across multiple recordings).
     */
    async function continueWithMediaStream(mediaStream, opts) {
      if (!mediaStream || typeof mediaStream.getTracks !== "function") {
        fail("Invalid microphone stream.");
        return false;
      }
      const callerOwnsStream = opts && opts.ownsStream === false;
      if (transcribing || voiceSessionId || recording || isRecorderLive()) {
        if (!callerOwnsStream) {
          try {
            mediaStream.getTracks().forEach((t) => t.stop());
          } catch (_) {}
        }
        fail("Voice is already active or still finishing. Wait a moment or close the voice panel.");
        return false;
      }

      skipTranscription = false;
      chunks.length = 0;
      elapsedSeconds = 0;
      autoStopFired = false;

      try {
        stream = mediaStream;
        ownsStream = !callerOwnsStream;
        const mimeType = pickMimeType();
        const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
        recorder = rec;

        rec.onstart = () => {
          recording = true;
          setState("recording");
          startTimer();
        };

        rec.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) chunks.push(e.data);
        };

        rec.onerror = () => {
          resetLocal();
          setState("idle");
          fail("Could not capture voice. Please try again.");
          releaseStream();
          recorder = null;
        };

        rec.onstop = async () => {
          const skip = skipTranscription;
          resetLocal();

          if (skip) {
            setState("idle");
            releaseStream();
            recorder = null;
            return;
          }

          const blobParts = chunks.splice(0, chunks.length);
          if (!blobParts.length) {
            setState("idle");
            fail("No audio captured. Please try again.");
            releaseStream();
            recorder = null;
            return;
          }

          const mime = rec.mimeType || blobParts[0].type || "audio/webm";
          const audioBlob = new Blob(blobParts, { type: mime });
          releaseStream();
          recorder = null;
          await finishWithBlob(audioBlob, mime);
        };

        rec.start(250);
        return true;
      } catch (err) {
        console.warn("[consumer-voice-transcribe] MediaRecorder:", err);
        fail(err && err.message ? String(err.message) : "Could not start voice recorder.");
        resetLocal();
        setState("idle");
        releaseStream();
        recorder = null;
        return false;
      }
    }

    /**
     * Fallback: awaits getUserMedia without a prior click chain (may fail in side panel).
     * @param {Promise<MediaStream>|undefined} userMediaPromise
     */
    async function startRecordingInline(userMediaPromise) {
      let s;
      try {
        s = userMediaPromise
          ? await userMediaPromise
          : await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (err) {
        console.warn("[consumer-voice-transcribe] getUserMedia:", err);
        fail(micErrorMessage(err));
        resetLocal();
        setState("idle");
        return;
      }
      await continueWithMediaStream(s, { ownsStream: true });
    }

    async function startRecording() {
      if (!isCaptureSupported()) {
        fail("Voice recording is not supported in this browser.");
        return;
      }

      if (useOffscreen) {
        await startRecordingOffscreen();
        return;
      }
      await startRecordingInline();
    }

    function confirm() {
      skipTranscription = false;
      timerPaused = false;
      stopTimer();
      if (voiceSessionId) {
        stopOffscreenAndMaybeTranscribe(false);
        return;
      }
      try {
        if (recorder && recorder.state !== "inactive") recorder.stop();
      } catch (_) {}
    }

    function cancel() {
      skipTranscription = true;
      stopTimer();
      timerPaused = false;
      if (voiceSessionId) {
        stopOffscreenAndMaybeTranscribe(true);
        return;
      }
      try {
        if (recorder && recorder.state !== "inactive") recorder.stop();
      } catch (_) {}
      releaseStream();
    }

    function togglePause() {
      if (voiceSessionId || !recorder) return false;
      if (typeof recorder.pause !== "function" || typeof recorder.resume !== "function") return false;
      try {
        if (recorder.state === "recording") {
          recorder.pause();
          timerPaused = true;
          setState("paused");
          return true;
        }
        if (recorder.state === "paused") {
          recorder.resume();
          timerPaused = false;
          setState("recording");
          return true;
        }
      } catch (_) {}
      return false;
    }

    function canPauseRecording() {
      return !!(recorder && typeof recorder.pause === "function" && !voiceSessionId);
    }

    function toggle() {
      if (recording || isRecorderLive()) confirm();
    }

    function dispose() {
      transcribing = false;
      skipTranscription = true;
      stopTimer();
      if (voiceSessionId) {
        const session = voiceSessionId;
        voiceSessionId = null;
        recording = false;
        if (session) {
          sendRuntimeVoiceMessage("TV_OFFSCREEN_VOICE_STOP", session, { cancelOnly: true }).catch(() => {});
        }
        resetLocal();
        setState("idle");
        return;
      }
      try {
        if (recorder && recorder.state !== "inactive") recorder.stop();
      } catch (_) {}
      releaseStream();
      recorder = null;
      chunks.length = 0;
      resetLocal();
      setState("idle");
    }

    return {
      toggle,
      continueWithMediaStream,
      cancel,
      confirm,
      togglePause,
      canPauseRecording,
      dispose,
      /** True while capturing or paused (second mic tap stops). */
      isRecording: () => !!(recording || isRecorderLive()),
      /** True while capture, offscreen session, or transcribe is in progress. */
      isVoiceSessionActive,
    };
  }

  root.TV.consumerVoiceTranscribe = {
    DEFAULT_TRANSCRIBE_URL,
    isCaptureSupported,
    buildAuthHeaders,
    createToggleController,
    micErrorMessage,
    checkMicPermission,
    openMicPermissionPage,
  };
})();
