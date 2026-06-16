/**
 * Dislike feedback popup — written feedback via TV_CONSUMER_SUBMIT_FEEDBACK (/reviews).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const $ = (id) => document.getElementById(id);

  let _popup = null;
  let _textarea = null;
  let _sendBtn = null;
  let _statusEl = null;
  let _reason = "Enhancement dislike";
  let _source = "sidebar-extension";
  let _sending = false;

  function sendMsg(action, payload) {
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

  function setStatus(text, kind) {
    if (!_statusEl) return;
    _statusEl.textContent = text || "";
    _statusEl.classList.remove("feedback-popup__status--error", "feedback-popup__status--success");
    if (kind === "error") _statusEl.classList.add("feedback-popup__status--error");
    if (kind === "success") _statusEl.classList.add("feedback-popup__status--success");
  }

  function syncSendEnabled() {
    if (!_sendBtn || !_textarea) return;
    const text = _textarea.value.trim();
    _sendBtn.disabled = _sending || text.length < 1;
  }

  function hide() {
    if (!_popup) return;
    _popup.hidden = true;
    if (_textarea) _textarea.value = "";
    setStatus("");
    syncSendEnabled();
  }

  function show(opts) {
    if (!_popup) init();
    const o = opts || {};
    if (o.reason) _reason = o.reason;
    if (o.source) _source = o.source;
    _popup.hidden = false;
    setStatus("");
    syncSendEnabled();
    window.setTimeout(() => {
      try {
        _textarea && _textarea.focus();
      } catch (_) {}
    }, 0);
  }

  async function submit() {
    if (!_textarea || _sending) return;
    const text = _textarea.value.trim();
    if (!text) return;

    _sending = true;
    syncSendEnabled();
    setStatus("Sending…");

    try {
      const res = await sendMsg("TV_CONSUMER_SUBMIT_FEEDBACK", {
        feedback: text,
        reason: _reason,
        source: _source,
      });
      if (res && res.success) {
        setStatus("Thanks for your feedback!", "success");
        window.setTimeout(hide, 900);
        return;
      }
      const msg = (res && res.error && res.error.message) || "Could not send feedback. Try again.";
      setStatus(msg, "error");
    } catch (err) {
      setStatus(err.message || "Could not send feedback.", "error");
    } finally {
      _sending = false;
      syncSendEnabled();
    }
  }

  function init() {
    _popup = $("feedbackPopup");
    _textarea = $("feedbackPopupText");
    _sendBtn = $("feedbackPopupSend");
    _statusEl = $("feedbackPopupStatus");
    if (!_popup) return;

    const closeBtn = $("feedbackPopupClose");
    const dismissBtn = $("feedbackPopupDismiss");
    const backdrop = _popup.querySelector("[data-feedback-dismiss]");

    if (closeBtn) closeBtn.addEventListener("click", hide);
    if (dismissBtn) dismissBtn.addEventListener("click", hide);
    if (backdrop) backdrop.addEventListener("click", hide);

    if (_textarea) {
      _textarea.addEventListener("input", syncSendEnabled);
      _textarea.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          hide();
        }
      });
    }

    if (_sendBtn) {
      _sendBtn.addEventListener("click", () => {
        void submit();
      });
    }

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && _popup && !_popup.hidden) hide();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  root.TV.feedbackPopup = { show, hide };
})();
