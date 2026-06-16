/**
 * Full-panel voice capture UI (waveform + timer + cancel / pause / confirm).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const BAR_COUNT = 32;

  const ICON_PAUSE = `<svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>`;
  const ICON_PLAY = `<svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>`;
  const ICON_STOP = `<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>`;

  let rootEl = null;
  let barEls = [];
  let rafId = 0;
  let tickFn = null;
  let audioCtx = null;
  let analyser = null;
  let sourceNode = null;
  let secTimer = null;
  let seconds = 0;
  let callbacks = null;
  let pausedUi = false;

  function $(id) {
    return document.getElementById(id);
  }

  function stopViz() {
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
    tickFn = null;
    try {
      if (sourceNode) sourceNode.disconnect();
    } catch (_) {}
    sourceNode = null;
    try {
      if (analyser) analyser.disconnect();
    } catch (_) {}
    analyser = null;
    try {
      if (audioCtx && audioCtx.state !== "closed") void audioCtx.close();
    } catch (_) {}
    audioCtx = null;
  }

  function startFakeViz(speed) {
    const mult = speed === "slow" ? 0.045 : 0.09;
    const n = barEls.length;
    let t = 0;
    tickFn = () => {
      t += mult;
      for (let i = 0; i < n; i++) {
        const wave = Math.sin(t + i * 0.38) * 0.42 + 0.58;
        const jitter = Math.sin(t * 2.2 + i * 0.67) * 0.14;
        const pct = Math.min(96, Math.max(12, (wave + jitter) * 70 + 8));
        barEls[i].style.height = `${pct}%`;
      }
      rafId = requestAnimationFrame(tickFn);
    };
    rafId = requestAnimationFrame(tickFn);
  }

  function startRealViz(stream) {
    stopViz();
    if (!stream || !barEls.length) {
      startFakeViz("fast");
      return;
    }
    try {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) {
        startFakeViz("fast");
        return;
      }
      audioCtx = new AC();
      sourceNode = audioCtx.createMediaStreamSource(stream);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.72;
      sourceNode.connect(analyser);
      const buf = new Uint8Array(analyser.frequencyBinCount);
      const n = barEls.length;
      tickFn = () => {
        analyser.getByteFrequencyData(buf);
        const slice = Math.max(1, Math.floor(buf.length / n));
        for (let i = 0; i < n; i++) {
          let sum = 0;
          const start = i * slice;
          for (let j = 0; j < slice && start + j < buf.length; j++) sum += buf[start + j];
          const v = sum / slice;
          const pct = 10 + (v / 255) * 90;
          barEls[i].style.height = `${Math.min(98, Math.max(8, pct))}%`;
        }
        rafId = requestAnimationFrame(tickFn);
      };
      rafId = requestAnimationFrame(tickFn);
    } catch (e) {
      console.warn("[voice-mode-overlay] Web Audio:", e);
      startFakeViz("fast");
    }
  }

  function resetBarsIdle() {
    barEls.forEach((el) => {
      el.style.height = "18%";
    });
  }

  function ensureShell() {
    if (rootEl) return;
    rootEl = document.createElement("div");
    rootEl.id = "voiceModeOverlay";
    rootEl.className = "voice-mode-overlay";
    rootEl.setAttribute("role", "dialog");
    rootEl.setAttribute("aria-modal", "true");
    rootEl.setAttribute("aria-label", "Voice input");
    rootEl.innerHTML = `
      <div class="voice-mode-overlay__backdrop" aria-hidden="true"></div>
      <div class="voice-mode-overlay__card">
        <p class="voice-mode-overlay__greeting" id="voiceModeGreeting">Hi, how can we help you today?</p>
        <div class="voice-mode-overlay__viz" id="voiceModeViz" aria-hidden="true"></div>
        <p class="voice-mode-overlay__preview" id="voiceModePreview">Listening…</p>
        <div class="voice-mode-overlay__dock">
          <div class="voice-mode-overlay__timer" id="voiceModeTimer">0:00</div>
          <div class="voice-mode-overlay__actions">
            <button type="button" class="voice-mode-overlay__btn voice-mode-overlay__btn--cancel" id="voiceModeCancel" aria-label="Cancel recording">×</button>
            <button type="button" class="voice-mode-overlay__btn voice-mode-overlay__btn--main" id="voiceModeMain" aria-label="Pause or stop recording"></button>
            <button type="button" class="voice-mode-overlay__btn voice-mode-overlay__btn--confirm" id="voiceModeConfirm" aria-label="Finish and transcribe">✓</button>
          </div>
          <p class="voice-mode-overlay__hint" id="voiceModeHint">Tap to pause</p>
        </div>
      </div>
    `;
    document.body.appendChild(rootEl);

    const viz = $("voiceModeViz");
    if (viz) {
      for (let i = 0; i < BAR_COUNT; i++) {
        const b = document.createElement("span");
        b.className = "voice-viz-bar";
        viz.appendChild(b);
        barEls.push(b);
      }
    }

    $("voiceModeCancel").addEventListener("click", () => {
      if (callbacks && typeof callbacks.onCancel === "function") callbacks.onCancel();
    });
    $("voiceModeConfirm").addEventListener("click", () => {
      if (callbacks && typeof callbacks.onConfirm === "function") callbacks.onConfirm();
    });
    $("voiceModeMain").addEventListener("click", () => {
      if (callbacks && typeof callbacks.onPauseToggle === "function") {
        callbacks.onPauseToggle();
      } else if (callbacks && typeof callbacks.onConfirm === "function") {
        callbacks.onConfirm();
      }
    });
  }

  function stopSecTimer() {
    if (secTimer) {
      clearInterval(secTimer);
      secTimer = null;
    }
  }

  function renderTimer() {
    const el = $("voiceModeTimer");
    if (!el) return;
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    el.textContent = `${m}:${String(s).padStart(2, "0")}`;
  }

  function startSecTimer(reset) {
    stopSecTimer();
    if (reset !== false) seconds = 0;
    renderTimer();
    secTimer = setInterval(() => {
      seconds += 1;
      renderTimer();
    }, 1000);
  }

  function setMainButtonRecording(canPause) {
    const main = $("voiceModeMain");
    const hint = $("voiceModeHint");
    if (!main) return;
    if (canPause) {
      main.innerHTML = ICON_PAUSE;
      main.setAttribute("aria-label", "Pause recording");
      if (hint) hint.textContent = "Tap to pause";
    } else {
      main.innerHTML = ICON_STOP;
      main.setAttribute("aria-label", "Stop and transcribe");
      if (hint) hint.textContent = "Tap to stop and transcribe";
    }
    main.disabled = false;
  }

  function setMainButtonPaused() {
    const main = $("voiceModeMain");
    const hint = $("voiceModeHint");
    if (main) {
      main.innerHTML = ICON_PLAY;
      main.setAttribute("aria-label", "Resume recording");
      main.disabled = false;
    }
    if (hint) hint.textContent = "Tap to resume";
  }

  function open(options) {
    ensureShell();
    callbacks = options || {};
    pausedUi = false;
    rootEl.hidden = false;
    rootEl.setAttribute("aria-hidden", "false");

    const greet = $("voiceModeGreeting");
    if (greet && options && options.greeting) greet.textContent = options.greeting;

    const prev = $("voiceModePreview");
    if (prev) prev.textContent = "Listening…";

    const viz = $("voiceModeViz");
    if (viz) viz.classList.remove("voice-mode-overlay__viz--dim");

    setMainButtonRecording(Boolean(options && options.canPause));
    startSecTimer(true);

    if (options && options.mediaStream) {
      startRealViz(options.mediaStream);
    } else {
      startFakeViz("fast");
    }
  }

  function setPaused(on) {
    pausedUi = !!on;
    const viz = $("voiceModeViz");
    const prev = $("voiceModePreview");
    stopViz();
    if (on) {
      stopSecTimer();
      if (prev) prev.textContent = "Paused";
      setMainButtonPaused();
      if (viz) viz.classList.remove("voice-mode-overlay__viz--dim");
      startFakeViz("slow");
    } else {
      startSecTimer(false);
      if (prev) prev.textContent = "Listening…";
      if (callbacks && callbacks.canPause) setMainButtonRecording(true);
      else setMainButtonRecording(false);
      if (viz) viz.classList.remove("voice-mode-overlay__viz--dim");
      if (callbacks && callbacks.mediaStream) startRealViz(callbacks.mediaStream);
      else startFakeViz("fast");
    }
  }

  function setTranscribing() {
    pausedUi = false;
    stopViz();
    stopSecTimer();
    const prev = $("voiceModePreview");
    const hint = $("voiceModeHint");
    const main = $("voiceModeMain");
    const viz = $("voiceModeViz");
    if (prev) prev.textContent = "Transcribing what we heard…";
    if (hint) hint.textContent = "";
    if (main) {
      main.innerHTML = ICON_STOP;
      main.disabled = true;
    }
    if (viz) {
      viz.classList.add("voice-mode-overlay__viz--dim");
      resetBarsIdle();
    }
  }

  function close() {
    stopSecTimer();
    stopViz();
    pausedUi = false;
    callbacks = null;
    if (rootEl) {
      rootEl.hidden = true;
      rootEl.setAttribute("aria-hidden", "true");
    }
    barEls.forEach((el) => {
      el.style.height = "";
    });
  }

  root.TV.voiceModeOverlay = {
    open,
    close,
    setPaused,
    setTranscribing,
  };
})();
