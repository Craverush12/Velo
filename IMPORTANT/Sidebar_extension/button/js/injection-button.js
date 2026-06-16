/**
 * Velocity injection button group (Pretty Prompt–style spec).
 * Default core (fixed): [ ✨ Enhance ] [ ⋮⋮ Drag ]
 * Hover (reveal order, closest to Enhance first):
 *   [ Prompt Library ] [ 🎙 Voice ] [ ✨ Enhance ] [ ⋮⋮ Drag ]
 * Hover expansion extends to the left; the core (Enhance + Drag) does not
 * move. Mic sits adjacent to Enhance so voice → enhance is one short hop;
 * Prompt Library is the outermost reveal.
 * Hosted links match Vel-Next `/chat?tab=` routes (see sidebar-hosted-nav.js).
 */
(function () {
  const GAP_ABOVE = 10;
  const BAR_STORAGE_KEY = "velocity_injection_bar_offset";
  const DRAG_CLICK_THRESHOLD_PX = 6;
  const HIDE_LIB_KEY = "velocity_hide_library_btn";
  // One-shot flag set by background.js on `chrome.runtime.onInstalled`
  // (reason === "install"). When the injection button is rendered on a
  // supported LLM page, it shows a welcome coachmark next to the bar and
  // clears the flag so the popup never fires twice.
  const POST_INSTALL_FLAG = "velocity_show_post_install_popup";
  const COACHMARK_AUTO_DISMISS_MS = 14000;

  /** Vel-Next chat deep links — same paths as TV.sidebarHostedNav.LINKS */
  const HOSTED_LINKS = {
    library: { path: "/chat?tab=library", utm: "injection_prompt_library" },
  };

  const MIC_SVG =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>' +
    '<path d="M19 10v2a7 7 0 0 1-14 0v-2"/>' +
    '<line x1="12" y1="19" x2="12" y2="23"/>' +
    '<line x1="8" y1="23" x2="16" y2="23"/>' +
    '</svg>';

  const SPARKLE_SVG =
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
    '<path class="vel-sparkle-main" d="M12 2L13.9 8.1L20 10L13.9 11.9L12 18L10.1 11.9L4 10L10.1 8.1L12 2Z" fill="#F59E0B"/>' +
    '<path class="vel-sparkle-sub" d="M19 14L19.8 16.5L22.3 17.3L19.8 18.1L19 20.6L18.2 18.1L15.7 17.3L18.2 16.5L19 14Z" fill="#FBBF24" opacity="0.9"/>' +
    "</svg>";
  // Space-free paths — chrome.runtime.getURL breaks on "Extension icons/" on some hosts.
  const LIBRARY_ICON_PATH = "assets/extension-icons/prompt_library.png";

  function extensionAssetUrl(relativePath) {
    try {
      const raw = chrome.runtime.getURL(relativePath);
      return encodeURI(raw);
    } catch (_) {
      return "";
    }
  }

  let barEl = null;
  let boundInput = null;
  let userDragged = false;
  let dragState = null;
  let rafId = 0;
  let collapseTimer = 0;
  let isDragging = false;
  let pinnedExpanded = false;
  let libraryBtnEl = null;
  let welcomeCoachmarkEl = null;
  let welcomeCoachmarkChecked = false;

  function hp() {
    return globalThis.VelocityHostPlatforms;
  }

  function detectPlatform() {
    const api = hp();
    return api ? api.detectPlatform() : null;
  }

  function findInput() {
    const api = hp();
    return api ? api.findChatInput(detectPlatform()) : null;
  }

  function readInputText(input) {
    if (!input) return "";
    if (input.tagName === "TEXTAREA" || input.tagName === "INPUT") return (input.value || "").trim();
    if (input.isContentEditable) return (input.innerText || input.textContent || "").trim();
    return "";
  }

  function writeInputText(input, text) {
    const inj = globalThis.VelocityPlatformInject;
    if (inj && typeof inj.injectText === "function") {
      inj.injectText(input, text);
      return;
    }
    if (!input) return;
    const t = String(text || "");
    if (input.tagName === "TEXTAREA" || input.tagName === "INPUT") {
      input.value = t;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    } else if (input.isContentEditable) {
      input.textContent = t;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  function isLibraryHidden() {
    try {
      return sessionStorage.getItem(HIDE_LIB_KEY) === "1";
    } catch (_) {
      return false;
    }
  }

  function isExcludedInput(input) {
    if (!input) return true;
    try {
      if (input.closest(".velocity-injection-bar")) return true;
    } catch (_) {}
    return false;
  }

  function buildDragDots() {
    const grid = document.createElement("span");
    grid.className = "velocity-drag-dots";
    for (let i = 0; i < 6; i++) grid.appendChild(document.createElement("span"));
    return grid;
  }

  function toolBtn(title, svg, action) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "velocity-injection-tool-btn";
    btn.title = title;
    btn.setAttribute("aria-label", title);
    btn.dataset.tooltip = title;
    btn.dataset.action = action;
    const icon = document.createElement("span");
    icon.className = "velocity-injection-tool-icon";
    icon.innerHTML = svg;
    btn.appendChild(icon);
    return btn;
  }

  function toolBtnImg(title, iconPath, action) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "velocity-injection-tool-btn";
    btn.title = title;
    btn.setAttribute("aria-label", title);
    btn.dataset.tooltip = title;
    btn.dataset.action = action;
    const icon = document.createElement("span");
    icon.className = "velocity-injection-tool-icon velocity-injection-tool-icon--img";
    const img = document.createElement("img");
    img.src = extensionAssetUrl(iconPath);
    img.alt = "";
    img.setAttribute("aria-hidden", "true");
    img.draggable = false;
    icon.appendChild(img);
    btn.appendChild(icon);
    return btn;
  }

  function setGroupExpanded(expanded) {
    if (!barEl) return;
    const on = Boolean(expanded);
    barEl.classList.toggle("is-expanded", on);
    const exp = barEl.querySelector(".velocity-injection-expandable");
    if (exp) exp.setAttribute("aria-hidden", on ? "false" : "true");
  }

  function scheduleCollapse() {
    if (collapseTimer) clearTimeout(collapseTimer);
    if (isDragging || dragState || pinnedExpanded) return;
    collapseTimer = window.setTimeout(() => setGroupExpanded(false), 260);
  }

  function cancelCollapse() {
    if (collapseTimer) {
      clearTimeout(collapseTimer);
      collapseTimer = 0;
    }
  }

  function dbg() {
    return globalThis.VelocitySidebarDebug;
  }

  function openHostedPage(key) {
    const cfg = HOSTED_LINKS[key];
    if (!cfg) return;
    const platform = detectPlatform() || "unknown";
    const d = dbg();
    if (d) d.boot("openHostedPage:", key, { path: cfg.path, platform });
    chrome.runtime.sendMessage(
      {
        action: "TV_OPEN_HOSTED_PAGE",
        requestId: "inj-" + Date.now(),
        payload: {
          path: cfg.path,
          platform,
          utmContent: cfg.utm,
        },
      },
      (response) => {
        const le = chrome.runtime.lastError;
        if (d) {
          d.logRuntimeMessage("TV_OPEN_HOSTED_PAGE", response, le);
        }
        if (le) {
          console.error("[Velocity] TV_OPEN_HOSTED_PAGE failed:", le.message);
          return;
        }
        if (response && response.success === false) {
          console.warn("[Velocity] TV_OPEN_HOSTED_PAGE rejected:", response.error);
        }
      }
    );
  }

  function openModal(opts) {
    const M = globalThis.VelocityInjectionModal;
    const d = dbg();
    if (d) d.boot("openModal:", opts && opts.tab);
    if (!M || typeof M.open !== "function") {
      if (d) d.error("VelocityInjectionModal not loaded — check manifest script order");
      return;
    }
    const input = boundInput || findInput();
    M.open({
      tab: opts.tab || "improve",
      prompt: readInputText(input),
      onApply: (text) => {
        if (input) writeInputText(input, text);
      },
    });
  }

  function openVoiceMode() {
    const d = dbg();
    if (d) d.log("openVoiceMode triggered");
    const platform = detectPlatform() || "";
    const requestId = "inj-voice-" + Date.now();
    const payload = {
      source: "injection_voice_btn",
      platform: platform,
      target: "voice",
    };
    chrome.runtime.sendMessage(
      { action: "TV_OPEN_SIDE_PANEL", requestId, payload },
      (response) => {
        const lastErr = chrome.runtime.lastError;
        if (lastErr) {
          if (d) d.error("openVoiceMode error:", lastErr.message);
          console.error("[Velocity] Voice panel error:", lastErr.message);
        } else if (d) {
          d.log("openVoiceMode response:", response);
        }
      }
    );
  }

  function triggerEnhanceHotkey() {
    const input = boundInput || findInput();
    if (!input) return;
    const prompt = readInputText(input);
    if (!prompt || !prompt.trim()) return;
    openModal({ tab: "improve" });
  }

  let hotkeysInitialized = false;
  function setupKeyboardHotkeys() {
    if (hotkeysInitialized) return;
    hotkeysInitialized = true;
    document.addEventListener("keydown", (e) => {
      if (e.altKey && (e.key === "e" || e.key === "E")) {
        e.preventDefault();
        console.log("[Velocity] Alt+E pressed - triggering enhance");
        triggerEnhanceHotkey();
      }
      if (e.altKey && (e.key === "v" || e.key === "V")) {
        e.preventDefault();
        console.log("[Velocity] Alt+V pressed - triggering voice mode");
        openVoiceMode();
      }
    });
    console.log("[Velocity] Hotkeys initialized (Alt+E, Alt+V)");
  }

  function createBar() {
    if (barEl && document.body.contains(barEl)) return barEl;

    const bar = document.createElement("div");
    bar.className = "velocity-injection-bar";
    bar.setAttribute("role", "toolbar");

    const actions = document.createElement("div");
    actions.className = "velocity-injection-actions";

    const expandable = document.createElement("div");
    expandable.className = "velocity-injection-expandable";
    expandable.setAttribute("aria-hidden", "true");

    const voiceBtn = toolBtn("Voice (Alt+V)", MIC_SVG, "voice");
    voiceBtn.className = "velocity-injection-tool-btn velocity-injection-voice-btn";
    const libraryBtn = toolBtnImg("Prompt Library", LIBRARY_ICON_PATH, "library");
    if (isLibraryHidden()) {
      libraryBtn.style.display = "none";
    }
    // Reveal order on hover (left → right):
    //   [ Prompt Library ] [ Voice ] [ Enhance ]
    // The mic sits closest to Enhance so voice → enhance is one short hop;
    // Prompt Library is the outermost reveal.
    expandable.appendChild(libraryBtn);
    expandable.appendChild(voiceBtn);

    const improveBtn = document.createElement("button");
    improveBtn.type = "button";
    improveBtn.className = "velocity-injection-enhance";
    improveBtn.title = "Improve Prompt";
    improveBtn.dataset.tooltip = "Improve Prompt";

    const logo = document.createElement("span");
    logo.className = "velocity-injection-logo";
    const logoImg = document.createElement("img");
    logoImg.src = extensionAssetUrl("assets/Velocity_logo.png");
    logoImg.alt = "";
    logoImg.setAttribute("aria-hidden", "true");
    logoImg.draggable = false;
    logo.appendChild(logoImg);
    improveBtn.appendChild(logo);

    const sparkle = document.createElement("span");
    sparkle.className = "velocity-injection-sparkle";
    sparkle.innerHTML = SPARKLE_SVG;
    improveBtn.appendChild(sparkle);

    const moreBtn = document.createElement("button");
    moreBtn.type = "button";
    moreBtn.className = "velocity-injection-drag";
    moreBtn.title = "More";
    moreBtn.setAttribute("aria-label", "More");
    moreBtn.appendChild(buildDragDots());

    const core = document.createElement("div");
    core.className = "velocity-injection-core";
    core.appendChild(improveBtn);
    core.appendChild(moreBtn);

    actions.appendChild(expandable);
    actions.appendChild(core);
    bar.appendChild(actions);
    document.body.appendChild(bar);

    voiceBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      console.log("[Velocity] Voice button clicked");
      openVoiceMode();
    });
    libraryBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      openHostedPage("library");
    });
    improveBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      openModal({ tab: "improve" });
    });

    function expandOnHover() {
      if (isDragging) return;
      cancelCollapse();
      setGroupExpanded(true);
    }
    improveBtn.addEventListener("mouseenter", expandOnHover);
    expandable.addEventListener("mouseenter", expandOnHover);
    moreBtn.addEventListener("mouseenter", () => {
      if (isDragging || pinnedExpanded) return;
      scheduleCollapse();
    });
    bar.addEventListener("mouseleave", (e) => {
      if (isDragging) return;
      const rel = e.relatedTarget;
      if (rel && bar.contains(rel)) return;
      scheduleCollapse();
    });

    moreBtn.addEventListener("pointerdown", onMorePointerDown);
    moreBtn.addEventListener("mousedown", (e) => e.preventDefault());

    libraryBtnEl = libraryBtn;
    barEl = bar;

    try {
      if (chrome && chrome.storage && chrome.storage.local) {
        chrome.storage.local.get(["velocity_theme_preference"], (res) => {
          if (res && res.velocity_theme_preference === "light") {
            barEl.classList.add("light-mode");
          }
        });
        chrome.storage.onChanged.addListener((changes, namespace) => {
          if (namespace === "local" && changes.velocity_theme_preference) {
            barEl.classList.toggle("light-mode", changes.velocity_theme_preference.newValue === "light");
          }
        });
      }
    } catch (_) {}

    return bar;
  }

  function loadDragOffset() {
    try {
      const o = JSON.parse(sessionStorage.getItem(BAR_STORAGE_KEY) || "null");
      if (o && typeof o.left === "number" && typeof o.top === "number") return o;
    } catch (_) {}
    return null;
  }

  function saveDragOffset(left, top) {
    try {
      sessionStorage.setItem(BAR_STORAGE_KEY, JSON.stringify({ left, top }));
    } catch (_) {}
  }

  function repositionAnchored(input) {
    if (!barEl || !input || userDragged) return;
    const rect = input.getBoundingClientRect();
    const barW = barEl.offsetWidth;
    const barH = barEl.offsetHeight;
    const cfg = hp() && detectPlatform() ? hp().getPlatform(detectPlatform()) : null;
    const anchor = (cfg && cfg.buttonAnchor) || { align: "right", top: -48 };
    let top = rect.top + (anchor.top || -48);
    if (top > rect.top - 8) top = rect.top - barH - GAP_ABOVE;
    top = Math.max(8, Math.min(top, window.innerHeight - barH - 8));
    barEl.style.top = Math.round(top) + "px";

    if (anchor.align === "center") {
      let left = rect.left + (rect.width - barW) / 2;
      left = Math.max(8, Math.min(left, window.innerWidth - barW - 8));
      barEl.style.left = Math.round(left) + "px";
      barEl.style.right = "auto";
      return;
    }
    if (anchor.align === "left") {
      let left = rect.left + 8;
      left = Math.max(8, Math.min(left, window.innerWidth - barW - 8));
      barEl.style.left = Math.round(left) + "px";
      barEl.style.right = "auto";
      return;
    }

    /* Right-align: pin bar's right edge so hover expand grows left, not shifting Improve/More */
    const marginRight = 12;
    let right = window.innerWidth - rect.right + marginRight;
    const maxRight = window.innerWidth - barW - 8;
    right = Math.max(marginRight, Math.min(right, maxRight));
    barEl.style.left = "auto";
    barEl.style.right = Math.round(right) + "px";
  }

  function positionBar(input) {
    const bar = createBar();
    if (!input || !document.body.contains(input)) {
      hideBar();
      return;
    }
    boundInput = input;
    if (userDragged) {
      const s = loadDragOffset();
      if (s) {
        barEl.style.left = s.left + "px";
        barEl.style.right = "auto";
        barEl.style.top = s.top + "px";
        bar.classList.add("is-visible");
        return;
      }
      userDragged = false;
    }
    repositionAnchored(input);
    bar.classList.add("is-visible");
    maybeShowWelcomeCoachmark();
  }

  /**
   * One-shot post-install welcome coachmark. Runs at most once per content
   * script lifetime, gated on the `velocity_show_post_install_popup` flag in
   * `chrome.storage.local`. Background sets the flag on install; clicking the
   * tutorial's "Try Velocity" button re-arms it as a safety net.
   */
  function maybeShowWelcomeCoachmark() {
    if (welcomeCoachmarkChecked) return;
    welcomeCoachmarkChecked = true;
    try {
      if (!chrome || !chrome.storage || !chrome.storage.local) return;
      chrome.storage.local.get([POST_INSTALL_FLAG], (r) => {
        if (chrome.runtime.lastError) return;
        if (!r || !r[POST_INSTALL_FLAG]) return;
        try {
          chrome.storage.local.remove(POST_INSTALL_FLAG);
        } catch (_) {}
        // Defer so the bar's `is-visible` transition has time to settle and
        // we can read its final on-screen rect for positioning.
        setTimeout(showWelcomeCoachmark, 320);
      });
    } catch (_) {}
  }

  function showWelcomeCoachmark() {
    if (welcomeCoachmarkEl || !barEl || !document.body.contains(barEl)) return;
    const tip = document.createElement("div");
    tip.className = "velocity-welcome-coachmark";
    tip.setAttribute("role", "dialog");
    tip.setAttribute("aria-label", "Welcome to Velocity");
    tip.innerHTML =
      '<button type="button" class="velocity-welcome-coachmark-close" aria-label="Dismiss">' +
      '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">' +
      '<path d="M6 6l12 12M18 6L6 18"/>' +
      "</svg></button>" +
      '<div class="velocity-welcome-coachmark-heading">' +
      '<span class="velocity-welcome-coachmark-dot" aria-hidden="true"></span>' +
      '<span class="velocity-welcome-coachmark-title">Welcome to Velocity</span>' +
      "</div>" +
      '<p class="velocity-welcome-coachmark-body">Click this button to instantly enhance your prompt with AI. It works on any chat box you focus.</p>' +
      '<button type="button" class="velocity-welcome-coachmark-cta">Got it</button>' +
      '<span class="velocity-welcome-coachmark-arrow" aria-hidden="true"></span>';
    document.body.appendChild(tip);
    welcomeCoachmarkEl = tip;
    positionWelcomeCoachmark();

    const closeBtn = tip.querySelector(".velocity-welcome-coachmark-close");
    const ctaBtn = tip.querySelector(".velocity-welcome-coachmark-cta");
    if (closeBtn) closeBtn.addEventListener("click", dismissWelcomeCoachmark);
    if (ctaBtn) ctaBtn.addEventListener("click", dismissWelcomeCoachmark);

    window.addEventListener("resize", positionWelcomeCoachmark);
    window.addEventListener("scroll", positionWelcomeCoachmark, true);
    setTimeout(() => {
      if (welcomeCoachmarkEl === tip) dismissWelcomeCoachmark();
    }, COACHMARK_AUTO_DISMISS_MS);
  }

  function dismissWelcomeCoachmark() {
    if (!welcomeCoachmarkEl) return;
    const el = welcomeCoachmarkEl;
    welcomeCoachmarkEl = null;
    window.removeEventListener("resize", positionWelcomeCoachmark);
    window.removeEventListener("scroll", positionWelcomeCoachmark, true);
    if (el.parentNode) el.parentNode.removeChild(el);
  }

  function positionWelcomeCoachmark() {
    if (!welcomeCoachmarkEl || !barEl) return;
    const barRect = barEl.getBoundingClientRect();
    const tipW = welcomeCoachmarkEl.offsetWidth || 280;
    const tipH = welcomeCoachmarkEl.offsetHeight || 130;
    const gap = 12;
    const margin = 8;

    let top = barRect.bottom + gap;
    let placement = "below";
    if (top + tipH > window.innerHeight - margin) {
      top = barRect.top - tipH - gap;
      placement = "above";
    }
    let left = barRect.right - tipW;
    left = Math.max(margin, Math.min(left, window.innerWidth - tipW - margin));
    welcomeCoachmarkEl.style.top = Math.round(top) + "px";
    welcomeCoachmarkEl.style.left = Math.round(left) + "px";
    welcomeCoachmarkEl.dataset.placement = placement;

    // Arrow horizontal offset: line up with the bar's center within viewport
    const barCenterX = barRect.left + barRect.width / 2;
    const arrowX = Math.max(16, Math.min(barCenterX - left, tipW - 16));
    welcomeCoachmarkEl.style.setProperty("--vel-coachmark-arrow-x", Math.round(arrowX) + "px");
  }

  function hideBar() {
    if (!barEl) return;
    setGroupExpanded(false);
    barEl.classList.remove("is-visible");
    boundInput = null;
  }

  let lastReposition = 0;
  const REPOSITION_THROTTLE_MS = 200;
  function scheduleReposition() {
    if (rafId) return;
    const now = Date.now();
    if (now - lastReposition < REPOSITION_THROTTLE_MS) return;
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      lastReposition = Date.now();
      if (!boundInput || userDragged) return;
      const input = findInput();
      if (input && !isExcludedInput(input)) positionBar(input);
      else hideBar();
    });
  }

  function onMorePointerDown(e) {
    if (!barEl || e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    cancelCollapse();

    const rect = barEl.getBoundingClientRect();
    dragState = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      origLeft: rect.left,
      origTop: rect.top,
      moved: false,
    };
    isDragging = true;
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch (_) {}
    document.body.style.userSelect = "none";
    document.addEventListener("pointermove", onMorePointerMove, true);
    document.addEventListener("pointerup", onMorePointerUp, true);
    document.addEventListener("pointercancel", onMorePointerUp, true);
  }

  function onMorePointerMove(e) {
    if (!dragState || e.pointerId !== dragState.pointerId) return;
    const dx = e.clientX - dragState.startX;
    const dy = e.clientY - dragState.startY;
    if (!dragState.moved && Math.hypot(dx, dy) > DRAG_CLICK_THRESHOLD_PX) {
      dragState.moved = true;
      setGroupExpanded(false);
      userDragged = true;
      barEl.classList.add("is-dragging");
      barEl.style.transition = "none";
      document.body.style.cursor = "grabbing";
    }
    if (!dragState.moved) return;
    e.preventDefault();
    const barW = barEl.offsetWidth;
    const barH = barEl.offsetHeight;
    barEl.style.right = "auto";
    barEl.style.left = Math.max(8, Math.min(dragState.origLeft + dx, window.innerWidth - barW - 8)) + "px";
    barEl.style.top = Math.max(8, Math.min(dragState.origTop + dy, window.innerHeight - barH - 8)) + "px";
  }

  function onMorePointerUp(e) {
    if (!dragState || e.pointerId !== dragState.pointerId) return;
    try {
      dragBtnRelease(e);
    } catch (_) {}

    const wasDrag = dragState.moved;
    if (wasDrag) {
      const r = barEl.getBoundingClientRect();
      saveDragOffset(r.left, r.top);
    } else {
      pinnedExpanded = !pinnedExpanded;
      setGroupExpanded(pinnedExpanded);
    }

    dragState = null;
    isDragging = false;
    barEl.classList.remove("is-dragging");
    barEl.style.transition = "";
    document.body.style.userSelect = "";
    document.body.style.cursor = "";
    document.removeEventListener("pointermove", onMorePointerMove, true);
    document.removeEventListener("pointerup", onMorePointerUp, true);
    document.removeEventListener("pointercancel", onMorePointerUp, true);

    if (!pinnedExpanded) scheduleCollapse();
  }

  function dragBtnRelease(e) {
    const btn = barEl && barEl.querySelector(".velocity-injection-drag");
    if (btn && e.pointerId != null) btn.releasePointerCapture(e.pointerId);
  }

  function onFocusIn(e) {
    const t = e.target;
    if (!t || isExcludedInput(t)) return;
    const input = findInput();
    if (input && (t === input || input.contains(t) || t.contains(input))) positionBar(input);
  }

  let observersInitialized = false;
  function initObservers() {
    if (observersInitialized) return;
    observersInitialized = true;
    new MutationObserver(scheduleReposition).observe(document.documentElement, {
      childList: true,
      subtree: true,
    });
    window.addEventListener("scroll", scheduleReposition, { capture: true, passive: true });
    window.addEventListener("resize", scheduleReposition, { passive: true });
    document.addEventListener("focusin", onFocusIn, true);
    document.addEventListener("input", scheduleReposition, { capture: true, passive: true });
  }

  function boot() {
    if (document.documentElement.dataset.velocityInjectionBooted) return;
    document.documentElement.dataset.velocityInjectionBooted = "1";
    const d = dbg();
    const platform = detectPlatform();
    if (d) {
      d.boot("injection button booted", { platform: platform || "(unknown)" });
    }
    if (loadDragOffset()) userDragged = true;
    initObservers();
    setupKeyboardHotkeys();
    const tryShow = () => {
      const input = findInput();
      if (input && !isExcludedInput(input)) {
        positionBar(input);
        return true;
      }
      return false;
    };
    if (!tryShow()) {
      let n = 0;
      const poll = setInterval(() => {
        n += 1;
        if (tryShow()) {
          if (d) d.log("input found after poll");
          clearInterval(poll);
        } else if (n > 40) {
          if (d) d.warn("chat input not found after 20s — button may stay hidden");
          clearInterval(poll);
        }
      }, 500);
    } else if (d) {
      d.log("input found on first try");
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
