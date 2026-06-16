/**
 * Velocity Thought Process loader — sidebar view wiring (steps live in features/thought-process-loader.js).
 * @global TV.thoughtProcess
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const Loader = root.TV.thoughtProcessLoader;
  const listEl = () => document.getElementById("thoughtStepsList");
  let instance = null;

  function getInstance() {
    const el = listEl();
    if (!el || !Loader || typeof Loader.createInstance !== "function") return null;
    if (!instance) instance = Loader.createInstance(el);
    return instance;
  }

  function hideSessionTabsForLoader() {
    ["viewOutput", "viewSuggestions", "viewContext", "viewVersions"].forEach((id) => {
      const v = document.getElementById(id);
      if (!v) return;
      v.classList.remove("view-surface--active");
      v.hidden = true;
    });
  }

  function syncRemainingPill() {
    const pill = document.getElementById("tpRemainingPill");
    if (!pill) return;
    const auth = root.TV && root.TV.sidebarAuthState;
    const snap = auth && typeof auth.getSnapshot === "function" ? auth.getSnapshot() : null;
    const raw = snap ? snap.remainingUsage : null;
    const n = raw === null || raw === undefined ? null : Number(raw);
    if (n === null || Number.isNaN(n)) {
      pill.hidden = true;
      pill.textContent = "";
      return;
    }
    pill.hidden = false;
    pill.textContent = `${Math.max(0, n)} remaining`;
  }

  function show() {
    const inst = getInstance();
    if (inst) inst.buildPanel();
    const home = document.getElementById("viewHome");
    const tabBar = document.getElementById("tabBar");
    const tp = document.getElementById("viewThoughtProcess");
    if (home) {
      home.classList.remove("view-surface--active");
      home.hidden = true;
    }
    hideSessionTabsForLoader();
    if (tabBar) tabBar.hidden = true;
    if (tp) {
      tp.classList.add("view-surface--active");
      tp.hidden = false;
    }
    syncRemainingPill();
  }

  const SESSION_VIEW_IDS = {
    output: "viewOutput",
    suggestions: "viewSuggestions",
    context: "viewContext",
    versions: "viewVersions",
  };

  /**
   * Hide the thought-process loader and (optionally) re-show the surface the
   * caller wants the user to land on. Without `restoreSession` / `restoreHome`
   * the panel stays blank — which is what we want during chained transitions
   * like refine→output, where the caller immediately swaps surfaces — but is
   * a bug on error paths, so callers MUST pass one of the restore options
   * whenever they own the next surface.
   *
   * @param {{ restoreHome?: boolean, restoreSession?: "output"|"suggestions"|"context"|"versions" }} [opts]
   */
  function hide(opts) {
    opts = opts || {};
    const tp = document.getElementById("viewThoughtProcess");
    if (tp) {
      tp.classList.remove("view-surface--active");
      tp.hidden = true;
    }
    if (opts.restoreHome) {
      const home = document.getElementById("viewHome");
      if (home) {
        home.hidden = false;
        home.classList.add("view-surface--active");
      }
    }
    if (opts.restoreSession) {
      const tabBar = document.getElementById("tabBar");
      if (tabBar) tabBar.hidden = false;
      const targetId = SESSION_VIEW_IDS[opts.restoreSession];
      if (targetId) {
        const target = document.getElementById(targetId);
        if (target) {
          target.hidden = false;
          target.classList.add("view-surface--active");
        }
      }
    }
  }

  function updateStep(id, status) {
    const inst = getInstance();
    if (inst) inst.updateStep(id, status);
  }

  function reset() {
    const inst = getInstance();
    if (inst) inst.reset();
  }

  function markAllStepsDone() {
    const inst = getInstance();
    if (inst) inst.markAllStepsDone();
  }

  function advanceVisualToFinalizingRunning(cancelRef) {
    show();
    const inst = getInstance();
    if (inst && typeof inst.advanceVisualToFinalizingRunning === "function") {
      return inst.advanceVisualToFinalizingRunning(cancelRef);
    }
    return Promise.resolve();
  }

  root.TV.thoughtProcess = {
    show,
    hide,
    updateStep,
    reset,
    markAllStepsDone,
    advanceVisualToFinalizingRunning,
    STEPS: Loader ? Loader.STEPS : [],
    LOADER_STEP_MS: Loader ? Loader.LOADER_STEP_MS : 500,
  };
})();
