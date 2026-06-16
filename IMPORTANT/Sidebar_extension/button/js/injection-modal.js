/**
 * Velocity prompt modal — Improve/Refine popup with light theme.
 * @global VelocityInjectionModal
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  const LOGIN_URL = "https://thinkvelocity.in/login";
  const PRO_URL = "https://thinkvelocity.in/";
  const GUEST_FREE_KEY = "velocity_guest_free_used";
  // One-shot flag: set the first time the user successfully completes an
  // enhance through this in-page modal so the celebration popup never re-fires.
  const FIRST_ENHANCE_KEY = "velocity_first_enhance_celebrated";

  const ENH_SPARKLE_SVG =
    '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
    '<path d="M12 3.5 13.4 8.6 18.5 10 13.4 11.4 12 16.5 10.6 11.4 5.5 10 10.6 8.6 12 3.5Z" fill="currentColor"/>' +
    '<path d="M18.5 14.5 19.15 16.4 21 17.05 19.15 17.7 18.5 19.55 17.85 17.7 16 17.05 17.85 16.4 18.5 14.5Z" fill="currentColor" opacity=".75"/>' +
    "</svg>";
  const EXPAND_SVG =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M4 9V4h5"/><path d="M20 9V4h-5"/><path d="M4 15v5h5"/><path d="M20 15v5h-5"/>' +
    "</svg>";
  const OPEN_SIDEBAR_SVG =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<rect x="3" y="4" width="18" height="16" rx="2"/>' +
    '<path d="M14 4v16"/>' +
    '<path d="M17 9l3 3-3 3"/>' +
    "</svg>";
  const CLOSE_SVG =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">' +
    '<path d="M6 6l12 12M18 6L6 18"/>' +
    "</svg>";

  let rootEl = null;
  let modalEl = null;
  let scrollEl = null;
  let toolbarEl = null;
  let composerEl = null;
  let remainingEl = null;
  let signInBtnEl = null;
  let isOpen = false;
  let activeTab = "improve";
  let snapshot = null;
  let currentPrompt = "";
  let improvedText = "";
  let currentPromptId = "";
  let onApplyCallback = null;
  let dragState = null;
  let guestFreeUsed = false;
  let docKeyListenerAdded = false;
  // Shared "thought-process" loader (same visual as sidebar enhance flow).
  // Held at module scope so runImprove() can advance/cancel/finish the
  // animation across the async boundary of the enhance API call.
  let thoughtLoaderInstance = null;
  let thoughtCancelRef = null;
  let annotatedSegments = [];

  // ── Annotated segments renderer (mirrors output-view.js) ─────────────────

  const _MODAL_SEG_COLORS = {
    indigo:  { bg: "#3730a3" },
    sky:     { bg: "#0369a1" },
    amber:   { bg: "#92400e" },
    emerald: { bg: "#065f46" },
    rose:    { bg: "#9f1239" },
    violet:  { bg: "#5b21b6" },
    purple:  { bg: "#6b21a8" },
    red:     { bg: "#991b1b" },
    orange:  { bg: "#9a3412" },
    teal:    { bg: "#115e59" },
    pink:    { bg: "#9d174d" },
    cyan:    { bg: "#155e75" },
    lime:    { bg: "#3f6212" },
    slate:   { bg: "#334155" },
    blue:    { bg: "#1e40af" },
    fuchsia: { bg: "#86198f" },
    green:   { bg: "#166534" },
  };

  let _modalSegTooltip = null;

  function _getModalTooltip() {
    if (_modalSegTooltip) return _modalSegTooltip;
    _modalSegTooltip = document.createElement("div");
    _modalSegTooltip.className = "vm-seg-tooltip";
    document.body.appendChild(_modalSegTooltip);
    return _modalSegTooltip;
  }

  function _showModalTooltip(target, label, reason) {
    const tip = _getModalTooltip();
    tip.innerHTML =
      '<div class="vm-seg-tooltip__label">' + esc(label) + "</div>" +
      '<div class="vm-seg-tooltip__reason">' + esc(reason) + "</div>";
    tip.style.display = "block";
    const rect = target.getBoundingClientRect();
    const vpW = window.innerWidth;
    const maxW = 260;
    let left = Math.min(rect.left, vpW - maxW - 8);
    if (left < 8) left = 8;
    tip.style.left = left + "px";
    tip.style.top = rect.top + "px";
    requestAnimationFrame(() => {
      const tipH = tip.offsetHeight;
      const above = rect.top - tipH - 8;
      tip.style.top = (above >= 4 ? above : rect.bottom + 8) + "px";
    });
  }

  function _hideModalTooltip() {
    if (_modalSegTooltip) _modalSegTooltip.style.display = "none";
  }

  function _segTextToHtml(text) {
    return esc(text)
      .replace(/\*\*(.+?)\*\*/gs, "<strong>$1</strong>")
      .replace(/\n/g, "<br>");
  }

  function buildModalAnnotatedBody(segments) {
    const container = document.createElement("div");
    container.className = "vm-annotated-body";
    for (const seg of segments) {
      if (!seg || !seg.text) continue;
      const span = document.createElement("span");
      if (seg.is_original) {
        span.className = "vm-seg vm-seg--original";
        span.innerHTML = _segTextToHtml(seg.text);
      } else {
        const colors = _MODAL_SEG_COLORS[seg.color_key] || _MODAL_SEG_COLORS.slate;
        span.className = "vm-seg";
        span.style.setProperty("--seg-bg", colors.bg);
        span.addEventListener("mouseenter", () =>
          _showModalTooltip(span, seg.technique_label || seg.technique || "", seg.reason || "")
        );
        span.addEventListener("mouseleave", _hideModalTooltip);
        span.innerHTML = _segTextToHtml(seg.text);
      }
      container.appendChild(span);
    }
    return container;
  }

  function send(action, payload) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(
        { action, requestId: "vm-" + Date.now(), payload: payload || {} },
        (raw) => {
          const le = chrome.runtime.lastError;
          if (le) return reject(new Error(le.message));
          if (!raw || raw.success === false) {
            const err = (raw && raw.error) || {};
            const e = new Error(err.message || "Request failed");
            e.code = err.code;
            return reject(e);
          }
          resolve(raw.data || {});
        }
      );
    });
  }

  function isChatGPTHost() {
    try {
      const h = (location.hostname || "").toLowerCase();
      return (
        h === "chatgpt.com" ||
        h.endsWith(".chatgpt.com") ||
        h === "chat.openai.com" ||
        h.endsWith(".chat.openai.com")
      );
    } catch (_) {
      return false;
    }
  }

  /**
   * One-shot first-enhance celebration popup (bottom-right overlay).
   * Fires only on ChatGPT and only the very first time the user completes a
   * successful enhance through this modal. Subsequent enhances no-op.
   */
  function maybeCelebrateFirstEnhance() {
    if (!isChatGPTHost()) return;
    const popups = root.VelocityInjectionPopups;
    if (!popups || typeof popups.showFirstEnhancePopup !== "function") return;
    try {
      if (!chrome || !chrome.storage || !chrome.storage.local) return;
      chrome.storage.local.get([FIRST_ENHANCE_KEY], (r) => {
        if (chrome.runtime.lastError) return;
        if (r && r[FIRST_ENHANCE_KEY]) return;
        try {
          chrome.storage.local.set({ [FIRST_ENHANCE_KEY]: true });
        } catch (_) {}
        try {
          popups.showFirstEnhancePopup();
        } catch (_) {}
      });
    } catch (_) {}
  }

  /**
   * Daily-limit / out-of-tokens popup. Fired on every USAGE_EXHAUSTED enhance
   * attempt — the popup module itself replaces any prior instance so repeated
   * attempts re-animate cleanly.
   */
  function showDailyLimitOverlay() {
    const popups = root.VelocityInjectionPopups;
    if (!popups || typeof popups.showDailyLimitPopup !== "function") return;
    try { popups.showDailyLimitPopup(); } catch (_) {}
  }

  /**
   * Like-reward incentive popup. Fires on every fresh thumbs-up — surfaces
   * the invite-a-friend program as a way to earn bonus "incentive prompts".
   * The popup module itself replaces any prior instance so repeated likes
   * re-animate cleanly without stacking.
   */
  function triggerLikeReward() {
    const popups = root.VelocityInjectionPopups;
    if (!popups || typeof popups.showLikeRewardPopup !== "function") return;
    try { popups.showLikeRewardPopup(); } catch (_) {}
  }

  function readGuestFreeUsed() {
    return new Promise((resolve) => {
      try {
        if (!chrome || !chrome.storage || !chrome.storage.local) {
          resolve(false);
          return;
        }
        chrome.storage.local.get([GUEST_FREE_KEY], (r) => {
          if (chrome.runtime.lastError) {
            resolve(false);
            return;
          }
          resolve(Boolean(r && r[GUEST_FREE_KEY]));
        });
      } catch (_) {
        resolve(false);
      }
    });
  }

  async function loadSnapshot() {
    try {
      snapshot = await send("TV_AUTH_GET_SNAPSHOT", { force: false });
    } catch (_) {
      snapshot = { isLoggedIn: false, isProUser: false, remainingUsage: null };
    }
    if (!snapshot || !snapshot.isLoggedIn) {
      guestFreeUsed = await readGuestFreeUsed();
    } else {
      guestFreeUsed = false;
    }
    return snapshot;
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  function plainTextToEditorHtml(text) {
    const t = String(text || "").trim();
    if (!t) return "";
    return "<p>" + esc(t).replace(/\n\n+/g, "</p><p>").replace(/\n/g, "<br>") + "</p>";
  }

  /**
   * Render `improvedText` (raw markdown from the enhance API) into `editor`
   * using the shared structured DOM renderer that mirrors the side panel's
   * Output tab — `**bold**` → `<strong>`, `**Section**: body` → section heads,
   * `1. ` numbered rows, `- ` bullets, paragraphs.
   */
  function renderEditorView(editor) {
    if (!editor) return;
    while (editor.firstChild) editor.removeChild(editor.firstChild);
    const spd = globalThis.TV && globalThis.TV.structuredPromptDom;
    if (spd && typeof spd.appendFormatted === "function") {
      spd.appendFormatted(editor, improvedText);
    } else {
      editor.innerHTML = plainTextToEditorHtml(improvedText);
    }
  }

  /**
   * Walk an inline container (paragraph / bullet body / num body) and
   * reconstruct its source text. `<strong class="fmt-strong">` round-trips
   * back to `**…**`; `<br>` becomes a soft newline.
   */
  function serializeInlineNode(node) {
    if (!node) return "";
    let out = "";
    node.childNodes.forEach((child) => {
      if (child.nodeType === 3) {
        out += child.nodeValue || "";
        return;
      }
      if (child.nodeType !== 1) return;
      const el = child;
      const tag = (el.tagName || "").toUpperCase();
      if (tag === "BR") {
        out += "\n";
        return;
      }
      if (
        tag === "STRONG" ||
        tag === "B" ||
        (el.classList && el.classList.contains("fmt-strong"))
      ) {
        const inner = serializeInlineNode(el).trim();
        if (inner) out += "**" + inner + "**";
        return;
      }
      out += serializeInlineNode(el);
    });
    return out;
  }

  /**
   * Reverse of `appendFormatted` — read the structured editor DOM and emit
   * the same markdown-ish source the enhance API returns, so the user's edits
   * round-trip without losing headings / numbered lists / bullets.
   */
  function serializeFormattedEditor(editor) {
    if (!editor) return "";
    const wrap = editor.querySelector(".formatted-content");
    if (!wrap) {
      const fallback = (editor.innerText || editor.textContent || "").trim();
      return fallback;
    }
    const parts = [];
    wrap.childNodes.forEach((node) => {
      if (node.nodeType !== 1) return;
      const el = node;
      if (el.classList.contains("fmt-section-head")) {
        const label = (el.textContent || "").trim();
        if (label) parts.push("**" + label + "**");
        return;
      }
      if (el.classList.contains("fmt-paragraph")) {
        const inline = serializeInlineNode(el).trim();
        if (inline) parts.push(inline);
        return;
      }
      if (el.classList.contains("fmt-num-row")) {
        const numEl = el.querySelector(".fmt-num");
        const bodyEl = el.querySelector(".fmt-num-body");
        const num = numEl ? (numEl.textContent || "").trim() : "";
        const body = bodyEl ? serializeInlineNode(bodyEl).trim() : (el.textContent || "").trim();
        parts.push((num ? num + " " : "") + body);
        return;
      }
      if (el.classList.contains("fmt-bullet-row")) {
        const bodyEl = el.querySelector(".fmt-bullet-body");
        const body = bodyEl ? serializeInlineNode(bodyEl).trim() : (el.textContent || "").trim();
        parts.push("- " + body);
        return;
      }
      const text = (el.textContent || "").trim();
      if (text) parts.push(text);
    });
    return parts.filter(Boolean).join("\n\n");
  }

  function placeCaretAtEnd(el) {
    if (!el) return;
    try {
      el.focus();
      const range = document.createRange();
      range.selectNodeContents(el);
      range.collapse(false);
      const sel = window.getSelection();
      if (sel) {
        sel.removeAllRanges();
        sel.addRange(range);
      }
    } catch (_) {}
  }

  /**
   * If the editor is in edit mode, flush its current DOM into `improvedText`.
   * Used by Insert / Save / Copy so they always read the latest user edits.
   */
  function commitEditorEdits() {
    const editor = scrollEl && scrollEl.querySelector("[data-editor]");
    if (!editor || !editor.classList.contains("is-editing")) return;
    const next = serializeFormattedEditor(editor).trim();
    if (next) improvedText = next;
  }

  /**
   * Convert raw markdown enhance output → paste-ready text that LLM chat
   * inputs render as plain prose (no literal `**`/`#`). Falls back to the raw
   * text if `TV.promptFormat` is not yet loaded.
   */
  function pasteFriendlyText(raw) {
    const t = String(raw || "");
    if (!t) return "";
    const pf = globalThis.TV && globalThis.TV.promptFormat;
    if (pf && typeof pf.formatForExternalPaste === "function") {
      try {
        const formatted = pf.formatForExternalPaste(t);
        if (formatted) return formatted;
      } catch (_) {}
    }
    return t;
  }

  function formatRemainingLabel() {
    if (!snapshot || !snapshot.isLoggedIn) return "";
    if (snapshot.isProUser) return "Unlimited";
    const n = snapshot.remainingUsage;
    if (n == null || n === "") return "";
    return String(n) + " Remaining";
  }

  function updateHeaderAuth() {
    if (!remainingEl) return;
    const label = formatRemainingLabel();
    if (label) {
      remainingEl.innerHTML = "<strong>" + esc(label) + "</strong>";
      remainingEl.style.display = "inline";
    } else {
      // Always show "Unlimited" for pro or fallback
      remainingEl.innerHTML = "<strong>Unlimited</strong>";
      remainingEl.style.display = "inline";
    }
  }

  function setToolbarVisible(show) {
    if (toolbarEl) toolbarEl.classList.toggle("is-hidden", !show);
  }

  function setComposerVisible(show) {
    if (composerEl) composerEl.classList.toggle("is-hidden", !show);
  }

  function setResultHeightEnabled(enabled) {
    if (modalEl) modalEl.classList.toggle("is-result-height", !!enabled);
  }


  function onEditClick() {
    const editor = scrollEl && scrollEl.querySelector("[data-editor]");
    if (!editor) return;
    const editBtn = rootEl && rootEl.querySelector("[data-edit]");
    const isEditing = editor.classList.contains("is-editing");

    if (!isEditing) {
      editor.classList.add("is-editing");
      if (editBtn) editBtn.classList.add("is-active");

      // Replace HTML body with a raw markdown textarea
      editor.innerHTML = "";
      const textarea = document.createElement("textarea");
      textarea.className = "velocity-injection-modal-editor-textarea";
      textarea.setAttribute("data-editor-textarea", "true");
      textarea.setAttribute("spellcheck", "true");
      textarea.setAttribute("aria-label", "Edit improved prompt");
      textarea.value = improvedText;
      editor.appendChild(textarea);
      // Auto-size to content
      textarea.style.height = "auto";
      textarea.style.height = textarea.scrollHeight + "px";
      textarea.addEventListener("input", () => {
        textarea.style.height = "auto";
        textarea.style.height = textarea.scrollHeight + "px";
      });
      textarea.focus();
      return;
    }

    const textarea = editor.querySelector("[data-editor-textarea]");
    if (textarea) {
      improvedText = textarea.value.trim();
    }
    
    editor.classList.remove("is-editing");
    if (editBtn) editBtn.classList.remove("is-active");

    // Re-render formatted HTML
    renderEditorView(editor);
  }

  async function onSaveClick() {
    const saveBtn = rootEl && rootEl.querySelector("[data-save]");
    if (!saveBtn || saveBtn.classList.contains("is-saving")) return;
    commitEditorEdits();
    saveBtn.classList.add("is-saving");
    try {
      await send("TV_CONSUMER_CREATE_COLLECTION", { 
        name: "My Prompts",
        description: improvedText ? improvedText.slice(0, 100) : "Enhanced prompt"
      });
      saveBtn.classList.remove("is-saving");
      saveBtn.classList.add("is-saved");
      setTimeout(() => saveBtn.classList.remove("is-saved"), 1500);
    } catch (err) {
      saveBtn.classList.remove("is-saving");
      saveBtn.classList.add("is-error");
      setTimeout(() => saveBtn.classList.remove("is-error"), 1500);
    }
  }

  function onCopyClick() {
    commitEditorEdits();
    const raw = improvedText || currentPrompt;
    if (!raw) return;
    const text = pasteFriendlyText(raw);
    try {
      navigator.clipboard.writeText(text);
      flashButton("[data-copy]");
    } catch (_) {}
  }

  function onFeedbackClick(type) {
    const btn = rootEl && rootEl.querySelector("[data-" + type + "]");
    if (!btn) return;
    if (btn.classList.contains("is-active")) return;
    btn.classList.add("is-active");
    const otherType = type === "like" ? "dislike" : "like";
    const otherBtn = rootEl && rootEl.querySelector("[data-" + otherType + "]");
    if (otherBtn) otherBtn.classList.remove("is-active");
    
    if (type === "like") {
      send("TV_CONSUMER_FEEDBACK", {
        promptId: currentPromptId,
        feedback: "like",
        mode: "standard",
        isRefine: false,
      }).catch(() => {});
      triggerLikeReward();
    } else {
      send("TV_CONSUMER_FEEDBACK", {
        promptId: currentPromptId,
        feedback: "dislike",
        mode: "standard",
        isRefine: false,
      }).catch(() => {});
      showFeedbackPopup();
    }
  }

  function showFeedbackPopup() {
    if (scrollEl.querySelector(".velocity-injection-modal-feedback-form")) return;
    const form = document.createElement("div");
    form.className = "velocity-injection-modal-feedback-form";
    form.innerHTML =
      '<div class="velocity-injection-modal-feedback-header">' +
      '<span class="velocity-injection-modal-feedback-title">What could be better?</span>' +
      '<button type="button" class="velocity-injection-modal-feedback-close" data-feedback-close>&times;</button>' +
      '</div>' +
      '<textarea class="velocity-injection-modal-feedback-textarea" data-feedback-text placeholder="Tell us how we can improve..." rows="3"></textarea>' +
      '<div class="velocity-injection-modal-feedback-footer">' +
      '<span class="velocity-injection-modal-feedback-status" data-feedback-status></span>' +
      '<button type="button" class="velocity-injection-modal-feedback-send" data-feedback-send>Send Feedback</button>' +
      '</div>';
    scrollEl.insertBefore(form, scrollEl.firstChild);
    
    const textarea = form.querySelector("[data-feedback-text]");
    const closeBtn = form.querySelector("[data-feedback-close]");
    const sendBtn = form.querySelector("[data-feedback-send]");
    const statusEl = form.querySelector("[data-feedback-status]");
    
    textarea.focus();
    sendBtn.disabled = true;
    
    textarea.addEventListener("input", () => {
      sendBtn.disabled = !textarea.value.trim();
    });
    
    closeBtn.addEventListener("click", () => {
      form.remove();
      const dislikeBtn = rootEl && rootEl.querySelector("[data-dislike]");
      if (dislikeBtn) dislikeBtn.classList.remove("is-active");
    });
    
    textarea.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        form.remove();
        const dislikeBtn = rootEl && rootEl.querySelector("[data-dislike]");
        if (dislikeBtn) dislikeBtn.classList.remove("is-active");
      }
    });
    
    sendBtn.addEventListener("click", async () => {
      const text = textarea.value.trim();
      if (!text) return;
      sendBtn.disabled = true;
      statusEl.textContent = "Sending...";
      statusEl.className = "velocity-injection-modal-feedback-status";
      try {
        await send("TV_CONSUMER_SUBMIT_FEEDBACK", {
          feedback: text,
          reason: "Enhancement dislike",
          source: "injection_modal"
        });
        statusEl.textContent = "Thanks for your feedback!";
        statusEl.classList.add("is-success");
        setTimeout(() => form.remove(), 900);
      } catch (err) {
        statusEl.textContent = "Failed to send. Try again.";
        statusEl.classList.add("is-error");
        sendBtn.disabled = false;
      }
    });
  }

  function flashButton(selector) {
    const btn = rootEl && rootEl.querySelector(selector);
    if (!btn) return;
    btn.classList.add("is-flash");
    setTimeout(() => btn.classList.remove("is-flash"), 600);
  }


  function ensureDom() {
    if (rootEl && document.body.contains(rootEl)) return;

    rootEl = document.createElement("div");
    rootEl.className = "velocity-injection-modal-root";
    rootEl.innerHTML =
      '<div class="velocity-injection-modal-backdrop" data-backdrop></div>' +
      '<div class="velocity-injection-modal" role="dialog" aria-modal="true" aria-label="Velocity prompt enhancer">' +
      '<header class="velocity-injection-modal-header">' +
      '<div class="velocity-injection-modal-header-row">' +
      '<div class="velocity-injection-modal-brand">' +
      '<span class="velocity-injection-modal-brand-ico">✨</span>' +
      '<span class="velocity-injection-modal-brand-name">Velocity</span>' +
      '</div>' +
      '<div class="velocity-injection-modal-drag" title="Drag">' +
      '<span class="velocity-injection-modal-drag-dots">' +
      "<span></span><span></span><span></span><span></span><span></span><span></span>" +
      "</span></div>" +
      '<div class="velocity-injection-modal-header-actions">' +
      '<span class="velocity-injection-modal-remaining" data-remaining><strong>Unlimited</strong></span>' +
      '<button type="button" class="velocity-injection-modal-icon-btn" data-open-sidebar title="Open in Velocity sidebar" aria-label="Open in Velocity sidebar">' + OPEN_SIDEBAR_SVG + '</button>' +
      '<button type="button" class="velocity-injection-modal-icon-btn" data-close title="Close">' + CLOSE_SVG + '</button>' +
      "</div></div>" +
      "</header>" +
      '<div class="velocity-injection-modal-body">' +
      '<div class="velocity-injection-modal-scroll" data-scroll></div></div>' +
      '<div class="velocity-injection-modal-composer" data-composer>' +
      '<div class="velocity-injection-modal-composer-actions" data-toolbar>' +
      '<button type="button" class="velocity-injection-modal-feedback-btn" data-like title="Like">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/><path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>' +
      '</button>' +
      '<button type="button" class="velocity-injection-modal-feedback-btn" data-dislike title="Dislike">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M10 15V19a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/><path d="M17 2h3a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-3"/></svg>' +
      '</button>' +
      '<button type="button" class="velocity-injection-modal-feedback-btn velocity-injection-modal-toolbar-btn" data-edit title="Edit">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h4.5L20 8.5 15.5 4 4 15.5V20z"/><path d="M13.5 6 18 10.5"/></svg>' +
      '</button>' +
      '<button type="button" class="velocity-injection-modal-feedback-btn velocity-injection-modal-toolbar-btn" data-save title="Save to Collection">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 10v6"/><path d="M9 13h6"/><path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/></svg>' +
      '</button>' +
      '<button type="button" class="velocity-injection-modal-feedback-btn velocity-injection-modal-toolbar-btn" data-copy title="Copy">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg>' +
      '</button>' +
      '</div>' +
      '<button type="button" class="velocity-injection-modal-apply" data-apply>' +
      '<span class="apply-label">Insert</span><span class="apply-hint">Ctrl+Enter</span></button>' +
      "</div></div>";

    document.body.appendChild(rootEl);
    modalEl = rootEl.querySelector(".velocity-injection-modal");
    scrollEl = rootEl.querySelector("[data-scroll]");
    toolbarEl = rootEl.querySelector("[data-toolbar]");
    composerEl = rootEl.querySelector("[data-composer]");
    remainingEl = rootEl.querySelector("[data-remaining]");
    signInBtnEl = rootEl.querySelector("[data-signin]");

    const proTheme = globalThis.VelocityInjectionProTheme;
    if (proTheme && typeof proTheme.register === "function") {
      try { proTheme.register(rootEl); } catch (_) {}
    }

    try {
      if (chrome && chrome.storage && chrome.storage.local) {
        chrome.storage.local.get(['velocity_theme_preference'], (res) => {
          if (res && res.velocity_theme_preference === 'light') {
            rootEl.classList.add('light-mode');
          }
        });
        chrome.storage.onChanged.addListener((changes, namespace) => {
          if (namespace === 'local' && changes.velocity_theme_preference) {
            rootEl.classList.toggle('light-mode', changes.velocity_theme_preference.newValue === 'light');
          }
        });
      }
    } catch (_) {}

    // Intentionally no click-to-close on the backdrop: the modal must persist
    // through stray misclicks on the host page. The user explicitly dismisses
    // via the close (X) button or the Escape key.
    rootEl.querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", close));

    const openSidebarBtn = rootEl.querySelector("[data-open-sidebar]");
    if (openSidebarBtn) {
      openSidebarBtn.addEventListener("click", onOpenSidebarClick);
    }

    // signInBtnEl is only shown in the empty state now; handled via event delegation on scrollEl

    rootEl.querySelectorAll("[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeTab = btn.getAttribute("data-tab");
        render();
      });
    });

    rootEl.querySelector("[data-edit]").addEventListener("click", onEditClick);
    rootEl.querySelector("[data-save]").addEventListener("click", onSaveClick);
    rootEl.querySelector("[data-copy]").addEventListener("click", onCopyClick);
    rootEl.querySelector("[data-like]").addEventListener("click", () => onFeedbackClick("like"));
    rootEl.querySelector("[data-dislike]").addEventListener("click", () => onFeedbackClick("dislike"));

    const applyBtn = rootEl.querySelector("[data-apply]");
    applyBtn.addEventListener("click", onApplyClick);

    const dragHandle = rootEl.querySelector(".velocity-injection-modal-drag");
    const DRAG_VIEWPORT_MARGIN = 8;
    dragHandle.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      const rect = modalEl.getBoundingClientRect();
      dragState = {
        id: e.pointerId,
        ox: e.clientX - rect.left,
        oy: e.clientY - rect.top,
        // Cache the modal size at drag-start so we can clamp against the
        // right/bottom viewport edges on every pointermove without paying
        // for a layout read each frame.
        w: rect.width,
        h: rect.height,
      };
      modalEl.style.position = "fixed";
      modalEl.style.left = rect.left + "px";
      modalEl.style.top = rect.top + "px";
      modalEl.style.margin = "0";
      modalEl.classList.add("is-dragging");
      try { dragHandle.setPointerCapture(e.pointerId); } catch (_) {}
    });
    dragHandle.addEventListener("pointermove", (e) => {
      if (!dragState || e.pointerId !== dragState.id) return;
      const m = DRAG_VIEWPORT_MARGIN;
      // Clamp on both axes: keep the modal fully inside the viewport. If the
      // modal is somehow larger than the viewport (small windows + is-large),
      // Math.max guards against a negative max that would otherwise pin the
      // modal in a position the user couldn't drag back from.
      const maxLeft = Math.max(m, window.innerWidth - dragState.w - m);
      const maxTop = Math.max(m, window.innerHeight - dragState.h - m);
      const nextLeft = Math.min(maxLeft, Math.max(m, e.clientX - dragState.ox));
      const nextTop = Math.min(maxTop, Math.max(m, e.clientY - dragState.oy));
      modalEl.style.left = nextLeft + "px";
      modalEl.style.top = nextTop + "px";
    });
    const endDrag = (e) => {
      if (!dragState || (e.pointerId != null && e.pointerId !== dragState.id)) return;
      dragState = null;
      modalEl.classList.remove("is-dragging");
    };
    dragHandle.addEventListener("pointerup", endDrag);
    dragHandle.addEventListener("pointercancel", endDrag);

    if (!docKeyListenerAdded) {
      docKeyListenerAdded = true;
      document.addEventListener("keydown", (e) => {
        if (!isOpen) return;
        if (e.key === "Escape") {
          close();
          return;
        }
        if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
          e.preventDefault();
          onApplyClick();
        }
      });
    }
  }

  function renderTabs() {
    const tabs = rootEl.querySelectorAll("[data-tab]");
    tabs.forEach((btn) => {
      const id = btn.getAttribute("data-tab");
      btn.classList.toggle("is-active", id === activeTab);
    });
  }

  function renderEmpty() {
    setResultHeightEnabled(false);
    setToolbarVisible(false);
    setComposerVisible(false);
    const signedIn = snapshot && snapshot.isLoggedIn;
    scrollEl.innerHTML =
      '<div class="velocity-injection-modal-center">' +
      '<div class="velocity-injection-modal-empty-ico">' + ENH_SPARKLE_SVG + "</div>" +
      '<h2 class="velocity-injection-modal-title">No prompt found</h2>' +
      '<p class="velocity-injection-modal-text">Start writing your prompt in the chat box and click Improve to enhance it.</p>' +
      (!signedIn ? '<button type="button" class="velocity-injection-modal-free-prompts-cta" data-signin-empty>✦ Get Free Prompts</button>' : '') +
      '<button type="button" class="velocity-injection-modal-explore-btn" data-explore-prompts>' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>' +
      'Explore Prompts</button>' +
      "</div>";
    const signinEmptyBtn = scrollEl.querySelector("[data-signin-empty]");
    if (signinEmptyBtn) {
      signinEmptyBtn.addEventListener("click", () => {
        send("TV_AUTH_OPEN_LOGIN", {}).catch(() => window.open(LOGIN_URL, "_blank"));
      });
    }
    const exploreBtn = scrollEl.querySelector("[data-explore-prompts]");
    if (exploreBtn) {
      exploreBtn.addEventListener("click", () => {
        const hp = globalThis.VelocityHostPlatforms;
        const platform = hp && typeof hp.detectPlatform === "function" ? hp.detectPlatform() || "" : "";
        const requestId = "inj-explore-library-" + Date.now();
        try {
          chrome.runtime.sendMessage(
            { action: "TV_OPEN_SIDE_PANEL", requestId, payload: { source: "injection_modal_explore", platform, target: "library" } },
            (response) => {
              const lastErr = chrome.runtime.lastError;
              if (lastErr) { console.error("[Velocity] explore-prompts runtime error:", lastErr.message); return; }
              if (response && response.success) { close(); }
            }
          );
        } catch (err) {
          console.error("[Velocity] explore-prompts threw:", err);
        }
      });
    }
  }

  function renderSignInWall(opts) {
    const o = opts || {};
    setResultHeightEnabled(false);
    setToolbarVisible(false);
    setComposerVisible(false);
    let title = "Sign in to Velocity";
    let body = "Create a free account to start improving your prompts.";
    if (o.refineGate) {
      title = "Sign in to refine";
      body = "Refining prompts requires a free account.";
    } else if (o.usedFree) {
      title = "You\u2019ve used your free prompt";
      body = "Sign in to keep improving prompts with Velocity.";
    }
    scrollEl.innerHTML =
      '<div class="velocity-injection-modal-center">' +
      '<h2 class="velocity-injection-modal-title">' + esc(title) + "</h2>" +
      '<p class="velocity-injection-modal-text">' + esc(body) + "</p>" +
      '<button type="button" class="velocity-injection-modal-btn-primary" data-signin-body>Sign In to Velocity</button>' +
      "</div>";
    scrollEl.querySelector("[data-signin-body]").addEventListener("click", () => {
      send("TV_AUTH_OPEN_LOGIN", {}).catch(() => window.open(LOGIN_URL, "_blank"));
    });
  }

  /**
   * Render the shared 5-step "Velocity Thought Process" loader inside the
   * modal scroll area — same visual the side-panel composer shows while
   * enhance is running. Returns the promise from the visual animation so
   * callers can `await` it before flipping to the result UI.
   *
   * If `TV.thoughtProcessLoader` is unavailable (script load order glitch),
   * falls back to a minimal "Improving your prompt…" label so the modal
   * never appears frozen.
   */
  function showLoading() {
    setResultHeightEnabled(false);
    setToolbarVisible(false);
    setComposerVisible(false);

    scrollEl.innerHTML =
      '<div class="thought-process-panel">' +
      '<div class="thought-process-heading">' +
      '<div class="thought-process-dot" aria-hidden="true"></div>' +
      '<h2 class="thought-process-title">Velocity Thought Process</h2>' +
      "</div>" +
      '<div class="thought-steps-list" data-thought-steps></div>' +
      "</div>";

    const listEl = scrollEl.querySelector("[data-thought-steps]");
    const Loader = globalThis.TV && globalThis.TV.thoughtProcessLoader;
    if (Loader && typeof Loader.createInstance === "function" && listEl) {
      thoughtLoaderInstance = Loader.createInstance(listEl);
      thoughtCancelRef = { cancelled: false };
      return thoughtLoaderInstance.advanceVisualToFinalizingRunning(thoughtCancelRef);
    }
    thoughtLoaderInstance = null;
    thoughtCancelRef = null;
    scrollEl.innerHTML +=
      '<p class="velocity-injection-modal-loading-label">Improving your prompt…</p>';
    return Promise.resolve();
  }

  function cancelLoadingVisual() {
    if (thoughtCancelRef) thoughtCancelRef.cancelled = true;
    thoughtCancelRef = null;
    thoughtLoaderInstance = null;
  }

  function resetFeedbackButtons() {
    if (!rootEl) return;
    const likeBtn = rootEl.querySelector("[data-like]");
    const dislikeBtn = rootEl.querySelector("[data-dislike]");
    if (likeBtn) likeBtn.classList.remove("is-active");
    if (dislikeBtn) dislikeBtn.classList.remove("is-active");
  }

  function renderImproveResult() {
    setResultHeightEnabled(true);
    setToolbarVisible(true);
    setComposerVisible(true);
    resetFeedbackButtons();
    scrollEl.innerHTML =
      '<div class="velocity-injection-modal-editor" data-editor></div>';
    const editor = scrollEl.querySelector("[data-editor]");
    // Always render as plain/formatted text — no annotation highlights
    renderEditorView(editor);
  }

  async function runImprove() {
    // Kick off the 5-step visual in parallel with the network call so the
    // user sees the same animated thought-process the sidebar shows.
    const visualDone = showLoading();
    const instance = thoughtLoaderInstance;
    try {
      const data = await send("TV_CONSUMER_ENHANCE", { prompt: currentPrompt, mode: "standard" });
      improvedText = String((data && data.enhanced_prompt) || "").trim();
      if (!improvedText) throw new Error("No improved text returned");
      currentPromptId = String((data && (data.prompt_id || data.enhanced_prompt_id || data.id)) || "").trim();
      annotatedSegments = Array.isArray(data && data.annotated_segments) ? data.annotated_segments : [];
      if (data && data.is_guest) guestFreeUsed = true;
      await loadSnapshot();
      updateHeaderAuth();
      // Let the visual reach the final step before flipping to the result so
      // it doesn't snap mid-animation.
      try { await visualDone; } catch (_) {}
      if (instance && typeof instance.markAllStepsDone === "function") {
        instance.markAllStepsDone();
      }
      // Brief "all done" pause mirrors the sidebar's POST_DONE_MS handoff.
      setTimeout(() => {
        if (!isOpen) return;
        cancelLoadingVisual();
        renderImproveResult();
        // Fire the one-shot first-enhance celebration once the result is
        // visible so the popup feels like a reward, not a pre-emptive flash.
        maybeCelebrateFirstEnhance();
      }, 300);
    } catch (err) {
      cancelLoadingVisual();
      setResultHeightEnabled(false);
      setToolbarVisible(false);
      setComposerVisible(false);
      if (err.code === "USAGE_EXHAUSTED") {
        scrollEl.innerHTML =
          '<div class="velocity-injection-modal-center">' +
          '<h2 class="velocity-injection-modal-title">You\u2019ve used all free prompts</h2>' +
          '<p class="velocity-injection-modal-text">Upgrade to Pro for unlimited enhancements.</p>' +
          '<button type="button" class="velocity-injection-modal-btn-primary" data-pro>Upgrade to Pro</button></div>';
        scrollEl.querySelector("[data-pro]").addEventListener("click", () => window.open(PRO_URL, "_blank"));
        // Surface the same daily-limit signal as a bottom-right overlay so
        // the user can't miss it — popup carries the richer feature list +
        // invite-a-friend CTA the inline message lacks.
        showDailyLimitOverlay();
      } else {
        scrollEl.innerHTML =
          '<div class="velocity-injection-modal-center">' +
          '<p class="velocity-injection-modal-text">' + esc(err.message || "Could not improve prompt") + "</p></div>";
      }
    }
  }

  function onApplyClick() {
    commitEditorEdits();
    const raw = improvedText || currentPrompt;
    const text = pasteFriendlyText(raw);
    if (text && onApplyCallback) onApplyCallback(text);
    close();
  }

  /**
   * Hand the current prompt off to the Velocity side panel.
   *
   * State flow:
   *   1. If the editor is in "edit" mode we first flush the in-progress
   *      textarea into `improvedText` so the user's unsaved edits travel too.
   *   2. Send the original user prompt separately from the enhanced result.
   *      The side panel uses that pair to rehydrate the Output session without
   *      calling /enhance again.
   *   3. Send the existing TV_OPEN_SIDE_PANEL message — the background
   *      validates the sender, opens the side panel synchronously (gesture
   *      safe), and writes `velocity_button_pending_prompt` to storage; the
   *      side panel's `applyPendingInjectionAction` then pre-fills the
   *      composer on the next render.
   *   4. Close the modal only after a successful response so a failed open
   *      (e.g. UNAUTHORIZED_SENDER) leaves the user where they were and they
   *      can retry. We disable the button while the request is in-flight to
   *      prevent double-fires that would queue up storage writes.
   */
  function onOpenSidebarClick(e) {
    const btn = e && e.currentTarget;
    if (btn && btn.disabled) return;

    const editor = scrollEl && scrollEl.querySelector("[data-editor]");
    if (editor && editor.classList.contains("is-editing")) {
      const ta = editor.querySelector("[data-editor-textarea]");
      if (ta) improvedText = ta.value.trim();
    }

    const originalPrompt = String(currentPrompt || "").trim();
    const enhancedPrompt = String(improvedText || "").trim();
    const prompt = originalPrompt || enhancedPrompt;
    if (!prompt) {
      console.warn("[Velocity] open-sidebar: nothing to hand off");
      return;
    }

    const hp = globalThis.VelocityHostPlatforms;
    const platform =
      hp && typeof hp.detectPlatform === "function" ? hp.detectPlatform() || "" : "";
    const requestId = "inj-open-sidebar-" + Date.now();
    // Pass BOTH the original prompt and the already-enhanced result so the
    // side panel can open straight into the session/Output view using the
    // existing enhancement — no fresh /enhance call, no extra usage tick.
    // Important: `prompt` intentionally stays the ORIGINAL user prompt for
    // the legacy sidebar pre-fill path. The enhanced result must only travel
    // via `enhanced`; otherwise the sidebar can accidentally enhance the
    // enhanced prompt if it falls back to composer pre-fill.
    const payload = {
      source: "injection_modal_open_sidebar",
      platform,
      target: "enhance",
      prompt,
      original: originalPrompt,
      enhanced: enhancedPrompt,
      mode: "standard",
    };

    if (btn) {
      btn.disabled = true;
      btn.setAttribute("aria-busy", "true");
    }

    try {
      chrome.runtime.sendMessage(
        { action: "TV_OPEN_SIDE_PANEL", requestId, payload },
        (response) => {
          if (btn) {
            btn.disabled = false;
            btn.removeAttribute("aria-busy");
          }
          const lastErr = chrome.runtime.lastError;
          if (lastErr) {
            console.error("[Velocity] open-sidebar runtime error:", lastErr.message);
            return;
          }
          if (response && response.success) {
            close();
          } else {
            console.warn("[Velocity] open-sidebar failed:", response);
          }
        }
      );
    } catch (err) {
      if (btn) {
        btn.disabled = false;
        btn.removeAttribute("aria-busy");
      }
      console.error("[Velocity] open-sidebar threw:", err);
    }
  }

  async function render() {
    renderTabs();
    await loadSnapshot();
    updateHeaderAuth();

    const hasText = Boolean(currentPrompt && currentPrompt.trim());
    const signedIn = snapshot && snapshot.isLoggedIn;

    if (!hasText) {
      renderEmpty();
      return;
    }
    if (!signedIn) {
      if (improvedText) {
        renderImproveResult();
        return;
      }
      if (guestFreeUsed) {
        renderSignInWall({ usedFree: true });
        return;
      }
      await runImprove();
      return;
    }
    if (improvedText) {
      renderImproveResult();
      return;
    }
    await runImprove();
  }

  function open(opts) {
    ensureDom();
    opts = opts || {};
    currentPrompt = String(opts.prompt || "").trim();
    improvedText = "";
    currentPromptId = "";
    annotatedSegments = [];
    onApplyCallback = typeof opts.onApply === "function" ? opts.onApply : null;
    activeTab = "improve";

    modalEl.classList.remove("is-large", "is-dragging");
    modalEl.style.position = "";
    modalEl.style.left = "";
    modalEl.style.top = "";
    modalEl.style.margin = "";

    resetFeedbackButtons();
    rootEl.classList.add("is-open");
    isOpen = true;
    render();
  }

  function close() {
    if (!rootEl) return;
    rootEl.classList.remove("is-open");
    isOpen = false;
    cancelLoadingVisual();
    if (modalEl) modalEl.classList.remove("is-large");
  }

  globalThis.VelocityInjectionModal = { open, close, isOpen: () => isOpen };
})();
