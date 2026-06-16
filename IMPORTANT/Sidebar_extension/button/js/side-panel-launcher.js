/**
 * Velocity side-panel launcher (right-edge floating trigger).
 *
 * Responsibility:
 *   Render a single, persistent launcher pinned to the right edge of the
 *   browser viewport on supported LLM host pages. Clicking it asks the
 *   background to open the Velocity side panel via the existing
 *   `TV_OPEN_SIDE_PANEL` message (auth + sender validation already handled
 *   there). This is independent from the in-line injection bar that hugs the
 *   chat input — that flow stays untouched.
 *
 * Boundaries (per extension-architecture-js-only skill):
 *   - UI only. No direct API calls, no storage writes outside the small
 *     position/visibility cache.
 *   - Talks to background through the messaging contract.
 *   - Platform detection is delegated to VelocityHostPlatforms.
 */
(function () {
  "use strict";

  const ROOT_CLASS = "velocity-launcher";
  const RESTORE_CLASS = "velocity-launcher-restore";
  const POSITION_KEY = "velocity_launcher_position";
  const HIDDEN_KEY = "velocity_launcher_hidden";
  const DRAG_THRESHOLD_PX = 5;
  const READY_DELAY_MS = 600;
  // Periodic attention shake — a small horizontal nudge applied to the orb
  // every SHAKE_INTERVAL_MS while the launcher is idle. The class is removed
  // after SHAKE_DURATION_MS so the animation can re-trigger on the next tick.
  const SHAKE_INTERVAL_MS = 10000;
  const SHAKE_DURATION_MS = 550;
  const SHAKE_CLASS = "is-shaking";
  const SIDE_PANEL_ACTIVE_CLASS = "is-sidebar-active";
  const SIDE_PANEL_STATE_ACTION = "TV_SIDE_PANEL_STATE";
  const SIDE_PANEL_QUERY_ACTION = "TV_QUERY_SIDE_PANEL_STATE";
  const SIDE_PANEL_STORAGE_KEY = "velocity_side_panel_open";

  let launcherEl = null;
  let orbEl = null;
  let restoreEl = null;
  let dragState = null;
  let isDragging = false;
  let booted = false;
  let suppressClickUntil = 0;
  let dragCleanupTimer = 0;
  let sidePanelOpen = false;
  let lifecycleMessageListener = null;
  let lifecycleStorageListener = null;
  let shakeIntervalId = 0;
  let shakeClearTimer = 0;

  function dbg() {
    return globalThis.VelocitySidebarDebug || null;
  }

  function hostPlatforms() {
    return globalThis.VelocityHostPlatforms || null;
  }

  function isHostPlatformPage() {
    const api = hostPlatforms();
    if (!api) return false;
    try {
      return Boolean(api.detectPlatform());
    } catch (_) {
      return false;
    }
  }

  function safeGetURL(path) {
    try {
      return chrome.runtime.getURL(path);
    } catch (_) {
      return "";
    }
  }

  function readSession(key) {
    try {
      return sessionStorage.getItem(key);
    } catch (_) {
      return null;
    }
  }

  function writeSession(key, value) {
    try {
      sessionStorage.setItem(key, value);
    } catch (_) {}
  }

  function removeSession(key) {
    try {
      sessionStorage.removeItem(key);
    } catch (_) {}
  }

  function loadStoredTop() {
    const raw = readSession(POSITION_KEY);
    if (!raw) return null;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : null;
  }

  function saveTop(topPx) {
    writeSession(POSITION_KEY, String(Math.round(topPx)));
  }

  function isStoredHidden() {
    return readSession(HIDDEN_KEY) === "1";
  }

  function setStoredHidden(hidden) {
    if (hidden) writeSession(HIDDEN_KEY, "1");
    else removeSession(HIDDEN_KEY);
  }

  function buildGrip() {
    const grip = document.createElement("span");
    grip.className = "velocity-launcher-grip";
    grip.setAttribute("aria-hidden", "true");
    grip.title = "Drag to reposition";
    for (let row = 0; row < 3; row++) {
      const r = document.createElement("span");
      r.className = "velocity-launcher-grip-row";
      for (let col = 0; col < 2; col++) {
        const d = document.createElement("span");
        d.className = "velocity-launcher-grip-dot";
        r.appendChild(d);
      }
      grip.appendChild(r);
    }
    return grip;
  }

  function buildLauncher() {
    const root = document.createElement("div");
    root.className = ROOT_CLASS;
    root.setAttribute("role", "button");
    root.setAttribute("tabindex", "0");
    root.setAttribute("aria-label", "Open Velocity side panel");

    const orb = document.createElement("span");
    orb.className = "velocity-launcher-orb";
    const img = document.createElement("img");
    img.src = safeGetURL("assets/Velocity_logo.png");
    img.alt = "";
    img.setAttribute("aria-hidden", "true");
    img.draggable = false;
    orb.appendChild(img);

    const label = document.createElement("span");
    label.className = "velocity-launcher-label";
    const title = document.createElement("span");
    title.className = "velocity-launcher-title";
    title.textContent = "Open Velocity";
    const subtitle = document.createElement("span");
    subtitle.className = "velocity-launcher-subtitle";
    subtitle.textContent = "Side panel";
    label.appendChild(title);
    label.appendChild(subtitle);

    const grip = buildGrip();

    root.appendChild(orb);
    root.appendChild(label);
    root.appendChild(grip);

    return { root, orb, grip };
  }

  function buildRestoreTab() {
    const tab = document.createElement("div");
    tab.className = RESTORE_CLASS;
    tab.setAttribute("role", "button");
    tab.setAttribute("tabindex", "0");
    tab.setAttribute("aria-label", "Show Velocity launcher");
    tab.title = "Show Velocity launcher";
    return tab;
  }

  function applyStoredPosition() {
    if (!launcherEl) return;
    const stored = loadStoredTop();
    if (stored == null) {
      launcherEl.style.top = "50%";
      launcherEl.classList.remove("is-positioned");
      return;
    }
    const height = launcherEl.offsetHeight || 48;
    const clamped = Math.max(8, Math.min(stored, window.innerHeight - height - 8));
    launcherEl.style.top = Math.round(clamped) + "px";
    launcherEl.classList.add("is-positioned");
  }

  function refreshHiddenState() {
    if (!launcherEl || !restoreEl) return;
    const hidden = isStoredHidden();
    launcherEl.classList.toggle("is-hidden", hidden);
    restoreEl.classList.toggle("is-visible", hidden);
  }

  function canShakeNow() {
    if (!orbEl || !launcherEl) return false;
    if (isDragging) return false;
    if (sidePanelOpen) return false;
    if (isStoredHidden()) return false;
    if (launcherEl.classList.contains("is-expanded")) return false;
    return true;
  }

  function triggerShakeOnce() {
    if (!canShakeNow()) return;
    // Remove first so re-adding restarts the CSS animation cleanly even if a
    // stray timer left the class on the element.
    orbEl.classList.remove(SHAKE_CLASS);
    // Force reflow so the browser sees the class removal before re-adding.
    void orbEl.offsetWidth;
    orbEl.classList.add(SHAKE_CLASS);
    if (shakeClearTimer) clearTimeout(shakeClearTimer);
    shakeClearTimer = setTimeout(() => {
      if (orbEl) orbEl.classList.remove(SHAKE_CLASS);
      shakeClearTimer = 0;
    }, SHAKE_DURATION_MS);
  }

  function startShakeLoop() {
    if (shakeIntervalId) return;
    shakeIntervalId = setInterval(triggerShakeOnce, SHAKE_INTERVAL_MS);
  }

  function stopShakeLoop() {
    if (shakeIntervalId) {
      clearInterval(shakeIntervalId);
      shakeIntervalId = 0;
    }
    if (shakeClearTimer) {
      clearTimeout(shakeClearTimer);
      shakeClearTimer = 0;
    }
    if (orbEl) orbEl.classList.remove(SHAKE_CLASS);
  }

  function applySidePanelState() {
    if (!launcherEl) return;
    launcherEl.classList.toggle(SIDE_PANEL_ACTIVE_CLASS, sidePanelOpen);
    if (sidePanelOpen) {
      stopShakeLoop();
    } else if (!isStoredHidden()) {
      startShakeLoop();
    }
  }

  function setSidePanelOpen(open) {
    const next = Boolean(open);
    if (next === sidePanelOpen) return;
    sidePanelOpen = next;
    applySidePanelState();
  }

  function listenForSidePanelState() {
    if (lifecycleMessageListener) return;
    if (!chrome || !chrome.runtime || !chrome.runtime.onMessage) return;
    lifecycleMessageListener = (message) => {
      if (!message || message.action !== SIDE_PANEL_STATE_ACTION) return;
      const open =
        message.payload && typeof message.payload.open !== "undefined"
          ? Boolean(message.payload.open)
          : false;
      setSidePanelOpen(open);
    };
    try {
      chrome.runtime.onMessage.addListener(lifecycleMessageListener);
    } catch (_) {
      lifecycleMessageListener = null;
    }
  }

  function querySidePanelStateOnce() {
    if (!chrome || !chrome.runtime || typeof chrome.runtime.sendMessage !== "function") return;
    try {
      chrome.runtime.sendMessage(
        {
          action: SIDE_PANEL_QUERY_ACTION,
          requestId: "launcher-query-" + Date.now(),
          payload: {},
        },
        (response) => {
          void chrome.runtime.lastError;
          if (!response || !response.success || !response.data) return;
          setSidePanelOpen(Boolean(response.data.open));
        }
      );
    } catch (_) {
      /* background not ready — broadcast will catch us up later */
    }
  }

  /**
   * Belt-and-braces fallback for the runtime broadcast. The lifecycle module
   * mirrors the panel-open flag into `chrome.storage.local`, so even if the
   * `TV_SIDE_PANEL_STATE` runtime message doesn't reach us (late content
   * script, service-worker race), reading + watching storage keeps the
   * launcher's glow in sync with the actual panel state.
   */
  function readSidePanelStateFromStorage() {
    if (!chrome || !chrome.storage || !chrome.storage.local) return;
    try {
      chrome.storage.local.get([SIDE_PANEL_STORAGE_KEY], (items) => {
        if (chrome.runtime.lastError || !items) return;
        if (Object.prototype.hasOwnProperty.call(items, SIDE_PANEL_STORAGE_KEY)) {
          setSidePanelOpen(Boolean(items[SIDE_PANEL_STORAGE_KEY]));
        }
      });
    } catch (_) {}
  }

  function listenForSidePanelStorage() {
    if (lifecycleStorageListener) return;
    if (!chrome || !chrome.storage || !chrome.storage.onChanged) return;
    lifecycleStorageListener = (changes, area) => {
      if (area !== "local" || !changes) return;
      const change = changes[SIDE_PANEL_STORAGE_KEY];
      if (!change) return;
      setSidePanelOpen(Boolean(change.newValue));
    };
    try {
      chrome.storage.onChanged.addListener(lifecycleStorageListener);
    } catch (_) {
      lifecycleStorageListener = null;
    }
  }

  function sendOpenSidePanel() {
    const api = hostPlatforms();
    const platform = api ? api.detectPlatform() : null;
    const requestId = "launcher-" + Date.now();
    const payload = {
      target: "enhance",
      platform: platform || "",
    };
    const d = dbg();
    if (d) d.boot && d.boot("launcher: open side panel", { platform });
    try {
      chrome.runtime.sendMessage(
        { action: "TV_OPEN_SIDE_PANEL", requestId, payload },
        (response) => {
          const lastErr = chrome.runtime.lastError;
          if (lastErr) {
            if (d) d.error && d.error("launcher: open failed", lastErr.message);
            return;
          }
          if (response && response.success === false) {
            if (d) d.warn && d.warn("launcher: open rejected", response.error);
          }
        }
      );
    } catch (e) {
      if (d) d.error && d.error("launcher: sendMessage threw", String(e));
    }
  }

  function onLauncherClick(e) {
    if (isDragging || Date.now() < suppressClickUntil) return;
    if (e && typeof e.stopPropagation === "function") e.stopPropagation();
    sendOpenSidePanel();
  }

  function onLauncherKey(e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    sendOpenSidePanel();
  }

  function onRestoreClick(e) {
    e.stopPropagation();
    setStoredHidden(false);
    refreshHiddenState();
    if (!sidePanelOpen) startShakeLoop();
  }

  function onGripPointerDown(e) {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    const rect = launcherEl.getBoundingClientRect();
    dragState = {
      pointerId: e.pointerId,
      startY: e.clientY,
      origTop: rect.top,
      moved: false,
      gripEl: e.currentTarget,
    };
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch (_) {}
    if (dragCleanupTimer) clearTimeout(dragCleanupTimer);
    dragCleanupTimer = setTimeout(cancelDragState, 6000);
    document.addEventListener("pointermove", onGripPointerMove, true);
    document.addEventListener("pointerup", onGripPointerUp, true);
    document.addEventListener("pointercancel", onGripPointerUp, true);
    window.addEventListener("blur", cancelDragState, true);
  }

  function onGripPointerMove(e) {
    if (!dragState || e.pointerId !== dragState.pointerId) return;
    const dy = e.clientY - dragState.startY;
    if (!dragState.moved && Math.abs(dy) > DRAG_THRESHOLD_PX) {
      dragState.moved = true;
      isDragging = true;
      launcherEl.classList.add("is-dragging");
      launcherEl.classList.add("is-positioned");
    }
    if (!dragState.moved) return;
    const height = launcherEl.offsetHeight || 48;
    const next = Math.max(8, Math.min(dragState.origTop + dy, window.innerHeight - height - 8));
    launcherEl.style.top = Math.round(next) + "px";
  }

  function onGripPointerUp(e) {
    if (!dragState || e.pointerId !== dragState.pointerId) return;
    const moved = dragState.moved;
    releasePointerCapture(e.pointerId);
    dragState = null;
    detachDragListeners();

    if (moved && launcherEl) {
      const rect = launcherEl.getBoundingClientRect();
      saveTop(rect.top);
      suppressClickUntil = Date.now() + 350;
    }
    // Delay reset so the click handler can suppress the drag-release click.
    setTimeout(() => {
      isDragging = false;
      if (launcherEl) launcherEl.classList.remove("is-dragging");
    }, 0);
  }

  function releasePointerCapture(pointerId) {
    if (!dragState || !dragState.gripEl || pointerId == null) return;
    try {
      dragState.gripEl.releasePointerCapture(pointerId);
    } catch (_) {}
  }

  function detachDragListeners() {
    if (dragCleanupTimer) {
      clearTimeout(dragCleanupTimer);
      dragCleanupTimer = 0;
    }
    document.removeEventListener("pointermove", onGripPointerMove, true);
    document.removeEventListener("pointerup", onGripPointerUp, true);
    document.removeEventListener("pointercancel", onGripPointerUp, true);
    window.removeEventListener("blur", cancelDragState, true);
  }

  function cancelDragState() {
    if (!dragState && !isDragging) return;
    releasePointerCapture(dragState && dragState.pointerId);
    dragState = null;
    isDragging = false;
    detachDragListeners();
    if (launcherEl) launcherEl.classList.remove("is-dragging");
  }

  function onWindowResize() {
    if (!launcherEl) return;
    const stored = loadStoredTop();
    if (stored == null) return;
    const height = launcherEl.offsetHeight || 48;
    const clamped = Math.max(8, Math.min(stored, window.innerHeight - height - 8));
    launcherEl.style.top = Math.round(clamped) + "px";
  }

  function mount() {
    if (launcherEl && document.body.contains(launcherEl)) return;
    const built = buildLauncher();
    launcherEl = built.root;
    orbEl = built.orb;
    restoreEl = buildRestoreTab();
    document.body.appendChild(launcherEl);
    document.body.appendChild(restoreEl);

    built.grip.addEventListener("pointerdown", onGripPointerDown);
    launcherEl.addEventListener("click", onLauncherClick);
    launcherEl.addEventListener("keydown", onLauncherKey);
    restoreEl.addEventListener("click", onRestoreClick);
    restoreEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onRestoreClick(e);
      }
    });
    window.addEventListener("resize", onWindowResize);

    applyStoredPosition();
    refreshHiddenState();
    listenForSidePanelState();
    listenForSidePanelStorage();
    readSidePanelStateFromStorage();
    querySidePanelStateOnce();
    applySidePanelState();

    setTimeout(() => {
      if (launcherEl) launcherEl.classList.add("is-ready");
      // Kick off the periodic attention shake after the launcher is visible.
      // Skipped while hidden by the user or while the side panel is open;
      // applySidePanelState() / onRestoreClick re-arm the loop on resume.
      if (!isStoredHidden() && !sidePanelOpen) startShakeLoop();
    }, READY_DELAY_MS);
  }

  function boot() {
    if (booted) return;
    if (!isHostPlatformPage()) return;
    booted = true;
    if (document.body) {
      mount();
    } else {
      const onReady = () => {
        document.removeEventListener("DOMContentLoaded", onReady);
        mount();
      };
      document.addEventListener("DOMContentLoaded", onReady);
    }
  }

  // Expose a minimal control surface for debugging / future hooks.
  globalThis.VelocityLauncher = {
    show() {
      setStoredHidden(false);
      refreshHiddenState();
      if (!sidePanelOpen) startShakeLoop();
    },
    hide() {
      setStoredHidden(true);
      refreshHiddenState();
      stopShakeLoop();
    },
    open: sendOpenSidePanel,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
