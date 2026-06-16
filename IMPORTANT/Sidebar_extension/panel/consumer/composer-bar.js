/**
 * Extension-new–style composer: attach (+ context/capture), mode row, mic + send (send runs enhance).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const STORAGE_ATTACHMENTS = "velocity_context_attachments_meta";
  const MAX_FILE_TEXT_BYTES = 400 * 1024;
  const MAX_PREVIEW_CHARS = 4000;

  const $ = (id) => document.getElementById(id);

  let attachmentsCache = [];

  function isSuggestionsTabActive() {
    const v = $("viewSuggestions");
    return !!(v && !v.hidden && v.classList.contains("view-surface--active"));
  }

  function isEnhanceSessionActive() {
    const shell = $("appShell");
    return !!(shell && shell.classList.contains("app-shell--in-session"));
  }

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

  // Toast state
  let _toastTimer = null;

  function getToastEl() {
    let el = $("composerToast");
    if (!el) {
      el = document.createElement("div");
      el.id = "composerToast";
      el.className = "composer-toast";
      el.setAttribute("role", "status");
      el.setAttribute("aria-live", "polite");
      document.body.appendChild(el);
    }
    return el;
  }

  function setEnhanceStatus(t) {
    // Also clear the legacy inline element so nothing lingers there
    const inline = $("enhanceStatus");
    if (inline) inline.textContent = "";

    const toast = getToastEl();
    if (_toastTimer) { clearTimeout(_toastTimer); _toastTimer = null; }

    if (!t) {
      toast.classList.remove("composer-toast--visible");
      return;
    }

    toast.textContent = t;
    toast.classList.add("composer-toast--visible");

    _toastTimer = setTimeout(() => {
      toast.classList.remove("composer-toast--visible");
      _toastTimer = null;
    }, 3000);
  }

  // Lucide icon SVG paths for each mode
  const MODE_ICONS = {
    zap: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></svg>',
    hammer: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 12-8.373 8.373a1 1 0 1 1-3-3L12 9"/><path d="m18 15 4-4"/><path d="m21.5 11.5-1.914-1.914A2 2 0 0 1 19 8.172V7l-2.26-2.26a6 6 0 0 0-4.202-1.756L9 2.96l.92.82A6.18 6.18 0 0 1 12 8.4V10l2 2h1.172a2 2 0 0 1 1.414.586L18.5 14.5"/></svg>',
    clapperboard: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.3Z"/><path d="m6.2 5.3 3.1 3.9"/><path d="m12.4 3.4 3.1 4"/><path d="M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/></svg>',
    'book-open': '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>',
    star: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.525 2.295a.53.53 0 0 1 .95 0l2.31 4.679a2.123 2.123 0 0 0 1.595 1.16l5.166.756a.53.53 0 0 1 .294.904l-3.736 3.638a2.123 2.123 0 0 0-.611 1.878l.882 5.14a.53.53 0 0 1-.771.56l-4.618-2.428a2.122 2.122 0 0 0-1.973 0L6.396 21.01a.53.53 0 0 1-.77-.56l.881-5.139a2.122 2.122 0 0 0-.611-1.879L2.16 9.795a.53.53 0 0 1 .294-.906l5.165-.755a2.122 2.122 0 0 0 1.597-1.16z"/></svg>'
  };

  function syncEnhanceModeSelect(apiValue, label) {
    const sel = $("enhanceMode");
    if (sel) {
      sel.value = apiValue;
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    }
    const lab = $("sbModeLabel");
    if (lab) lab.textContent = label;
    // Sync the icon in the mode button based on selected mode's icon
    const icon = $("sbModeIcon");
    if (icon) {
      const opt = document.querySelector(`.sb-mode-option[data-api-value="${apiValue}"]`);
      if (opt) {
        const iconName = opt.getAttribute("data-icon") || "zap";
        icon.setAttribute("data-icon", iconName);
        if (MODE_ICONS[iconName]) {
          icon.innerHTML = MODE_ICONS[iconName];
        }
      }
    }
  }

  // Update mode dropdown user tier (free/pro) for icon coloring
  function updateModeDropdownTier(isPro) {
    const dropdown = $("sbModeDropdown");
    if (dropdown) {
      dropdown.setAttribute("data-user-tier", isPro ? "pro" : "free");
    }
  }

  async function postCaptureBody(body) {
    try {
      const res = await sendMsg("TV_CONTEXT_CAPTURE", { body });
      if (!res || !res.success) {
        const msg = (res && res.error && res.error.message) || "Capture sync failed";
        setEnhanceStatus(msg);
        return false;
      }
      return true;
    } catch (e) {
      setEnhanceStatus(e.message || String(e));
      return false;
    }
  }

  function buildCaptureEnvelope(type, items) {
    return {
      source: "velocity_sidebar",
      kind: type,
      capturedAt: new Date().toISOString(),
      items,
    };
  }

  function isUsageBlocked() {
    const auth = root.TV && root.TV.sidebarAuthState;
    if (!auth || typeof auth.getSnapshot !== "function") return false;
    const snap = auth.getSnapshot();
    return Boolean(snap.isLoggedIn && snap.isUsageExhausted);
  }

  function setPrimaryActionMode(mode, opts) {
    const slot = $("composerPrimaryAction");
    const micBtn = $("voiceMicBtn");
    const sendBtn = $("btnComposerSend");
    const controls = $("originalSendControls");
    const useSend = mode === "send";
    const hideMic = Boolean(opts && opts.hideMic);
    if (slot) slot.dataset.mode = useSend ? "send" : "voice";
    if (controls) controls.dataset.mode = useSend ? "send" : "voice";
    // Mic stays visible alongside send so the two distinct buttons are
    // always available; we only collapse it when explicitly asked (e.g.
    // usage exhausted, where only the upgrade CTA should remain).
    if (micBtn) {
      micBtn.classList.toggle("is-visible", !hideMic);
      micBtn.classList.toggle("is-hidden", hideMic);
      micBtn.setAttribute("aria-hidden", hideMic ? "true" : "false");
    }
    if (sendBtn) {
      sendBtn.classList.toggle("is-visible", useSend);
      sendBtn.classList.toggle("is-hidden", !useSend);
      sendBtn.setAttribute("aria-hidden", useSend ? "false" : "true");
    }
  }

  function updateSendMic() {
    const ta = $("promptInput");
    const sendBtn = $("btnComposerSend");
    const micBtn = $("voiceMicBtn");
    const hasText = ta && ta.value.trim().length > 0;
    const sug = isSuggestionsTabActive();
    const usageBlocked = isUsageBlocked();
    const SV = root.TV.suggestionsView;
    const canRefine =
      !usageBlocked &&
      sug &&
      SV &&
      typeof SV.canSubmitRefine === "function" &&
      SV.canSubmitRefine();
    const refineComposerActive =
      sug && SV && typeof SV.isRefineComposerActive === "function" && SV.isRefineComposerActive();
    const customRefineReady =
      sug &&
      refineComposerActive &&
      hasText &&
      SV &&
      typeof SV.canSubmitCustomRefine === "function" &&
      SV.canSubmitCustomRefine();
    const showSend = (hasText || canRefine || customRefineReady) && !usageBlocked;
    const inSession = isEnhanceSessionActive();
    const voiceBusy =
      micBtn &&
      (micBtn.classList.contains("listening") || micBtn.classList.contains("voice-mic--transcribing"));
    const useSendSlot = showSend && !voiceBusy;

    // Hide the mic entirely only when usage is exhausted (the dimmed
    // upgrade-styled send button is the sole CTA in that state).
    setPrimaryActionMode(useSendSlot ? "send" : "voice", { hideMic: usageBlocked });

    if (sendBtn) {
      sendBtn.disabled = !showSend || usageBlocked;
      if (usageBlocked) {
        sendBtn.title = "You have run out of free prompts";
        sendBtn.setAttribute("aria-label", "Enhance prompt unavailable. Out of free prompts");
      } else if (sug && (canRefine || customRefineReady)) {
        sendBtn.title = "Refine prompt with your input";
        sendBtn.setAttribute("aria-label", "Refine prompt with your input");
      } else {
        sendBtn.title = "Enhance prompt";
        sendBtn.setAttribute("aria-label", "Enhance prompt");
      }
    }
    if (micBtn) {
      micBtn.disabled = usageBlocked || voiceBusy;
    }
    if (inSession && usageBlocked) {
      setPrimaryActionMode("send", { hideMic: true });
    }
  }

  async function saveAttachmentsToStorage() {
    await chrome.storage.local.set({ [STORAGE_ATTACHMENTS]: attachmentsCache });
  }

  async function loadAttachmentsFromStorage() {
    const r = await chrome.storage.local.get(STORAGE_ATTACHMENTS);
    attachmentsCache = Array.isArray(r[STORAGE_ATTACHMENTS]) ? r[STORAGE_ATTACHMENTS] : [];
  }

  async function pushAttachment(item) {
    attachmentsCache.push(item);
    await saveAttachmentsToStorage();
    renderAttachmentChips();
    await postCaptureBody(buildCaptureEnvelope("attachment", [item]));
  }

  async function removeAttachment(id) {
    attachmentsCache = attachmentsCache.filter((x) => x.id !== id);
    await saveAttachmentsToStorage();
    renderAttachmentChips();
  }

  function showContextPreview(att) {
    const popup = $("contextPreviewPopup");
    const title = $("contextPreviewTitle");
    const body = $("contextPreviewBody");
    if (!popup || !body) return;

    if (title) title.textContent = att.label || att.name || "Context Preview";
    
    let text = att.textContent || "";
    if (root.TV && root.TV.promptMarkdown) {
      body.innerHTML = root.TV.promptMarkdown.formatBlock(text);
    } else {
      body.textContent = text;
    }
    popup.hidden = false;
  }

  function wireContextPreview() {
    const popup = $("contextPreviewPopup");
    const closeBtn = $("contextPreviewClose");
    if (!popup) return;

    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        popup.hidden = true;
      });
    }

    popup.addEventListener("click", (e) => {
      if (e.target.hasAttribute("data-context-dismiss")) {
        popup.hidden = true;
      }
    });
  }

  function renderAttachmentChips() {
    const row = $("attachedFilesRow");
    if (!row) return;
    row.innerHTML = "";
    if (!attachmentsCache.length) {
      row.style.display = "none";
      return;
    }
    row.style.display = "flex";
    attachmentsCache.forEach((att) => {
      const chip = document.createElement("div");
      chip.className = "context-chip";
      const name = document.createElement("span");
      name.className = "context-chip-name";
      name.textContent = att.label || att.name || "file";
      const rm = document.createElement("button");
      rm.type = "button";
      rm.className = "context-chip-remove";
      rm.setAttribute("aria-label", "Remove");
      rm.textContent = "×";
      rm.addEventListener("click", () => void removeAttachment(att.id));
      
      if (att.textContent) {
        name.classList.add("context-chip-name--clickable");
        name.addEventListener("click", () => showContextPreview(att));
      }

      chip.appendChild(name);
      chip.appendChild(rm);
      row.appendChild(chip);
    });
  }

  function isTextLike(name, mime) {
    const lower = String(name || "").toLowerCase();
    if (/\.(txt|md|json|csv|xml|html|htm|css|js|ts|tsx|jsx|py|rb|go|rs|c|h|cpp|yaml|yml)$/i.test(lower)) {
      return true;
    }
    if (String(mime || "").startsWith("text/")) return true;
    if (mime === "application/json") return true;
    return false;
  }

  function readFileAsText(file) {
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(String(r.result || ""));
      r.onerror = () => reject(r.error);
      r.readAsText(file);
    });
  }

  async function fileToAttachmentItem(file, fromFolder) {
    const id = `file-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    const base = {
      id,
      kind: "file",
      label: (fromFolder ? file.webkitRelativePath || file.name : file.name).slice(0, 200),
      name: file.name,
      size: file.size,
      mimeType: file.type || "application/octet-stream",
      addedAt: Date.now(),
    };
    const textLike = isTextLike(file.name, file.type);
    if (textLike && file.size <= MAX_FILE_TEXT_BYTES) {
      try {
        const text = await readFileAsText(file);
        base.textContent = text.slice(0, MAX_FILE_TEXT_BYTES);
        base.preview = base.textContent.slice(0, MAX_PREVIEW_CHARS);
      } catch {
        base.preview = "[Could not read file as text]";
      }
    } else {
      base.preview = `[Binary or large file: ${file.name}]`;
    }
    return base;
  }

  async function ingestFiles(files, fromFolder) {
    const list = Array.from(files || []);
    if (attachmentsCache.length + list.length > 5) {
      setEnhanceStatus(`Limit reached: Max 5 attachments allowed.`);
      return;
    }
    let n = 0;
    for (const f of list) {
      const item = await fileToAttachmentItem(f, fromFolder);
      if (item) {
        await pushAttachment(item);
        n += 1;
      }
    }
    if (n) setEnhanceStatus(`Added ${n} attachment(s).`);
  }

  function closeAttachMenu() {
    const panel = $("attachMenuPanel");
    const btn = $("attachMenuBtn");
    if (panel) panel.hidden = true;
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  function wireAttachMenu() {
    const btn = $("attachMenuBtn");
    const panel = $("attachMenuPanel");
    const fileInput = $("contextFileInput");
    const filesBtn = $("attachMenuFiles");
    const extractBtn = $("attachMenuExtract");
    if (!btn || !panel || !fileInput) return;

    btn.addEventListener("click", (e) => {
      e.stopPropagation();

      // Close mode menu if open
      const modeMenu = $("sbModeMenu");
      const modeBtn = $("sbModeBtn");
      if (modeMenu && !modeMenu.hidden) {
        modeMenu.hidden = true;
        if (modeBtn) modeBtn.setAttribute("aria-expanded", "false");
      }

      if (panel.hidden) {
        panel.hidden = false;
        btn.setAttribute("aria-expanded", "true");
      } else {
        closeAttachMenu();
      }
    });

    document.addEventListener("click", (e) => {
      if (panel.hidden) return;
      const t = e.target;
      if (panel.contains(t) || btn.contains(t)) return;
      closeAttachMenu();
    });

    filesBtn &&
      filesBtn.addEventListener("click", () => {
        fileInput.value = "";
        fileInput.click();
        closeAttachMenu();
      });
    extractBtn &&
      extractBtn.addEventListener("click", () => {
        if (attachmentsCache.length >= 5) {
          setEnhanceStatus("Limit reached: Max 5 attachments allowed.");
          closeAttachMenu();
          return;
        }
        void (async () => {
          closeAttachMenu();
          extractBtn.disabled = true;
          setEnhanceStatus("Extracting page…");
          try {
            const res = await sendMsg("TV_EXTRACT_PAGE_CONTEXT", {});
            if (!res || !res.success) {
              setEnhanceStatus((res && res.error && res.error.message) || "Extract failed");
              return;
            }
            const data = res.data;
            const md = `# Page context\n\n- **URL:** ${data.url || ""}\n- **Title:** ${data.title || ""}\n\n${data.extractedText || ""}`;
            const filename = `page-context-${new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19)}.md`;
            const id = `page-${Date.now()}`;
            const item = {
              id,
              kind: "page",
              label: filename,
              name: filename,
              pageUrl: data.url,
              title: data.title,
              preview: (data.extractedText || "").slice(0, MAX_PREVIEW_CHARS),
              textContent: md,
              addedAt: Date.now(),
            };
            await pushAttachment(item);
            setEnhanceStatus("Page extracted and synced.");
          } catch (e) {
            setEnhanceStatus(e.message || String(e));
          } finally {
            extractBtn.disabled = false;
          }
        })();
      });

    fileInput.addEventListener("change", async (ev) => {
      const files = ev.target && ev.target.files;
      if (!files || !files.length) return;
      await ingestFiles(files, false);
      ev.target.value = "";
    });
  }

  function getSubscriptionStatus() {
    const auth = root.TV && root.TV.sidebarAuthState;
    if (!auth || typeof auth.getSnapshot !== "function") return "";
    return auth.getSnapshot().subscriptionStatus || "";
  }

  function applySubscriptionTier(snap) {
    const status = (snap && snap.subscriptionStatus) || getSubscriptionStatus();
    const acc = root.TV && root.TV.subscriptionAccess;
    const canPro =
      acc && typeof acc.canUseProEnhancementModes === "function"
        ? acc.canUseProEnhancementModes(status)
        : Boolean(snap && snap.isProUser);

    const menu = $("sbModeMenu");
    if (menu) {
      menu.querySelectorAll(".sb-mode-option").forEach((opt) => {
        const locked = opt.getAttribute("data-requires-pro") === "true" && !canPro;
        opt.classList.toggle("sb-mode-option--locked", locked);
        opt.setAttribute("aria-disabled", locked ? "true" : "false");
      });
    }

    const sel = $("enhanceMode");
    if (sel && acc && typeof acc.clampEnhancementModeForSubscription === "function") {
      const clamped = acc.clampEnhancementModeForSubscription(sel.value, status);
      if (clamped !== sel.value) {
        const labelMap = {
          standard: "Quick",
          build: "Build",
          media: "Media",
          research: "Research"
        };
        syncEnhanceModeSelect(clamped, labelMap[clamped] || "Quick");
      }
    }
  }

  function wireModeDropdown() {
    const btn = $("sbModeBtn");
    const menu = $("sbModeMenu");
    if (!btn || !menu) return;
    const options = menu.querySelectorAll(".sb-mode-option");

    const close = () => {
      menu.hidden = true;
      btn.setAttribute("aria-expanded", "false");
    };

    btn.addEventListener("click", (e) => {
      e.stopPropagation();

      // Close attachment menu if open
      const attachPanel = $("attachMenuPanel");
      const attachBtn = $("attachMenuBtn");
      if (attachPanel && !attachPanel.hidden) {
        attachPanel.hidden = true;
        if (attachBtn) attachBtn.setAttribute("aria-expanded", "false");
      }

      menu.hidden = !menu.hidden;
      btn.setAttribute("aria-expanded", menu.hidden ? "false" : "true");
    });

    document.addEventListener("click", () => close());

    options.forEach((opt) => {
      opt.addEventListener("click", (e) => {
        e.stopPropagation();
        const locked = opt.classList.contains("sb-mode-option--locked");
        if (locked) {
          close();
          const auth = root.TV && root.TV.sidebarAuthState;
          if (auth && typeof auth.openHostedPage === "function") {
            void auth.openHostedPage("/pricing", "sidebar_mode_upgrade");
          } else {
            setEnhanceStatus("");
          }
          return;
        }
        const v = opt.getAttribute("data-api-value") || "standard";
        const lab = opt.getAttribute("data-label") || opt.textContent || "Quick";
        syncEnhanceModeSelect(v, lab);
        close();
      });
    });

    const sel = $("enhanceMode");
    if (sel && sel.value) {
      const cur = sel.querySelector(`option[value="${sel.value}"]`);
      const labelMap = { standard: "Quick", build: "Build", media: "Media", research: "Research" };
      syncEnhanceModeSelect(sel.value, labelMap[sel.value] || "Quick");
    }
  }

  function wireVoice() {
    const mic = $("voiceMicBtn");
    const ta = $("promptInput");
    if (!mic || !ta) return;

    const V = root.TV.consumerVoiceTranscribe;
    if (!V || typeof V.createToggleController !== "function") {
      mic.addEventListener("click", () => {
        setEnhanceStatus("Voice module failed to load.");
      });
      return;
    }

    let voiceCtrl = null;
    let lastVoiceStream = null;
    let voiceOverlayOpen = false;
    /**
     * Cached mic stream for this side-panel session. Granted once via
     * `getUserMedia` on the first click, reused on subsequent clicks so Chrome
     * never re-prompts. Tracks are released only when this side panel page is
     * unloaded.
     */
    let cachedMicStream = null;

    function micStreamIsLive(stream) {
      if (!stream || typeof stream.getAudioTracks !== "function") return false;
      const tracks = stream.getAudioTracks();
      if (!tracks.length) return false;
      return tracks.some((t) => t.readyState === "live");
    }

    function releaseCachedMicStream() {
      if (!cachedMicStream) return;
      try {
        cachedMicStream.getTracks().forEach((t) => t.stop());
      } catch (_) {}
      cachedMicStream = null;
    }

    if (typeof window !== "undefined") {
      window.addEventListener("pagehide", releaseCachedMicStream);
      window.addEventListener("beforeunload", releaseCachedMicStream);
    }

    function getVoiceCtrl() {
      if (!voiceCtrl) {
        voiceCtrl = V.createToggleController({
          transcribeUrl: V.DEFAULT_TRANSCRIBE_URL,
          getHeaders: typeof V.buildAuthHeaders === "function" ? V.buildAuthHeaders : undefined,
          maxDurationSeconds: 120,
          onTranscript(text) {
            const t = String(text || "").trim();
            if (!t) return;
            // Re-fetch the live textarea instead of relying on the closure
            // ref so a re-rendered composer (e.g. after view switches) still
            // appends correctly. Preserve any existing typed/refine content.
            const liveTa = $("promptInput") || ta;
            const existing = liveTa.value || "";
            const needsSpace = existing.length > 0 && !/\s$/.test(existing);
            liveTa.value = existing + (needsSpace ? " " : "") + t;
            // Notify input listeners (autosize, suggestions-view editing
            // guard, send-state refresh) that the value changed.
            liveTa.dispatchEvent(new Event("input", { bubbles: true }));
            try {
              liveTa.focus();
              const end = liveTa.value.length;
              liveTa.setSelectionRange(end, end);
            } catch (_) {}
            updateSendMic();
            setEnhanceStatus("");
          },
          onError(msg) {
            setEnhanceStatus(msg || "Voice error.");
          },
          onStateChange(state) {
            try {
              const ctrl = voiceCtrl;
              const O = root.TV.voiceModeOverlay;

              mic.classList.remove("listening", "voice-mic--transcribing");
              mic.removeAttribute("aria-busy");

              if (state === "recording") {
                mic.classList.add("listening");
                mic.setAttribute("aria-busy", "true");
                setEnhanceStatus("Recording… use the voice panel to pause or finish.");
                if (O && typeof O.open === "function" && ctrl) {
                  if (voiceOverlayOpen && typeof O.setPaused === "function") {
                    O.setPaused(false);
                  } else {
                    O.open({
                      greeting: "Hi, how can we help you today?",
                      mediaStream: lastVoiceStream,
                      canPause: typeof ctrl.canPauseRecording === "function" && ctrl.canPauseRecording(),
                      onCancel: () => ctrl.cancel(),
                      onConfirm: () => ctrl.confirm(),
                      onPauseToggle: () => {
                        if (ctrl.canPauseRecording && ctrl.canPauseRecording()) {
                          ctrl.togglePause();
                        } else {
                          ctrl.confirm();
                        }
                      },
                    });
                    voiceOverlayOpen = true;
                  }
                }
              } else if (state === "paused") {
                mic.classList.add("listening");
                mic.setAttribute("aria-busy", "true");
                setEnhanceStatus("Paused…");
                if (O && voiceOverlayOpen && typeof O.setPaused === "function") O.setPaused(true);
              } else if (state === "transcribing") {
                mic.classList.add("voice-mic--transcribing");
                mic.setAttribute("aria-busy", "true");
                setEnhanceStatus("Transcribing audio…");
                if (O && voiceOverlayOpen && typeof O.setTranscribing === "function") O.setTranscribing();
              } else if (state === "idle") {
                if (O && voiceOverlayOpen && typeof O.close === "function") {
                  O.close();
                  voiceOverlayOpen = false;
                }
                lastVoiceStream = null;
              }
            } catch (e) {
              console.warn("[composer-bar] voice onStateChange:", e);
              setEnhanceStatus("Voice UI hit an error. Try the mic again or reload the sidebar.");
            }
          },
        });
      }
      return voiceCtrl;
    }

    let voiceMicBusy = false;

    mic.addEventListener("click", async () => {
      if (!V.isCaptureSupported()) {
        setEnhanceStatus("Voice recording is not supported in this browser.");
        return;
      }
      const ctrl = getVoiceCtrl();
      if (typeof ctrl.isVoiceSessionActive === "function" && ctrl.isVoiceSessionActive()) {
        if (typeof ctrl.isRecording === "function" && ctrl.isRecording()) {
          ctrl.toggle();
        } else {
          setEnhanceStatus("Please wait for voice to finish (transcribing) before using the mic again.");
        }
        return;
      }
      if (voiceMicBusy) {
        setEnhanceStatus("Microphone is starting… try again in a moment.");
        return;
      }
      if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== "function") {
        setEnhanceStatus("Voice recording is not supported in this browser.");
        return;
      }

      let permState = "prompt";
      if (typeof V.checkMicPermission === "function") {
        try {
          permState = await V.checkMicPermission();
        } catch (e) {
          console.warn("[composer-bar] checkMicPermission:", e);
          permState = "prompt";
        }
      }

      if (permState === "denied") {
        setEnhanceStatus(
          "Microphone is blocked for this extension. Open Chrome → Extensions → Velocity Sidebar → Details → Site settings → Microphone → Allow."
        );
        return;
      }

      /* Permissions API often reports "prompt" in extension side panels even when Chrome can still
       * show the normal mic prompt for getUserMedia. Always try capture unless already denied.
       * The granted stream is cached on `cachedMicStream` so subsequent mic clicks within this
       * side-panel session reuse it instead of triggering a fresh permission prompt. */
      voiceMicBusy = true;
      try {
        if (!micStreamIsLive(cachedMicStream)) {
          releaseCachedMicStream();
          cachedMicStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        }
        lastVoiceStream = cachedMicStream;
        const started = await ctrl.continueWithMediaStream(cachedMicStream, {
          ownsStream: false,
        });
        if (started === false) {
          lastVoiceStream = null;
        }
      } catch (err) {
        lastVoiceStream = null;
        releaseCachedMicStream();
        const name = err && err.name ? String(err.name) : "";
        if (name === "NotAllowedError" && typeof V.openMicPermissionPage === "function") {
          V.openMicPermissionPage();
          setEnhanceStatus(
            "Microphone was not allowed. Use the tab that opened to grant access, then tap the mic again."
          );
          return;
        }
        console.warn("[composer-bar] getUserMedia:", err);
        setEnhanceStatus(
          typeof V.micErrorMessage === "function" ? V.micErrorMessage(err) : "Microphone permission was not granted."
        );
      } finally {
        voiceMicBusy = false;
      }
    });
  }

  function wireEnhanceAndSend() {
    const ta = $("promptInput");
    const sendBtn = $("btnComposerSend");

    if (ta) {
      ta.addEventListener("input", () => updateSendMic());
    }

    async function ensureCanConsumeUsage() {
      const auth = root.TV && root.TV.sidebarAuthState;
      if (!auth) return true;
      const snap = auth.getSnapshot();
      if (!snap.isLoggedIn) return true;
      if (auth.canConsumeUsage && !auth.canConsumeUsage()) {
        return false;
      }
      try {
        await auth.refresh({ force: true });
      } catch (_) {}
      const latest = auth.getSnapshot();
      if (auth.canConsumeUsage && !auth.canConsumeUsage()) {
        return false;
      }
      return !latest.isUsageExhausted;
    }

    async function runEnhanceFromComposer() {
      if (!ta || !sendBtn) return;

      if (!(await ensureCanConsumeUsage())) {
        setEnhanceStatus("You have run out of free prompts. Upgrade to Pro for unlimited access.");
        if (root.TV.consumerUsageLimitBanner && typeof root.TV.consumerUsageLimitBanner.render === "function") {
          const auth = root.TV.sidebarAuthState;
          root.TV.consumerUsageLimitBanner.render(auth ? auth.getSnapshot() : {});
        }
        updateSendMic();
        return;
      }

      if (isSuggestionsTabActive() && root.TV.suggestionsView) {
        const SV = root.TV.suggestionsView;
        const customText = ta ? ta.value.trim() : "";

        if (typeof SV.canSubmitRefine === "function" && SV.canSubmitRefine()) {
          try {
            const ok = await SV.submitRefine();
            if (!ok) setEnhanceStatus("Refine did not complete. Try again.");
            else setEnhanceStatus("");
          } catch (e) {
            setEnhanceStatus(e.message || String(e));
          } finally {
            updateSendMic();
          }
          return;
        }

        if (
          customText &&
          typeof SV.canSubmitCustomRefine === "function" &&
          SV.canSubmitCustomRefine()
        ) {
          try {
            const ok = await SV.submitCustomRefine(customText);
            if (!ok) setEnhanceStatus("Refine did not complete. Try again.");
            else setEnhanceStatus("");
          } catch (e) {
            setEnhanceStatus(e.message || String(e));
          } finally {
            updateSendMic();
          }
          return;
        }

        const pendingOther =
          typeof SV.isOtherPending === "function" && SV.isOtherPending();
        setEnhanceStatus(
          pendingOther
            ? "Save your custom “Other” answer in the card above, then Send."
            : "Answer a question, use Improve Prompt, or type a refinement, then Send."
        );
        return;
      }

      const text = ta.value.trim();
      if (!text) {
        setEnhanceStatus("Enter a prompt first.");
        return;
      }
      const mode = ($("enhanceMode") && $("enhanceMode").value) || "standard";
      sendBtn.disabled = true;

      const TP = root.TV && root.TV.thoughtProcess;
      const cancelRef = { cancelled: false };
      const visualDone =
        TP && typeof TP.advanceVisualToFinalizingRunning === "function"
          ? TP.advanceVisualToFinalizingRunning(cancelRef)
          : Promise.resolve();

      try {
        const res = await sendMsg("TV_CONSUMER_ENHANCE", { prompt: text, mode });
        await visualDone;

        if (res && res.success && res.data && res.data.enhanced_prompt) {
          const auth = root.TV && root.TV.sidebarAuthState;
          if (auth && typeof auth.consumeOneUsageLocally === "function") {
            auth.consumeOneUsageLocally();
          }
          ta.value = "";
          ta.dispatchEvent(new Event("input", { bubbles: true }));
          updateSendMic();

          if (TP && typeof TP.markAllStepsDone === "function") {
            TP.markAllStepsDone();
          }
          const POST_DONE_MS = 300;
          setTimeout(() => {
            if (TP) TP.hide();
            const startSession = root.TV && root.TV._startSession;
            if (typeof startSession === "function") {
              startSession({
                original: text,
                enhanced: res.data.enhanced_prompt,
                annotated_segments: res.data.annotated_segments || [],
                promptId: res.data.prompt_id || null,
                mode,
                quality: res.data.quality || {},
              });
            } else {
              ta.value = res.data.enhanced_prompt;
              ta.dispatchEvent(new Event("input", { bubbles: true }));
              setEnhanceStatus("Done.");
            }
          }, POST_DONE_MS);
        } else {
          cancelRef.cancelled = true;
          if (TP) TP.hide({ restoreHome: true });
          const errObj = res && res.error;
          const errCode = errObj && errObj.code;
          if (errCode === "USAGE_EXHAUSTED") {
            const auth = root.TV && root.TV.sidebarAuthState;
            if (auth && typeof auth.refresh === "function") {
              try {
                await auth.refresh({ force: true });
              } catch (_) {}
            }
            if (
              root.TV.consumerUsageLimitBanner &&
              typeof root.TV.consumerUsageLimitBanner.render === "function"
            ) {
              root.TV.consumerUsageLimitBanner.render(auth ? auth.getSnapshot() : {});
            }
          }
          setEnhanceStatus(
            (errObj && errObj.message) || (typeof errObj === "string" ? errObj : null) || "Enhance failed"
          );
        }
      } catch (e) {
        cancelRef.cancelled = true;
        if (TP) TP.hide({ restoreHome: true });
        setEnhanceStatus(e.message || String(e));
      } finally {
        updateSendMic();
      }
    }

    if (sendBtn) {
      sendBtn.addEventListener("click", () => {
        void runEnhanceFromComposer();
      });
    }

    ta &&
      ta.addEventListener("keydown", (ev) => {
        if (ev.key !== "Enter" || !ev.ctrlKey) return;
        ev.preventDefault();
        if (sendBtn && !sendBtn.disabled) sendBtn.click();
      });
  }

  function triggerVoiceMic() {
    const mic = $("voiceMicBtn");
    if (mic) mic.click();
  }

  root.TV.consumerComposerBar = {
    triggerVoiceMic,
    async init(opts) {
      await loadAttachmentsFromStorage();
      renderAttachmentChips();
      wireContextPreview();
      wireAttachMenu();
      wireModeDropdown();
      wireVoice();
      wireEnhanceAndSend();
      const auth = (opts && opts.authState) || (root.TV && root.TV.sidebarAuthState);
      if (auth && typeof auth.subscribe === "function") {
        auth.subscribe((snap) => {
          applySubscriptionTier(snap);
          updateSendMic();
        });
        applySubscriptionTier(auth.getSnapshot());
      }
      updateSendMic();
    },
    applySubscriptionTier,
    refreshSendState() {
      updateSendMic();
    },
  };
})();
