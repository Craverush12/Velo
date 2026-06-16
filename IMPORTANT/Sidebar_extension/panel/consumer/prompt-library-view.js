/**
 * In-panel prompt library from packaged `data/prompt-library.json`.
 * Search + category filters; lazy appends cards via IntersectionObserver.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const $ = (id) => document.getElementById(id);

  function previewLimit() {
    const nav = root.TV.sidebarHostedNav;
    return nav && nav.PREVIEW_LIMIT != null ? nav.PREVIEW_LIMIT : 20;
  }

  function hostedNav() {
    return root.TV.sidebarHostedNav || null;
  }

  const state = {
    all: [],
    filtered: [],
    activeCategory: "All",
    loadPromise: null,
    authRef: null,
    authUnsub: null,
    onInsertPrompt: null,
    onOpenInPlatform: null,
    searchBound: false,
    /** @type {object|null} */
    detailPrompt: null,
    detailShell: null,
    onDocKeydown: null,
  };

  function getOpenInPlatforms() {
    const actions = root.TV.platformPromptActions;
    return (actions && actions.OPEN_IN_PLATFORMS) || [];
  }

  function escapeAttr(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  const LOCK_ICON_SVG =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';

  function getAccess() {
    const snap =
      state.authRef && typeof state.authRef.getSnapshot === "function"
        ? state.authRef.getSnapshot()
        : {};
    return {
      isLoggedIn: Boolean(snap.isLoggedIn),
      isProUser: Boolean(snap.isProUser),
    };
  }

  function canAccessPrompt(p) {
    const acc = root.TV.subscriptionAccess;
    const { isProUser } = getAccess();
    if (acc && typeof acc.canAccessLibraryPrompt === "function") {
      return acc.canAccessLibraryPrompt(p, isProUser);
    }
    return !p || !p.isProOnly || isProUser;
  }

  function isLockedPro(p) {
    return Boolean(p && p.isProOnly && !canAccessPrompt(p));
  }

  function openPaywallAction() {
    const { isLoggedIn } = getAccess();
    if (!isLoggedIn && state.authRef && typeof state.authRef.openLoginTab === "function") {
      void state.authRef.openLoginTab();
      return;
    }
    if (state.authRef && typeof state.authRef.openHostedPage === "function") {
      void state.authRef.openHostedPage("/pricing", "sidebar_library_upgrade");
    }
  }

  function setStatus(el, text) {
    if (el) el.textContent = text || "";
  }

  function updateViewMoreButton() {
    const nav = hostedNav();
    if (!nav || typeof nav.setViewMoreVisible !== "function") return;
    nav.setViewMoreVisible("btnLibraryViewMore", state.filtered.length > previewLimit());
  }

  function uniqueCategories() {
    const s = new Set();
    state.all.forEach((p) => {
      if (p && p.category) s.add(String(p.category));
    });
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }

  function renderFilterPills() {
    const host = $("libraryFilterRow");
    if (!host) return;
    host.innerHTML = "";
    const preferred = ["All", "Coding", "Marketing", "Creative", "Content"];
    const cats = uniqueCategories();
    const ordered = [];
    preferred.forEach((p) => {
      if (p === "All") {
        if (!ordered.includes("All")) ordered.push("All");
      } else if (cats.includes(p)) {
        ordered.push(p);
      }
    });
    cats.forEach((c) => {
      if (!ordered.includes(c)) ordered.push(c);
    });
    if (!ordered.includes("All")) ordered.unshift("All");

    ordered.forEach((label) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "library-filter-pill";
      b.textContent = label;
      b.dataset.category = label;
      b.setAttribute("role", "tab");
      b.setAttribute("aria-selected", label === state.activeCategory ? "true" : "false");
      if (label === state.activeCategory) b.classList.add("library-filter-pill--active");
      b.addEventListener("click", () => {
        state.activeCategory = label;
        host.querySelectorAll(".library-filter-pill").forEach((x) => {
          const on = x.dataset.category === state.activeCategory;
          x.classList.toggle("library-filter-pill--active", on);
          x.setAttribute("aria-selected", on ? "true" : "false");
        });
        refilter();
      });
      host.appendChild(b);
    });
  }

  function refilter() {
    const inp = $("librarySearch");
    const q = (inp && inp.value ? inp.value : "").trim().toLowerCase();
    state.filtered = state.all.filter((p) => {
      if (state.activeCategory !== "All" && String(p.category || "") !== state.activeCategory) {
        return false;
      }
      if (!q) return true;
      const t = (p.title || "").toLowerCase();
      const sp = (p.short_prompt || p.prompt || "").toLowerCase();
      return t.includes(q) || sp.includes(q);
    });
    const list = $("libraryList");
    if (list) list.innerHTML = "";
    state.filtered.slice(0, previewLimit()).forEach((p) => renderOneCard(p));
    updateViewMoreButton();
    setStatus(
      $("libraryStatus"),
      state.filtered.length ? "" : state.all.length ? "No prompts match filters." : ""
    );
  }

  function getUsableText(p) {
    const acc = root.TV.subscriptionAccess;
    const { isProUser } = getAccess();
    if (acc && typeof acc.getUsablePromptText === "function") {
      return acc.getUsablePromptText(p, isProUser);
    }
    if (isLockedPro(p)) return "";
    return String((p && (p.prompt || p.short_prompt)) || "").trim();
  }

  function insertPrompt(p) {
    if (isLockedPro(p) || !canAccessPrompt(p)) {
      openPaywallAction();
      return;
    }
    const text = getUsableText(p);
    if (!text) return;
    if (state.onInsertPrompt) {
      state.onInsertPrompt(text, p);
    }
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /** Light structure for long prompt text (markdown-ish # lines). */
  function formatPromptBodyHtml(raw) {
    const md = root.TV.promptMarkdown;
    if (md && typeof md.formatBlock === "function") {
      return md.formatBlock(raw);
    }
    const lines = String(raw || "").split("\n");
    const out = [];
    lines.forEach((line) => {
      const t = line.replace(/\s+$/, "");
      if (!t.trim()) {
        out.push('<p class="library-prompt-detail__md-sp">&nbsp;</p>');
        return;
      }
      if (/^#\s+/.test(t.trim())) {
        out.push(`<p class="library-prompt-detail__md-h">${escapeHtml(t.trim())}</p>`);
      } else {
        out.push(`<p class="library-prompt-detail__md-p">${escapeHtml(t)}</p>`);
      }
    });
    return out.join("");
  }

  function truncateTitle(s, max) {
    const t = String(s || "").trim();
    if (t.length <= max) return t;
    return `${t.slice(0, Math.max(0, max - 1))}…`;
  }

  function closePromptDetail() {
    if (!state.detailShell) return;
    state.detailShell.hidden = true;
    state.detailShell.setAttribute("aria-hidden", "true");
    state.detailPrompt = null;
    const menu = $("libraryDetailOpenMenu");
    if (menu) menu.hidden = true;
    if (state.onDocKeydown) {
      document.removeEventListener("keydown", state.onDocKeydown);
      state.onDocKeydown = null;
    }
  }

  function copyTextToClipboard(text, okMsg) {
    const t = String(text || "");
    if (!t || (state.detailPrompt && isLockedPro(state.detailPrompt))) return;
    const done = () => {
      const st = $("libraryDetailStatus");
      if (st) {
        st.textContent = okMsg || "Copied.";
        setTimeout(() => {
          if (st) st.textContent = "";
        }, 2000);
      }
    };
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      void navigator.clipboard.writeText(t).then(done).catch(() => {
        try {
          const ta = document.createElement("textarea");
          ta.value = t;
          ta.style.position = "fixed";
          ta.style.left = "-9999px";
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          ta.remove();
          done();
        } catch (_) {}
      });
    }
  }

  function ensureDetailShell() {
    if (state.detailShell) return;
    const rootEl = document.createElement("div");
    rootEl.id = "libraryPromptDetail";
    rootEl.className = "library-prompt-detail";
    rootEl.hidden = true;
    rootEl.setAttribute("aria-hidden", "true");
    rootEl.innerHTML = `
      <div class="library-prompt-detail__backdrop" data-library-detail-dismiss="1" aria-hidden="true"></div>
      <div class="library-prompt-detail__sheet" role="dialog" aria-modal="true" aria-labelledby="libraryDetailTitle">
        <header class="library-prompt-detail__header">
          <button type="button" class="library-prompt-detail__iconbtn" id="libraryDetailBack" aria-label="Back">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          </button>
          <h2 class="library-prompt-detail__header-title" id="libraryDetailHeaderTitle"></h2>
          <button type="button" class="library-prompt-detail__iconbtn" id="libraryDetailCopy" aria-label="Copy prompt">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </svg>
          </button>
        </header>
        <p class="library-prompt-detail__status" id="libraryDetailStatus" aria-live="polite"></p>
        <div class="library-prompt-detail__scroll">
          <div class="library-prompt-detail__hero" id="libraryDetailHero"></div>
          <h1 class="library-prompt-detail__title" id="libraryDetailTitle"></h1>
          <p class="library-prompt-detail__subtitle" id="libraryDetailSubtitle"></p>
          <div class="library-prompt-detail__tags" id="libraryDetailTags"></div>
          <p class="library-prompt-detail__pro-kicker" id="libraryDetailProKicker" hidden>Pro prompt</p>
          <div class="library-prompt-detail__content-wrap" id="libraryDetailContentWrap">
            <div class="library-prompt-detail__content" id="libraryDetailContent"></div>
            <div class="library-prompt-detail__paywall" id="libraryDetailPaywall" hidden>
              <div class="library-prompt-detail__paywall-card">
                <span class="library-prompt-detail__paywall-badge">Pro access</span>
                <p class="library-prompt-detail__paywall-text" id="libraryDetailPaywallText"></p>
                <button type="button" class="library-prompt-detail__paywall-cta" id="libraryDetailPaywallCta"></button>
              </div>
            </div>
          </div>
        </div>
        <footer class="library-prompt-detail__footer">
          <div class="library-prompt-detail__open-wrap">
            <button type="button" class="library-prompt-detail__open-btn" id="libraryDetailOpenBtn" aria-expanded="false" aria-haspopup="true" aria-controls="libraryDetailOpenMenu">
              <span>Open in</span><span class="library-prompt-detail__open-chev" aria-hidden="true">▾</span>
            </button>
            <div class="library-prompt-detail__open-menu" id="libraryDetailOpenMenu" role="menu" hidden></div>
          </div>
          <button type="button" class="library-prompt-detail__insert" id="libraryDetailInsert">Insert in Chat</button>
        </footer>
      </div>
    `;
    document.body.appendChild(rootEl);
    state.detailShell = rootEl;

    const back = $("libraryDetailBack");
    if (back) back.addEventListener("click", () => closePromptDetail());
    const backdrop = rootEl.querySelector("[data-library-detail-dismiss]");
    if (backdrop) backdrop.addEventListener("click", () => closePromptDetail());
    const paywallCta = $("libraryDetailPaywallCta");
    if (paywallCta) {
      paywallCta.addEventListener("click", () => openPaywallAction());
    }
    const copyBtn = $("libraryDetailCopy");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        if (!state.detailPrompt) return;
        if (isLockedPro(state.detailPrompt)) {
          openPaywallAction();
          return;
        }
        const full = String(state.detailPrompt.prompt || state.detailPrompt.short_prompt || "").trim();
        copyTextToClipboard(full, "Prompt copied.");
      });
    }
    const insBtn = $("libraryDetailInsert");
    if (insBtn) {
      insBtn.addEventListener("click", () => {
        if (!state.detailPrompt) return;
        if (isLockedPro(state.detailPrompt) || !canAccessPrompt(state.detailPrompt)) {
          openPaywallAction();
          return;
        }
        insertPrompt(state.detailPrompt);
        closePromptDetail();
      });
    }

    const openBtn = $("libraryDetailOpenBtn");
    const openMenu = $("libraryDetailOpenMenu");
    if (!openBtn || !openMenu) return;

    renderPlatformMenuItems(openMenu, openBtn);

    openBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const on = openMenu.hidden;
      openMenu.hidden = !on;
      openBtn.setAttribute("aria-expanded", on ? "true" : "false");
    });
    document.addEventListener("click", (e) => {
      if (!openMenu || openMenu.hidden) return;
      const t = e.target;
      if (openBtn.contains(t) || openMenu.contains(t)) return;
      openMenu.hidden = true;
      openBtn.setAttribute("aria-expanded", "false");
    });
  }

  function renderPlatformMenuItems(openMenu, openBtn) {
    if (!openMenu) return;
    openMenu.innerHTML = "";
    const platforms = getOpenInPlatforms();
    if (!platforms.length) {
      const empty = document.createElement("p");
      empty.className = "library-prompt-detail__menu-empty";
      empty.textContent = "No platforms available.";
      openMenu.appendChild(empty);
      return;
    }
    platforms.forEach((p) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "library-prompt-detail__menu-item library-prompt-detail__menu-item--platform";
      item.setAttribute("role", "menuitem");
      item.setAttribute("data-platform-key", p.key);
      const iconHtml = p.icon
        ? `<img class="library-prompt-detail__menu-item-icon" src="${escapeAttr(p.icon)}" alt="" width="18" height="18" />`
        : '<span class="library-prompt-detail__menu-item-icon" aria-hidden="true"></span>';
      item.innerHTML = `${iconHtml}<span>${escapeAttr(p.label)}</span>`;
      item.addEventListener("click", (e) => {
        e.stopPropagation();
        handleOpenInPlatformClick(p.key);
        if (openMenu) openMenu.hidden = true;
        if (openBtn) openBtn.setAttribute("aria-expanded", "false");
      });
      openMenu.appendChild(item);
    });
  }

  function handleOpenInPlatformClick(platformKey) {
    if (!state.detailPrompt) return;
    if (isLockedPro(state.detailPrompt) || !canAccessPrompt(state.detailPrompt)) {
      openPaywallAction();
      return;
    }
    const text = String(
      state.detailPrompt.prompt || state.detailPrompt.short_prompt || ""
    ).trim();
    if (!text) return;
    if (typeof state.onOpenInPlatform === "function") {
      state.onOpenInPlatform(text, platformKey, state.detailPrompt);
    } else {
      // Fallback: send message directly if callback not registered
      console.warn("[prompt-library-view] Open In: callback not registered, using direct message");
      const { isProUser } = getAccess();
      chrome.runtime.sendMessage({
        action: "TV_CONSUMER_OPEN_IN_PLATFORM",
        payload: {
          prompt: text,
          platformKey: platformKey || "openai",
          isPro: Boolean(isProUser),
        },
        requestId: `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      });
    }
    closePromptDetail();
  }

  function openPromptDetail(p) {
    ensureDetailShell();
    if (state.onDocKeydown) {
      document.removeEventListener("keydown", state.onDocKeydown);
      state.onDocKeydown = null;
    }
    const { isProUser, isLoggedIn } = getAccess();
    const acc = root.TV.subscriptionAccess;
    const safe =
      acc && typeof acc.sanitizePromptForViewer === "function"
        ? acc.sanitizePromptForViewer(p, isProUser)
        : p;
    state.detailPrompt = safe;
    const shell = state.detailShell;
    const title = p.title || "Untitled";
    const isPro = Boolean(p.isProOnly);
    const locked = isLockedPro(p);
    const headerEl = $("libraryDetailHeaderTitle");
    const titleEl = $("libraryDetailTitle");
    const subEl = $("libraryDetailSubtitle");
    const tagsEl = $("libraryDetailTags");
    const contentEl = $("libraryDetailContent");
    const contentWrap = $("libraryDetailContentWrap");
    const paywall = $("libraryDetailPaywall");
    const paywallText = $("libraryDetailPaywallText");
    const paywallCta = $("libraryDetailPaywallCta");
    const proKicker = $("libraryDetailProKicker");
    const hero = $("libraryDetailHero");
    const insBtn = $("libraryDetailInsert");
    const copyBtn = $("libraryDetailCopy");
    const st = $("libraryDetailStatus");
    if (st) st.textContent = "";

    const openMenuReset = $("libraryDetailOpenMenu");
    const openBtnReset = $("libraryDetailOpenBtn");
    if (openMenuReset) openMenuReset.hidden = true;
    if (openBtnReset) openBtnReset.setAttribute("aria-expanded", "false");

    if (shell) {
      shell.classList.toggle("library-prompt-detail--pro", isPro);
      shell.classList.toggle("library-prompt-detail--locked", locked);
    }
    if (headerEl) headerEl.textContent = truncateTitle(title, 22);
    if (titleEl) titleEl.textContent = title;
    if (subEl) {
      subEl.textContent = locked
        ? "Premium library prompt. Upgrade to Pro to view and use in chat."
        : String(p.short_prompt || "")
            .replace(/\s+/g, " ")
            .trim();
      subEl.classList.toggle("library-prompt-detail__subtitle--pro", isPro);
    }
    if (proKicker) proKicker.hidden = !isPro;

    if (tagsEl) {
      tagsEl.innerHTML = "";
      const cat = (p.category && String(p.category).toUpperCase()) || "";
      if (cat) {
        const span = document.createElement("span");
        span.className = `library-prompt-detail__tag${isPro ? " library-prompt-detail__tag--pro" : ""}`;
        span.textContent = cat;
        tagsEl.appendChild(span);
      }
    }

    if (hero) {
      hero.innerHTML = "";
      hero.classList.toggle("library-prompt-detail__hero--pro", isPro);
      hero.classList.remove("library-prompt-detail__hero--fallback");
      if (p.cover_src) {
        const img = document.createElement("img");
        img.alt = "";
        img.loading = "eager";
        img.decoding = "async";
        img.referrerPolicy = "no-referrer";
        img.src = p.cover_src;
        img.addEventListener("error", () => {
          img.remove();
          hero.classList.add("library-prompt-detail__hero--fallback");
          hero.innerHTML =
            '<span class="library-prompt-detail__hero-ph" aria-hidden="true"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg></span>';
        });
        hero.appendChild(img);
      } else {
        hero.classList.add("library-prompt-detail__hero--fallback");
        hero.innerHTML =
          '<span class="library-prompt-detail__hero-ph" aria-hidden="true"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg></span>';
      }
    }

    const bodyText = locked ? "" : getUsableText(p);
    const showPaywall = locked || (!isLoggedIn && Boolean(getUsableText(p) || p.isProOnly));
    if (contentEl) {
      contentEl.innerHTML = showPaywall
        ? '<p class="library-prompt-detail__md-p">Full prompt hidden until you have access.</p>'
        : formatPromptBodyHtml(bodyText);
      contentEl.classList.toggle("library-prompt-detail__content--blurred", showPaywall);
    }
    if (contentWrap) {
      contentWrap.classList.toggle("library-prompt-detail__content-wrap--locked", showPaywall);
    }
    if (paywall) paywall.hidden = !showPaywall;
    if (paywallText) {
      paywallText.textContent = !isLoggedIn
        ? "Create an account to continue and access premium library prompts."
        : "Unlock this premium prompt and all Pro library content.";
    }
    if (paywallCta) {
      paywallCta.textContent = !isLoggedIn ? "Sign up to view full prompt" : "Upgrade to Pro to unlock";
    }
    if (insBtn) {
      insBtn.textContent = locked ? "Upgrade to unlock" : "Insert in Chat";
      insBtn.classList.toggle("library-prompt-detail__insert--pro", isPro && !locked);
      insBtn.classList.toggle("library-prompt-detail__insert--locked", locked);
    }
    if (copyBtn) copyBtn.disabled = showPaywall;
    const openWrap = $("libraryDetailOpenBtn") && $("libraryDetailOpenBtn").closest(".library-prompt-detail__open-wrap");
    if (openWrap) openWrap.hidden = showPaywall;

    shell.hidden = false;
    shell.setAttribute("aria-hidden", "false");

    state.onDocKeydown = (ev) => {
      if (ev.key === "Escape") {
        ev.preventDefault();
        closePromptDetail();
      }
    };
    document.addEventListener("keydown", state.onDocKeydown);

    const ins = $("libraryDetailInsert");
    if (ins && !locked) {
      setTimeout(() => ins.focus(), 50);
    }
  }

  function renderOneCard(p) {
    const list = $("libraryList");
    if (!list) return;
    const isPro = Boolean(p.isProOnly);
    const locked = isLockedPro(p);
    const card = document.createElement("article");
    card.className = "library-card";
    if (isPro) card.classList.add("library-card--pro");
    if (locked) card.classList.add("library-card--locked");

    const thumb = document.createElement("div");
    thumb.className = "library-card-thumb";
    if (p.cover_src) {
      const img = document.createElement("img");
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      img.referrerPolicy = "no-referrer";
      img.src = p.cover_src;
      img.addEventListener("error", () => {
        img.remove();
        thumb.classList.add("library-card-thumb--fallback");
      });
      thumb.appendChild(img);
    } else {
      thumb.classList.add("library-card-thumb--fallback");
    }

    const top = document.createElement("div");
    top.className = "library-card-top";

    const body = document.createElement("div");
    body.className = "library-card-body";
    const title = document.createElement("div");
    title.className = "library-card-title";
    title.textContent = p.title || "Untitled";
    const desc = document.createElement("div");
    desc.className = "library-card-desc";
    desc.textContent = locked
      ? "Upgrade to Pro to view and use in chat."
      : String(p.short_prompt || "")
          .replace(/\s+/g, " ")
          .trim();
    body.appendChild(title);
    body.appendChild(desc);

    const openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.className = `library-card-open${isPro ? " library-card-open--pro" : ""}${locked ? " library-card-open--locked" : ""}`;
    openBtn.title = locked ? "Upgrade to Pro" : "Insert into composer";
    openBtn.setAttribute(
      "aria-label",
      locked ? "Upgrade to unlock prompt" : "Insert prompt into composer"
    );
    openBtn.innerHTML = locked
      ? LOCK_ICON_SVG
      : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>';
    openBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      insertPrompt(p);
    });

    top.appendChild(body);
    top.appendChild(openBtn);

    card.classList.add("library-card--clickable");
    card.addEventListener("click", (e) => {
      const t = e.target;
      if (t && typeof t.closest === "function" && t.closest(".library-card-open")) return;
      openPromptDetail(p);
    });

    card.appendChild(thumb);
    card.appendChild(top);
    list.appendChild(card);
  }

  function wireSearch() {
    const inp = $("librarySearch");
    if (!inp || state.searchBound) return;
    state.searchBound = true;
    inp.addEventListener("input", () => {
      refilter();
    });
  }

  root.TV.consumerPromptLibraryView = {
    init(opts) {
      const o = opts || {};
      state.onInsertPrompt = typeof o.onInsertPrompt === "function" ? o.onInsertPrompt : null;
      state.onOpenInPlatform = typeof o.onOpenInPlatform === "function" ? o.onOpenInPlatform : null;
      state.authRef = o.authState || null;
      const nav = hostedNav();
      if (nav && typeof nav.wireViewMoreButton === "function") {
        nav.wireViewMoreButton("btnLibraryViewMore", "library", state.authRef);
      }
      wireSearch();
      if (state.authUnsub) state.authUnsub();
      if (state.authRef && typeof state.authRef.subscribe === "function") {
        state.authUnsub = state.authRef.subscribe(() => {
          if ($("viewPromptLibrary") && !$("viewPromptLibrary").hidden) {
            refilter();
            if (state.detailPrompt && !state.detailShell?.hidden) {
              openPromptDetail(state.detailPrompt);
            }
          }
        });
      }
    },

    async onShown() {
      setStatus($("libraryStatus"), "Loading…");
      try {
        if (!state.loadPromise) {
          state.loadPromise = (async () => {
            const url = chrome.runtime.getURL("data/prompt-library.json");
            const res = await fetch(url);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            state.all = Array.isArray(data.prompts) ? data.prompts : [];
          })();
        }
        await state.loadPromise;
        state.activeCategory = "All";
        renderFilterPills();
        refilter();
        setStatus($("libraryStatus"), "");
      } catch (e) {
        setStatus($("libraryStatus"), e.message || "Could not load prompt library.");
      }
    },

    onHidden() {
      closePromptDetail();
    },

    closeDetail() {
      closePromptDetail();
    },
  };
})();
