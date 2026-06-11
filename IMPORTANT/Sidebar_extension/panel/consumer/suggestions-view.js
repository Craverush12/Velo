/**
 * Suggestions view — clarifying Q&A flow.
 * Layout:
 *   - #suggestionsScroll      : ORIGINAL collapsible only
 *   - #suggestionsActivePanel : answer-saved toast + current Q card
 * Answered Q&A is mirrored into the main composer; Send runs refine (composer-bar).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const $ = (id) => document.getElementById(id);

  const MAX_QUESTIONS = 4;
  const OTHER_LABEL = "Other";
  const QA_SUMMARY_CLASS = "composer-input--qa-summary";
  const QA_SUMMARY_MAX_PX = 220;
  const REFINE_PLACEHOLDER = "Describe how to refine your prompt…";

  let _session   = null;
  let _questions = [];
  let _answers   = {};
  let _current   = 0;
  let _onRefined = null;
  /** Question key (`q.id` or index) when user chose Other and has not saved custom text yet */
  let _otherPendingKey = null;
  let _refineComposerActive = false;
  let _composerUserEditing = false;
  let _autoOpenActiveQuestion = false;
  /** Question keys whose QA card body is currently expanded. */
  const _expandedKeys = new Set();

  // ── Style injection ───────────────────────────────────────────────────────
  (function injectStyles() {
    if (document.getElementById("tv-suggestions-styles")) return;
    const s = document.createElement("style");
    s.id = "tv-suggestions-styles";
    s.textContent = `
      /* ── Hide composer dock while suggestions view is active ──── */
      .app-shell:has(#viewSuggestions.view-surface--active:not([hidden])) .composer-dock {
        display: none !important;
      }

      /* ── Progress bar ─────────────────────────────────────────── */
      .refine-progress-wrap {
        margin: 0 0 16px;
        padding: 0 2px;
        flex-shrink: 0;
      }
      .refine-progress-track {
        height: 3px;
        background: rgba(25, 216, 230, 0.12);
        border-radius: 99px;
        overflow: hidden;
        margin-bottom: 8px;
        box-shadow: inset 0 1px 2px rgba(0,0,0,0.2);
      }
      .refine-progress-fill {
        height: 100%;
        background: linear-gradient(90deg, #0fb6c4, #19d8e6);
        border-radius: 99px;
        transition: width 0.5s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.5s ease;
        min-width: 0;
        box-shadow: 0 0 10px rgba(25, 216, 230, 0.4);
      }
      .refine-progress-meta {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }
      .refine-progress-label {
        font-size: clamp(0.66rem, 1.8vw, 0.72rem);
        color: var(--vel-muted-text, #bac9cc);
        letter-spacing: 0.02em;
        font-weight: 600;
        flex: 1;
      }
      .refine-progress-count {
        font-size: clamp(0.66rem, 1.8vw, 0.72rem);
        font-weight: 800;
        color: var(--vel-accent, #19d8e6);
        letter-spacing: 0.05em;
        white-space: nowrap;
      }

      /* ── Refine CTA button ────────────────────────────────────── */
      .refine-btn-wrap {
        padding: 14px 0 2px;
        flex-shrink: 0;
      }
      .refine-cta-btn {
        width: 100%;
        padding: clamp(12px, 3vw, 14px) 20px;
        border-radius: 999px;
        border: 1px solid rgba(25, 216, 230, 0.2);
        background: rgba(25, 216, 230, 0.05);
        color: rgba(25, 216, 230, 0.4);
        font-family: inherit;
        font-size: clamp(0.85rem, 2.2vw, 0.95rem);
        font-weight: 800;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        cursor: not-allowed;
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        outline: none;
        backdrop-filter: blur(8px);
        -webkit-backdrop-filter: blur(8px);
      }
      .refine-cta-btn.refine-cta-btn--active {
        cursor: pointer;
        color: var(--vel-accent, #19d8e6);
        border-color: rgba(25, 216, 230, 0.5);
        background: rgba(25, 216, 230, 0.1);
        box-shadow: 0 4px 16px rgba(25, 216, 230, 0.15);
      }
      .refine-cta-btn.refine-cta-btn--active:hover {
        background: rgba(25, 216, 230, 0.15);
        border-color: rgba(25, 216, 230, 0.7);
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(25, 216, 230, 0.25);
      }
      .refine-cta-btn.refine-cta-btn--ready {
        background: linear-gradient(135deg, #19d8e6, #0fb6c4);
        border-color: transparent;
        color: #000;
        animation: tv-refine-pulse 2.4s ease-in-out infinite;
        text-shadow: 0 1px 2px rgba(255, 255, 255, 0.4);
      }
      .refine-cta-btn.refine-cta-btn--ready:hover {
        transform: translateY(-2px);
        filter: brightness(1.1);
      }
      @keyframes tv-refine-pulse {
        0%, 100% {
          box-shadow: 0 0 10px rgba(25,216,230,.32),
                      0 0 26px rgba(25,216,230,.14);
        }
        50% {
          box-shadow: 0 0 20px rgba(25,216,230,.58),
                      0 0 44px rgba(25,216,230,.26);
        }
      }
      .refine-cta-btn.refine-cta-btn--busy {
        cursor: wait;
        animation: none;
        opacity: 0.6;
        transform: none;
      }
    `;
    (document.head || document.documentElement).appendChild(s);
  })();

  const CHEVRON_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>`;
  const PREV_SVG    = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M15 18l-6-6 6-6"/></svg>`;
  const NEXT_SVG    = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M9 18l6-6-6-6"/></svg>`;
  const ARROW_RIGHT_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 6 15 12 9 18"/></svg>`;

  function sendMsg(action, payload) {
    const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ action, payload: payload || {}, requestId }, (res) => {
        if (chrome.runtime.lastError) { reject(new Error(chrome.runtime.lastError.message)); return; }
        resolve(res);
      });
    });
  }

  // ── Builders ─────────────────────────────────────────────────────────────

  function buildOriginalCollapsible(text) {
    const short = String(text || "").replace(/\s+/g, " ").trim();
    const preview = short.length > 70 ? short.slice(0, 67) + "…" : short;

    const wrap = document.createElement("div");
    wrap.className = "sug-original";

    const row1 = document.createElement("button");
    row1.type = "button";
    row1.className = "sug-original-header";

    const main = document.createElement("div");
    main.className = "sug-original-header-main";

    const lbl = document.createElement("span");
    lbl.className = "sug-original-label";
    lbl.textContent = "ORIGINAL";

    const previewEl = document.createElement("span");
    previewEl.className = "sug-original-preview";
    previewEl.textContent = preview;

    const chev = document.createElement("span");
    chev.className = "sug-original-chevron";
    chev.setAttribute("aria-hidden", "true");
    chev.innerHTML = CHEVRON_SVG;

    main.appendChild(lbl);
    main.appendChild(previewEl);
    row1.appendChild(main);
    row1.appendChild(chev);

    const body = document.createElement("div");
    body.className = "sug-original-body";
    body.textContent = short;

    let open = false;
    row1.addEventListener("click", () => {
      open = !open;
      wrap.classList.toggle("sug-original--open", open);
    });

    wrap.appendChild(row1);
    wrap.appendChild(body);
    return wrap;
  }

  /** Returns true only for questions that should render as radio buttons. */
  function isSelectQuestion(q) {
    return (
      q.answer_type === "single_select" &&
      Array.isArray(q.options) &&
      q.options.length > 0
    );
  }

  function normalizeOptions(q) {
    const raw = Array.isArray(q.options) && q.options.length
      ? q.options.map((o) => String(o).trim()).filter(Boolean)
      : [];
    if (!raw.length) return [];
    const mapped = raw.map(displayOptionLabel);
    const uniq = [];
    const seen = new Set();
    mapped.forEach((label) => {
      const k = label.toLowerCase();
      if (seen.has(k)) return;
      seen.add(k);
      uniq.push(label);
    });
    if (!seen.has(OTHER_LABEL.toLowerCase())) uniq.push(OTHER_LABEL);
    return uniq;
  }

  function predefinedSansOther(q) {
    return normalizeOptions(q).filter((o) => o !== OTHER_LABEL);
  }

  function isCustomOtherAnswer(q, index, answer) {
    if (!answer || typeof answer !== "string") return false;
    const predefined = predefinedSansOther(q);
    return !predefined.includes(answer);
  }

  function displayOptionLabel(optText) {
    const s = String(optText || "").trim();
    if (s === "Option 4" || s.toLowerCase().includes("option 4")) return OTHER_LABEL;
    return s;
  }

  function questionKey(q, index) {
    if (q && q.id != null && q.id !== "") return q.id;
    return index;
  }

  function expandActiveQuestion() {
    if (!_questions.length || _current < 0 || _current >= _questions.length) return;
    _expandedKeys.add(questionKey(_questions[_current], _current));
  }

  function focusActiveQuestionControl() {
    window.requestAnimationFrame(() => {
      const card = $(`qa-card-${_current}`);
      const target =
        card &&
        card.querySelector(".qa-option:not(:disabled), .qa-other-input, .qa-card-toggle");
      if (!target || typeof target.focus !== "function") return;
      try {
        target.focus({ preventScroll: true });
      } catch (_) {
        try { target.focus(); } catch (_) {}
      }
      const panel = $("suggestionsActivePanel");
      if (panel && typeof panel.scrollTo === "function") {
        panel.scrollTo({ top: 0, behavior: "smooth" });
      }
    });
  }

  function handleOtherCommit(q, index, inputEl) {
    const key = questionKey(q, index);
    const v = inputEl && String(inputEl.value || "").trim();
    if (!v) {
      inputEl.classList.add("qa-other-input--invalid");
      window.setTimeout(() => inputEl.classList.remove("qa-other-input--invalid"), 700);
      return;
    }
    _answers[key] = v;
    _otherPendingKey = null;
    _refineComposerActive = true;
    syncComposerFromAnswers();
    window.setTimeout(() => {
      if (_current < _questions.length - 1) _current += 1;
      _autoOpenActiveQuestion = true;
      render();
    }, 380);
  }

  /**
   * Slim glowing progress bar shown at the top of the active panel.
   * Always visible; grows and glows as questions are answered.
   */
  function buildProgressBar(answeredCount, total) {
    const safeTotal = Math.max(1, Number(total) || 1);
    const safeAnswered = Math.min(safeTotal, Math.max(0, Number(answeredCount) || 0));
    const remaining = safeTotal - safeAnswered;
    const ratio = safeAnswered / safeTotal;
    const pct = Math.round(ratio * 100);

    const wrap = document.createElement("div");
    wrap.className = "refine-progress-wrap";
    wrap.setAttribute("role", "progressbar");
    wrap.setAttribute("aria-valuenow", String(safeAnswered));
    wrap.setAttribute("aria-valuemin", "0");
    wrap.setAttribute("aria-valuemax", String(safeTotal));
    wrap.setAttribute("aria-label", `${safeAnswered} of ${safeTotal} questions answered`);

    const track = document.createElement("div");
    track.className = "refine-progress-track";

    const fill = document.createElement("div");
    fill.className = "refine-progress-fill";
    fill.style.width = `${pct}%`;

    // Glow grows with ratio — cyan matches product accent (#19d8e6)
    if (ratio > 0) {
      const glowSz = Math.round(2 + ratio * 8);
      const glowOp = (0.25 + ratio * 0.55).toFixed(2);
      fill.style.boxShadow =
        `0 0 ${glowSz}px rgba(25,216,230,${glowOp}),` +
        ` 0 0 ${glowSz * 2}px rgba(25,216,230,${(parseFloat(glowOp) * 0.4).toFixed(2)})`;
    }

    track.appendChild(fill);

    const meta = document.createElement("div");
    meta.className = "refine-progress-meta";

    const label = document.createElement("span");
    label.className = "refine-progress-label";
    if (safeAnswered === 0) {
      label.textContent = "Answer questions for a stronger refinement";
    } else if (remaining === 0) {
      label.textContent = "All questions answered — ready to refine!";
    } else {
      label.textContent = `${remaining} question${remaining !== 1 ? "s" : ""} remaining`;
    }

    const count = document.createElement("span");
    count.className = "refine-progress-count";
    count.textContent = `${safeAnswered}/${safeTotal}`;

    meta.appendChild(label);
    meta.appendChild(count);
    wrap.appendChild(track);
    wrap.appendChild(meta);
    return wrap;
  }

  /**
   * Glowing "Refine Prompt" CTA button.
   * Dim when no answers, progressively brighter with each answer,
   * pulsing "ready" state when all answered.
   */
  function buildRefineButton(answeredCount, total) {
    const safeTotal = Math.max(1, Number(total) || 1);
    const safeAnswered = Math.min(safeTotal, Math.max(0, Number(answeredCount) || 0));
    const ratio = safeAnswered / safeTotal;
    const allDone = safeAnswered >= safeTotal;
    const hasAny = safeAnswered > 0;
    const canRefine = hasAny && _session != null && _otherPendingKey == null;

    const wrap = document.createElement("div");
    wrap.className = "refine-btn-wrap";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.id = "btnRefineAction";

    const classes = ["refine-cta-btn"];
    if (canRefine) classes.push("refine-cta-btn--active");
    if (allDone && canRefine) classes.push("refine-cta-btn--ready");
    btn.className = classes.join(" ");
    btn.disabled = !canRefine;
    btn.setAttribute("aria-label", canRefine ? "Refine prompt with your answers" : "Answer at least one question to refine");

    // Progressive cyan glow — scales from subtle to bright as ratio increases
    if (canRefine && !allDone) {
      const glowSz = Math.round(4 + ratio * 16);
      const glowOp = (0.18 + ratio * 0.42).toFixed(2);
      btn.style.boxShadow =
        `0 0 ${glowSz}px rgba(25,216,230,${glowOp}),` +
        ` 0 0 ${Math.round(glowSz * 1.8)}px rgba(25,216,230,${(parseFloat(glowOp) * 0.45).toFixed(2)})`;
      btn.style.borderColor = `rgba(25,216,230,${(0.3 + ratio * 0.4).toFixed(2)})`;
    }

    const label = document.createElement("span");
    label.className = "refine-cta-label";
    label.textContent = "Refine Prompt";
    btn.appendChild(label);

    btn.addEventListener("click", async () => {
      if (!canRefine || btn.disabled) return;
      btn.disabled = true;
      btn.classList.remove("refine-cta-btn--ready");
      btn.classList.add("refine-cta-btn--busy");
      btn.style.boxShadow = "";
      label.textContent = "Refining…";
      const ok = await submitRefine();
      if (!ok) {
        // Restore on failure
        btn.disabled = false;
        btn.classList.remove("refine-cta-btn--busy");
        if (allDone) btn.classList.add("refine-cta-btn--ready");
        label.textContent = "Refine Prompt";
      }
    });

    wrap.appendChild(btn);
    return wrap;
  }

  function buildQACard(q, index, total, onSelect, onPrev, onNext, onClose) {
    const key = questionKey(q, index);
    const useSelect = isSelectQuestion(q);
    const optionsList = useSelect ? normalizeOptions(q) : [];
    const currentAnswer = _answers[key];
    const pendingHere = _otherPendingKey === key;
    const showOtherField =
      useSelect && (pendingHere || isCustomOtherAnswer(q, index, currentAnswer));
    // Force-expand whenever the "Other" custom-text flow is in progress so the
    // user can see (and reach) the textarea. Otherwise honor the persisted
    // per-question expand state.
    const expanded = pendingHere || _expandedKeys.has(key);

    const card = document.createElement("div");
    card.className = "qa-card qa-card--preview" + (expanded ? " qa-card--expanded" : "");
    card.id = `qa-card-${index}`;

    // ── Tappable preview header ────────────────────────────────────────────
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "qa-card-toggle";
    toggle.setAttribute("aria-expanded", expanded ? "true" : "false");
    toggle.setAttribute("aria-controls", `qa-card-body-${index}`);

    const toggleMain = document.createElement("div");
    toggleMain.className = "qa-card-toggle-main";

    const qText = document.createElement("p");
    qText.className = "qa-card-question";
    qText.textContent = q.question || "";

    const hint = document.createElement("p");
    hint.className = "qa-card-hint";
    hint.textContent = "Tap to answer this question.";

    toggleMain.appendChild(qText);
    toggleMain.appendChild(hint);

    const toggleMeta = document.createElement("div");
    toggleMeta.className = "qa-card-toggle-meta";

    const chip = document.createElement("span");
    chip.className = "qa-priority-chip";
    chip.textContent = "High Priority";

    const arrow = document.createElement("span");
    arrow.className = "qa-arrow-btn";
    arrow.setAttribute("aria-hidden", "true");
    arrow.innerHTML = ARROW_RIGHT_SVG;

    toggleMeta.appendChild(chip);
    toggleMeta.appendChild(arrow);

    toggle.appendChild(toggleMain);
    toggle.appendChild(toggleMeta);

    toggle.addEventListener("click", () => {
      if (_expandedKeys.has(key)) {
        // Collapsing while an Other-pending textarea is open would strand the
        // user without a way back, so block collapse in that state.
        if (pendingHere) return;
        _expandedKeys.delete(key);
      } else {
        _expandedKeys.add(key);
      }
      render();
    });

    card.appendChild(toggle);

    // ── Expanded body (options + Other field + nav footer) ─────────────────
    const body = document.createElement("div");
    body.className = "qa-card-body";
    body.id = `qa-card-body-${index}`;
    if (!expanded) body.hidden = true;

    if (useSelect) {
      // ── Radio-button path: single_select with real options ──────────────
      const opts = document.createElement("div");
      opts.className = "qa-options";

      optionsList.forEach((display) => {
        const selected =
          display === OTHER_LABEL
            ? Boolean(showOtherField)
            : Boolean(!showOtherField && currentAnswer === display);

        const optBtn = document.createElement("button");
        optBtn.type = "button";
        optBtn.className = "qa-option" + (selected ? " qa-option--selected" : "");

        const radio = document.createElement("span");
        radio.className = "qa-radio";
        const dot = document.createElement("span");
        dot.className = "qa-radio-dot";
        radio.appendChild(dot);

        const text = document.createElement("span");
        text.textContent = display;

        optBtn.appendChild(radio);
        optBtn.appendChild(text);
        optBtn.addEventListener("click", () => onSelect(q, index, display, opts));
        opts.appendChild(optBtn);
      });

      body.appendChild(opts);
    } else {
      // ── Textarea path: short_text / long_text / select with no options ──
      const textWrap = document.createElement("div");
      textWrap.className = "qa-other-wrap";

      const inp = document.createElement("textarea");
      inp.className = "qa-other-input";
      inp.setAttribute("aria-label", q.question || "Your answer");
      inp.rows = q.answer_type === "long_text" ? 4 : 2;
      inp.placeholder = "Type your answer…";
      inp.value = currentAnswer || "";

      const actions = document.createElement("div");
      actions.className = "qa-other-actions";
      const saveBtn = document.createElement("button");
      saveBtn.type = "button";
      saveBtn.className = "qa-other-done";
      saveBtn.textContent = "Save answer";
      saveBtn.addEventListener("click", () => handleOtherCommit(q, index, inp));
      inp.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
          ev.preventDefault();
          handleOtherCommit(q, index, inp);
        }
      });

      actions.appendChild(saveBtn);
      textWrap.appendChild(inp);
      textWrap.appendChild(actions);
      body.appendChild(textWrap);

      if (expanded) {
        window.requestAnimationFrame(() => { try { inp.focus(); } catch (_) {} });
      }
    }

    if (showOtherField) {
      const otherWrap = document.createElement("div");
      otherWrap.className = "qa-other-wrap";

      const otherHint = document.createElement("p");
      otherHint.className = "qa-other-hint";
      otherHint.textContent =
        "Type your own answer, then Save. It is included when you Send in the bar below to refine.";

      const inp = document.createElement("textarea");
      inp.className = "qa-other-input";
      inp.setAttribute("aria-label", "Custom answer for this question");
      inp.rows = 3;
      inp.placeholder = "Describe your answer…";
      const initialVal =
        pendingHere && !isCustomOtherAnswer(q, index, currentAnswer)
          ? ""
          : String(currentAnswer || "");
      inp.value = initialVal;

      const actions = document.createElement("div");
      actions.className = "qa-other-actions";
      const doneBtn = document.createElement("button");
      doneBtn.type = "button";
      doneBtn.className = "qa-other-done";
      doneBtn.textContent = "Save answer";
      doneBtn.addEventListener("click", () => handleOtherCommit(q, index, inp));

      inp.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
          ev.preventDefault();
          handleOtherCommit(q, index, inp);
        }
      });

      actions.appendChild(doneBtn);
      otherWrap.appendChild(otherHint);
      otherWrap.appendChild(inp);
      otherWrap.appendChild(actions);
      if (pendingHere) {
        window.requestAnimationFrame(() => {
          try {
            inp.focus();
          } catch (_) {}
        });
      }
      body.appendChild(otherWrap);
    }

    const footer = document.createElement("div");
    footer.className = "qa-card-footer";

    const prevBtn = document.createElement("button");
    prevBtn.type = "button";
    prevBtn.className = "qa-nav-btn";
    prevBtn.innerHTML = PREV_SVG;
    prevBtn.title = "Previous question";
    prevBtn.setAttribute("aria-label", "Previous question");
    prevBtn.disabled = index === 0;
    prevBtn.addEventListener("click", onPrev);

    const nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "qa-nav-btn";
    nextBtn.innerHTML = NEXT_SVG;
    nextBtn.title = "Next question";
    nextBtn.setAttribute("aria-label", "Next question");
    nextBtn.disabled = index >= total - 1;
    nextBtn.addEventListener("click", onNext);

    const spacer = document.createElement("span");
    spacer.className = "qa-card-footer-spacer";

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "qa-close-btn";
    closeBtn.textContent = "×";
    closeBtn.title = "Close";
    closeBtn.setAttribute("aria-label", "Close suggestions");
    closeBtn.addEventListener("click", onClose);

    footer.appendChild(prevBtn);
    footer.appendChild(nextBtn);
    footer.appendChild(spacer);
    footer.appendChild(closeBtn);
    body.appendChild(footer);

    card.appendChild(body);

    return card;
  }

  function buildImproveSectionTitle(answeredCount, total) {
    const title = document.createElement("p");
    title.className = "qa-section-title";
    const safeTotal = Math.max(1, Number(total) || 1);
    const safeAnswered = Math.min(safeTotal, Math.max(0, Number(answeredCount) || 0));
    title.textContent = `Improve your prompt (${safeAnswered}/${safeTotal})`;
    return title;
  }

  function buildComposerQaSummary() {
    const lines = [];
    _questions.forEach((q, i) => {
      const a = _answers[questionKey(q, i)];
      if (!a) return;
      lines.push(`${i + 1}. ${q.question || ""}`);
      lines.push(a);
      lines.push("");
    });
    return lines.join("\n").trim();
  }

  function autoSizeQaTextarea(ta) {
    if (!ta) return;
    ta.classList.add(QA_SUMMARY_CLASS);
    ta.style.height = "auto";
    const next = Math.min(QA_SUMMARY_MAX_PX, ta.scrollHeight);
    ta.style.height = next + "px";
  }

  function resetQaTextareaSize(ta) {
    if (!ta) return;
    ta.classList.remove(QA_SUMMARY_CLASS);
    ta.style.height = "";
  }

  function syncComposerFromAnswers() {
    const ta = $("promptInput");
    const sugView = $("viewSuggestions");
    const suggestionsVisible =
      sugView &&
      !sugView.hidden &&
      sugView.classList.contains("view-surface--active");
    if (!ta || !suggestionsVisible) return;
    const answeredCount = Object.keys(_answers).length;
    // Only skip sync if user is editing custom text AND there are no Q&A answers.
    // Once an answer is selected, always sync to show the Q&A summary.
    if (_composerUserEditing && _refineComposerActive && answeredCount === 0) return;
    if (answeredCount > 0) {
      // Clear user editing flag since we're now showing Q&A summary
      _composerUserEditing = false;
      ta.value = buildComposerQaSummary();
      ta.readOnly = true;
      autoSizeQaTextarea(ta);
    } else {
      ta.readOnly = false;
      resetQaTextareaSize(ta);
      if (!ta.value.trim()) ta.placeholder = REFINE_PLACEHOLDER;
    }
    ta.dispatchEvent(new Event("input", { bubbles: true }));
    if (root.TV.consumerComposerBar && typeof root.TV.consumerComposerBar.refreshSendState === "function") {
      root.TV.consumerComposerBar.refreshSendState();
    }
    if (typeof root.TV.refreshSuggestionsComposerChrome === "function") {
      root.TV.refreshSuggestionsComposerChrome();
    }
  }

  function canSubmitRefine() {
    return (
      _otherPendingKey == null &&
      Object.keys(_answers).length > 0 &&
      _session != null
    );
  }

  function buildQaArray() {
    return _questions
      .map((q, i) => ({
        question: q.question || "",
        answer: _answers[questionKey(q, i)] || "",
      }))
      .filter((x) => x.answer);
  }

  async function runRefineRequest(qaArray) {
    const sendBtn = $("btnComposerSend");
    const setBusy = (busy) => {
      if (sendBtn) {
        sendBtn.disabled = busy;
        sendBtn.setAttribute("aria-busy", busy ? "true" : "false");
      }
    };

    // Defensive check: ensure we have a valid session
    if (!_session) {
      console.warn("[suggestions-view] runRefineRequest: _session is null, cannot refine");
      // Show suggestions view to prevent blank page
      show();
      return false;
    }

    setBusy(true);
    const TP = root.TV && root.TV.thoughtProcess;
    const cancelRef = { cancelled: false };
    const visualDone =
      TP && typeof TP.advanceVisualToFinalizingRunning === "function"
        ? TP.advanceVisualToFinalizingRunning(cancelRef)
        : Promise.resolve();

    let succeeded = false;
    try {
      const res = await sendMsg("TV_CONSUMER_REFINE", {
        original: _session && _session.original,
        enhanced: _session && _session.enhanced,
        qaArray: Array.isArray(qaArray) ? qaArray : [],
      });

      await visualDone;

      const refined =
        res &&
        res.success &&
        res.data &&
        (res.data.refined_prompt || res.data.enhanced_prompt);

      if (refined && _onRefined) {
        if (TP && typeof TP.markAllStepsDone === "function") {
          TP.markAllStepsDone();
        }

        // Fetch annotations for the refined prompt — best-effort, same
        // mechanism as the enhanced prompt path in consumer-enhance-flow.js.
        // Runs before the setTimeout so the segments are ready when the
        // output view renders. Never throws, returns [] on any failure.
        let refinedAnnotations = [];
        const annotate =
          root.TV.consumerEnhanceFlow &&
          root.TV.consumerEnhanceFlow.fetchLocalAnnotations;
        if (typeof annotate === "function" && refined) {
          try {
            refinedAnnotations = await annotate(
              refined,
              (_session && _session.original) || ""
            );
          } catch (_) { /* silent — local server may be offline */ }
        }

        setTimeout(() => {
          // Restore the suggestions surface before handing off to _onRefined.
          // _onRefined immediately swaps to the Output tab via showSessionShell,
          // but if that handler ever short-circuits (missing session, throws,
          // etc.) we'd otherwise be left with a blank panel until refresh.
          if (TP) TP.hide({ restoreSession: "suggestions" });
          try {
            _onRefined(refined, qaArray, refinedAnnotations);
          } catch (err) {
            console.warn("[suggestions-view] onRefined handler failed:", err);
          }
        }, 300);
        succeeded = true;
        return true;
      }
      cancelRef.cancelled = true;
      if (TP) TP.hide({ restoreSession: "suggestions" });
      return false;
    } catch (e) {
      cancelRef.cancelled = true;
      if (TP) TP.hide({ restoreSession: "suggestions" });
      console.warn("[suggestions-view] refine error:", e);
      return false;
    } finally {
      setBusy(false);
      if (!succeeded) {
        syncComposerFromAnswers();
      }
      if (root.TV.consumerComposerBar && typeof root.TV.consumerComposerBar.refreshSendState === "function") {
        root.TV.consumerComposerBar.refreshSendState();
      }
    }
  }

  async function submitRefine() {
    if (!canSubmitRefine()) return false;
    return runRefineRequest(buildQaArray());
  }

  function canSubmitCustomRefine() {
    return (
      _refineComposerActive &&
      _otherPendingKey == null &&
      _session != null &&
      Object.keys(_answers).length === 0
    );
  }

  async function submitCustomRefine(message) {
    const custom = String(message || "").trim();
    if (!custom || !canSubmitCustomRefine()) return false;
    const qaArray = [{ question: "Additional refinement", answer: custom }];
    return runRefineRequest(qaArray);
  }

  function shouldShowImproveButton() {
    // The Improve Prompt button is permanently retired in the Suggestions tab.
    // Users always see the regular composer input + send button instead, even
    // before any clarifying question is answered.
    return false;
  }

  function isRefineComposerActive() {
    return _refineComposerActive;
  }

  function activateImproveComposer() {
    _refineComposerActive = true;
    _composerUserEditing = false;
    _autoOpenActiveQuestion = true;
    if (_questions.length) {
      const firstUnanswered = _questions.findIndex((q, i) => !_answers[questionKey(q, i)]);
      _current = firstUnanswered >= 0 ? firstUnanswered : Math.min(_current, _questions.length - 1);
      expandActiveQuestion();
    }
    const ta = $("promptInput");
    if (ta) {
      ta.readOnly = false;
      if (!ta.value.trim()) {
        ta.placeholder = "Describe how to refine your prompt…";
      }
      try {
        ta.focus();
      } catch (_) {}
    }
    render();
    focusActiveQuestionControl();
    syncComposerFromAnswers();
    if (typeof root.TV.refreshSuggestionsComposerChrome === "function") {
      root.TV.refreshSuggestionsComposerChrome();
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────

  function render() {
    const scroll      = $("suggestionsScroll");
    const activePanel = $("suggestionsActivePanel");
    if (!scroll || !activePanel) return;

    // The scroll area no longer shows the ORIGINAL collapsible — hide it.
    scroll.innerHTML = "";
    scroll.hidden = true;

    activePanel.innerHTML = "";

    // — Active panel —
    const answeredCount = Object.keys(_answers).length;
    const total = Math.min(MAX_QUESTIONS, _questions.length || MAX_QUESTIONS);

    // Always-visible slim progress bar (replaces the full answer-saved toast box)
    activePanel.appendChild(buildProgressBar(answeredCount, total));

    activePanel.appendChild(buildImproveSectionTitle(answeredCount, total));

    if (_questions.length === 0) {
      const loading = document.createElement("p");
      loading.style.cssText = "font-size:0.72rem;color:var(--vel-muted-text);text-align:center;padding:1rem 0;";
      loading.textContent = "Loading suggestions…";
      activePanel.appendChild(loading);
    } else if (_current < _questions.length) {
      if (_autoOpenActiveQuestion) {
        expandActiveQuestion();
        _autoOpenActiveQuestion = false;
        focusActiveQuestionControl();
      }
      const q = _questions[_current];
      activePanel.appendChild(buildQACard(
        q, _current, _questions.length,
        handleSelect,
        () => {
          _otherPendingKey = null;
          if (_current > 0) {
            _current -= 1;
            _autoOpenActiveQuestion = true;
            render();
          }
        },
        () => {
          _otherPendingKey = null;
          if (_current < _questions.length - 1) {
            _current += 1;
            _autoOpenActiveQuestion = true;
            render();
          }
        },
        () => { hide(); }
      ));
    }

    // Glowing Refine CTA button — replaces the bottom composer input
    activePanel.appendChild(buildRefineButton(answeredCount, total));

    syncComposerFromAnswers();
  }

  function handleSelect(q, index, optText, optsContainer) {
    const key = questionKey(q, index);
    if (optText === OTHER_LABEL) {
      _otherPendingKey = key;
      render();
      return;
    }
    if (_otherPendingKey === key) _otherPendingKey = null;
    _answers[key] = optText;
    _refineComposerActive = true;
    if (optsContainer) {
      optsContainer.querySelectorAll(".qa-option").forEach((btn) => {
        const labelSpan = btn.querySelector("span:last-child");
        const btnLabel = labelSpan ? labelSpan.textContent : "";
        const selected = btnLabel === optText;
        btn.classList.toggle("qa-option--selected", selected);
        const dot = btn.querySelector(".qa-radio-dot");
        if (dot) dot.style.display = selected ? "block" : "none";
      });
    }
    syncComposerFromAnswers();
    window.setTimeout(() => {
      if (_current < _questions.length - 1) _current += 1;
      _autoOpenActiveQuestion = true;
      render();
    }, 380);
  }

  // ── Public API ───────────────────────────────────────────────────────────

  async function load(session) {
    _session   = session;
    _questions = [];
    _answers   = {};
    _current   = 0;
    _otherPendingKey = null;
    _refineComposerActive = true;
    _composerUserEditing = false;
    _autoOpenActiveQuestion = false;
    _expandedKeys.clear();
    const ta = $("promptInput");
    if (ta) {
      ta.readOnly = false;
      ta.value = "";
      ta.placeholder = REFINE_PLACEHOLDER;
      resetQaTextareaSize(ta);
    }
    render();

    try {
      const res = await sendMsg("TV_CONSUMER_CLARIFY", {
        original: (session && session.original) || "",
        enhanced: (session && session.enhanced) || "",
      });
      if (res && res.success) {
        const qs = (res.data && res.data.questions) || (Array.isArray(res.data) ? res.data : []);
        _questions = qs.slice(0, MAX_QUESTIONS);
        // Forward neuro state to context view so the Context tab can display it.
        if (root.TV.contextView && typeof root.TV.contextView.updateNeuro === "function") {
          root.TV.contextView.updateNeuro(
            res.data && res.data.neuro_state,
            res.data && res.data.context_patterns,
          );
        }
      }
    } catch (e) {
      console.warn("[suggestions-view] clarify error:", e);
    }
    render();
  }

  // The composer-dock is hidden while the suggestions view is active via a
  // CSS :has() rule injected in injectStyles() — no JS DOM walk needed.

  function show() {
    const view = $("viewSuggestions");
    if (view) { view.classList.add("view-surface--active"); view.hidden = false; }
    render();
    if (typeof root.TV.refreshSuggestionsComposerChrome === "function") {
      root.TV.refreshSuggestionsComposerChrome();
    }
  }

  function hide() {
    const view = $("viewSuggestions");
    if (view) { view.classList.remove("view-surface--active"); view.hidden = true; }
    _otherPendingKey = null;
    _refineComposerActive = false;
    _composerUserEditing = false;
    _autoOpenActiveQuestion = false;
    _expandedKeys.clear();
    const ta = $("promptInput");
    if (ta) {
      ta.readOnly = false;
      resetQaTextareaSize(ta);
    }
  }

  function onRefined(cb) { _onRefined = cb; }

  function isOtherPending() {
    return _otherPendingKey != null;
  }

  function bindComposerInputGuard() {
    const ta = $("promptInput");
    if (!ta || ta.dataset.suggestionsInputBound === "1") return;
    ta.dataset.suggestionsInputBound = "1";
    ta.addEventListener("input", () => {
      const sugView = $("viewSuggestions");
      const visible =
        sugView && !sugView.hidden && sugView.classList.contains("view-surface--active");
      if (!visible) return;
      if (_refineComposerActive && Object.keys(_answers).length === 0) {
        _composerUserEditing = true;
      }
      if (root.TV.consumerComposerBar && typeof root.TV.consumerComposerBar.refreshSendState === "function") {
        root.TV.consumerComposerBar.refreshSendState();
      }
    });
  }
  bindComposerInputGuard();

  root.TV.suggestionsView = {
    load,
    show,
    hide,
    onRefined,
    submitRefine,
    submitCustomRefine,
    canSubmitRefine,
    canSubmitCustomRefine,
    isOtherPending,
    shouldShowImproveButton,
    isRefineComposerActive,
    activateImproveComposer,
  };
})();
