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

  function normalizeOptions(q) {
    const raw = Array.isArray(q.options) && q.options.length
      ? q.options.map((o) => String(o).trim()).filter(Boolean)
      : ["Option A", "Option B", "Option C"];
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

  function buildAnswerSavedToast(answeredCount, total) {
    const toast = document.createElement("div");
    toast.className = "answer-saved-toast";

    const textBlock = document.createElement("div");
    textBlock.className = "answer-saved-text-block";
    const title = document.createElement("div");
    title.className = "answer-saved-title";
    title.textContent = "Answer saved.";
    const sub = document.createElement("div");
    sub.className = "answer-saved-sub";
    sub.textContent = "You can refine now, or answer more questions for a stronger result.";
    textBlock.appendChild(title);
    textBlock.appendChild(sub);

    toast.appendChild(textBlock);
    toast.appendChild(buildProgressRing(answeredCount, total));
    return toast;
  }

  function buildProgressRing(answeredCount, total) {
    const safeTotal = Math.max(1, Number(total) || 1);
    const safeAnswered = Math.min(safeTotal, Math.max(0, Number(answeredCount) || 0));
    const ratio = safeAnswered / safeTotal;

    const size = 56;
    const stroke = 4;
    const radius = (size - stroke) / 2;
    const circumference = 2 * Math.PI * radius;
    const dashOffset = circumference * (1 - ratio);

    const badge = document.createElement("div");
    badge.className = "progress-badge";
    badge.setAttribute("role", "img");
    badge.setAttribute(
      "aria-label",
      `Progress: ${safeAnswered} of ${safeTotal} answered`
    );

    const SVG_NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "progress-ring-svg");
    svg.setAttribute("width", String(size));
    svg.setAttribute("height", String(size));
    svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
    svg.setAttribute("aria-hidden", "true");

    const track = document.createElementNS(SVG_NS, "circle");
    track.setAttribute("class", "progress-ring-track");
    track.setAttribute("cx", String(size / 2));
    track.setAttribute("cy", String(size / 2));
    track.setAttribute("r", String(radius));
    track.setAttribute("fill", "none");
    track.setAttribute("stroke-width", String(stroke));

    const arc = document.createElementNS(SVG_NS, "circle");
    arc.setAttribute("class", "progress-ring-arc");
    arc.setAttribute("cx", String(size / 2));
    arc.setAttribute("cy", String(size / 2));
    arc.setAttribute("r", String(radius));
    arc.setAttribute("fill", "none");
    arc.setAttribute("stroke-width", String(stroke));
    arc.setAttribute("stroke-linecap", "round");
    arc.setAttribute("stroke-dasharray", String(circumference));
    arc.setAttribute("stroke-dashoffset", String(dashOffset));

    svg.appendChild(track);
    svg.appendChild(arc);

    const center = document.createElement("div");
    center.className = "progress-ring-center";
    const blbl = document.createElement("span");
    blbl.className = "progress-badge-label";
    blbl.textContent = "PROGRESS";
    const bval = document.createElement("span");
    bval.className = "progress-badge-value";
    bval.textContent = `${safeAnswered}/${safeTotal}`;
    center.appendChild(blbl);
    center.appendChild(bval);

    badge.appendChild(svg);
    badge.appendChild(center);
    return badge;
  }

  function buildQACard(q, index, total, onSelect, onPrev, onNext, onClose) {
    const key = questionKey(q, index);
    const optionsList = normalizeOptions(q);
    const currentAnswer = _answers[key];
    const pendingHere = _otherPendingKey === key;
    const showOtherField =
      pendingHere || isCustomOtherAnswer(q, index, currentAnswer);
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
        setTimeout(() => {
          // Restore the suggestions surface before handing off to _onRefined.
          // _onRefined immediately swaps to the Output tab via showSessionShell,
          // but if that handler ever short-circuits (missing session, throws,
          // etc.) we'd otherwise be left with a blank panel until refresh.
          if (TP) TP.hide({ restoreSession: "suggestions" });
          try {
            _onRefined(refined, qaArray);
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

    scroll.innerHTML      = "";
    activePanel.innerHTML = "";

    // — History scroll (ORIGINAL only; current/past answers use active panel + composer) —
    scroll.appendChild(buildOriginalCollapsible(_session && _session.original));

    // — Active panel —
    const answeredCount = Object.keys(_answers).length;
    const total = Math.min(MAX_QUESTIONS, _questions.length || MAX_QUESTIONS);

    if (answeredCount > 0) {
      activePanel.appendChild(buildAnswerSavedToast(answeredCount, total));
    }

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
      }
    } catch (e) {
      console.warn("[suggestions-view] clarify error:", e);
    }
    render();
  }

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
