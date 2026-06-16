/**
 * In-panel Collections + Memory + lazy Prompt Book (consumer sidebar).
 * Uses background messages (no direct fetch from UI).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const PROMPT_FETCH_SIZE = 20;
  const FEED_FETCH_SIZE = 1000;
  const MEMORY_FETCH_SIZE = 20;

  const VELOCITY_LOGO_URL =
    typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.getURL
      ? chrome.runtime.getURL("assets/Velocity_logo.png")
      : "../../assets/Velocity_logo.png";

  const FEED_ICON = {
    chatgpt: "https://thinkvelocity.in/next-assets/chatgpt_icon.png",
    claude: "https://thinkvelocity.in/next-assets/claude_logo.png",
    gemini: "https://thinkvelocity.in/next-assets/gemini_logo.png",
    perplexity: "https://thinkvelocity.in/next-assets/perplexity_logo.png",
    grok: "https://thinkvelocity.in/next-assets/grok_logo.png",
    suno: "https://thinkvelocity.in/next-assets/suno_logo.png",
    velocity: VELOCITY_LOGO_URL,
  };

  const PLATFORM_LABEL = {
    chatgpt: "ChatGPT",
    claude: "Claude",
    gemini: "Gemini",
    perplexity: "Perplexity",
    grok: "Grok",
    suno: "Suno",
    mistral: "Mistral",
    bolt: "Bolt",
    lovable: "Lovable",
    replit: "Replit",
    vercel: "v0",
    gamma: "Gamma",
    velocity: "Velocity",
  };

  /**
   * Resolve the platform icon for a prompt-book / feed item.
   * Reads `item.aiType` (or `ai_type`), normalises through `TV.hostContext`,
   * and returns the hosted icon URL when known, falling back to the local
   * Velocity logo so the card never shows a random / generic glyph.
   */
  function resolvePromptPlatform(item) {
    const raw = item && (item.aiType || item.ai_type);
    const HC = root.TV && root.TV.hostContext;
    let key = String(raw || "").toLowerCase().trim();
    if (HC && typeof HC.normalizeAiType === "function") {
      key = HC.normalizeAiType(key) || key;
    }
    if (!key) key = "velocity";
    const iconUrl = FEED_ICON[key] || VELOCITY_LOGO_URL;
    const label = PLATFORM_LABEL[key] || key.charAt(0).toUpperCase() + key.slice(1);
    return { key, label, iconUrl };
  }

  function previewLimit() {
    const nav = root.TV.sidebarHostedNav;
    return nav && nav.PREVIEW_LIMIT != null ? nav.PREVIEW_LIMIT : 20;
  }

  function hostedNav() {
    return root.TV.sidebarHostedNav || null;
  }

  function $(id) {
    return document.getElementById(id);
  }

  function sendRuntime(action, payload) {
    const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ action, payload: payload || {}, requestId }, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        resolve(response);
      });
    });
  }

  function setStatus(el, text) {
    if (el) el.textContent = text || "";
  }

  const state = {
    authRef: null,
    /** @type {((hint?: string) => void) | null} */
    onRequestComposerFocus: null,
    /** @type {string|null} */
    lastPanel: null,
    /** @type {object|null} */
    activeHostContext: null,
    collectionsRaw: [],
    platformFeedsRaw: [],
    promptLoaded: false,
    promptLoading: false,
    memLoaded: false,
    memLoading: false,
  };

  const SESSION_SURFACE_IDS = [
    "viewOutput",
    "viewSuggestions",
    "viewContext",
    "viewVersions",
    "viewThoughtProcess",
  ];

  function hideSessionSurfaces() {
    SESSION_SURFACE_IDS.forEach((id) => {
      const sec = $(id);
      if (!sec) return;
      sec.classList.remove("view-surface--active");
      sec.hidden = true;
    });
    if (root.TV.suggestionsView && typeof root.TV.suggestionsView.hide === "function") {
      root.TV.suggestionsView.hide();
    }
  }

  function setComposerPromptHidden(hidden) {
    const shell = $("appShell");
    if (shell) {
      shell.classList.toggle(
        "app-shell--hide-composer-prompt",
        !!hidden
      );
    }
  }

  function exitSessionChrome() {
    const shell = $("appShell");
    if (shell) shell.classList.remove("app-shell--in-session");
    const tabs = $("tabBar");
    if (tabs) tabs.hidden = true;
  }

  function toggleViews(which) {
    const prev = state.lastPanel;
    if (prev === "library" && which !== "library") {
      if (root.TV.consumerPromptLibraryView && root.TV.consumerPromptLibraryView.onHidden) {
        root.TV.consumerPromptLibraryView.onHidden();
      }
    }
    if (which !== "collections" && root.TV.consumerPromptBookDetailView && root.TV.consumerPromptBookDetailView.close) {
      root.TV.consumerPromptBookDetailView.close();
    }
    if (which !== "memory" && root.TV.consumerMemoryEditor && root.TV.consumerMemoryEditor.close) {
      root.TV.consumerMemoryEditor.close();
    }
    exitSessionChrome();
    hideSessionSurfaces();
    const login = $("viewLogin");
    if (login) {
      login.classList.remove("view-surface--active");
      login.hidden = true;
    }
    const home = $("viewHome");
    const lib = $("viewPromptLibrary");
    const col = $("viewCollections");
    const mem = $("viewMemory");
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
    if (which === "library" && root.TV.consumerPromptLibraryView && root.TV.consumerPromptLibraryView.onShown) {
      root.TV.consumerPromptLibraryView.onShown();
    }
    state.lastPanel = which;
  }

  function buildPlatformFeeds(enhancedItems) {
    const grouped = {};
    (enhancedItems || []).forEach((item) => {
      const type = String(item.aiType || item.ai_type || "chatgpt").toLowerCase();
      if (!grouped[type]) grouped[type] = [];
      grouped[type].push(item);
    });
    return Object.keys(grouped)
      .sort()
      .map((type) => {
        const prompts = grouped[type];
        const label = type.charAt(0).toUpperCase() + type.slice(1);
        return {
          id: `pl-${type}`,
          collectionId: `pl-${type}`,
          name: `${label} Feed`,
          description: `All items enhanced with ${type}.`,
          tag: type.toUpperCase(),
          icon: FEED_ICON[type] || "https://thinkvelocity.in/next-assets/AI_Placeholder.png",
          count: prompts.length,
          isPlatformFeed: true,
        };
      });
  }

  function renderFeedCards(feeds) {
    const host = $("feedCards");
    const block = host && host.closest(".feed-block");
    if (!host) return;
    host.innerHTML = "";
    const list = feeds || [];
    if (!list.length) {
      if (block) block.hidden = true;
      return;
    }
    if (block) block.hidden = false;
    list.forEach((feed) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "feed-card feed-card--clickable";
      const iconWrap = document.createElement("div");
      iconWrap.className = "feed-card-icon";
      const img = document.createElement("img");
      img.className = "feed-card-icon-img";
      img.src = feed.icon || FEED_ICON.velocity;
      img.alt = "";
      img.setAttribute("aria-hidden", "true");
      iconWrap.appendChild(img);
      const body = document.createElement("div");
      body.className = "feed-card-body";
      const name = document.createElement("div");
      name.className = "feed-card-name";
      const ctx = state.activeHostContext;
      const isNative =
        ctx && ctx.platformFeedId && String(feed.id || feed.collectionId) === ctx.platformFeedId;
      name.textContent = isNative && ctx.label ? `${ctx.label} prompts` : feed.name || "Feed";
      const meta = document.createElement("div");
      meta.className = "feed-card-meta";
      const n = feed.count;
      meta.textContent = isNative
        ? "On this platform"
        : n != null
          ? `${n} prompt${n === 1 ? "" : "s"}`
          : "Automatic platform feed";
      if (isNative) card.classList.add("feed-card--native");
      body.appendChild(name);
      body.appendChild(meta);
      card.appendChild(iconWrap);
      card.appendChild(body);
      card.addEventListener("click", () => openCollectionInHosted(feed));
      host.appendChild(card);
    });
  }

  function applyCollectionsSearch() {
    const q = ($("collectionSearch") && $("collectionSearch").value.trim().toLowerCase()) || "";
    const collections = state.collectionsRaw || [];
    const feeds = state.platformFeedsRaw || [];
    const filteredCollections = q
      ? collections.filter((c) => (c.name || "").toLowerCase().includes(q))
      : collections;
    let filteredFeeds = q
      ? feeds.filter(
          (f) =>
            (f.name || "").toLowerCase().includes(q) ||
            (f.tag || "").toLowerCase().includes(q)
        )
      : feeds.slice();
    const ctx = state.activeHostContext;
    if (ctx && ctx.platformFeedId && !q) {
      filteredFeeds.sort((a, b) => {
        const aId = String(a.id || a.collectionId || "");
        const bId = String(b.id || b.collectionId || "");
        if (aId === ctx.platformFeedId) return -1;
        if (bId === ctx.platformFeedId) return 1;
        return 0;
      });
    }
    renderCollectionRows(filteredCollections);
    renderFeedCards(filteredFeeds);
  }

  async function loadPlatformFeeds() {
    try {
      const res = await sendRuntime("TV_CONSUMER_LIST_ENHANCED_PROMPTS", {
        page: 1,
        limit: FEED_FETCH_SIZE,
      });
      if (!res || !res.success) {
        state.platformFeedsRaw = [];
        renderFeedCards([]);
        return;
      }
      const raw = (res.data && res.data.items) || [];
      state.platformFeedsRaw = buildPlatformFeeds(raw);
      applyCollectionsSearch();
    } catch (e) {
      state.platformFeedsRaw = [];
      renderFeedCards([]);
    }
  }

  function openCollectionInHosted(c) {
    const id = c && (c.id != null ? c.id : c.collectionId);
    if (id == null || String(id).trim() === "") return;
    const nav = hostedNav();
    if (nav && typeof nav.openCollection === "function" && state.authRef) {
      void nav.openCollection(id, state.authRef);
      return;
    }
    if (state.authRef && typeof state.authRef.openHostedPage === "function") {
      const path = `/chat?tab=prompt-book&collection=${encodeURIComponent(String(id))}`;
      void state.authRef.openHostedPage(path, "sidebar_collection_open");
    }
  }

  function renderCollectionRows(items) {
    const host = $("collectionsList");
    if (!host) return;
    host.innerHTML = "";
    if (!items.length) {
      const p = document.createElement("p");
      p.className = "view-muted view-empty-inline";
      p.textContent = "No collections yet.";
      host.appendChild(p);
      return;
    }
    items.forEach((c) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "collection-row collection-row--clickable";
      const name = document.createElement("div");
      name.className = "collection-row-name";
      name.textContent = c.name || "Untitled";
      const meta = document.createElement("div");
      meta.className = "collection-row-meta";
      const n = c.count;
      meta.textContent = n != null ? `${n} prompts` : "Collection";
      row.appendChild(name);
      row.appendChild(meta);
      row.addEventListener("click", () => openCollectionInHosted(c));
      host.appendChild(row);
    });
  }

  function appendPromptCards(items) {
    const host = $("promptBookList");
    if (!host || !items || !items.length) return;
    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "prompt-book-card";
      const top = document.createElement("div");
      top.className = "prompt-book-card-top";
      const platform = resolvePromptPlatform(item);
      const icon = document.createElement("div");
      icon.className = `prompt-book-card-icon prompt-book-card-icon--${platform.key}`;
      icon.title = platform.label;
      const iconImg = document.createElement("img");
      iconImg.className = "prompt-book-card-icon-img";
      iconImg.src = platform.iconUrl;
      iconImg.alt = "";
      iconImg.decoding = "async";
      iconImg.setAttribute("aria-hidden", "true");
      iconImg.addEventListener("error", () => {
        iconImg.src = VELOCITY_LOGO_URL;
      });
      icon.appendChild(iconImg);
      const actions = document.createElement("div");
      actions.className = "prompt-book-card-actions";
      const copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "icon-chip-btn";
      copyBtn.title = "Copy";
      copyBtn.setAttribute("aria-label", "Copy prompt");
      copyBtn.innerHTML =
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
      const chatBtn = document.createElement("button");
      chatBtn.type = "button";
      chatBtn.className = "icon-chip-btn icon-chip-btn--chat";
      chatBtn.title = "Open in chat";
      chatBtn.setAttribute("aria-label", "Open in chat");
      chatBtn.innerHTML =
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>';
      const detailApi = root.TV.consumerPromptBookDetailView;
      const copyText =
        detailApi && typeof detailApi.getComposerText === "function"
          ? detailApi.getComposerText(item)
          : item.body || item.preview || "";
      copyBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const flash = root.TV.copyButtonFeedback && root.TV.copyButtonFeedback.flash;
        const done = () => {
          if (typeof flash === "function") flash(copyBtn, { label: "Copied" });
        };
        if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
          void navigator.clipboard.writeText(copyText).then(done).catch(() => {});
        } else {
          done();
        }
      });
      chatBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const detail = root.TV.consumerPromptBookDetailView;
        if (detail && typeof detail.openInChat === "function") {
          detail.openInChat(item);
        }
      });
      actions.appendChild(copyBtn);
      actions.appendChild(chatBtn);
      top.appendChild(icon);
      top.appendChild(actions);
      const h = document.createElement("h4");
      h.className = "prompt-book-card-title";
      // The card itself styles the title as a heading, so request a clean
      // plain-text title (no literal `# ` markdown prefix).
      const formatTitle =
        root.TV.promptDisplayTitle && typeof root.TV.promptDisplayTitle.formatSavedPromptTitle === "function"
          ? root.TV.promptDisplayTitle.formatSavedPromptTitle(item, { withHash: false })
          : String(item.title || "Prompt").replace(/^#+\s*/, "");
      h.textContent = formatTitle;
      const prev = document.createElement("p");
      prev.className = "prompt-book-card-preview";
      prev.textContent = item.preview || "";
      card.appendChild(top);
      card.appendChild(h);
      card.appendChild(prev);
      card.classList.add("prompt-book-card--clickable");
      card.addEventListener("click", (e) => {
        const t = e.target;
        if (
          t &&
          typeof t.closest === "function" &&
          (t.closest(".icon-chip-btn") || t.closest(".prompt-book-card-actions"))
        ) {
          return;
        }
        if (root.TV.consumerPromptBookDetailView && root.TV.consumerPromptBookDetailView.open) {
          root.TV.consumerPromptBookDetailView.open(item);
        }
      });
      host.appendChild(card);
    });
  }

  /** @param {"loading"|"empty"|"list"} mode */
  function setMemoryPanelState(mode) {
    const empty = $("memoryEmpty");
    const host = $("memoryList");
    if (!empty || !host) return;
    const showList = mode === "list";
    empty.hidden = showList;
    host.hidden = !showList;
    if (mode === "loading" && host) host.innerHTML = "";
  }

  function memoryEditor() {
    return root.TV.consumerMemoryEditor || null;
  }

  async function reloadMemoryPreview() {
    state.memLoaded = false;
    state.memLoading = false;
    await loadMemoryPreview();
  }

  async function deleteMemoryItem(item) {
    if (!item || item.id == null) return;
    const ok = window.confirm("Delete this memory? This cannot be undone.");
    if (!ok) return;
    const status = $("memoryStatus");
    setStatus(status, "Deleting…");
    try {
      const res = await sendRuntime("TV_CONSUMER_DELETE_MEMORY", { id: item.id });
      if (!res || !res.success) {
        const msg = (res && res.error && res.error.message) || "Could not delete memory.";
        setStatus(status, msg);
        return;
      }
      setStatus(status, "");
      await reloadMemoryPreview();
    } catch (e) {
      setStatus(status, e.message || String(e));
    }
  }

  function appendMemoryCards(items) {
    const host = $("memoryList");
    if (!host || !items || !items.length) return;
    const editor = memoryEditor();
    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "memory-card";

      const top = document.createElement("div");
      top.className = "memory-card-top";

      const h = document.createElement("h4");
      h.className = "memory-card-title";
      h.textContent = item.title || "Memory";

      const actions = document.createElement("div");
      actions.className = "memory-card-actions";

      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.className = "memory-card-iconbtn";
      editBtn.title = "Edit memory";
      editBtn.setAttribute("aria-label", "Edit memory");
      editBtn.innerHTML =
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M11 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-5M16.5 3.5a2.121 2.121 0 113 3L11.707 10.707a1 1 0 01-.414.263l-3 .75a1 1 0 01-1.212-1.212l.75-3a1 1 0 01.263-.414L16.5 3.5z"/></svg>';
      editBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (editor && editor.openEdit) editor.openEdit(item);
      });

      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "memory-card-iconbtn memory-card-iconbtn--danger";
      delBtn.title = "Delete memory";
      delBtn.setAttribute("aria-label", "Delete memory");
      delBtn.innerHTML =
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>';
      delBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        void deleteMemoryItem(item);
      });

      actions.appendChild(editBtn);
      actions.appendChild(delBtn);
      top.appendChild(h);
      top.appendChild(actions);

      const p = document.createElement("p");
      p.className = "memory-card-preview";
      p.textContent = item.preview || item.text || "";

      if (item.source) {
        const tag = document.createElement("span");
        tag.className = "memory-card-source";
        tag.textContent = String(item.source).toUpperCase();
        card.appendChild(top);
        card.appendChild(p);
        card.appendChild(tag);
      } else {
        card.appendChild(top);
        card.appendChild(p);
      }

      card.addEventListener("click", () => {
        if (editor && editor.openEdit) editor.openEdit(item);
      });
      card.classList.add("memory-card--clickable");

      host.appendChild(card);
    });
  }

  async function loadCollectionsData() {
    const status = $("promptBookStatus");
    setStatus(status, "");
    const res = await sendRuntime("TV_CONSUMER_LIST_COLLECTIONS", {});
    if (!res || !res.success) {
      const msg = (res && res.error && res.error.message) || "Could not load collections.";
      setStatus($("promptBookStatus"), msg);
      state.collectionsRaw = [];
      renderCollectionRows([]);
      return;
    }
    const items = (res.data && res.data.items) || [];
    state.collectionsRaw = items;
    applyCollectionsSearch();
  }

  function resetPromptBook() {
    const host = $("promptBookList");
    if (host) host.innerHTML = "";
    state.promptLoaded = false;
    state.promptLoading = false;
    const nav = hostedNav();
    if (nav) nav.setViewMoreVisible("btnCollectionsViewMore", false);
  }

  function updateCollectionsViewMore(rawCount, hasMore) {
    const nav = hostedNav();
    if (!nav) return;
    const limit = previewLimit();
    nav.setViewMoreVisible(
      "btnCollectionsViewMore",
      rawCount > limit || Boolean(hasMore)
    );
  }

  async function loadPromptBookPreview() {
    if (state.promptLoading || state.promptLoaded) return;
    const status = $("promptBookStatus");
    state.promptLoading = true;
    setStatus(status, "Loading prompts…");
    try {
      const res = await sendRuntime("TV_CONSUMER_LIST_ENHANCED_PROMPTS", {
        page: 1,
        limit: PROMPT_FETCH_SIZE,
      });
      if (!res || !res.success) {
        const msg = (res && res.error && res.error.message) || "Prompts failed to load.";
        setStatus(status, msg);
        updateCollectionsViewMore(0, false);
        return;
      }
      const data = res.data || {};
      let raw = data.items || [];
      const ctx = state.activeHostContext;
      const HC = root.TV.hostContext;
      if (ctx && ctx.aiType && HC && typeof HC.normalizeAiType === "function") {
        const want = HC.normalizeAiType(ctx.aiType);
        const matched = raw.filter((item) => HC.normalizeAiType(item.aiType || item.ai_type) === want);
        if (matched.length) raw = matched;
      }
      const items = raw.slice(0, previewLimit());
      appendPromptCards(items);
      updateCollectionsViewMore(raw.length, data.hasMore);
      setStatus(status, items.length ? "" : "No enhanced prompts yet.");
      state.promptLoaded = true;
    } catch (e) {
      setStatus(status, e.message || String(e));
      updateCollectionsViewMore(0, false);
    } finally {
      state.promptLoading = false;
    }
  }

  function resetMemoryList() {
    const host = $("memoryList");
    if (host) host.innerHTML = "";
    state.memLoaded = false;
    state.memLoading = false;
    const nav = hostedNav();
    if (nav) nav.setViewMoreVisible("btnMemoryViewMore", false);
  }

  function updateMemoryViewMore(rawCount, hasMore) {
    const nav = hostedNav();
    if (!nav) return;
    const limit = previewLimit();
    nav.setViewMoreVisible("btnMemoryViewMore", rawCount > limit || Boolean(hasMore));
  }

  async function loadMemoryPreview() {
    if (state.memLoading || state.memLoaded) return;
    const status = $("memoryStatus");
    state.memLoading = true;
    setStatus(status, "Loading memories…");
    try {
      const res = await sendRuntime("TV_CONSUMER_LIST_MEMORIES", {
        page: 1,
        limit: MEMORY_FETCH_SIZE,
      });
      if (!res || !res.success) {
        const msg = (res && res.error && res.error.message) || "Memories could not load.";
        setStatus(status, msg);
        setMemoryPanelState("empty");
        updateMemoryViewMore(0, false);
        return;
      }
      const data = res.data || {};
      const raw = data.items || [];
      const host = $("memoryList");
      if (host) host.innerHTML = "";
      if (!raw.length) {
        setMemoryPanelState("empty");
        setStatus(status, "");
        updateMemoryViewMore(0, false);
      } else {
        setMemoryPanelState("list");
        appendMemoryCards(raw.slice(0, previewLimit()));
        setStatus(status, "");
        updateMemoryViewMore(raw.length, data.hasMore);
      }
      state.memLoaded = true;
    } catch (e) {
      setStatus(status, e.message || String(e));
      updateMemoryViewMore(0, false);
    } finally {
      state.memLoading = false;
    }
  }

  async function showCollections() {
    toggleViews("collections");
    resetPromptBook();
    state.platformFeedsRaw = [];
    renderFeedCards([]);
    await loadCollectionsData();
    void loadPlatformFeeds();
    void loadPromptBookPreview();
  }

  async function showMemory() {
    toggleViews("memory");
    resetMemoryList();
    setMemoryPanelState("loading");
    setStatus($("memoryStatus"), "");
    void loadMemoryPreview();
  }

  function showHome() {
    toggleViews("home");
  }

  function openLibraryPanel() {
    toggleViews("library");
  }

  function wireSearch() {
    const inp = $("collectionSearch");
    if (!inp || inp.dataset.bound) return;
    inp.dataset.bound = "1";
    inp.addEventListener("input", () => {
      applyCollectionsSearch();
    });
  }

  function wireHostedNav() {
    const nav = hostedNav();
    if (!nav) return;
    nav.wireViewMoreButton("btnCollectionsViewMore", "collections", state.authRef);
    nav.wireViewMoreButton("btnMemoryViewMore", "memory", state.authRef);
  }

  function wireEssenceStorageRefresh() {
    if (wireEssenceStorageRefresh._bound) return;
    wireEssenceStorageRefresh._bound = true;
    const keys = root.TV && root.TV.STORAGE_KEYS;
    const watchKey = keys && keys.ESSENCE_LAST_STORED_AT;
    if (!watchKey || !chrome.storage || !chrome.storage.onChanged) return;
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "local" || !changes[watchKey]) return;
      const memView = $("viewMemory");
      if (memView && !memView.hidden) {
        void reloadMemoryPreview();
      } else {
        state.memLoaded = false;
      }
    });
  }

  function wireButtons() {
    const btnNew = $("btnNewCollection");
    if (btnNew && !btnNew.dataset.bound) {
      btnNew.dataset.bound = "1";
      btnNew.addEventListener("click", () => {
        void (async () => {
          const name = window.prompt("Name your collection");
          if (!name || !String(name).trim()) return;
          const res = await sendRuntime("TV_CONSUMER_CREATE_COLLECTION", { name: String(name).trim() });
          if (res && res.success) {
            await loadCollectionsData();
          } else {
            const msg = (res && res.error && res.error.message) || "Could not create collection.";
            window.alert(msg);
          }
        })();
      });
    }
    const btnAdd = $("btnAddMemory");
    if (btnAdd && !btnAdd.dataset.bound) {
      btnAdd.dataset.bound = "1";
      btnAdd.addEventListener("click", () => {
        const editor = memoryEditor();
        if (editor && editor.openAdd) editor.openAdd();
      });
    }
  }

  root.TV.consumerCollectionMemoryViews = {
    init(opts) {
      const o = opts || {};
      state.authRef = o.authState || null;
      state.onRequestComposerFocus =
        typeof o.onRequestComposerFocus === "function" ? o.onRequestComposerFocus : null;
      if (root.TV.consumerPromptBookDetailView && typeof root.TV.consumerPromptBookDetailView.init === "function") {
        root.TV.consumerPromptBookDetailView.init({
          onInsertPrompt: typeof o.onInsertPrompt === "function" ? o.onInsertPrompt : null,
        });
      }
      if (root.TV.consumerMemoryEditor && typeof root.TV.consumerMemoryEditor.init === "function") {
        root.TV.consumerMemoryEditor.init({
          sendRuntime,
          onSaved() {
            void reloadMemoryPreview();
          },
        });
      }
      wireSearch();
      wireHostedNav();
      wireButtons();
      wireEssenceStorageRefresh();
    },
    showHome() {
      showHome();
    },
    showCollections() {
      void showCollections();
    },
    showMemory() {
      void showMemory();
    },
    showLibrary() {
      openLibraryPanel();
    },
    setActiveHostContext(ctx) {
      state.activeHostContext = ctx || null;
      applyCollectionsSearch();
      if (state.promptLoaded) {
        state.promptLoaded = false;
        void loadPromptBookPreview();
      }
    },
  };
})();
