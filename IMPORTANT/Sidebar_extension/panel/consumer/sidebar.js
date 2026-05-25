/**
 * Consumer side-panel UI (B2C) — this is the product surface for the consumer
 * reference layout (hero, cards, bottom composer, right rail). Enterprise uses
 * `panel/enterprise/sidebar.*` with a different UI and (later) different APIs.
 * Session: profile rail + optional slim hint when signed out (no signed-in strip).
 */
(function () {
  const el = (id) => document.getElementById(id);
  const appShell = el("appShell");
  const authHint = el("authHint");
  const authHintText = el("authHintText");
  const btnLogin = el("btnLogin");
  const btnRefresh = el("btnRefresh");
  const enhanceStatus = el("enhanceStatus");
  const promptInput = el("promptInput");
  const COMPOSER_PLACEHOLDER_DEFAULT = "Write or paste your prompt...";
  const COMPOSER_PLACEHOLDER_CONTEXT = "Write to create your context...";
  const COMPOSER_PLACEHOLDER_SUGGESTIONS =
    "Your answers appear here. Edit if needed, then Send to refine.";
  const profileInitials = el("profileInitials");
  const railToggle = el("railToggle");
  const sidebarExpandBtn = el("sidebarExpandBtn");
  const railHome = el("railHome");
  const railNewChat = el("railNewChat");
  const railLibrary = el("railLibrary");

  const railProfile = el("railProfile");
  const homeFeaturedCards = el("homeFeaturedCards");
  /** How many library prompts to show on home (always this many when available). */
  const HOME_FEATURED_PROMPT_COUNT = 2;
  let homeFeaturedLoadSeq = 0;
  const btnShowMorePrompts = el("btnShowMorePrompts");
  const btnShufflePrompts = el("btnShufflePrompts");
  const heroGreetingName = el("heroGreetingName");
  const heroRotatingWord = el("heroRotatingWord");
  const HERO_ROTATING_WORDS = ["code", "create", "design", "build", "ship"];
  let heroRotatingIdx = 0;
  let heroRotatingTimer = null;
  const tabBar = el("tabBar");
  const viewLogin = el("viewLogin");
  const welcomeLoginBtn = el("welcomeLoginBtn");
  const welcomeSignupBtn = el("welcomeSignupBtn");
  const welcomeLoginStatus = el("welcomeLoginStatus");
  const welcomeLoginSub = el("welcomeLoginSub");
  let _authPollTimer = null;
  let _authPollStartedAt = 0;
  const AUTH_POLL_INTERVAL_MS = 2500;
  const AUTH_POLL_MAX_MS = 3 * 60 * 1000;
  const composerDock = document.querySelector(".composer-dock");

  const CONSUMER_HOME_VIEW_IDS = [
    "viewHome",
    "viewPromptLibrary",
    "viewCollections",
    "viewMemory",
  ];

  const root = typeof globalThis !== "undefined" ? globalThis : window;
  if (!root.TV || !root.TV.sidebarAuthState) {
    console.error("[sidebar-consumer] TV.sidebarAuthState missing");
    return;
  }
  const authState = root.TV.sidebarAuthState;
  const composerImproveSlot = el("composerImproveSlot");
  const btnComposerImprove = el("btnComposerImprove");
  let activeHostContext = null;

  // ── View-state persistence (rehydrate on panel reopen) ────────────────
  const viewState = root.TV.sidebarViewState || null;
  let _viewStateRestored = false;
  let _viewStateApplying = false;

  function persistView(patch, opts) {
    if (!viewState || _viewStateApplying) return;
    try { viewState.save(patch, opts); } catch (_) {}
  }

  function persistSessionTab(tabName) {
    persistView({ panel: "session", sessionTab: tabName });
  }

  function persistPanel(name) {
    persistView({ panel: name });
  }

  function persistComposerInput() {
    if (!viewState) return;
    if (!promptInput) return;
    persistView({ composerInput: String(promptInput.value || "") });
  }

  function refreshComposerSend() {
    if (root.TV.consumerComposerBar && typeof root.TV.consumerComposerBar.refreshSendState === "function") {
      root.TV.consumerComposerBar.refreshSendState();
    }
  }

  function refreshSuggestionsComposerChrome() {
    const sugView = el("viewSuggestions");
    const onSuggestions =
      sugView && !sugView.hidden && sugView.classList.contains("view-surface--active");
    const SV = root.TV.suggestionsView;
    const showImprove =
      onSuggestions &&
      appShell &&
      appShell.classList.contains("app-shell--in-session") &&
      SV &&
      typeof SV.shouldShowImproveButton === "function" &&
      SV.shouldShowImproveButton();

    if (composerImproveSlot) {
      if (showImprove) composerImproveSlot.removeAttribute("hidden");
      else composerImproveSlot.setAttribute("hidden", "");
    }
    if (promptInput) {
      const hideInput = showImprove;
      promptInput.hidden = hideInput;
      promptInput.style.display = hideInput ? "none" : "";
    }
    if (appShell) {
      appShell.classList.toggle("app-shell--suggestions-improve", !!showImprove);
    }
    refreshComposerSend();
  }

  root.TV.refreshSuggestionsComposerChrome = refreshSuggestionsComposerChrome;

  async function loadActiveHostContext() {
    try {
      const res = await sendRuntimeMessage("TV_GET_ACTIVE_HOST_CONTEXT", {});
      if (res && res.success && res.data && res.data.context) {
        activeHostContext = res.data.context;
      }
    } catch (_) {}
    if (views && typeof views.setActiveHostContext === "function") {
      views.setActiveHostContext(activeHostContext);
    }
  }

  function mapPromptBookEnhanceMode(tag) {
    const t = String(tag || "").toUpperCase();
    if (t.includes("BUILD") || t === "DEEP") return "build";
    if (t.includes("STUDIO") || t === "MEDIA") return "media";
    if (t.includes("BEST") || t.includes("MAX")) return "best";
    return "standard";
  }

  // Lucide icon SVG paths for each mode
  const MODE_ICONS = {
    zap: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></svg>',
    hammer: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 12-8.373 8.373a1 1 0 1 1-3-3L12 9"/><path d="m18 15 4-4"/><path d="m21.5 11.5-1.914-1.914A2 2 0 0 1 19 8.172V7l-2.26-2.26a6 6 0 0 0-4.202-1.756L9 2.96l.92.82A6.18 6.18 0 0 1 12 8.4V10l2 2h1.172a2 2 0 0 1 1.414.586L18.5 14.5"/></svg>',
    clapperboard: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.3Z"/><path d="m6.2 5.3 3.1 3.9"/><path d="m12.4 3.4 3.1 4"/><path d="M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/></svg>',
    star: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/></svg>',
    'book-open': '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>',
    leaf: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 22l10-10"/></svg>'
  };

  function syncComposerEnhanceMode(apiValue) {
    const sel = el("enhanceMode");
    if (sel) {
      sel.value = apiValue;
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    }
    const labels = { standard: "Quick", build: "Build", media: "Media", research: "Research" };
    const lab = el("sbModeLabel");
    if (lab) lab.textContent = labels[apiValue] || "Quick";
    // Sync the icon in the mode button based on selected mode's icon
    const icon = el("sbModeIcon");
    if (icon) {
      const opt = document.querySelector(`.sb-mode-option[data-api-value="${apiValue}"]`);
      if (opt) {
        const iconName = opt.getAttribute("data-icon") || "zap";
        icon.setAttribute("data-icon", iconName);
        if (MODE_ICONS[iconName]) {
          icon.innerHTML = MODE_ICONS[iconName];
        }
      }
    }
  }

  // Update mode dropdown user tier (free/pro) for icon coloring
  function updateModeDropdownTier(isPro) {
    const dropdown = el("sbModeDropdown");
    if (dropdown) {
      dropdown.setAttribute("data-user-tier", isPro ? "pro" : "free");
    }
  }

  function applyPromptToComposer(text) {
    if (!promptInput) return;
    promptInput.value = String(text || "").trim();
    promptInput.dispatchEvent(new Event("input", { bubbles: true }));
    promptInput.focus();
    refreshComposerSend();
  }

  function sendRuntimeMessage(action, payload) {
    const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({ action, payload: payload || {}, requestId }, (response) => {
        if (chrome.runtime.lastError) {
          resolve({
            success: false,
            error: { message: chrome.runtime.lastError.message },
          });
          return;
        }
        resolve(response || { success: false });
      });
    });
  }

  function platformLabelFromKey(key) {
    const pa = root.TV.platformPromptActions;
    if (pa && pa.OPEN_IN_PLATFORMS) {
      const row = pa.OPEN_IN_PLATFORMS.find((p) => p.key === key);
      if (row && row.label) return row.label;
    }
    const labels = {
      openai: "ChatGPT",
      anthropic: "Claude",
      google: "Gemini",
      perplexity: "Perplexity",
      mistral: "Mistral",
      grok: "Grok",
    };
    return labels[key] || "chat";
  }

  function showComposerInsertHint(message, durationMs) {
    if (!enhanceStatus || !message) return;
    enhanceStatus.textContent = message;
    if (window.__tvInsertHintTimer) {
      window.clearTimeout(window.__tvInsertHintTimer);
    }
    window.__tvInsertHintTimer = window.setTimeout(() => {
      if (enhanceStatus) enhanceStatus.textContent = "";
      window.__tvInsertHintTimer = null;
    }, durationMs || 4500);
  }

  function flashInsertInChatButton() {
    const btn = document.getElementById("btnOutputInsertChat");
    const flash = root.TV.copyButtonFeedback && root.TV.copyButtonFeedback.flash;
    if (flash && btn) {
      flash(btn, {
        label: "Inserted",
        durationMs: 1600,
        copiedClass: "out-insert-btn--inserted",
      });
    }
  }

  function formatPromptForPlatform(text) {
    const raw = String(text || "").trim();
    if (!raw) return "";
    if (root.TV.structuredPromptDom && typeof root.TV.structuredPromptDom.formatForExternalPaste === "function") {
      return root.TV.structuredPromptDom.formatForExternalPaste(raw);
    }
    if (root.TV.promptFormat && typeof root.TV.promptFormat.formatForExternalPaste === "function") {
      return root.TV.promptFormat.formatForExternalPaste(raw);
    }
    return raw;
  }

  /** Insert into the active tab's chat input (ChatGPT, Claude, …); fallback to sidebar composer. */
  async function insertPromptIntoActiveTabChat(text, options) {
    const opts = options || {};
    const prompt = formatPromptForPlatform(text);
    if (!prompt) return { ok: false, target: "none" };

    // Pro users get the gold insert glow on the platform's prompt area —
    // the content-script animation reads this flag and silently inserts
    // for free-tier users.
    const isPro = Boolean(authState.getSnapshot && authState.getSnapshot().isProUser);

    try {
      const res = await sendRuntimeMessage("TV_CONSUMER_INSERT_ACTIVE_TAB", { prompt, isPro });
      if (res && res.success && res.data && res.data.success) {
        const label = platformLabelFromKey(res.data.platform);
        showComposerInsertHint(`Inserted into ${label}`);
        if (opts.flashButton !== false) flashInsertInChatButton();
        return { ok: true, target: "tab", platform: res.data.platform };
      }

      const errMsg =
        (res && res.error && res.error.message) ||
        (res && res.data && res.data.error) ||
        "";

      if (opts.fallbackComposer !== false) {
        applyPromptToComposer(prompt);
        autoResizeTextarea();
        refreshComposerSend();
        showComposerInsertHint(
          errMsg
            ? `${errMsg} Added to sidebar composer instead.`
            : "No chat input on this tab. Added to sidebar composer."
        );
        return { ok: true, target: "composer", fallback: true };
      }

      showComposerInsertHint(errMsg || "Could not insert into this page.");
      return { ok: false, target: "none", error: errMsg };
    } catch (e) {
      const msg = e.message || String(e);
      if (opts.fallbackComposer !== false) {
        applyPromptToComposer(prompt);
        autoResizeTextarea();
        refreshComposerSend();
        showComposerInsertHint(`Added to sidebar composer. (${msg})`);
        return { ok: true, target: "composer", fallback: true };
      }
      showComposerInsertHint(msg);
      return { ok: false, target: "none", error: msg };
    }
  }

  function fillComposerFromPromptBook(text) {
    const t = String(text || "").trim();
    if (!t) return;
    applyPromptToComposer(t);
    window.requestAnimationFrame(() => {
      applyPromptToComposer(t);
      autoResizeTextarea();
      refreshComposerSend();
    });
  }

  /**
   * Route a saved-library / collection / memory prompt into the sidebar's own
   * composer rather than into the active browser tab. Used when the user
   * triggers "Insert in Chat" from inside the side panel — the expectation is
   * the prompt lands in the composer so they can enhance/refine before sending.
   */
  function insertPromptIntoSidebarComposer(text) {
    const safe = String(text || "").trim();
    if (!safe) return;
    if (views && typeof views.showHome === "function") views.showHome();
    else showPanelFallback("home");
    setRailActive(railHome);
    if (appShell) appShell.classList.remove("app-shell--in-session");
    applyPromptToComposer(safe);
    autoResizeTextarea();
    refreshComposerSend();
    showComposerInsertHint("Added to sidebar composer.");
    persistPanel("home");
  }

  function continuePromptBookInChat(text, promptMeta) {
    const enhanced = String((promptMeta && promptMeta.sessionEnhanced) || "").trim();
    const original = String((promptMeta && promptMeta.sessionOriginal) || "").trim();
    const composerText = String(text || "").trim() || enhanced || original;
    const mode = mapPromptBookEnhanceMode(promptMeta && promptMeta.tag);
    syncComposerEnhanceMode(mode);

    const startSession = root.TV._startSession;
    if (typeof startSession === "function" && enhanced) {
      startSession({
        original,
        enhanced,
        displayPrompt: enhanced,
        promptId: (promptMeta && promptMeta.id) || null,
        mode,
        fromPromptBook: true,
        composerFill: composerText,
      });
      setRailActive(null);
    } else if (views && views.showHome) {
      views.showHome();
      setRailActive(railHome);
    } else {
      showPanelFallback("home");
      setRailActive(railHome);
    }
    fillComposerFromPromptBook(composerText);
  }

  function getComposerInputMaxPx() {
    if (!promptInput) return 140;
    const max = parseFloat(getComputedStyle(promptInput).maxHeight);
    return Number.isFinite(max) && max > 0 ? max : 140;
  }

  function autoResizeTextarea() {
    if (!promptInput) return;
    const maxPx = getComposerInputMaxPx();
    promptInput.style.height = "auto";
    const next = Math.min(promptInput.scrollHeight, maxPx);
    const minPx = parseFloat(getComputedStyle(promptInput).minHeight) || 0;
    promptInput.style.height = Math.max(next, minPx) + "px";
  }
  if (promptInput) {
    promptInput.addEventListener("input", autoResizeTextarea);
    // Also reset height when value is cleared externally
    const origDescriptor = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    if (origDescriptor) {
      Object.defineProperty(promptInput, "value", {
        set(v) {
          origDescriptor.set.call(this, v);
          autoResizeTextarea();
        },
        get() { return origDescriptor.get.call(this); },
        configurable: true,
      });
    }
  }

  const HOSTED = {
    // The hosted "Account" panel lives inside Vel-Next `/chat` and is opened via
    // `?panel=account`, which sets `layoutView=profile` and strips the query
    // (see Vel-Next-Live-working/src/app/chat/page.js → TestAccountPanelQuery).
    profile: { path: "/chat?panel=account", utm: "extension_open_profile" },
  };

  function redirectIfWrongFlow(s) {
    if (s.loading || s.error || !root.TV.normalizeSidebarFlow || !root.TV.SidebarFlow) return;
    const want = root.TV.normalizeSidebarFlow(s.sidebarFlow);
    if (want === root.TV.SidebarFlow.ENTERPRISE) {
      window.location.replace(chrome.runtime.getURL("panel/bootstrap.html"));
    }
  }

  function initialsFromSnapshot(s) {
    const name = (s.userName || s.userEmail || "").trim();
    if (!name) return "?";
    const parts = name.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase().slice(0, 2);
    }
    return name.slice(0, 2).toUpperCase();
  }

  function firstNameFromSnapshot(s) {
    const raw = (s && (s.userName || s.userEmail) ? String(s.userName || s.userEmail) : "").trim();
    if (!raw) return "";
    let candidate = raw.split(/\s+/)[0] || "";
    if (candidate.includes("@")) candidate = candidate.split("@")[0];
    candidate = candidate.replace(/[._-]+/g, " ").trim().split(/\s+/)[0] || "";
    if (!candidate) return "";
    return candidate.charAt(0).toUpperCase() + candidate.slice(1);
  }

  function setHeroGreetingName(s) {
    if (!heroGreetingName) return;
    const first = firstNameFromSnapshot(s);
    heroGreetingName.textContent = first || "there";
  }

  function startHeroRotatingWord() {
    if (!heroRotatingWord || heroRotatingTimer) return;
    heroRotatingWord.textContent = HERO_ROTATING_WORDS[heroRotatingIdx];
    heroRotatingTimer = setInterval(() => {
      heroRotatingWord.classList.add("is-out");
      setTimeout(() => {
        heroRotatingIdx = (heroRotatingIdx + 1) % HERO_ROTATING_WORDS.length;
        heroRotatingWord.textContent = HERO_ROTATING_WORDS[heroRotatingIdx];
        heroRotatingWord.classList.remove("is-out");
      }, 220);
    }, 2200);
  }

  function setRailActive(activeBtn) {
    [railHome, railNewChat, railLibrary].forEach((b) => {
      if (b) b.classList.toggle("rail-btn--active", b === activeBtn);
    });
  }

  const views =
    root.TV && root.TV.consumerCollectionMemoryViews ? root.TV.consumerCollectionMemoryViews : null;

  /** Output / suggestions / context / versions / thought-process — hidden when browsing home stack. */
  const SESSION_SURFACE_IDS = [
    "viewOutput",
    "viewSuggestions",
    "viewContext",
    "viewVersions",
    "viewThoughtProcess",
  ];

  function hideSessionSurfaces() {
    if (appShell) {
      appShell.classList.remove("app-shell--output-mode");
    }
    SESSION_SURFACE_IDS.forEach((id) => {
      const v = el(id);
      if (!v) return;
      v.classList.remove("view-surface--active");
      v.hidden = true;
    });
    if (root.TV.suggestionsView && typeof root.TV.suggestionsView.hide === "function") {
      root.TV.suggestionsView.hide();
    }
  }

  function setComposerPromptHidden(hidden) {
    if (appShell) appShell.classList.toggle("app-shell--hide-composer-prompt", !!hidden);
  }

  function shufflePick(arr, n) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      const t = a[i];
      a[i] = a[j];
      a[j] = t;
    }
    return a.slice(0, Math.max(0, n));
  }

  function canUseLibraryPromptInChat(p) {
    if (!p) return false;
    const snap = authState.getSnapshot();
    const acc = root.TV.subscriptionAccess;
    if (acc && typeof acc.canAccessLibraryPrompt === "function") {
      return acc.canAccessLibraryPrompt(p, Boolean(snap.isProUser));
    }
    return !p.isProOnly || Boolean(snap.isProUser);
  }

  function homeCardDesc(p, locked) {
    if (locked) return "Upgrade to Pro to use in chat.";
    const raw = String((p && (p.short_prompt || p.prompt)) || "")
      .replace(/\s+/g, " ")
      .trim();
    if (raw.length <= 140) return raw || "Tap to use in composer.";
    return `${raw.slice(0, 137)}…`;
  }

  function buildHomePromptCard(p) {
    const isPro = Boolean(p && p.isProOnly);
    const locked = isPro && !canUseLibraryPromptInChat(p);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `prompt-card prompt-card--clickable${isPro ? " prompt-card--pro" : ""}${locked ? " prompt-card--locked" : ""}`;
    btn.setAttribute("aria-label", `Use prompt: ${(p && p.title) || "Untitled"}`);

    const thumb = document.createElement("div");
    thumb.className = "prompt-card-thumb";
    if (p && p.cover_src) {
      const img = document.createElement("img");
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      img.referrerPolicy = "no-referrer";
      img.src = p.cover_src;
      img.addEventListener("error", () => {
        img.remove();
        thumb.classList.add("prompt-card-thumb--fallback");
      });
      thumb.appendChild(img);
    }

    const body = document.createElement("div");
    body.className = "prompt-card-body";
    const title = document.createElement("div");
    title.className = "prompt-card-title";
    title.textContent = (p && p.title) || "Untitled";
    const desc = document.createElement("div");
    desc.className = "prompt-card-desc";
    desc.textContent = homeCardDesc(p, locked);
    body.appendChild(title);
    body.appendChild(desc);

    btn.appendChild(thumb);
    btn.appendChild(body);
    btn.addEventListener("click", () => {
      if (!canUseLibraryPromptInChat(p)) {
        const snap = authState.getSnapshot();
        if (!snap.isLoggedIn) {
          void authState.openLoginTab();
        } else {
          void authState.openHostedPage("/pricing", "sidebar_home_library_upgrade");
        }
        return;
      }
      const acc = root.TV.subscriptionAccess;
      const snap = authState.getSnapshot();
      const text =
        acc && typeof acc.getUsablePromptText === "function"
          ? acc.getUsablePromptText(p, Boolean(snap.isProUser))
          : String((p && (p.prompt || p.short_prompt)) || "").trim();
      if (!text) return;
      
      const startSession = root.TV._startSession;
      if (typeof startSession === "function") {
        if (promptInput) {
          promptInput.value = "";
          promptInput.dispatchEvent(new Event("input", { bubbles: true }));
        }
        startSession({
          original: text,
          enhanced: text,
          displayPrompt: text,
          promptId: p.id || null,
          mode: "standard",
        });
        setRailActive(null);
      }
    });
    return btn;
  }

  async function loadHomeFeaturedCards() {
    if (!homeFeaturedCards) return;
    const seq = ++homeFeaturedLoadSeq;
    
    if (homeFeaturedCards.children.length > 0) {
      homeFeaturedCards.classList.add("cards-shuffling");
      await new Promise(r => setTimeout(r, 250));
    }
    
    if (seq !== homeFeaturedLoadSeq) return;
    homeFeaturedCards.innerHTML = "";
    try {
      const url = chrome.runtime.getURL("data/prompt-library.json");
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (seq !== homeFeaturedLoadSeq) return;
      const all = Array.isArray(data.prompts) ? data.prompts : [];
      const snap = authState.getSnapshot();
      let pool = snap.isProUser ? all : all.filter((item) => !item.isProOnly);

      if (activeHostContext && activeHostContext.hostKey) {
        const platformMap = {
          bolt: "Coding",
          lovable: "Coding",
          vercel: "Coding",
          replit: "Coding",
          gamma: "Creative",
          suno: "Creative"
        };
        const preferredCategory = platformMap[activeHostContext.hostKey];
        if (preferredCategory) {
          const matching = pool.filter(p => p.category === preferredCategory);
          if (matching.length >= HOME_FEATURED_PROMPT_COUNT) {
            pool = matching;
          }
        }
      }

      const count = Math.min(HOME_FEATURED_PROMPT_COUNT, pool.length);
      const picks = shufflePick(pool, count);
      if (seq !== homeFeaturedLoadSeq) return;
      homeFeaturedCards.innerHTML = "";
      picks.forEach((p) => homeFeaturedCards.appendChild(buildHomePromptCard(p)));
      if (!picks.length) {
        const empty = document.createElement("p");
        empty.className = "home-featured-empty";
        empty.textContent = "No prompts in library.";
        homeFeaturedCards.appendChild(empty);
      }
    } catch (e) {
      if (seq !== homeFeaturedLoadSeq) return;
      console.warn("[sidebar-consumer] home featured prompts:", e);
      homeFeaturedCards.innerHTML = "";
      const err = document.createElement("p");
      err.className = "home-featured-empty";
      err.textContent = "Could not load prompts.";
      homeFeaturedCards.appendChild(err);
    } finally {
      if (seq === homeFeaturedLoadSeq) {
        requestAnimationFrame(() => {
          homeFeaturedCards.classList.remove("cards-shuffling");
        });
      }
    }
  }

  function goToPromptLibrary() {
    if (!requireAuth()) return;
    setRailActive(railLibrary);
    if (views && views.showLibrary) views.showLibrary();
    else {
      console.warn("[sidebar-consumer] In-panel library unavailable; check prompt-library-view.js");
      showPanelFallback("library");
    }
    persistPanel("library");
  }

  function showPanelFallback(which) {
    if (!requireAuth()) return;
    const home = el("viewHome");
    const lib = el("viewPromptLibrary");
    const col = el("viewCollections");
    const mem = el("viewMemory");
    if (!home || !col || !mem) return;
    if (appShell) appShell.classList.remove("app-shell--in-session");
    if (tabBar) tabBar.hidden = true;
    hideSessionSurfaces();
    if (viewLogin) {
      viewLogin.classList.remove("view-surface--active");
      viewLogin.hidden = true;
    }
    [home, lib, col, mem].forEach((sec) => {
      if (!sec) return;
      const active =
        (which === "home" && sec === home) ||
        (which === "library" && sec === lib) ||
        (which === "collections" && sec === col) ||
        (which === "memory" && sec === mem);
      sec.classList.toggle("view-surface--active", active);
      sec.hidden = !active;
    });
    setComposerPromptHidden(
      which === "library" || which === "collections" || which === "memory"
    );
    if (
      which === "library" &&
      root.TV.consumerPromptLibraryView &&
      root.TV.consumerPromptLibraryView.onShown
    ) {
      void root.TV.consumerPromptLibraryView.onShown();
    }
    persistPanel(which);
  }

  function setAuthHintVisible(visible) {
    if (!authHint) return;
    if (visible) authHint.removeAttribute("hidden");
    else authHint.setAttribute("hidden", "");
  }

  function setAuthGateActive(active) {
    if (appShell) appShell.classList.toggle("app-shell--auth-gate", Boolean(active));
  }

  function hideConsumerHomeViews() {
    CONSUMER_HOME_VIEW_IDS.forEach((id) => {
      const v = el(id);
      if (!v) return;
      v.classList.remove("view-surface--active");
      v.hidden = true;
    });
  }

  function showLoginView(message) {
    setAuthGateActive(true);
    setAuthHintVisible(false);
    if (tabBar) tabBar.hidden = true;
    hideConsumerHomeViews();
    hideSessionSurfaces();
    if (viewLogin) {
      viewLogin.classList.add("view-surface--active");
      viewLogin.hidden = false;
    }
    if (appShell) appShell.classList.add("app-shell--hide-composer-prompt");
    if (welcomeLoginStatus) {
      welcomeLoginStatus.textContent = message || "";
    }
  }

  let wasLoggedIn = false;

  function dismissAuthGate() {
    setAuthGateActive(false);
    setAuthHintVisible(false);
    if (viewLogin) {
      viewLogin.classList.remove("view-surface--active");
      viewLogin.hidden = true;
    }
    if (welcomeLoginStatus) welcomeLoginStatus.textContent = "";
    stopAuthPolling();
  }

  function startAuthPolling() {
    stopAuthPolling();
    _authPollStartedAt = Date.now();
    _authPollTimer = window.setInterval(() => {
      const elapsed = Date.now() - _authPollStartedAt;
      if (elapsed > AUTH_POLL_MAX_MS) {
        stopAuthPolling();
        return;
      }
      void authState.refresh({ force: true });
    }, AUTH_POLL_INTERVAL_MS);
  }

  function stopAuthPolling() {
    if (_authPollTimer != null) {
      window.clearInterval(_authPollTimer);
      _authPollTimer = null;
    }
    _authPollStartedAt = 0;
  }

  function syncComposerDockForCurrentPanel() {
    const inSession = tabBar && !tabBar.hidden;
    if (inSession) {
      if (appShell) appShell.classList.remove("app-shell--hide-composer-prompt");
      return;
    }
    const lib = el("viewPromptLibrary");
    const col = el("viewCollections");
    const mem = el("viewMemory");
    const hideComposer =
      (lib && lib.classList.contains("view-surface--active") && !lib.hidden) ||
      (col && col.classList.contains("view-surface--active") && !col.hidden) ||
      (mem && mem.classList.contains("view-surface--active") && !mem.hidden);
    if (appShell) {
      appShell.classList.toggle("app-shell--hide-composer-prompt", hideComposer);
    }
  }

  function showHomeAfterLogin() {
    dismissAuthGate();
    // First time the panel resolves to a signed-in state, prefer the saved
    // view (last enhance session, last opened sub-panel, etc.) if available.
    if (!_viewStateRestored) {
      const restored = restoreSavedView();
      if (restored) {
        _viewStateRestored = true;
        return;
      }
      _viewStateRestored = true;
    }
    const inSession = tabBar && !tabBar.hidden;
    if (inSession) {
      if (appShell) appShell.classList.remove("app-shell--hide-composer-prompt");
      return;
    }
    hideConsumerHomeViews();
    const home = el("viewHome");
    if (home) {
      home.classList.add("view-surface--active");
      home.hidden = false;
    }
    if (appShell) appShell.classList.remove("app-shell--hide-composer-prompt");
    void loadHomeFeaturedCards();
  }

  /**
   * Apply a saved view-state snapshot. Returns true when something was
   * restored (caller should then skip its default routing). Returns false
   * when there's nothing meaningful to rehydrate.
   */
  function restoreSavedView() {
    if (!viewState) return false;
    const saved = viewState.getSnapshot();
    if (!saved) return false;
    if (saved.panel === "session" && saved.session) {
      _viewStateApplying = true;
      try {
        if (typeof startSession === "function") {
          // Validate session has required data before restoring
          const session = saved.session;
          if (!session || (!session.original && !session.enhanced && !session.displayPrompt)) {
            console.warn("[sidebar] restoreSavedView: invalid session data, showing home");
            _viewStateApplying = false;
            return false; // Fall through to default home view
          }
          startSession(session);
        }
        const tab = saved.sessionTab && TAB_VIEWS[saved.sessionTab] ? saved.sessionTab : "output";
        if (tab !== "output") switchTab(tab);
      } catch (e) {
        console.error("[sidebar] restoreSavedView: failed to restore session:", e);
        _viewStateApplying = false;
        return false; // Fall through to default home view
      } finally {
        _viewStateApplying = false;
      }
      restoreComposerDraft(saved);
      return true;
    }
    if (saved.panel === "library" || saved.panel === "collections" || saved.panel === "memory") {
      _viewStateApplying = true;
      try {
        if (saved.panel === "library") {
          setRailActive(railLibrary);
          if (views && views.showLibrary) views.showLibrary();
          else showPanelFallback("library");
        } else if (saved.panel === "collections") {
          setRailActive(null);
          if (views && views.showCollections) views.showCollections();
          else showPanelFallback("collections");
        } else {
          setRailActive(null);
          if (views && views.showMemory) views.showMemory();
          else showPanelFallback("memory");
        }
      } finally {
        _viewStateApplying = false;
      }
      restoreComposerDraft(saved);
      return true;
    }
    return false;
  }

  function restoreComposerDraft(saved) {
    if (!promptInput) return;
    const draft = saved && typeof saved.composerInput === "string" ? saved.composerInput : "";
    if (!draft || promptInput.value) return;
    promptInput.value = draft;
    promptInput.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function isLoggedInSnapshot(s) {
    return Boolean(s && s.isLoggedIn);
  }

  function requireAuth(action) {
    const snap = authState.getSnapshot();
    if (!isLoggedInSnapshot(snap)) {
      showLoginView();
      return false;
    }
    if (typeof action === "function") action();
    return true;
  }

  function render(s) {
    redirectIfWrongFlow(s);

    if (profileInitials) {
      profileInitials.textContent = initialsFromSnapshot(s);
    }

    setHeroGreetingName(s);

    setAuthHintVisible(false);

    const loginBusy = Boolean(welcomeLoginBtn && welcomeSignupBtn);
    if (loginBusy) {
      const busy = Boolean(s.loading);
      welcomeLoginBtn.disabled = busy;
      welcomeSignupBtn.disabled = busy;
    }
    if (btnRefresh) btnRefresh.disabled = Boolean(s.loading);
    if (btnLogin) btnLogin.disabled = Boolean(s.loading);

    if (s.loading) {
      if (!wasLoggedIn) {
        showLoginView("Checking sign-in…");
      }
      return;
    }

    if (s.error) {
      if (!wasLoggedIn) {
        showLoginView(s.error);
      }
      return;
    }

    if (!s.isLoggedIn) {
      if (wasLoggedIn) {
        // Genuine logout — drop the saved view so the next sign-in starts
        // fresh and so the next user on this machine doesn't inherit
        // someone else's session.
        if (viewState && typeof viewState.clear === "function") {
          viewState.clear();
        }
        _viewStateRestored = false;
      }
      wasLoggedIn = false;
      showLoginView();
      return;
    }

    const justAuthed = !wasLoggedIn;
    wasLoggedIn = true;

    if (justAuthed) {
      showHomeAfterLogin();
    } else {
      dismissAuthGate();
      syncComposerDockForCurrentPanel();
    }
  }

  async function openHosted(key) {
    const cfg = HOSTED[key];
    if (!cfg) return;
    try {
      await authState.openHostedPage(cfg.path, cfg.utm);
    } catch (e) {
      console.warn("[sidebar-consumer] openHostedPage failed:", e);
    }
  }

  function setConsumerSidebarCollapsed(collapsed) {
    if (!appShell) return;
    const on = Boolean(collapsed);
    appShell.classList.toggle("shell--collapsed", on);
    if (railToggle) {
      railToggle.setAttribute("aria-expanded", on ? "false" : "true");
    }
    if (sidebarExpandBtn) {
      sidebarExpandBtn.hidden = !on;
      sidebarExpandBtn.setAttribute("aria-expanded", on ? "false" : "true");
    }
  }

  if (railToggle) {
    railToggle.addEventListener("click", () => {
      setConsumerSidebarCollapsed(true);
    });
  }

  if (sidebarExpandBtn) {
    sidebarExpandBtn.addEventListener("click", () => {
      setConsumerSidebarCollapsed(false);
    });
  }

  if (root.TV.consumerPromptLibraryView && typeof root.TV.consumerPromptLibraryView.init === "function") {
    root.TV.consumerPromptLibraryView.init({
      authState,
      onInsertPrompt(text, promptMeta) {
        if (promptMeta && !canUseLibraryPromptInChat(promptMeta)) {
          const snap = authState.getSnapshot();
          if (!snap.isLoggedIn) {
            void authState.openLoginTab();
          } else {
            void authState.openHostedPage("/pricing", "sidebar_library_upgrade");
          }
          return;
        }
        const safeText =
          promptMeta && root.TV.subscriptionAccess && typeof root.TV.subscriptionAccess.getUsablePromptText === "function"
            ? root.TV.subscriptionAccess.getUsablePromptText(
                promptMeta,
                Boolean(authState.getSnapshot().isProUser)
              )
            : String(text || "").trim();
        if (!safeText) return;
        insertPromptIntoSidebarComposer(safeText);
      },
      onOpenInPlatform(text, platformKey, promptMeta) {
        if (promptMeta && !canUseLibraryPromptInChat(promptMeta)) {
          const snap = authState.getSnapshot();
          if (!snap.isLoggedIn) {
            void authState.openLoginTab();
          } else {
            void authState.openHostedPage("/pricing", "sidebar_library_upgrade");
          }
          return;
        }
        const safeText =
          promptMeta && root.TV.subscriptionAccess && typeof root.TV.subscriptionAccess.getUsablePromptText === "function"
            ? root.TV.subscriptionAccess.getUsablePromptText(
                promptMeta,
                Boolean(authState.getSnapshot().isProUser)
              )
            : String(text || "").trim();
        const prompt = formatPromptForPlatform(safeText);
        if (!prompt) {
          showComposerInsertHint("Nothing to open. No prompt text available.");
          return;
        }
        void sendRuntimeMessage("TV_CONSUMER_OPEN_IN_PLATFORM", {
          prompt,
          platformKey: platformKey || "openai",
          isPro: Boolean(authState.getSnapshot && authState.getSnapshot().isProUser),
        }).then((res) => {
          if (res && res.success) {
            const label = platformLabelFromKey(
              (res.data && res.data.platform) || platformKey
            );
            showComposerInsertHint(`Opening ${label}…`);
            return;
          }
          const msg =
            (res && res.error && res.error.message) ||
            (res && res.data && res.data.error) ||
            "Could not open platform.";
          showComposerInsertHint(msg);
          console.warn("[sidebar] library open in:", msg);
        });
      },
    });
  }

  if (views && typeof views.init === "function") {
    views.init({
      authState,
      onInsertPrompt(text, promptMeta) {
        const snap = authState.getSnapshot();
        if (promptMeta && promptMeta.isProOnly && !canUseLibraryPromptInChat(promptMeta)) {
          if (!snap.isLoggedIn) {
            void authState.openLoginTab();
          } else {
            void authState.openHostedPage("/pricing", "sidebar_library_upgrade");
          }
          return;
        }
        const safeText = String(text || "").trim();
        if (!safeText) return;
        if (promptMeta && promptMeta.source === "prompt-book" && promptMeta.continueSession) {
          continuePromptBookInChat(safeText, promptMeta);
          return;
        }
        insertPromptIntoSidebarComposer(safeText);
      },
      onRequestComposerFocus(hint) {
        if (views && views.showHome) views.showHome();
        else showPanelFallback("home");
        setRailActive(railHome);
        if (promptInput) {
          promptInput.focus();
        }
        if (enhanceStatus && hint) {
          if (window.__tvComposerHintTimer) {
            window.clearTimeout(window.__tvComposerHintTimer);
          }
          enhanceStatus.textContent = hint;
          window.__tvComposerHintTimer = window.setTimeout(() => {
            if (enhanceStatus) enhanceStatus.textContent = "";
            window.__tvComposerHintTimer = null;
          }, 8000);
        }
        refreshComposerSend();
      },
    });
  }

  if (railHome) {
    railHome.addEventListener("click", () => {
      if (!requireAuth()) return;
      setRailActive(railHome);
      if (views && views.showHome) views.showHome();
      else showPanelFallback("home");
      void loadHomeFeaturedCards();
      persistPanel("home");
    });
  }

  railNewChat.addEventListener("click", () => {
    if (!requireAuth()) return;
    setRailActive(railNewChat);
    if (typeof resetSession === "function") resetSession();
    if (views && views.showHome) views.showHome();
    else showPanelFallback("home");
    if (promptInput) {
      promptInput.value = "";
      promptInput.focus();
    }
    void loadHomeFeaturedCards();
    refreshComposerSend();
  });

  if (railLibrary) {
    railLibrary.addEventListener("click", () => {
      goToPromptLibrary();
    });
  }

  if (btnShowMorePrompts) {
    btnShowMorePrompts.addEventListener("click", () => {
      goToPromptLibrary();
    });
  }

  if (btnShufflePrompts) {
    btnShufflePrompts.addEventListener("click", () => {
      if (!requireAuth()) return;
      btnShufflePrompts.classList.remove("is-spinning");
      void btnShufflePrompts.offsetWidth;
      btnShufflePrompts.classList.add("is-spinning");
      loadHomeFeaturedCards();
    });
  }



  railProfile.addEventListener("click", () => {
    const snap = authState.getSnapshot();
    if (!isLoggedInSnapshot(snap)) {
      void authState.openLoginTab();
      return;
    }
    void openHosted("profile");
  });



  function syncRailUpsells(snap) {
    const isConfirmedPro = Boolean(snap && !snap.loading && !snap.error && snap.isProUser);
    // Update mode dropdown icon colors based on user tier
    updateModeDropdownTier(isConfirmedPro);
  }
  authState.subscribe(syncRailUpsells);
  syncRailUpsells(authState.getSnapshot());

  function closeSidePanelAfterAuthRedirect() {
    // Give Chrome a tick to actually open the new tab before this panel
    // window is torn down, then close ourselves. Background reopens the
    // panel once `storeUserData` fires from the hosted login flow.
    window.setTimeout(() => {
      try { window.close(); } catch (_) {}
    }, 150);
  }

  if (welcomeLoginBtn) {
    welcomeLoginBtn.addEventListener("click", async () => {
      welcomeLoginBtn.disabled = true;
      if (welcomeSignupBtn) welcomeSignupBtn.disabled = true;
      try {
        await authState.openLoginTab();
      } catch (e) {
        console.warn("[sidebar-consumer] openLoginTab failed:", e);
      }
      closeSidePanelAfterAuthRedirect();
    });
  }
  if (welcomeSignupBtn) {
    welcomeSignupBtn.addEventListener("click", async () => {
      welcomeSignupBtn.disabled = true;
      if (welcomeLoginBtn) welcomeLoginBtn.disabled = true;
      try {
        await authState.openHostedPage("/register", "sidebar_welcome_signup");
      } catch (e) {
        console.warn("[sidebar-consumer] openHostedPage failed:", e);
      }
      closeSidePanelAfterAuthRedirect();
    });
  }

  btnRefresh.addEventListener("click", () => authState.refresh());
  btnLogin.addEventListener("click", () => authState.openLoginTab());

  if (root.TV.consumerComposerBar && typeof root.TV.consumerComposerBar.init === "function") {
    void root.TV.consumerComposerBar.init({ authState });
  }

  if (root.TV.consumerUsageLimitBanner && typeof root.TV.consumerUsageLimitBanner.init === "function") {
    root.TV.consumerUsageLimitBanner.init(authState);
  }

  if (root.TV.consumerSubscriptionTheme && typeof root.TV.consumerSubscriptionTheme.init === "function") {
    root.TV.consumerSubscriptionTheme.init(authState);
  }

  authState.subscribe(() => {
    refreshComposerSend();
  });

  // ── Session & Tab management ─────────────────────────────────────────────

  const TAB_VIEWS = {
    output:      "viewOutput",
    suggestions: "viewSuggestions",
    context:     "viewContext",
    versions:    "viewVersions",
  };
  let previousSessionTab = "output";

  const SESSION_VIEWS = Object.values(TAB_VIEWS);
  const HOME_VIEWS    = ["viewHome", "viewPromptLibrary", "viewCollections", "viewMemory"];
  const ALL_VIEWS     = [...HOME_VIEWS, "viewThoughtProcess", ...SESSION_VIEWS];

  function hideAllViews() {
    if (appShell) {
      appShell.classList.remove("app-shell--output-mode");
    }
    ALL_VIEWS.forEach((id) => {
      const v = el(id);
      if (!v) return;
      v.classList.remove("view-surface--active");
      v.hidden = true;
    });
  }

  function switchTab(tabName) {
    const leavingSuggestions =
      previousSessionTab === "suggestions" &&
      tabName !== "suggestions" &&
      TAB_VIEWS[tabName];

    if (leavingSuggestions && promptInput) {
      promptInput.value = "";
      promptInput.dispatchEvent(new Event("input", { bubbles: true }));
      if (root.TV.consumerComposerBar && typeof root.TV.consumerComposerBar.refreshSendState === "function") {
        root.TV.consumerComposerBar.refreshSendState();
      }
    }

    // Update tab button states
    if (tabBar) {
      tabBar.querySelectorAll(".tab-btn").forEach((btn) => {
        const active = btn.getAttribute("data-tab") === tabName;
        btn.classList.toggle("tab-btn--active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      });
    }

    // Leave home-stack surfaces so session content is not stacked under library/collections/memory
    HOME_VIEWS.forEach((id) => {
      const v = el(id);
      if (!v) return;
      v.classList.remove("view-surface--active");
      v.hidden = true;
    });

    hideSessionSurfaces();

    const targetId = TAB_VIEWS[tabName];
    const target = targetId && el(targetId);
    if (target) {
      target.classList.add("view-surface--active");
      target.hidden = false;
    }

    if (promptInput) {
      if (tabName === "context") {
        promptInput.placeholder = COMPOSER_PLACEHOLDER_CONTEXT;
      } else if (tabName === "suggestions") {
        promptInput.placeholder = COMPOSER_PLACEHOLDER_SUGGESTIONS;
      } else {
        promptInput.placeholder = COMPOSER_PLACEHOLDER_DEFAULT;
      }
    }

    // Show/activate per-module
    if (tabName === "output"      && root.TV.outputView)      { /* already rendered */ }
    if (tabName === "suggestions" && root.TV.suggestionsView) root.TV.suggestionsView.show();
    if (tabName === "context"     && root.TV.contextView)     root.TV.contextView.show(_session || {});
    if (tabName === "versions"    && root.TV.versionsView)    root.TV.versionsView.render(_session || null);

    if (appShell) {
      appShell.classList.toggle("app-shell--output-mode", tabName === "output");
    }

    if (TAB_VIEWS[tabName]) previousSessionTab = tabName;

    setComposerPromptHidden(false);
    refreshComposerSend();
    refreshSuggestionsComposerChrome();

    if (TAB_VIEWS[tabName]) persistSessionTab(tabName);
  }

  let _session = null;

  function showSessionShell(tabName) {
    // Close any open detail popups first to ensure clean state
    try {
      if (root.TV.consumerPromptBookDetailView && typeof root.TV.consumerPromptBookDetailView.close === "function") {
        root.TV.consumerPromptBookDetailView.close();
      }
    } catch (_) {}
    try {
      if (root.TV.consumerPromptLibraryView && typeof root.TV.consumerPromptLibraryView.closeDetail === "function") {
        root.TV.consumerPromptLibraryView.closeDetail();
      }
    } catch (_) {}
    
    if (appShell) appShell.classList.add("app-shell--in-session");
    autoResizeTextarea();
    refreshComposerSend();
    // Hide home / library / etc.
    HOME_VIEWS.forEach((id) => {
      const v = el(id);
      if (!v) return;
      v.classList.remove("view-surface--active");
      v.hidden = true;
    });
    if (tabBar) tabBar.hidden = false;
    switchTab(tabName || "output");
  }

  function startSession(data) {
    const safeRefinements = Array.isArray(data && data._refinements) ? data._refinements : [];
    _session = { ...data, _refinements: safeRefinements };

    // Wire versions-view "Use in Output" callback
    if (root.TV.versionsView) {
      root.TV.versionsView.onUse((text, label) => {
        _session = { ..._session, displayPrompt: text };
        if (root.TV.outputView) root.TV.outputView.show(_session);
        showSessionShell("output");
        persistView({
          panel: "session",
          sessionTab: "output",
          session: serializeSession(_session),
        });
      });
    }

    // Wire output-view callbacks
    if (root.TV.outputView) {
      root.TV.outputView.onEdit((text) => {
        if (promptInput) {
          promptInput.value = text || "";
          promptInput.dispatchEvent(new Event("input", { bubbles: true }));
          promptInput.focus();
        }
        refreshComposerSend();
        showSessionShell("output");
      });
      root.TV.outputView.onRefine(() => {
        showSessionShell("suggestions");
        if (root.TV.suggestionsView) {
          root.TV.suggestionsView.show();
          if (typeof root.TV.suggestionsView.activateImproveComposer === "function") {
            root.TV.suggestionsView.activateImproveComposer();
          }
        }
      });
      root.TV.outputView.onFeedback(({ feedback, promptId }) => {
        const isRefine = _session && _session._refinements && _session._refinements.length > 0;
        chrome.runtime.sendMessage({
          action: "TV_CONSUMER_FEEDBACK",
          payload: { promptId, feedback, mode: data.mode || "standard", isRefine },
          requestId: `req_${Date.now()}`,
        });
        if (feedback === "dislike" && root.TV.feedbackPopup && typeof root.TV.feedbackPopup.show === "function") {
          root.TV.feedbackPopup.show({
            reason: "Enhancement dislike",
            source: "sidebar-extension",
          });
        }
      });
      root.TV.outputView.onInsertInChat((text) => {
        void insertPromptIntoActiveTabChat(text, { flashButton: true });
      });
      root.TV.outputView.onOpenIn((text, platformKey) => {
        const prompt = formatPromptForPlatform(text);
        if (!prompt) {
          showComposerInsertHint("Nothing to open. Enhance a prompt first.");
          return;
        }
        void sendRuntimeMessage("TV_CONSUMER_OPEN_IN_PLATFORM", {
          prompt,
          platformKey: platformKey || "openai",
          isPro: Boolean(authState.getSnapshot && authState.getSnapshot().isProUser),
        }).then((res) => {
          if (res && res.success) {
            const label = platformLabelFromKey((res.data && res.data.platform) || platformKey);
            showComposerInsertHint(`Opening ${label}…`);
            return;
          }
          const msg =
            (res && res.error && res.error.message) ||
            (res && res.data && res.data.error) ||
            "Could not open platform.";
          showComposerInsertHint(msg);
          console.warn("[sidebar] open in:", msg);
        });
      });
      root.TV.outputView.show(_session);
    }

    if (root.TV.contextView) root.TV.contextView.show(_session);
    if (root.TV.versionsView) root.TV.versionsView.render(_session);

    if (root.TV.suggestionsView) {
      root.TV.suggestionsView.onRefined((refinedPrompt, qaArray, annotatedSegments) => {
        // Defensive check: ensure _session exists before accessing
        if (!_session) {
          console.warn("[sidebar] onRefined: _session is null, cannot apply refinement");
          // Try to restore home view as fallback
          if (views && views.showHome) views.showHome();
          else showPanelFallback("home");
          setRailActive(railHome);
          return;
        }

        const refineNum = (_session._refinements || []).length + 1;
        const refinement = { label: `REFINED ${refineNum}`, text: refinedPrompt };
        _session = {
          ..._session,
          displayPrompt: refinedPrompt,
          // Store fresh annotations for the refined prompt so output-view
          // renders the annotated view. Falls back to [] (plain text) when
          // the local annotation server is offline.
          annotated_segments:
            Array.isArray(annotatedSegments) && annotatedSegments.length > 0
              ? annotatedSegments
              : [],
          _refinements: [...(_session._refinements || []), refinement],
        };

        // Ensure views are properly updated
        try {
          if (root.TV.versionsView) root.TV.versionsView.render(_session);
          if (root.TV.outputView) root.TV.outputView.show(_session);
        } catch (e) {
          console.error("[sidebar] onRefined: error updating views:", e);
        }

        void root.TV.suggestionsView.load(_session);

        // Ensure proper view transition
        showSessionShell("output");
        
        // Force output view visibility as a safeguard
        const viewOutput = el("viewOutput");
        if (viewOutput) {
          viewOutput.classList.add("view-surface--active");
          viewOutput.hidden = false;
        }

        persistView({
          panel: "session",
          sessionTab: "output",
          session: serializeSession(_session),
        });
      });
      void root.TV.suggestionsView.load(_session);
    }

    showSessionShell("output");
    setRailActive(null);

    if (data.fromPromptBook && data.composerFill) {
      fillComposerFromPromptBook(data.composerFill);
    }

    persistView({
      panel: "session",
      sessionTab: "output",
      session: serializeSession(_session),
    });
  }

  /** Strip non-JSON fields from a session before writing to storage. */
  function serializeSession(s) {
    if (!s || typeof s !== "object") return null;
    try {
      return JSON.parse(JSON.stringify(s));
    } catch (_) {
      return null;
    }
  }

  // Expose startSession so composer-bar.js can call it after enhance
  root.TV._startSession = startSession;

  function resetSession() {
    if (appShell) appShell.classList.remove("app-shell--in-session");
    autoResizeTextarea();
    _session = null;
    previousSessionTab = "output";
    if (promptInput) {
      promptInput.value = "";
      promptInput.placeholder = COMPOSER_PLACEHOLDER_DEFAULT;
      promptInput.dispatchEvent(new Event("input", { bubbles: true }));
    }
    if (root.TV.consumerComposerBar && typeof root.TV.consumerComposerBar.refreshSendState === "function") {
      root.TV.consumerComposerBar.refreshSendState();
    }
    if (tabBar) tabBar.hidden = true;
    hideSessionSurfaces();
    HOME_VIEWS.forEach((id) => {
      const v = el(id);
      if (!v) return;
      if (id === "viewHome") {
        v.classList.add("view-surface--active");
        v.hidden = false;
      } else {
        v.classList.remove("view-surface--active");
        v.hidden = true;
      }
    });
    setComposerPromptHidden(false);
    persistView({
      panel: "home",
      sessionTab: "output",
      session: null,
      composerInput: "",
    });
  }

  // Tab bar click wiring
  if (tabBar) {
    tabBar.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.getAttribute("data-tab");
        if (tab) switchTab(tab);
      });
    });
  }

  function applyPendingInjectionAction() {
    chrome.storage.local.get(
      [
        "velocity_button_pending_prompt",
        "velocity_button_pending_original",
        "velocity_button_pending_enhanced",
        "velocity_button_pending_mode",
        "velocity_button_pending_platform",
        "velocity_button_nav_target",
        "velocity_button_pending_at",
      ],
      (items) => {
        const at = Number(items.velocity_button_pending_at) || 0;
        if (!at || Date.now() - at > 120000) return;

        const target = String(items.velocity_button_nav_target || "enhance").trim().toLowerCase();
        const prompt = String(items.velocity_button_pending_prompt || "").trim();
        const originalText = String(items.velocity_button_pending_original || "").trim();
        const enhancedText = String(items.velocity_button_pending_enhanced || "").trim();
        const sessionMode = String(items.velocity_button_pending_mode || "").trim() || "standard";

        if (target === "library" && !isLoggedInSnapshot(authState.getSnapshot())) {
          chrome.storage.local.remove([
            "velocity_button_pending_prompt",
            "velocity_button_pending_original",
            "velocity_button_pending_enhanced",
            "velocity_button_pending_mode",
            "velocity_button_pending_platform",
            "velocity_button_pending_at",
            "velocity_button_nav_target",
          ]);
          showLoginView();
          return;
        }

        const pendingPlatform = String(items.velocity_button_pending_platform || "").trim();
        chrome.storage.local.remove([
          "velocity_button_pending_prompt",
          "velocity_button_pending_original",
          "velocity_button_pending_enhanced",
          "velocity_button_pending_mode",
          "velocity_button_pending_platform",
          "velocity_button_pending_at",
          "velocity_button_nav_target",
        ]);

        if (pendingPlatform && root.TV.hostContext && root.TV.hostContext.HOST_RULES) {
          const rule = root.TV.hostContext.HOST_RULES.find((r) => r.hostKey === pendingPlatform);
          if (rule) {
            activeHostContext = {
              hostKey: rule.hostKey,
              aiType: rule.aiType,
              openInKey: rule.openInKey,
              label: rule.label,
              platformFeedId: `pl-${rule.aiType}`,
            };
            if (views && typeof views.setActiveHostContext === "function") {
              views.setActiveHostContext(activeHostContext);
            }
          }
        }

        if (target === "library") {
          goToPromptLibrary();
          return;
        }

        if (target === "voice" || target === "enhance") {
          // Hand-off from the in-page Improve modal: when both `original` and
          // `enhanced` are present we render the session/Output view directly
          // using the existing enhancement — no /enhance call, no extra
          // usage tick. Falls back to a plain composer pre-fill when only
          // the legacy `prompt` field is available (e.g. user clicked Open
          // before the in-page enhance returned).
          const startSession = root.TV && root.TV._startSession;
          const canRehydrateSession =
            target === "enhance" &&
            enhancedText &&
            typeof startSession === "function";

          if (canRehydrateSession) {
            try {
              startSession({
                original: originalText || prompt,
                enhanced: enhancedText,
                displayPrompt: enhancedText,
                promptId: null,
                mode: sessionMode,
                quality: {},
                fromInjectionModal: true,
              });
              setRailActive(null);
              return;
            } catch (err) {
              console.warn("[Velocity Sidebar] session rehydrate failed:", err);
              // Fall through to the pre-fill path below.
            }
          }

          if (views && typeof views.showHome === "function") {
            views.showHome();
          } else {
            showPanelFallback("home");
          }
          setRailActive(railHome);
          if (prompt) fillComposerFromPromptBook(prompt);
        }

        if (target === "voice") {
          const tryVoice = (left) => {
            if (
              root.TV.consumerComposerBar &&
              typeof root.TV.consumerComposerBar.triggerVoiceMic === "function"
            ) {
              root.TV.consumerComposerBar.triggerVoiceMic();
              return;
            }
            if (left > 0) window.setTimeout(() => tryVoice(left - 1), 200);
          };
          window.setTimeout(() => tryVoice(10), 300);
        }
      }
    );
  }

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    if (changes.velocity_button_pending_at || changes.velocity_button_nav_target) {
      applyPendingInjectionAction();
    }
    if (
      changes.userId ||
      changes.accessToken ||
      changes.refreshToken ||
      changes.userEmail
    ) {
      void authState.refresh({ force: true });
    }
  });

  if (promptInput) {
    promptInput.addEventListener("input", () => {
      persistComposerInput();
    });
  }

  if (btnComposerImprove) {
    btnComposerImprove.addEventListener("click", () => {
      if (root.TV.suggestionsView && typeof root.TV.suggestionsView.activateImproveComposer === "function") {
        root.TV.suggestionsView.activateImproveComposer();
      }
      refreshSuggestionsComposerChrome();
    });
  }

  const btnOutputDockImprove = el("btnOutputDockImprove");
  const btnOutputDockUse = el("btnOutputDockUse");

  if (btnOutputDockImprove) {
    btnOutputDockImprove.addEventListener("click", () => {
      showSessionShell("suggestions");
      if (root.TV.suggestionsView) {
        root.TV.suggestionsView.show();
        if (typeof root.TV.suggestionsView.activateImproveComposer === "function") {
          root.TV.suggestionsView.activateImproveComposer();
        }
      }
    });
  }

  if (btnOutputDockUse) {
    btnOutputDockUse.addEventListener("click", () => {
      if (!_session) return;
      const text = _session.displayPrompt || _session.enhanced || "";
      if (text) {
        void insertPromptIntoActiveTabChat(text, { flashButton: true });
      }
    });
  }

  authState.subscribe(render);
  // ── Enterprise mode switcher ─────────────────────────────────────────────
  (function initEnterpriseSwitcher() {
    const railEnterprise = document.getElementById("railEnterprise");
    if (!railEnterprise) return;
    const SK = root.TV && root.TV.STORAGE_KEYS;
    if (!SK) return;
    // Show the button if enterprise tokens exist in storage.
    chrome.storage.local.get([SK.ENT_ACCESS_TOKEN, SK.ENT_REFRESH_TOKEN], (r) => {
      if (chrome.runtime.lastError) return;
      if (r[SK.ENT_ACCESS_TOKEN] || r[SK.ENT_REFRESH_TOKEN]) {
        railEnterprise.style.display = "";
      }
    });
    railEnterprise.addEventListener("click", () => {
      chrome.storage.local.set({ [SK.SIDEBAR_FLOW]: "enterprise" }, () => {
        window.location.replace(chrome.runtime.getURL("panel/bootstrap.html"));
      });
    });
  })();
  startHeroRotatingWord();
  // Load the persisted view-state snapshot before kicking off the first
  // auth refresh, so `showHomeAfterLogin()` can route the user back to the
  // last screen they were on (Library / Collections / a live enhance session).
  (async () => {
    try {
      if (viewState && typeof viewState.init === "function") {
        await viewState.init();
      }
    } finally {
      void authState.refresh();
    }
  })();
  refreshComposerSend();
  void loadActiveHostContext();
  applyPendingInjectionAction();

  // Long-lived port the background uses to detect this side panel's open/close
  // transitions (see features/side-panel-lifecycle.js). Closing the panel tears
  // down the page, the port disconnects, and the launcher pill on host pages
  // resumes its idle glow.
  try {
    const lifecyclePort = chrome.runtime.connect({ name: "velocity-side-panel-lifecycle" });
    lifecyclePort.onDisconnect.addListener(() => {
      void chrome.runtime.lastError;
    });
  } catch (e) {
    console.warn("[sidebar-consumer] lifecycle port failed:", e);
  }
})();
