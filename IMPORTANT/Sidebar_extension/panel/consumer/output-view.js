/**
 * Output view — ORIGINAL collapsible + ENHANCED card + session actions (Insert / Refine / Open In).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const $ = (id) => document.getElementById(id);

  let _session = null;
  let _onEdit = null;
  let _onRefine = null;
  let _onFeedback = null;
  let _onInsertInChat = null;
  let _onOpenIn = null;
  let _openInPlatformKey = "openai";
  let _closeOpenInMenu = null;

  const STAR_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/></svg>`;
  // Action icons (Edit / Save to Collection / Copy) — kept in lock-step with
  // the injected-button popup (`button/js/injection-modal.js`) so the side
  // panel and the in-chat improve modal show the identical glyph set.
  const EDIT_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h4.5L20 8.5 15.5 4 4 15.5V20z"/><path d="M13.5 6 18 10.5"/></svg>`;
  const BOOKMARK_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 10v6"/><path d="M9 13h6"/><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg>`;
  const COPY_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg>`;
  const CHEVRON_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>`;
  const CHEVRON_DN_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>`;
  const THUMB_UP_SVG = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/><path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>`;
  const THUMB_DN_SVG = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/><path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/></svg>`;
  const REFINE_SPARKLE_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 3 14.5 9.5 21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/></svg>`;
  const INSERT_ARROW_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5V20"/></svg>`;
  const OPEN_IN_CHEVRON_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>`;

  function closeOpenInMenu() {
    if (typeof _closeOpenInMenu === "function") {
      _closeOpenInMenu();
      _closeOpenInMenu = null;
    }
  }

  function getOpenInPlatform(key) {
    const actions = root.TV.platformPromptActions;
    if (actions && typeof actions.getPlatform === "function") {
      return actions.getPlatform(key);
    }
    return { key: key || "openai", label: "ChatGPT", icon: "" };
  }

  function getOpenInPlatformList() {
    const actions = root.TV.platformPromptActions;
    const list = (actions && actions.OPEN_IN_PLATFORMS) || [];
    // Fallback if platform actions module didn't load
    if (!list.length) {
      return [
        { key: "openai", label: "ChatGPT", icon: "https://thinkvelocity.in/next-assets/chatgpt_colored.png" },
        { key: "anthropic", label: "Claude", icon: "https://thinkvelocity.in/next-assets/claude_colored.png" },
        { key: "google", label: "Gemini", icon: "https://thinkvelocity.in/next-assets/gemini-color.png" },
      ];
    }
    return list;
  }

  function isProEnhancedChrome() {
    const shell = $("appShell");
    return Boolean(shell && shell.classList.contains("app-shell--theme-pro"));
  }

  function enhancedLabelText(isRefined) {
    if (isRefined) return "REFINED";
    return isProEnhancedChrome() ? "PRO ENHANCED" : "ENHANCED";
  }

  function copyToClipboard(text, btn) {
    const done = () => {
      const flash = root.TV.copyButtonFeedback && root.TV.copyButtonFeedback.flash;
      if (typeof flash === "function" && btn) {
        flash(btn, { label: "Copied", copiedClass: "out-icon-btn--copied" });
      }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      void navigator.clipboard.writeText(text).then(done).catch(() => {});
    } else {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.cssText = "position:fixed;left:-9999px;top:-9999px;";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        done();
      } catch (_) {}
      document.body.removeChild(ta);
    }
  }

  function getDisplayText(session) {
    return session.displayPrompt || session.enhanced || "";
  }

  // ── Annotated segments renderer ──────────────────────────────────────────

  // Solid opaque block highlights — white text on dark-toned backgrounds,
  // matching the filled-block annotation style in the design reference.
  const _SEG_COLORS = {
    indigo:  { bg: "#3730a3" },   // indigo-800  — persona_injection
    sky:     { bg: "#0369a1" },   // sky-700     — task_clarification
    amber:   { bg: "#92400e" },   // amber-800   — chain_of_thought
    emerald: { bg: "#065f46" },   // emerald-800 — output_format_spec
    rose:    { bg: "#9f1239" },   // rose-800    — constraint_definition
    violet:  { bg: "#5b21b6" },   // violet-800  — context_framing
    purple:  { bg: "#6b21a8" },   // purple-800  — few_shot_example
    red:     { bg: "#991b1b" },   // red-800     — negative_space
    orange:  { bg: "#9a3412" },   // orange-800  — target_ai_optimization
    teal:    { bg: "#115e59" },   // teal-800    — step_back_trigger
    pink:    { bg: "#9d174d" },   // pink-800    — contrastive
    cyan:    { bg: "#155e75" },   // cyan-800    — domain_specific_depth
    lime:    { bg: "#3f6212" },   // lime-800    — user_context_integration
    slate:   { bg: "#334155" },   // slate-700   — placeholder_facilitation
    blue:    { bg: "#1e40af" },   // blue-800    — tree_of_thought
    fuchsia: { bg: "#86198f" },   // fuchsia-800 — socratic_prompting
    green:   { bg: "#166534" },   // green-800   — structured_output
  };

  let _segTooltip = null;

  function _getTooltip() {
    if (_segTooltip) return _segTooltip;
    _segTooltip = document.createElement("div");
    _segTooltip.className = "out-seg-tooltip";
    _segTooltip.style.display = "none";
    document.body.appendChild(_segTooltip);
    return _segTooltip;
  }

  function _escHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function _showSegTooltip(target, label, reason) {
    const tip = _getTooltip();
    tip.innerHTML =
      `<div class="out-seg-tooltip__label">${_escHtml(label)}</div>` +
      `<div class="out-seg-tooltip__reason">${_escHtml(reason)}</div>`;
    tip.style.display = "block";

    // Position: try above first, fall back to below
    const rect = target.getBoundingClientRect();
    const vpW = window.innerWidth;
    const maxW = 260;
    let left = Math.min(rect.left, vpW - maxW - 8);
    if (left < 8) left = 8;
    tip.style.left = `${left}px`;
    tip.style.top = `${rect.top - 4}px`; // placeholder; refined in rAF

    requestAnimationFrame(() => {
      const tipH = tip.offsetHeight;
      const above = rect.top - tipH - 8;
      tip.style.top = `${above >= 4 ? above : rect.bottom + 8}px`;
    });
  }

  function _hideSegTooltip() {
    if (_segTooltip) _segTooltip.style.display = "none";
  }

  function buildAnnotatedBody(segments) {
    const container = document.createElement("div");
    container.className = "out-annotated-body";

    for (const seg of segments) {
      if (!seg || !seg.text) continue;
      const span = document.createElement("span");

      if (seg.is_original) {
        span.className = "out-seg out-seg--original";
        span.textContent = seg.text;
      } else {
        const colors = _SEG_COLORS[seg.color_key] || _SEG_COLORS.slate;
        span.className = "out-seg";
        span.style.setProperty("--seg-bg", colors.bg);
        span.title = ""; // suppress default browser tooltip
        span.addEventListener("mouseenter", () =>
          _showSegTooltip(span, seg.technique_label || seg.technique || "", seg.reason || "")
        );
        span.addEventListener("mouseleave", _hideSegTooltip);
        span.textContent = seg.text;
      }

      container.appendChild(span);
    }

    return container;
  }

  function buildOriginalCollapsible(original) {
    const short = String(original || "").replace(/\s+/g, " ").trim();
    const preview = short.length > 52 ? short.slice(0, 49) + "…" : short;

    const wrap = document.createElement("div");
    wrap.className = "out-original";

    const header = document.createElement("button");
    header.type = "button";
    header.className = "out-original-header";

    const main = document.createElement("div");
    main.className = "out-original-header-main";

    const lbl = document.createElement("span");
    lbl.className = "out-original-label";
    lbl.textContent = "ORIGINAL";

    const prev = document.createElement("span");
    prev.className = "out-original-preview";
    prev.textContent = preview;

    const chev = document.createElement("span");
    chev.className = "out-original-chevron";
    chev.setAttribute("aria-hidden", "true");
    chev.innerHTML = CHEVRON_SVG;

    main.appendChild(lbl);
    main.appendChild(prev);
    header.appendChild(main);
    header.appendChild(chev);

    const body = document.createElement("div");
    body.className = "out-original-body";
    body.textContent = short;

    let open = false;
    header.addEventListener("click", () => {
      open = !open;
      body.classList.toggle("out-original-body--open", open);
      chev.classList.toggle("out-original-chevron--open", open);
    });

    wrap.appendChild(header);
    wrap.appendChild(body);
    return wrap;
  }

  function buildEnhancedCard(session) {
    const displayText = getDisplayText(session);
    const isRefined = Boolean(session.displayPrompt && session.displayPrompt !== session.enhanced);

    const card = document.createElement("div");
    card.className = "out-enhanced-card";

    // ── Header: [label · thumbs] | [edit, copy] ──────────
    const header = document.createElement("div");
    header.className = "out-enhanced-header";

    const headerLeft = document.createElement("div");
    headerLeft.className = "out-enhanced-header-left";

    const labelWrap = document.createElement("div");
    labelWrap.className = "out-enhanced-label";
    labelWrap.innerHTML = `<span>${enhancedLabelText(isRefined)}</span><span class="out-enhanced-star">${STAR_SVG}</span>`;

    // Ambient thumbs — live in the header, not a competing action row
    const thumbsWrap = document.createElement("div");
    thumbsWrap.className = "out-thumbs out-thumbs--ambient";

    const upBtn = document.createElement("button");
    upBtn.type = "button";
    upBtn.id = "btnThumbUp";
    upBtn.className = "thumb-btn thumb-btn--ambient";
    upBtn.setAttribute("aria-label", "Helpful");
    upBtn.innerHTML = THUMB_UP_SVG;

    const downBtn = document.createElement("button");
    downBtn.type = "button";
    downBtn.id = "btnThumbDown";
    downBtn.className = "thumb-btn thumb-btn--ambient";
    downBtn.setAttribute("aria-label", "Not helpful");
    downBtn.innerHTML = THUMB_DN_SVG;

    thumbsWrap.appendChild(upBtn);
    thumbsWrap.appendChild(downBtn);
    headerLeft.appendChild(labelWrap);
    headerLeft.appendChild(thumbsWrap);

    const mkBtn = (svg, title, onClick) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "out-icon-btn";
      btn.title = title;
      btn.setAttribute("aria-label", title);
      btn.innerHTML = svg;
      btn.addEventListener("click", onClick);
      return btn;
    };

    const actions = document.createElement("div");
    actions.className = "out-enhanced-actions";

    let isEditing = false;
    let currentText = displayText;

    const editBtn = mkBtn(EDIT_SVG, "Edit", () => {
      if (!isEditing) {
        isEditing = true;
        editBtn.classList.add("is-active");
        body.innerHTML = "";
        body.classList.add("out-enhanced-body--editing");
        const textarea = document.createElement("textarea");
        textarea.className = "out-editor-textarea";
        textarea.value = currentText;
        body.appendChild(textarea);
        // Auto-size to content
        textarea.style.height = "auto";
        textarea.style.height = textarea.scrollHeight + "px";
        textarea.focus();
        textarea.addEventListener("input", () => {
          textarea.style.height = "auto";
          textarea.style.height = textarea.scrollHeight + "px";
        });
      } else {
        isEditing = false;
        editBtn.classList.remove("is-active");
        const textarea = body.querySelector("textarea");
        if (textarea) {
          currentText = textarea.value.trim();
          session.enhanced = currentText;
          session.displayPrompt = currentText;
        }
        // Clear annotations permanently
        session.annotated_segments = null;
        body.innerHTML = "";
        body.classList.remove("out-enhanced-body--editing", "out-enhanced-body--annotated", "out-enhanced-body--formatted");
        body.textContent = currentText;
      }
    });
    actions.appendChild(editBtn);

    const copyBtn = mkBtn(COPY_SVG, "Copy", () => copyToClipboard(currentText, copyBtn));
    actions.appendChild(copyBtn);

    header.appendChild(headerLeft);
    header.appendChild(actions);

    // ── Body — annotated segments when available, plain text fallback ────
    const body = document.createElement("div");
    body.className = "out-enhanced-body";

    const segs = session.annotated_segments;
    if (Array.isArray(segs) && segs.length > 0) {
      body.classList.add("out-enhanced-body--annotated");
      body.appendChild(buildAnnotatedBody(segs));
    } else {
      body.textContent = currentText;
    }

    card.appendChild(header);
    card.appendChild(body);
    return card;
  }

  function buildOpenInWrap(session) {
    const wrap = document.createElement("div");
    wrap.className = "out-openin-wrap";

    const platforms = getOpenInPlatformList();

    // Hover-driven single button: the button itself doesn't open any platform.
    // Hover (or click for touch/keyboard) reveals the drop-up menu; selecting
    // a platform fires the open+inject flow for that specific platform.
    const openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.id = "btnOutputOpenIn";
    openBtn.className = "out-session-btn out-session-btn--open";
    openBtn.setAttribute("aria-haspopup", "menu");
    openBtn.setAttribute("aria-expanded", "false");
    openBtn.title = "Open prompt in a chat platform";
    openBtn.innerHTML =
      `<span>Open In</span>` +
      `<span class="out-openin-chevron" aria-hidden="true">${OPEN_IN_CHEVRON_SVG}</span>`;

    const menu = document.createElement("div");
    menu.className = "out-openin-menu";
    menu.hidden = true;
    menu.setAttribute("role", "menu");

    let hoverCloseTimer = null;
    let docClickHandler = null;

    function detachDocClick() {
      if (docClickHandler) {
        document.removeEventListener("click", docClickHandler, true);
        docClickHandler = null;
      }
    }

    function setMenuOpen(open) {
      menu.hidden = !open;
      wrap.classList.toggle("out-openin-wrap--open", open);
      openBtn.setAttribute("aria-expanded", open ? "true" : "false");
      if (!open) {
        detachDocClick();
        if (_closeOpenInMenu === closeMenu) _closeOpenInMenu = null;
      }
    }

    function closeMenu() {
      if (hoverCloseTimer) {
        clearTimeout(hoverCloseTimer);
        hoverCloseTimer = null;
      }
      setMenuOpen(false);
    }

    function openMenu() {
      if (hoverCloseTimer) {
        clearTimeout(hoverCloseTimer);
        hoverCloseTimer = null;
      }
      closeOpenInMenu();
      setMenuOpen(true);
      _closeOpenInMenu = closeMenu;
    }

    function fireOpen(platformKey) {
      const text = getDisplayText(session);
      if (!text) {
        console.warn("[output-view] Open In: no display text available");
        return;
      }
      if (typeof _onOpenIn === "function") {
        _onOpenIn(text, platformKey);
        return;
      }
      // Fallback path — callback wasn't registered yet.
      console.warn("[output-view] Open In: callback not registered, using direct message");
      const auth = root && root.TV && root.TV.sidebarAuthState;
      const isPro = Boolean(
        auth && typeof auth.getSnapshot === "function" && auth.getSnapshot().isProUser
      );
      chrome.runtime.sendMessage({
        action: "TV_CONSUMER_OPEN_IN_PLATFORM",
        payload: { prompt: text, platformKey, isPro },
        requestId: `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      });
    }

    wrap.addEventListener("mouseenter", openMenu);
    wrap.addEventListener("mouseleave", () => {
      if (hoverCloseTimer) clearTimeout(hoverCloseTimer);
      // Small grace window so users can cross the visual gap between the
      // button and the drop-up menu without it snapping shut.
      hoverCloseTimer = setTimeout(closeMenu, 160);
    });

    // Click on the trigger is for touch + keyboard users who can't hover.
    openBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (menu.hidden) {
        openMenu();
        docClickHandler = (ev) => {
          if (!wrap.contains(ev.target)) closeMenu();
        };
        requestAnimationFrame(() =>
          document.addEventListener("click", docClickHandler, true)
        );
      } else {
        closeMenu();
      }
    });

    platforms.forEach((p) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "out-openin-item";
      item.setAttribute("role", "menuitem");
      item.title = `Open in ${p.label} and insert this prompt`;
      item.innerHTML =
        `<img class="out-openin-item-icon" src="${p.icon}" alt="" width="18" height="18" />` +
        `<span>${p.label}</span>`;
      item.addEventListener("click", (e) => {
        e.stopPropagation();
        _openInPlatformKey = p.key;
        closeMenu();
        fireOpen(p.key);
      });
      menu.appendChild(item);
    });

    wrap.appendChild(openBtn);
    wrap.appendChild(menu);
    return wrap;
  }

  function buildSessionActionsBar(session) {
    const bar = document.createElement("div");
    bar.className = "out-session-actions";
    bar.id = "outputSessionActions";

    // ── Compound "Use Prompt" button ──────────────────────
    // Left zone: inserts into current page chat
    // Right zone: platform picker drop-up (Open In)
    const compoundWrap = document.createElement("div");
    compoundWrap.className = "out-use-wrap";

    const compound = document.createElement("div");
    compound.className = "out-use-compound";

    const mainBtn = document.createElement("button");
    mainBtn.type = "button";
    mainBtn.id = "btnOutputInsertChat";
    mainBtn.className = "out-use-main";
    mainBtn.setAttribute("aria-label", "Insert into chat");
    mainBtn.innerHTML = `${INSERT_ARROW_SVG}<span>Use Prompt</span>`;
    mainBtn.addEventListener("click", () => {
      if (_onInsertInChat) _onInsertInChat(getDisplayText(session));
    });

    const divider = document.createElement("span");
    divider.className = "out-use-divider";
    divider.setAttribute("aria-hidden", "true");

    const pickerBtn = document.createElement("button");
    pickerBtn.type = "button";
    pickerBtn.className = "out-use-platform";
    pickerBtn.setAttribute("aria-haspopup", "menu");
    pickerBtn.setAttribute("aria-expanded", "false");
    pickerBtn.title = "Open in another platform";
    pickerBtn.innerHTML = OPEN_IN_CHEVRON_SVG;

    compound.appendChild(mainBtn);
    compound.appendChild(divider);
    compound.appendChild(pickerBtn);

    // Platform drop-up menu
    const platforms = getOpenInPlatformList();
    const menu = document.createElement("div");
    menu.className = "out-use-menu";
    menu.hidden = true;
    menu.setAttribute("role", "menu");

    let hoverCloseTimer = null;
    let docClickHandler = null;

    function detachDocClick() {
      if (docClickHandler) {
        document.removeEventListener("click", docClickHandler, true);
        docClickHandler = null;
      }
    }

    function setMenuOpen(open) {
      menu.hidden = !open;
      compoundWrap.classList.toggle("out-use-wrap--open", open);
      pickerBtn.setAttribute("aria-expanded", open ? "true" : "false");
      if (!open) {
        detachDocClick();
        if (_closeOpenInMenu === closeMenu) _closeOpenInMenu = null;
      }
    }

    function closeMenu() {
      if (hoverCloseTimer) { clearTimeout(hoverCloseTimer); hoverCloseTimer = null; }
      setMenuOpen(false);
    }

    function openMenu() {
      if (hoverCloseTimer) { clearTimeout(hoverCloseTimer); hoverCloseTimer = null; }
      closeOpenInMenu();
      setMenuOpen(true);
      _closeOpenInMenu = closeMenu;
    }

    pickerBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (menu.hidden) {
        openMenu();
        docClickHandler = (ev) => { if (!compoundWrap.contains(ev.target)) closeMenu(); };
        requestAnimationFrame(() => document.addEventListener("click", docClickHandler, true));
      } else {
        closeMenu();
      }
    });

    platforms.forEach((p) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "out-use-menu-item";
      item.setAttribute("role", "menuitem");
      item.title = `Open in ${p.label}`;
      item.innerHTML =
        `<img class="out-openin-item-icon" src="${p.icon}" alt="" width="16" height="16" />` +
        `<span>${p.label}</span>`;
      item.addEventListener("click", (e) => {
        e.stopPropagation();
        closeMenu();
        if (typeof _onOpenIn === "function") _onOpenIn(getDisplayText(session), p.key);
      });
      menu.appendChild(item);
    });

    compoundWrap.appendChild(compound);
    compoundWrap.appendChild(menu);

    // ── Refine: demoted to a ghost text link ──────────────
    const refineLink = document.createElement("button");
    refineLink.type = "button";
    refineLink.id = "btnOutputRefine";
    refineLink.className = "out-refine-link";
    refineLink.setAttribute("aria-label", "Improve prompt");
    refineLink.innerHTML = `${REFINE_SPARKLE_SVG}<span>Refine this prompt</span>`;
    refineLink.addEventListener("click", () => {
      if (_onRefine) _onRefine(getDisplayText(session));
    });

    bar.appendChild(compoundWrap);
    bar.appendChild(refineLink);
    return bar;
  }

  function pulseThumb(btn, activeClass) {
    if (!btn) return;
    btn.classList.remove("thumb-btn--pop");
    void btn.offsetWidth;
    btn.classList.add("thumb-btn--pop", activeClass);
    window.setTimeout(() => btn.classList.remove("thumb-btn--pop"), 520);
  }

  function wireActionRow(session) {
    const upBtn = $("btnThumbUp");
    const downBtn = $("btnThumbDown");

    if (upBtn) {
      upBtn.onclick = () => {
        pulseThumb(upBtn, "thumb-btn--active-up");
        downBtn && downBtn.classList.remove("thumb-btn--active-down");
        if (_onFeedback) _onFeedback({ feedback: "like", promptId: session.promptId });
      };
    }
    if (downBtn) {
      downBtn.onclick = () => {
        pulseThumb(downBtn, "thumb-btn--active-down");
        upBtn && upBtn.classList.remove("thumb-btn--active-up");
        if (_onFeedback) _onFeedback({ feedback: "dislike", promptId: session.promptId });
      };
    }
  }

  function show(session, opts = { forceVisible: true }) {
    _session = session;
    closeOpenInMenu();
    const view = $("viewOutput");
    if (!view) return;

    const container = $("outputCards");
    if (container) {
      container.innerHTML = "";
      container.appendChild(buildOriginalCollapsible(session.original || ""));
      container.appendChild(buildEnhancedCard(session));
    }

    wireActionRow(session);
    if (opts.forceVisible) {
      view.classList.add("view-surface--active");
      view.hidden = false;
    }
  }

  function hide() {
    const view = $("viewOutput");
    if (view) {
      view.classList.remove("view-surface--active");
      view.hidden = true;
    }
  }

  function refresh() {
    if (_session) show(_session, { forceVisible: false });
  }

  function onEdit(cb) {
    _onEdit = cb;
  }
  function onRefine(cb) {
    _onRefine = cb;
  }
  function onFeedback(cb) {
    _onFeedback = cb;
  }
  function onInsertInChat(cb) {
    _onInsertInChat = cb;
  }
  function onOpenIn(cb) {
    _onOpenIn = cb;
  }

  root.TV.outputView = { show, hide, refresh, onEdit, onRefine, onFeedback, onInsertInChat, onOpenIn };
})();
