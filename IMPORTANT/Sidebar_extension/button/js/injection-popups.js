/**
 * Velocity in-page popups (content script).
 *
 * Three bottom-right popups that overlay any LLM chat platform:
 *   1. First-enhance celebration  — "You just enhanced your first prompt!"
 *      • Auto-fades out after FIRST_ENHANCE_FADE_MS
 *      • Triggered once globally; only fires on chatgpt.com (handled by the
 *        caller in injection-modal.js).
 *   2. Daily-limit reached         — "Daily limit reached!" gold/Pro upsell
 *      • Stays until dismissed; CTA opens the invite hosted page.
 *   3. Like-reward incentive       — "Glad you loved it!" invite upsell
 *      • Fires when the user thumbs-ups an enhanced prompt (any host).
 *      • Auto-fades out after LIKE_REWARD_FADE_MS; CTA opens the invite page.
 *      • Caller in injection-modal.js gates one-shot via chrome.storage.
 *
 * Also mounts floating "Test" buttons in the bottom-left so QA can fire each
 * popup on demand. The test buttons are hidden in production unless the
 * `VELOCITY_SHOW_TEST_BUTTONS` localStorage flag is set to "1".
 *
 * @global VelocityInjectionPopups
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;

  const FIRST_ENHANCE_FADE_MS = 3000;
  const LIKE_REWARD_FADE_MS = 5500;
  // Canonical invite URL. The hosted page reads `invite=1` to open the
  // invite-a-friend flow. UTM params are appended for attribution but are
  // never required for the modal to open.
  const INVITE_URL =
    "https://thinkvelocity.in/chat?invite=1&source=extension&utm_source=extension&utm_medium=chrome_extension&utm_campaign=invite_friend";
  const PRO_URL =
    "https://thinkvelocity.in/?source=extension&utm_source=extension&utm_medium=chrome_extension&utm_campaign=daily_limit_upgrade";

  // ── Asset helpers ────────────────────────────────────────────
  function logoUrl() {
    try {
      return chrome.runtime.getURL("assets/Velocity_logo.png");
    } catch (_) {
      return "";
    }
  }

  function svgClose() {
    return (
      '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" aria-hidden="true">' +
      '<path d="M6 6l12 12M18 6L6 18"/></svg>'
    );
  }

  function svgGift() {
    return (
      '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" ' +
      'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<polyline points="20 12 20 22 4 22 4 12"/>' +
      '<rect x="2" y="7" width="20" height="5"/>' +
      '<line x1="12" y1="22" x2="12" y2="7"/>' +
      '<path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"/>' +
      '<path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"/>' +
      "</svg>"
    );
  }

  function svgArrowRight() {
    return (
      '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<line x1="5" y1="12" x2="19" y2="12"/>' +
      '<polyline points="12 5 19 12 12 19"/></svg>'
    );
  }

  function svgFeatureLightning() {
    return (
      '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" ' +
      'stroke-width="1.8" stroke-linejoin="round" aria-hidden="true">' +
      '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'
    );
  }

  function svgFeatureBrain() {
    return (
      '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" ' +
      'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M12 5c-1.5 0-2.8.8-3.5 2-.3-.2-.7-.3-1.1-.3-1.7 0-3 1.6-3 3.5 0 .6.2 1.2.4 1.7-1.1.6-1.8 1.8-1.8 3.1 0 2 1.6 3.6 3.5 3.6h.3c.4 1.3 1.5 2.2 2.8 2.4"/>' +
      '<path d="M12 5c1.5 0 2.8.8 3.5 2 .3-.2.7-.3 1.1-.3 1.7 0 3 1.6 3 3.5 0 .6-.2 1.2-.4 1.7 1.1.6 1.8 1.8 1.8 3.1 0 2-1.6 3.6-3.5 3.6h-.3c-.4 1.3-1.5 2.2-2.8 2.4"/>' +
      "</svg>"
    );
  }

  function svgFeatureRefine() {
    return (
      '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" ' +
      'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M21 12a9 9 0 0 1-15.36 6.36"/>' +
      '<path d="M3 12a9 9 0 0 1 15.36-6.36"/>' +
      '<polyline points="21 4 21 9 16 9"/>' +
      '<polyline points="3 20 3 15 8 15"/></svg>'
    );
  }

  // ── Popup mount/dismiss helpers ──────────────────────────────
  function getOrCreateLayer() {
    let layer = document.getElementById("velocity-injection-popups-layer");
    if (layer) return layer;
    layer = document.createElement("div");
    layer.id = "velocity-injection-popups-layer";
    layer.className = "velocity-popup-layer";
    document.body.appendChild(layer);
    return layer;
  }

  function dismiss(popupEl) {
    if (!popupEl || !popupEl.parentNode) return;
    popupEl.classList.add("is-leaving");
    setTimeout(() => {
      if (popupEl.parentNode) popupEl.parentNode.removeChild(popupEl);
    }, 240);
  }

  /** Drop popup synchronously (no leaving animation) so a fresh re-trigger animates cleanly. */
  function removeInstant(popupEl) {
    if (popupEl && popupEl.parentNode) {
      popupEl.parentNode.removeChild(popupEl);
    }
  }

  function buildCloseBtn(onClick) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "velocity-popup-close";
    btn.setAttribute("aria-label", "Dismiss");
    btn.innerHTML = svgClose();
    btn.addEventListener("click", onClick);
    return btn;
  }

  // ── 1. First-enhance popup ───────────────────────────────────
  function showFirstEnhancePopup(opts) {
    const layer = getOrCreateLayer();
    const existing = layer.querySelector(".velocity-popup--first-enhance");
    if (existing) removeInstant(existing);

    const o = opts || {};
    const popup = document.createElement("section");
    popup.className = "velocity-popup velocity-popup--first-enhance";
    popup.setAttribute("role", "dialog");
    popup.setAttribute("aria-label", "First prompt enhanced");

    popup.innerHTML =
      '<div class="velocity-popup-logo" aria-hidden="true">' +
      '<img src="' + logoUrl() + '" alt="" decoding="async"/></div>' +
      '<h2 class="velocity-popup-title">You just enhanced your first prompt!</h2>' +
      '<p class="velocity-popup-body">Notice the difference? Cleaner prompts. Better outputs. Less back-and-forth.</p>' +
      '<button type="button" class="velocity-popup-invite-card" data-invite>' +
      '<span class="velocity-popup-invite-icon">' + svgGift() + "</span>" +
      '<span class="velocity-popup-invite-text">' +
      '<span class="velocity-popup-invite-headline">Invite a friend &amp;</span>' +
      '<span class="velocity-popup-invite-sub">Get 5 extra prompts</span>' +
      "</span>" +
      '<span class="velocity-popup-invite-chev">' + svgArrowRight() + "</span>" +
      "</button>" +
      '<button type="button" class="velocity-popup-cta velocity-popup-cta--cyan" data-cta>Invite a friend</button>';

    popup.appendChild(buildCloseBtn(() => dismiss(popup)));
    layer.appendChild(popup);

    popup.querySelector("[data-invite]").addEventListener("click", () => {
      openInvite();
    });
    popup.querySelector("[data-cta]").addEventListener("click", () => {
      // Default CTA → invite flow. Caller can override via opts.onCta.
      const ctaHandler = typeof o.onCta === "function" ? o.onCta : openInvite;
      ctaHandler();
    });

    // Auto-fade after FIRST_ENHANCE_FADE_MS
    const fadeMs = typeof o.autoDismissMs === "number" ? o.autoDismissMs : FIRST_ENHANCE_FADE_MS;
    if (fadeMs > 0) {
      setTimeout(() => dismiss(popup), fadeMs);
    }
    return popup;
  }

  // ── 1b. Like-reward incentive popup ──────────────────────────
  // Visually identical to the first-enhance popup (logo + headline + invite
  // card + cyan CTA) but framed as an incentive reward: the moment the user
  // expresses they liked the enhancement (thumbs-up) we surface the
  // invite-a-friend program as a way to earn more "incentive prompts".
  // Auto-fades after LIKE_REWARD_FADE_MS; caller decides whether to gate
  // this to a single global firing.
  function showLikeRewardPopup(opts) {
    const layer = getOrCreateLayer();
    const existing = layer.querySelector(".velocity-popup--like-reward");
    if (existing) removeInstant(existing);

    const o = opts || {};
    const popup = document.createElement("section");
    popup.className = "velocity-popup velocity-popup--like-reward";
    popup.setAttribute("role", "dialog");
    popup.setAttribute("aria-label", "Earn incentive prompts");

    popup.innerHTML =
      '<div class="velocity-popup-logo" aria-hidden="true">' +
      '<img src="' + logoUrl() + '" alt="" decoding="async"/></div>' +
      '<h2 class="velocity-popup-title">Glad you loved it!</h2>' +
      '<p class="velocity-popup-body">Earn 5 incentive prompts every time a friend joins Velocity. Share the magic, keep enhancing.</p>' +
      '<button type="button" class="velocity-popup-invite-card" data-invite>' +
      '<span class="velocity-popup-invite-icon">' + svgGift() + "</span>" +
      '<span class="velocity-popup-invite-text">' +
      '<span class="velocity-popup-invite-headline">Invite a friend &amp;</span>' +
      '<span class="velocity-popup-invite-sub">Get 5 extra prompts</span>' +
      "</span>" +
      '<span class="velocity-popup-invite-chev">' + svgArrowRight() + "</span>" +
      "</button>" +
      '<button type="button" class="velocity-popup-cta velocity-popup-cta--cyan" data-cta>Invite a friend</button>';

    popup.appendChild(buildCloseBtn(() => dismiss(popup)));
    layer.appendChild(popup);

    popup.querySelector("[data-invite]").addEventListener("click", () => {
      openInvite();
    });
    popup.querySelector("[data-cta]").addEventListener("click", () => {
      const ctaHandler = typeof o.onCta === "function" ? o.onCta : openInvite;
      ctaHandler();
    });

    const fadeMs = typeof o.autoDismissMs === "number" ? o.autoDismissMs : LIKE_REWARD_FADE_MS;
    if (fadeMs > 0) {
      setTimeout(() => dismiss(popup), fadeMs);
    }
    return popup;
  }

  // ── 2. Daily-limit popup ─────────────────────────────────────
  // Re-triggered on every USAGE_EXHAUSTED enhance attempt: instantly removes
  // any existing daily-limit popup so the new one animates in cleanly, giving
  // the user clear visual feedback that the click was registered.
  function showDailyLimitPopup(opts) {
    const layer = getOrCreateLayer();
    const existing = layer.querySelector(".velocity-popup--daily-limit");
    if (existing) removeInstant(existing);

    const o = opts || {};
    const popup = document.createElement("section");
    popup.className = "velocity-popup velocity-popup--daily-limit";
    popup.setAttribute("role", "dialog");
    popup.setAttribute("aria-label", "Daily limit reached");

    popup.innerHTML =
      '<h2 class="velocity-popup-title velocity-popup-title--gold">Daily limit reached!</h2>' +
      '<p class="velocity-popup-body">You’re already optimizing prompts faster than most users. Upgrade to Pro for unlimited enhancements.</p>' +
      '<ul class="velocity-popup-features" aria-label="Pro features">' +
      '<li class="velocity-popup-feature"><span class="velocity-popup-feature-ico">' +
      svgFeatureLightning() + "</span><span>Unlimited enhancements</span></li>" +
      '<li class="velocity-popup-feature"><span class="velocity-popup-feature-ico">' +
      svgFeatureBrain() + "</span><span>Unlimited Memory</span></li>" +
      '<li class="velocity-popup-feature"><span class="velocity-popup-feature-ico">' +
      svgFeatureRefine() + "</span><span>Unlimited Refines</span></li>" +
      "</ul>" +
      '<div class="velocity-popup-cta-row">' +
      '<button type="button" class="velocity-popup-cta velocity-popup-cta--gold" data-pro>Upgrade to Pro</button>' +
      '<button type="button" class="velocity-popup-cta-secondary" data-invite>Invite a friend</button>' +
      "</div>";

    popup.appendChild(buildCloseBtn(() => dismiss(popup)));
    layer.appendChild(popup);

    popup.querySelector("[data-pro]").addEventListener("click", () => {
      const proHandler = typeof o.onPro === "function" ? o.onPro : openPro;
      proHandler();
    });
    popup.querySelector("[data-invite]").addEventListener("click", () => {
      openInvite();
    });

    // No auto-dismiss — user must close or act
    return popup;
  }

  // ── URL openers ──────────────────────────────────────────────
  function openInvite() {
    try {
      window.open(INVITE_URL, "_blank", "noopener,noreferrer");
    } catch (_) {}
  }

  function openPro() {
    try {
      window.open(PRO_URL, "_blank", "noopener,noreferrer");
    } catch (_) {}
  }

  // ── 3. Install-tutorial popup (in-page overlay) ──────────────
  // Rendered directly on the host LLM page (e.g. chatgpt.com) instead of in
  // a separate chrome-extension://… tab. Auto-shown post-install via the
  // `velocity_show_install_tutorial_popup` storage flag; also fireable from
  // the QA test bar.
  function showInstallTutorialPopup(opts) {
    // Singleton — never stack
    const existing = document.getElementById("velocity-install-tutorial-overlay");
    if (existing) existing.parentNode && existing.parentNode.removeChild(existing);

    const o = opts || {};
    const overlay = document.createElement("div");
    overlay.id = "velocity-install-tutorial-overlay";
    overlay.className = "velocity-tutorial-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "Welcome to Velocity");

    const posterUrl = logoUrl();
    const stepVideos = [
      { title: "Write or speak your prompt", desc: "Use ChatGPT, Claude, Gemini, or any AI tool normally.", file: "assets/Extension videos/tutorialvideo_step1.mp4" },
      { title: "Enhance seamlessly", desc: "Your lazy prompt turned into an enhanced prompt effortlessly.", file: "assets/Extension videos/tutorialvideo_step2.mp4" },
      { title: "Insert & continue", desc: "Drop the upgraded prompt back into the chat instantly.", file: "assets/Extension videos/tutorialvideo_step3.mp4" },
    ].map((s) => {
      let url = "";
      try { url = chrome.runtime.getURL(s.file); } catch (_) { url = ""; }
      return { ...s, url };
    });

    const stepsHtml = stepVideos
      .map(
        (s, i) =>
          (i > 0
            ? '<li class="velocity-tutorial-step-connector" aria-hidden="true"></li>'
            : "") +
          '<li class="velocity-tutorial-step" data-step="' + i + '">' +
          '<span class="velocity-tutorial-step-num" aria-hidden="true">' + (i + 1) + "</span>" +
          '<div class="velocity-tutorial-step-body">' +
          '<p class="velocity-tutorial-step-title">' + s.title + "</p>" +
          '<p class="velocity-tutorial-step-desc">' + s.desc + "</p>" +
          "</div></li>"
      )
      .join("");
    const videosHtml = stepVideos
      .map(
        (_s, i) =>
          '<video class="velocity-tutorial-video-el" data-video-step="' + i + '" muted playsinline preload="auto"' +
          (posterUrl ? ' poster="' + posterUrl + '"' : "") +
          "></video>"
      )
      .join("");

    overlay.innerHTML =
      '<div class="velocity-tutorial-backdrop" data-backdrop></div>' +
      '<main class="velocity-tutorial-card" role="document">' +
      '<button type="button" class="velocity-tutorial-close" aria-label="Close" data-close>' +
      svgClose() + "</button>" +
      '<header class="velocity-tutorial-header">' +
      '<h1 class="velocity-tutorial-title">' +
      (posterUrl
        ? '<img class="velocity-tutorial-title-logo" src="' + posterUrl + '" alt="" aria-hidden="true" decoding="async"/>'
        : "") +
      '<span>Turn lazy prompts into enhanced prompts for any AI</span>' +
      "</h1>" +
      "</header>" +
      '<section class="velocity-tutorial-steps-section">' +
      '<p class="velocity-tutorial-steps-heading">How do I use Velocity?</p>' +
      '<ol class="velocity-tutorial-steps" aria-label="How Velocity works">' +
      stepsHtml +
      "</ol></section>" +
      '<section class="velocity-tutorial-video" aria-label="Velocity preview">' +
      videosHtml +
      '<div class="velocity-tutorial-video-fallback" aria-hidden="true">' +
      (posterUrl
        ? '<img class="velocity-tutorial-video-fallback-logo" src="' + posterUrl + '" alt="" decoding="async"/>'
        : "") +
      '<p class="velocity-tutorial-video-fallback-title">Velocity preview</p>' +
      '<p class="velocity-tutorial-video-fallback-sub">A quick look at the enhance flow inside your AI chat.</p>' +
      "</div>" +
      '<div class="velocity-tutorial-video-progress" aria-hidden="true">' +
      stepVideos
        .map((_, i) => '<span class="velocity-tutorial-video-dot" data-dot="' + i + '"></span>')
        .join("") +
      "</div>" +
      "</section>" +
      '<div class="velocity-tutorial-cta-row">' +
      '<button type="button" class="velocity-tutorial-next" data-next>Next' +
      '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M5 12h14M12 5l7 7-7 7"/></svg></button>' +
      '<button type="button" class="velocity-tutorial-cta" data-try style="display:none;">Start Prompting</button>' +
      "</div>" +
      "</main>";

    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add("is-open"));

    function dismissOverlay() {
      if (!overlay.parentNode) return;
      overlay.classList.remove("is-open");
      overlay.classList.add("is-leaving");
      try { videoEls.forEach((el) => el.pause()); } catch (_) {}
      setTimeout(() => {
        if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
        document.removeEventListener("keydown", onKey);
        // Release any blob URLs we created for the step videos
        blobUrls.forEach((u) => { try { URL.revokeObjectURL(u); } catch (_) {} });
        blobUrls.length = 0;
      }, 220);
    }
    function onKey(e) {
      if (e.key === "Escape") dismissOverlay();
    }
    document.addEventListener("keydown", onKey);

    overlay.querySelector("[data-close]").addEventListener("click", dismissOverlay);
    overlay.querySelector("[data-backdrop]").addEventListener("click", dismissOverlay);
    
    const nextBtn = overlay.querySelector("[data-next]");
    const tryBtn = overlay.querySelector("[data-try]");
    
    function updateCtaButtons() {
      if (currentStep >= stepVideos.length - 1) {
        if (nextBtn) nextBtn.style.display = "none";
        if (tryBtn) tryBtn.style.display = "inline-flex";
      } else {
        if (nextBtn) nextBtn.style.display = "inline-flex";
        if (tryBtn) tryBtn.style.display = "none";
      }
    }
    
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        if (currentStep < stepVideos.length - 1) {
          playStep(currentStep + 1);
          updateCtaButtons();
        }
      });
    }
    
    if (tryBtn) {
      tryBtn.addEventListener("click", () => {
        const handler = typeof o.onTry === "function" ? o.onTry : dismissOverlay;
        handler();
      });
    }

    // ── Step ↔ video sequencer ──────────────────────────────────
    const videoEls = Array.prototype.slice.call(overlay.querySelectorAll(".velocity-tutorial-video-el"));
    const videoSection = overlay.querySelector(".velocity-tutorial-video");
    const stepEls = Array.prototype.slice.call(overlay.querySelectorAll(".velocity-tutorial-step"));
    const connectorEls = Array.prototype.slice.call(overlay.querySelectorAll(".velocity-tutorial-step-connector"));
    const dotEls = Array.prototype.slice.call(overlay.querySelectorAll(".velocity-tutorial-video-dot"));
    const blobUrls = [];
    let currentStep = -1;
    let pendingPlay = -1;

    function markVideoMissing() {
      if (videoSection) videoSection.classList.add("is-video-missing");
    }

    function highlight(idx) {
      if (idx === currentStep) return;
      currentStep = idx;
      stepEls.forEach((el, i) => el.classList.toggle("is-active", i === idx));
      // Connectors sit BETWEEN steps, so connector at position i links
      // step[i] to step[i+1]. Mark a connector as "passed" once the user
      // has advanced past the step that precedes it.
      connectorEls.forEach((el, i) => el.classList.toggle("is-passed", i < idx));
      dotEls.forEach((el, i) => el.classList.toggle("is-active", i === idx));
    }

    function playStep(idx) {
      if (!videoEls.length) return;
      const safeIdx = ((idx % stepVideos.length) + stepVideos.length) % stepVideos.length;
      const activeVideo = videoEls[safeIdx];
      if (!activeVideo) {
        markVideoMissing();
        return;
      }
      highlight(safeIdx);
      videoEls.forEach((el, i) => {
        const isActive = i === safeIdx;
        el.classList.toggle("is-active", isActive);
        try {
          if (isActive) {
            el.currentTime = 0;
          } else {
            el.pause();
          }
        } catch (_) {}
      });
      // If the blob hasn't loaded yet, remember the step and let the loader
      // start it the moment it becomes ready.
      if (!activeVideo.src) {
        pendingPlay = safeIdx;
        return;
      }
      pendingPlay = -1;
      const playPromise = activeVideo.play();
      if (playPromise && typeof playPromise.catch === "function") {
        playPromise.catch(() => {});
      }
    }

    // Host CSPs (chatgpt.com, claude.ai, …) block both
    //   <video src="chrome-extension://…">    (media-src)
    //   fetch("chrome-extension://…")          (connect-src)
    // so we ask the background service worker to fetch the bytes, then build
    // a same-origin blob: URL — page CSP permits blob: media.
    function loadStepBlob(i) {
      const meta = stepVideos[i];
      const el = videoEls[i];
      if (!el || !meta || !meta.file) return Promise.resolve(false);
      return new Promise((resolve) => {
        let settled = false;
        const done = (ok) => { if (!settled) { settled = true; resolve(ok); } };
        try {
          chrome.runtime.sendMessage(
            {
              action: "TV_FETCH_PACKAGED_RESOURCE",
              requestId: "tut-vid-" + i + "-" + Date.now(),
              payload: { path: meta.file },
            },
            (response) => {
              if (chrome.runtime.lastError || !response || !response.success || !response.data) {
                done(false);
                return;
              }
              try {
                const data = response.data;
                const bin = atob(String(data.base64 || ""));
                const bytes = new Uint8Array(bin.length);
                for (let j = 0; j < bin.length; j++) bytes[j] = bin.charCodeAt(j);
                const blob = new Blob([bytes], { type: data.mime || "video/mp4" });
                const objectUrl = URL.createObjectURL(blob);
                if (!el.isConnected) {
                  try { URL.revokeObjectURL(objectUrl); } catch (_) {}
                  done(false);
                  return;
                }
                blobUrls.push(objectUrl);
                el.src = objectUrl;
                if (pendingPlay === i || (currentStep === i && el.paused)) {
                  const p = el.play();
                  if (p && typeof p.catch === "function") p.catch(() => {});
                  pendingPlay = -1;
                }
                done(true);
              } catch (_) {
                done(false);
              }
            }
          );
        } catch (_) {
          done(false);
        }
      });
    }

    if (videoEls.length) {
      videoEls.forEach((el) => {
        el.addEventListener("ended", () => {
          playStep(currentStep + 1);
          updateCtaButtons();
        });
      });
      stepEls.forEach((el, i) => {
        el.addEventListener("click", () => {
          playStep(i);
          updateCtaButtons();
        });
      });
      dotEls.forEach((el, i) => {
        el.addEventListener("click", () => {
          playStep(i);
          updateCtaButtons();
        });
      });
      // Prefer step 1 first so it can start playing the moment its blob is ready
      playStep(0);
      updateCtaButtons();
      Promise.all(stepVideos.map((_v, i) => loadStepBlob(i))).then((results) => {
        if (results.every((ok) => !ok)) markVideoMissing();
      });
    } else {
      markVideoMissing();
    }

    return overlay;
  }

  function isChatGPTHost() {
    try {
      const h = (location.hostname || "").toLowerCase();
      return (
        h === "chatgpt.com" ||
        h.endsWith(".chatgpt.com") ||
        h === "chat.openai.com" ||
        h.endsWith(".chat.openai.com")
      );
    } catch (_) {
      return false;
    }
  }

  // Tutorial popup: install-time, ChatGPT only, one-shot.
  // background.js sets `velocity_show_install_tutorial_popup` on install and
  // opens chatgpt.com — we consume the flag the first time the user lands on
  // ChatGPT, so it never re-shows (and never appears on Claude/Gemini/etc.).
  function maybeShowInstallTutorialPopup() {
    if (!isChatGPTHost()) return;
    try {
      if (!chrome || !chrome.storage || !chrome.storage.local) return;
      chrome.storage.local.get(["velocity_show_install_tutorial_popup"], (r) => {
        if (chrome.runtime.lastError) return;
        if (!r || !r.velocity_show_install_tutorial_popup) return;
        try { chrome.storage.local.remove("velocity_show_install_tutorial_popup"); } catch (_) {}
        // Give the host page a moment to settle so we don't compete with its
        // own initial layout/animations.
        setTimeout(showInstallTutorialPopup, 600);
      });
    } catch (_) {}
  }

  // ── QA test buttons (floating, bottom-left) ──────────────────

  function mountTestButtons() {
    // Hidden in production. Dev override: localStorage.VELOCITY_SHOW_TEST_BUTTONS = "1"
    let enabled = false;
    try {
      enabled = localStorage.getItem("VELOCITY_SHOW_TEST_BUTTONS") === "1";
    } catch (_) {}
    if (!enabled) return;
    if (document.getElementById("velocity-popup-testbar")) return;

    const bar = document.createElement("div");
    bar.id = "velocity-popup-testbar";
    bar.className = "velocity-popup-testbar";
    bar.innerHTML =
      '<span class="velocity-popup-testbar-label">QA</span>' +
      '<button type="button" data-test="tutorial">Test Tutorial Popup</button>' +
      '<button type="button" data-test="first">Test 1st Popup</button>' +
      '<button type="button" data-test="like">Test Like Reward</button>' +
      '<button type="button" data-test="limit">Test Limit Popup</button>';
    document.body.appendChild(bar);

    bar.querySelector('[data-test="tutorial"]').addEventListener("click", () => {
      showInstallTutorialPopup();
    });
    bar.querySelector('[data-test="first"]').addEventListener("click", () => {
      showFirstEnhancePopup();
    });
    bar.querySelector('[data-test="like"]').addEventListener("click", () => {
      showLikeRewardPopup();
    });
    bar.querySelector('[data-test="limit"]').addEventListener("click", () => {
      showDailyLimitPopup();
    });
  }

  function init() {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => {
        mountTestButtons();
        maybeShowInstallTutorialPopup();
      }, { once: true });
    } else {
      mountTestButtons();
      maybeShowInstallTutorialPopup();
    }
  }

  root.VelocityInjectionPopups = {
    showFirstEnhancePopup,
    showLikeRewardPopup,
    showDailyLimitPopup,
    showInstallTutorialPopup,
    maybeShowInstallTutorialPopup,
    mountTestButtons,
    INVITE_URL,
  };

  init();
})();
