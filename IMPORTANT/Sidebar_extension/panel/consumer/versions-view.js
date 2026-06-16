/**
 * Versions view — reprompts (refined) first, then enhanced, then original.
 * Click header+body (or "Use in Output") to set Output display — same session update as v-chat choosing a prompt version.
 * Cards are always expanded. Latest version gets a "LATEST" badge.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const $ = (id) => document.getElementById(id);

  const COPY_SVG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
  const USE_SVG  = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 3 21 3 21 9"/><path d="M10 14L21 3"/><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/></svg>`;

  let _onUse = null;

  /** Active text shown in Output; mirrors output-view default when displayPrompt unset */
  function activeDisplayText(session) {
    if (!session) return "";
    if (session.displayPrompt !== undefined && session.displayPrompt !== null) {
      return session.displayPrompt;
    }
    return session.enhanced || "";
  }

  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).catch(() => {});
    } else {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.cssText = "position:fixed;left:-9999px;top:-9999px;";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch (_) {}
      document.body.removeChild(ta);
    }
  }

  /**
   * @param {object} opts
   * @param {string} opts.label       - e.g. "Enhanced" | "Original Prompt" | "Refined 1"
   * @param {string} opts.text        - the prompt text
   * @param {string} opts.dotColor    - CSS color for the left dot
   * @param {string} opts.cardClass   - extra class on the card
   * @param {boolean} opts.isLatest   - show "LATEST" badge
   * @param {boolean} opts.canUse     - show "Use in Output" button
   * @param {boolean} opts.isSelected - active version (matches Output display)
   */
  function buildCard({ label, text, dotColor, cardClass, isLatest, canUse, isSelected }) {
    const card = document.createElement("div");
    card.className = `ver-card${cardClass ? ` ${cardClass}` : ""}`;

    // ── Header ──────────────────────────────────────────
    const header = document.createElement("div");
    header.className = "ver-card-header";

    const labelGroup = document.createElement("div");
    labelGroup.className = "ver-card-label-group";

    const dot = document.createElement("span");
    dot.className = "ver-dot";
    dot.style.background = dotColor || "var(--vel-muted-text)";

    const labelEl = document.createElement("span");
    labelEl.className = "ver-card-label";
    labelEl.textContent = label;

    labelGroup.appendChild(dot);
    labelGroup.appendChild(labelEl);
    header.appendChild(labelGroup);

    if (isLatest) {
      const badge = document.createElement("span");
      badge.className = "ver-latest-badge";
      badge.textContent = "LATEST";
      header.appendChild(badge);
    }

    // ── Body ─────────────────────────────────────────────
    const body = document.createElement("div");
    body.className = "ver-card-body";
    body.textContent = text || "";

    const main = document.createElement("div");
    main.className = "ver-card-main";
    main.appendChild(header);
    main.appendChild(body);

    // ── Footer actions ───────────────────────────────────
    const footer = document.createElement("div");
    footer.className = "ver-card-footer";

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "ver-action-btn";
    copyBtn.innerHTML = `${COPY_SVG}<span>Copy</span>`;
    copyBtn.addEventListener("click", () => {
      copyToClipboard(text);
      const sp = copyBtn.querySelector("span");
      sp.textContent = "Copied!";
      setTimeout(() => { sp.textContent = "Copy"; }, 1500);
    });
    footer.appendChild(copyBtn);

    if (canUse) {
      const useBtn = document.createElement("button");
      useBtn.type = "button";
      useBtn.className = "ver-action-btn ver-action-btn--use";
      useBtn.innerHTML = `${USE_SVG}<span>Use in Output</span>`;
      useBtn.addEventListener("click", () => {
        if (_onUse) _onUse(text, label);
      });
      footer.appendChild(useBtn);
    }

    card.appendChild(main);
    card.appendChild(footer);

    if (_onUse && text) {
      if (isSelected) card.classList.add("ver-card--selected");
      main.classList.add("ver-card-main--interactive");
      main.setAttribute("tabindex", "0");
      main.setAttribute("role", "button");
      main.setAttribute("aria-label", `${label}: show this version in Output`);
      main.addEventListener("click", () => {
        _onUse(text, label);
      });
      main.addEventListener("keydown", (ev) => {
        if (ev.target !== main) return;
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          _onUse(text, label);
        }
      });
    }

    return card;
  }

  function render(session) {
    const scroll = $("versionsScroll");
    if (!scroll) return;
    scroll.innerHTML = "";

    if (!session) {
      scroll.innerHTML = `<div class="versions-empty"><p class="versions-empty-title">No versions yet</p><p class="versions-empty-sub">Enhance a prompt to see versions here.</p></div>`;
      return;
    }

    const refinements = Array.isArray(session._refinements) ? session._refinements : [];
    const hasRefinements = refinements.length > 0;

    const latestIsRefined = hasRefinements;
    const active = activeDisplayText(session);

    // ── Refined (reprompts) first — last in chain keeps LATEST badge ──
    refinements.forEach((r, i) => {
      const isLatest = i === refinements.length - 1;
      const t = r.text;
      scroll.appendChild(buildCard({
        label: r.label,
        text: t,
        dotColor: "var(--vel-accent)",
        cardClass: isLatest ? "ver-card--latest" : "",
        isLatest,
        canUse: true,
        isSelected: active === t,
      }));
    });

    // ── Enhanced (after reprompts) ───────────────────────
    if (session.enhanced) {
      const t = session.enhanced;
      scroll.appendChild(buildCard({
        label: "Enhanced",
        text: t,
        dotColor: "var(--tv-pro-yellow)",
        cardClass: "ver-card--enhanced",
        isLatest: !latestIsRefined,
        canUse: hasRefinements,
        isSelected: active === t,
      }));
    }

    // ── Original Prompt (last — reference) ──────────────
    if (session.original) {
      const t = session.original;
      scroll.appendChild(buildCard({
        label: "Original Prompt",
        text: t,
        dotColor: "rgba(255,255,255,0.3)",
        cardClass: "ver-card--original",
        isLatest: false,
        canUse: false,
        isSelected: active === t,
      }));
    }
  }

  function show(session) {
    render(session);
    const view = $("viewVersions");
    if (view) { view.classList.add("view-surface--active"); view.hidden = false; }
  }

  function hide() {
    const view = $("viewVersions");
    if (view) { view.classList.remove("view-surface--active"); view.hidden = true; }
  }

  function onUse(cb) { _onUse = cb; }

  root.TV.versionsView = { show, hide, render, onUse };
})();
