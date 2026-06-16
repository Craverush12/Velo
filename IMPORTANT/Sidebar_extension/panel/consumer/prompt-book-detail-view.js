/**
 * Prompt Book detail sheet (enhanced prompts) — popup like library + Vel-Next PromptGrid viewer.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const $ = (id) => document.getElementById(id);

  const state = {
    detailItem: null,
    detailShell: null,
    onDocKeydown: null,
    onInsertPrompt: null,
  };

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatBodyHtml(raw) {
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

  function copyText(text, okMsg, btn) {
    const t = String(text || "").trim();
    if (!t) return;
    const done = () => {
      const flash = root.TV.copyButtonFeedback && root.TV.copyButtonFeedback.flash;
      if (typeof flash === "function" && btn) {
        flash(btn, { label: "Copied", copiedClass: "library-prompt-detail__iconbtn--copied" });
      }
      const st = $("promptBookDetailStatus");
      if (st) {
        st.textContent = okMsg || "Copied.";
        setTimeout(() => {
          if (st) st.textContent = "";
        }, 2000);
      }
    };
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      void navigator.clipboard.writeText(t).then(done).catch(() => {});
    } else {
      done();
    }
  }

  function closeDetail() {
    if (!state.detailShell) return;
    state.detailShell.hidden = true;
    state.detailShell.setAttribute("aria-hidden", "true");
    state.detailItem = null;
    if (state.onDocKeydown) {
      document.removeEventListener("keydown", state.onDocKeydown);
      state.onDocKeydown = null;
    }
  }

  function buildPromptBookChatPayload(item) {
    const userPrompt = String((item && item.userPrompt) || "").trim();
    const enhanced = String((item && item.body) || "").trim();
    const parts = [];
    if (userPrompt) parts.push(userPrompt);
    if (enhanced && enhanced !== userPrompt) {
      if (parts.length) parts.push("");
      parts.push(enhanced);
    }
    const composerText = parts.join("\n").trim() || enhanced || userPrompt;
    return { userPrompt, enhanced, composerText };
  }

  function insertIntoChat(item) {
    if (!item) return;
    const { userPrompt, enhanced, composerText } = buildPromptBookChatPayload(item);
    if (!composerText) return;
    // Close detail FIRST to ensure clean view state before session starts
    closeDetail();
    if (typeof state.onInsertPrompt === "function") {
      state.onInsertPrompt(composerText, {
        ...item,
        source: "prompt-book",
        continueSession: Boolean(enhanced),
        sessionOriginal: userPrompt,
        sessionEnhanced: enhanced,
      });
    }
  }

  function ensureDetailShell() {
    if (state.detailShell) return;
    const rootEl = document.createElement("div");
    rootEl.id = "promptBookDetail";
    rootEl.className = "library-prompt-detail prompt-book-detail";
    rootEl.hidden = true;
    rootEl.setAttribute("aria-hidden", "true");
    rootEl.innerHTML = `
      <div class="library-prompt-detail__backdrop" data-prompt-book-dismiss="1" aria-hidden="true"></div>
      <div class="library-prompt-detail__sheet prompt-book-detail__sheet" role="dialog" aria-modal="true" aria-labelledby="promptBookDetailTitle">
        <header class="library-prompt-detail__header prompt-book-detail__header">
          <button type="button" class="library-prompt-detail__iconbtn" id="promptBookDetailBack" aria-label="Back">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          </button>
          <div id="prompt-book-detail__header-main" class="prompt-book-detail__header-main">
            <h2 class="library-prompt-detail__header-title" id="promptBookDetailHeaderTitle"></h2>
          </div>
          <div class="prompt-book-detail__header-actions">
            <button type="button" class="library-prompt-detail__iconbtn" id="promptBookDetailCopy" aria-label="Copy enhanced prompt">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
              </svg>
            </button>
          </div>
        </header>
        <p class="library-prompt-detail__status" id="promptBookDetailStatus" aria-live="polite"></p>
        <div class="library-prompt-detail__scroll prompt-book-detail__body-scroll">
          <h1 class="library-prompt-detail__title" id="promptBookDetailTitle"></h1>
          <p class="library-prompt-detail__subtitle" id="promptBookDetailSubtitle"></p>
          <section class="prompt-book-detail__block" id="promptBookDetailUserBlock">
            <h3 class="prompt-book-detail__section-label">Original prompt</h3>
            <div id="promptBookDetailUserContent" class="prompt-book-detail__scroll-box"></div>
          </section>
          <section class="prompt-book-detail__block">
            <h3 class="prompt-book-detail__section-label">Enhanced prompt</h3>
            <div id="promptBookDetailEnhancedContent" class="prompt-book-detail__scroll-box prompt-book-detail__scroll-box--enhanced"></div>
          </section>
        </div>
        <footer class="library-prompt-detail__footer prompt-book-detail__footer">
          <button type="button" class="library-prompt-detail__insert" id="promptBookDetailInsert">Use in Chat →</button>
        </footer>
      </div>
    `;
    document.body.appendChild(rootEl);
    state.detailShell = rootEl;

    const back = $("promptBookDetailBack");
    if (back) back.addEventListener("click", () => closeDetail());
    const backdrop = rootEl.querySelector("[data-prompt-book-dismiss]");
    if (backdrop) backdrop.addEventListener("click", () => closeDetail());

    const copyBtn = $("promptBookDetailCopy");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        if (!state.detailItem) return;
        copyText(
          buildPromptBookChatPayload(state.detailItem).composerText,
          "Prompt copied.",
          copyBtn
        );
      });
    }

    const ins = $("promptBookDetailInsert");
    if (ins) {
      ins.addEventListener("click", () => {
        if (state.detailItem) insertIntoChat(state.detailItem);
      });
    }
  }

  function setScrollBoxContent(el, raw, emptyMsg) {
    if (!el) return;
    const text = String(raw || "").trim();
    el.innerHTML = text
      ? formatBodyHtml(text)
      : `<p class="library-prompt-detail__md-p">${escapeHtml(emptyMsg)}</p>`;
  }

  function openPromptBookDetail(item) {
    if (!item) return;
    ensureDetailShell();
    if (state.onDocKeydown) {
      document.removeEventListener("keydown", state.onDocKeydown);
      state.onDocKeydown = null;
    }
    state.detailItem = item;

    const shell = state.detailShell;
    const title = item.title || "Prompt";
    const userPrompt = String(item.userPrompt || "").trim();
    const body = String(item.body || "").trim();

    const headerEl = $("promptBookDetailHeaderTitle");
    const titleEl = $("promptBookDetailTitle");
    const subEl = $("promptBookDetailSubtitle");
    const userContentEl = $("promptBookDetailUserContent");
    const enhancedContentEl = $("promptBookDetailEnhancedContent");
    const st = $("promptBookDetailStatus");
    if (st) st.textContent = "";

    if (headerEl) headerEl.textContent = truncateTitle(title, 28);
    if (titleEl) titleEl.textContent = title;
    if (subEl) {
      subEl.textContent = item.preview || "";
    }
    setScrollBoxContent(userContentEl, userPrompt, "—");
    setScrollBoxContent(enhancedContentEl, body, "No enhanced prompt text.");

    shell.hidden = false;
    shell.setAttribute("aria-hidden", "false");

    if (
      root.TV.consumerSubscriptionTheme &&
      typeof root.TV.consumerSubscriptionTheme.apply === "function" &&
      root.TV.sidebarAuthState
    ) {
      root.TV.consumerSubscriptionTheme.apply(root.TV.sidebarAuthState.getSnapshot());
    }

    state.onDocKeydown = (ev) => {
      if (ev.key === "Escape") {
        ev.preventDefault();
        closeDetail();
      }
    };
    document.addEventListener("keydown", state.onDocKeydown);

    const ins = $("promptBookDetailInsert");
    if (ins) setTimeout(() => ins.focus(), 50);
  }

  root.TV.consumerPromptBookDetailView = {
    init(opts) {
      const o = opts || {};
      state.onInsertPrompt = typeof o.onInsertPrompt === "function" ? o.onInsertPrompt : null;
    },
    getComposerText(item) {
      return buildPromptBookChatPayload(item).composerText;
    },
    open(item) {
      openPromptBookDetail(item);
    },
    openInChat(item) {
      insertIntoChat(item);
    },
    close() {
      closeDetail();
    },
  };
})();
