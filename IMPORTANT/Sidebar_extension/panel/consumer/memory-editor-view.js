/**
 * Add / edit memory modal (matches Vel-Next MemoryPage).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const $ = (id) => document.getElementById(id);

  const state = {
    shell: null,
    editing: null,
    saving: false,
    onSaved: null,
    sendRuntime: null,
    onDocKeydown: null,
  };

  function parseMemoryFields(item) {
    const text = String((item && item.text) || "").trim();
    const lines = text.split("\n");
    const firstLine = (lines[0] || "").trim();
    const rest = lines.slice(1).join("\n").trim();
    const looksLikeTitle =
      !!firstLine && firstLine.length <= 80 && firstLine.trim() && rest.length > 0;
    return {
      title: looksLikeTitle ? firstLine : "",
      body: looksLikeTitle ? rest : text,
    };
  }

  function buildEssence(title, body) {
    const t = String(title || "").trim();
    const b = String(body || "").trim();
    if (!b) return "";
    return t ? `${t}\n${b}` : b;
  }

  function setFormError(msg) {
    const el = $("memoryEditorError");
    if (el) el.textContent = msg || "";
  }

  function setSaving(on) {
    state.saving = !!on;
    const btn = $("memoryEditorSave");
    if (btn) {
      btn.disabled = on;
      btn.textContent = on ? "Syncing…" : state.editing ? "Update Memory" : "Save Memory";
    }
  }

  function closeModal() {
    if (!state.shell) return;
    state.shell.hidden = true;
    state.shell.setAttribute("aria-hidden", "true");
    state.editing = null;
    setFormError("");
    if (state.onDocKeydown) {
      document.removeEventListener("keydown", state.onDocKeydown);
      state.onDocKeydown = null;
    }
  }

  function ensureShell() {
    if (state.shell) return;
    const rootEl = document.createElement("div");
    rootEl.id = "memoryEditor";
    rootEl.className = "memory-editor";
    rootEl.hidden = true;
    rootEl.setAttribute("aria-hidden", "true");
    rootEl.innerHTML = `
      <div class="memory-editor__backdrop" data-memory-editor-dismiss="1" aria-hidden="true"></div>
      <div class="memory-editor__sheet" role="dialog" aria-modal="true" aria-labelledby="memoryEditorTitle">
        <button type="button" class="memory-editor__close" id="memoryEditorClose" aria-label="Close">✕</button>
        <h2 class="memory-editor__title" id="memoryEditorTitle">Add New Memory</h2>
        <p class="memory-editor__sub" id="memoryEditorSub"></p>
        <p class="memory-editor__error" id="memoryEditorError" aria-live="polite"></p>
        <form id="memoryEditorForm" class="memory-editor__form">
          <label class="memory-editor__label" for="memoryEditorTitleInput">Memory title (optional)</label>
          <input type="text" id="memoryEditorTitleInput" class="memory-editor__input" placeholder="e.g. Coding preferences" autocomplete="off" />
          <label class="memory-editor__label" for="memoryEditorBody">What should AI remember?</label>
          <textarea id="memoryEditorBody" class="memory-editor__textarea" required placeholder="Example: I prefer concise answers with code snippets in JavaScript."></textarea>
          <p class="memory-editor__hint">Tip: Include durable preferences and context, not one-time instructions.</p>
          <div class="memory-editor__actions">
            <button type="button" class="memory-editor__btn memory-editor__btn--ghost" id="memoryEditorCancel">Cancel</button>
            <button type="submit" class="memory-editor__btn memory-editor__btn--primary" id="memoryEditorSave">Save Memory</button>
          </div>
        </form>
      </div>
    `;
    document.body.appendChild(rootEl);
    state.shell = rootEl;

    const dismiss = rootEl.querySelector("[data-memory-editor-dismiss]");
    if (dismiss) dismiss.addEventListener("click", () => closeModal());
    const closeBtn = $("memoryEditorClose");
    if (closeBtn) closeBtn.addEventListener("click", () => closeModal());
    const cancel = $("memoryEditorCancel");
    if (cancel) cancel.addEventListener("click", () => closeModal());

    const form = $("memoryEditorForm");
    if (form) {
      form.addEventListener("submit", (ev) => {
        ev.preventDefault();
        void saveMemory();
      });
    }
  }

  async function saveMemory() {
    if (state.saving || !state.sendRuntime) return;
    const titleInp = $("memoryEditorTitleInput");
    const bodyInp = $("memoryEditorBody");
    const essence = buildEssence(titleInp && titleInp.value, bodyInp && bodyInp.value);
    if (!essence) {
      setFormError("Enter what AI should remember.");
      return;
    }
    setFormError("");
    setSaving(true);
    try {
      const editing = state.editing;
      const action = editing ? "TV_CONSUMER_UPDATE_MEMORY" : "TV_CONSUMER_CREATE_MEMORY";
      const payload = editing
        ? {
            id: editing.id,
            sessionId: editing.sessionId || null,
            essence,
          }
        : { essence, platform: "velocity" };
      const res = await state.sendRuntime(action, payload);
      if (!res || !res.success) {
        const msg = (res && res.error && res.error.message) || "Could not save memory.";
        setFormError(msg);
        return;
      }
      closeModal();
      if (typeof state.onSaved === "function") state.onSaved();
    } catch (e) {
      setFormError(e.message || String(e));
    } finally {
      setSaving(false);
    }
  }

  function openModal(item) {
    ensureShell();
    state.editing = item || null;
    const isEdit = !!item;
    const fields = isEdit ? parseMemoryFields(item) : { title: "", body: "" };

    const titleEl = $("memoryEditorTitle");
    const subEl = $("memoryEditorSub");
    const titleInp = $("memoryEditorTitleInput");
    const bodyInp = $("memoryEditorBody");
    const saveBtn = $("memoryEditorSave");

    if (titleEl) titleEl.textContent = isEdit ? "Edit Memory" : "Add New Memory";
    if (subEl) {
      subEl.textContent = isEdit
        ? "Update this memory so future responses stay aligned with your latest preferences."
        : "Add a reusable fact, preference, or project detail that AI should remember across chats.";
    }
    if (titleInp) titleInp.value = fields.title;
    if (bodyInp) bodyInp.value = fields.body;
    if (saveBtn) saveBtn.textContent = isEdit ? "Update Memory" : "Save Memory";

    setFormError("");
    setSaving(false);
    state.shell.hidden = false;
    state.shell.setAttribute("aria-hidden", "false");

    state.onDocKeydown = (ev) => {
      if (ev.key === "Escape") {
        ev.preventDefault();
        closeModal();
      }
    };
    document.addEventListener("keydown", state.onDocKeydown);
    setTimeout(() => {
      if (bodyInp) bodyInp.focus();
    }, 50);
  }

  root.TV.consumerMemoryEditor = {
    init(opts) {
      const o = opts || {};
      state.onSaved = typeof o.onSaved === "function" ? o.onSaved : null;
      state.sendRuntime = typeof o.sendRuntime === "function" ? o.sendRuntime : null;
    },
    openAdd() {
      openModal(null);
    },
    openEdit(item) {
      openModal(item || null);
    },
    close() {
      closeModal();
    },
  };
})();
