/**
 * Context view — domain/intent meta + neuro goal state from /refine/prepare.
 * Populates when a session starts (enhance data) and enriches when clarify runs.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const $ = (id) => document.getElementById(id);

  let _session   = null;
  let _neuro     = null;   // NeuroGoalState from /refine/prepare
  let _patterns  = [];     // context_patterns strings

  // ── Formatters ─────────────────────────────────────────────────────────────

  function fmt(raw) {
    if (raw == null || String(raw).trim() === "") return "—";
    return String(raw)
      .replace(/_/g, " ")
      .trim()
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function modeLabel(mode) {
    return { research: "Research", build: "Deep Build", media: "Studio" }[mode] || fmt(mode);
  }

  function confidencePct(conf) {
    const n = parseFloat(conf);
    return isNaN(n) ? null : Math.round(Math.max(0, Math.min(1, n)) * 100);
  }

  // ── Section builders ────────────────────────────────────────────────────────

  function makePill(text, mod) {
    const el = document.createElement("span");
    el.className = "ctx-pill" + (mod ? " ctx-pill--" + mod : "");
    el.textContent = text;
    return el;
  }

  function makeLabel(text) {
    const el = document.createElement("div");
    el.className = "ctx-label";
    el.textContent = text;
    return el;
  }

  function makeSectionHead(icon, title) {
    const el = document.createElement("div");
    el.className = "ctx-section-head";
    el.innerHTML = `<span class="ctx-section-icon" aria-hidden="true">${icon}</span>`;
    const t = document.createElement("span");
    t.textContent = title;
    el.appendChild(t);
    return el;
  }

  // ── Meta pills (domain / intent / mode) ─────────────────────────────────────

  function buildMetaRow(quality, mode) {
    const row = document.createElement("div");
    row.className = "ctx-meta-row";

    const domain = fmt((quality && quality.domain) || "");
    const intent = fmt((quality && quality.intent) || "");
    const modeStr = mode ? modeLabel(mode) : null;

    if (domain && domain !== "—") {
      const wrap = document.createElement("div");
      wrap.className = "ctx-meta-cell";
      wrap.appendChild(makeLabel("DOMAIN"));
      wrap.appendChild(makePill(domain, "domain"));
      row.appendChild(wrap);
    }

    if (intent && intent !== "—") {
      const wrap = document.createElement("div");
      wrap.className = "ctx-meta-cell";
      wrap.appendChild(makeLabel("INTENT"));
      wrap.appendChild(makePill(intent, "intent"));
      row.appendChild(wrap);
    }

    if (modeStr) {
      const wrap = document.createElement("div");
      wrap.className = "ctx-meta-cell";
      wrap.appendChild(makeLabel("MODE"));
      wrap.appendChild(makePill(modeStr, "mode"));
      row.appendChild(wrap);
    }

    return row;
  }

  // ── Neuro goal-state card ────────────────────────────────────────────────────

  function buildNeuroCard(neuro) {
    const card = document.createElement("div");
    card.className = "ctx-neuro-card";

    const ICON_BRAIN = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z"/></svg>`;

    card.appendChild(makeSectionHead(ICON_BRAIN, "How Velocity Sees This"));

    // Goal row
    if (neuro.user_final_goal) {
      const row = document.createElement("div");
      row.className = "ctx-neuro-row";
      row.innerHTML = `<span class="ctx-neuro-key">Goal</span>`;
      const val = document.createElement("span");
      val.className = "ctx-neuro-val";
      val.textContent = neuro.user_final_goal;
      row.appendChild(val);
      card.appendChild(row);
    }

    // Task row
    if (neuro.immediate_task) {
      const row = document.createElement("div");
      row.className = "ctx-neuro-row";
      row.innerHTML = `<span class="ctx-neuro-key">Task</span>`;
      const val = document.createElement("span");
      val.className = "ctx-neuro-val";
      val.textContent = neuro.immediate_task;
      row.appendChild(val);
      card.appendChild(row);
    }

    // Success row
    if (neuro.success_definition) {
      const row = document.createElement("div");
      row.className = "ctx-neuro-row";
      row.innerHTML = `<span class="ctx-neuro-key">Success</span>`;
      const val = document.createElement("span");
      val.className = "ctx-neuro-val";
      val.textContent = neuro.success_definition;
      row.appendChild(val);
      card.appendChild(row);
    }

    // Confidence bar
    const pct = confidencePct(neuro.confidence);
    if (pct !== null) {
      const barWrap = document.createElement("div");
      barWrap.className = "ctx-confidence-wrap";
      const barLabel = document.createElement("div");
      barLabel.className = "ctx-confidence-label";
      barLabel.innerHTML = `<span class="ctx-neuro-key">Confidence</span><span class="ctx-confidence-pct">${pct}%</span>`;
      const track = document.createElement("div");
      track.className = "ctx-confidence-track";
      const fill = document.createElement("div");
      fill.className = "ctx-confidence-fill" + (pct >= 70 ? " ctx-confidence-fill--high" : pct >= 40 ? " ctx-confidence-fill--mid" : " ctx-confidence-fill--low");
      fill.style.width = pct + "%";
      track.appendChild(fill);
      barWrap.appendChild(barLabel);
      barWrap.appendChild(track);
      card.appendChild(barWrap);
    }

    return card;
  }

  // ── Gaps card ────────────────────────────────────────────────────────────────

  function buildGapsCard(neuro) {
    const gaps = [
      ...(neuro.blocking_gaps || []),
      ...(neuro.context_needs || []),
    ].filter(Boolean).slice(0, 5);

    if (!gaps.length) return null;

    const card = document.createElement("div");
    card.className = "ctx-gaps-card";

    const ICON_WARN = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>`;
    card.appendChild(makeSectionHead(ICON_WARN, "Gaps Identified"));

    const list = document.createElement("ul");
    list.className = "ctx-gap-list";
    gaps.forEach((g) => {
      const li = document.createElement("li");
      li.className = "ctx-gap-item";
      li.textContent = g;
      list.appendChild(li);
    });
    card.appendChild(list);
    return card;
  }

  // ── Next step card ──────────────────────────────────────────────────────────

  function buildNextStepCard(neuro) {
    const next = neuro.fastest_next_action;
    if (!next) return null;

    const card = document.createElement("div");
    card.className = "ctx-next-card";

    const ICON_ARROW = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>`;
    card.appendChild(makeSectionHead(ICON_ARROW, "Recommended Next Step"));

    const text = document.createElement("p");
    text.className = "ctx-next-text";
    text.textContent = next;
    card.appendChild(text);
    return card;
  }

  // ── Context patterns card ────────────────────────────────────────────────────

  function buildPatternsCard(patterns) {
    const valid = (patterns || []).filter(Boolean).slice(0, 5);
    if (!valid.length) return null;

    const card = document.createElement("div");
    card.className = "ctx-patterns-card";

    const ICON_SPARK = `<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 3 14.5 9.5 21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z"/></svg>`;
    card.appendChild(makeSectionHead(ICON_SPARK, "Personalization Signals"));

    const list = document.createElement("ul");
    list.className = "ctx-pattern-list";
    valid.forEach((p) => {
      const li = document.createElement("li");
      li.className = "ctx-pattern-item";
      li.textContent = p;
      list.appendChild(li);
    });
    card.appendChild(list);
    return card;
  }

  // ── Document history ─────────────────────────────────────────────────────────

  function buildDocumentHistory(original) {
    const section = document.createElement("div");
    section.className = "ctx-history-section";

    const ICON_DOC = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`;
    section.appendChild(makeSectionHead(ICON_DOC, "Document History"));

    const inputBlock = document.createElement("div");
    inputBlock.className = "ctx-input-block";

    const dot = document.createElement("div");
    dot.className = "ctx-input-dot";
    const dotInner = document.createElement("div");
    dotInner.className = "ctx-input-dot-inner";
    dot.appendChild(dotInner);

    const content = document.createElement("div");
    content.className = "ctx-input-content";
    const label = document.createElement("div");
    label.className = "ctx-input-label";
    label.textContent = "User Input";

    const text = document.createElement("div");
    text.className = "ctx-input-text";
    if (root.TV.structuredPromptDom && typeof root.TV.structuredPromptDom.appendFormatted === "function") {
      root.TV.structuredPromptDom.appendFormatted(text, original || "");
    } else {
      text.textContent = original || "";
    }

    content.appendChild(label);
    content.appendChild(text);
    inputBlock.appendChild(dot);
    inputBlock.appendChild(content);
    section.appendChild(inputBlock);
    return section;
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  function render() {
    const scroll = $("contextScroll");
    if (!scroll) return;
    scroll.innerHTML = "";

    const quality = (_session && _session.quality) || {};
    const mode    = _session && _session.mode;

    const metaRow = buildMetaRow(quality, mode);
    if (metaRow.children.length) scroll.appendChild(metaRow);

    if (_neuro) {
      scroll.appendChild(buildNeuroCard(_neuro));

      const gaps = buildGapsCard(_neuro);
      if (gaps) scroll.appendChild(gaps);

      const next = buildNextStepCard(_neuro);
      if (next) scroll.appendChild(next);
    }

    const patterns = buildPatternsCard(_patterns);
    if (patterns) scroll.appendChild(patterns);

    scroll.appendChild(buildDocumentHistory(_session && _session.original));
  }

  // ── Public API ───────────────────────────────────────────────────────────────

  function show(session) {
    if (root.TV.suggestionsView && typeof root.TV.suggestionsView.hide === "function") {
      root.TV.suggestionsView.hide();
    }
    _session = session || null;
    render();
    const view = $("viewContext");
    if (view) { view.classList.add("view-surface--active"); view.hidden = false; }
  }

  function hide() {
    const view = $("viewContext");
    if (view) { view.classList.remove("view-surface--active"); view.hidden = true; }
  }

  /** Called by suggestions-view after clarify completes with neuro data. */
  function updateNeuro(neuroState, contextPatterns) {
    _neuro    = neuroState    || null;
    _patterns = contextPatterns || [];
    // Re-render only if context tab is currently visible.
    const view = $("viewContext");
    if (view && !view.hidden && view.classList.contains("view-surface--active")) {
      render();
    }
  }

  root.TV.contextView = { show, hide, updateNeuro };
})();
