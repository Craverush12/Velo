/**
 * Velocity Thought Process loader — shared 5-step visual for sidebar + injection modal.
 * @global TV.thoughtProcessLoader
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const LOADER_STEP_MS = 500;

  const STEPS = [
    { id: "understanding", label: "Understanding your request" },
    { id: "generating", label: "Tool Result: Generating optimized enhancement draft…" },
    { id: "context", label: "Adding useful context" },
    { id: "quality_check", label: "Quality check" },
    { id: "finalizing", label: "Final prompt ready" },
  ];

  const ICON_SVG =
    '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/></svg>';
  const RUNNING_SVG =
    '<svg width="10" height="10" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="6" fill="currentColor"/></svg>';
  const CHECK_SVG =
    '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';

  const STEP_IDS = STEPS.map((s) => s.id);

  function buildStepEl(step) {
    const row = document.createElement("div");
    row.className = "thought-step thought-step--queued";
    row.id = `tp-step-${step.id}`;

    const icon = document.createElement("div");
    icon.className = "thought-step-icon";
    icon.innerHTML = ICON_SVG;

    const body = document.createElement("div");
    body.className = "thought-step-body";

    const labelRow = document.createElement("div");
    labelRow.style.cssText = "display:flex;align-items:center;justify-content:space-between;gap:0.4rem;";

    const label = document.createElement("div");
    label.className = "thought-step-label";
    label.textContent = step.label;

    const badge = document.createElement("span");
    badge.className = "thought-step-badge badge--queued";
    badge.textContent = "Queued";

    labelRow.appendChild(label);
    labelRow.appendChild(badge);

    const progress = document.createElement("div");
    progress.className = "thought-step-progress";
    const bar = document.createElement("div");
    bar.className = "thought-step-progress-bar";
    progress.appendChild(bar);

    body.appendChild(labelRow);
    body.appendChild(progress);

    row.appendChild(icon);
    row.appendChild(body);

    return { row, icon, label, badge, bar };
  }

  /**
   * @param {HTMLElement} listEl - container for step rows (e.g. #thoughtStepsList)
   */
  function createInstance(listEl) {
    let stepEls = {};

    function buildPanel() {
      if (!listEl) return;
      listEl.innerHTML = "";
      stepEls = {};
      STEPS.forEach((step) => {
        const parts = buildStepEl(step);
        listEl.appendChild(parts.row);
        stepEls[step.id] = parts;
      });
    }

    function updateStep(id, status) {
      const parts = stepEls[id];
      if (!parts) return;
      const { row, icon, badge } = parts;

      row.classList.remove("thought-step--done", "thought-step--running", "thought-step--queued");

      if (status === "done") {
        row.classList.add("thought-step--done");
        icon.innerHTML = CHECK_SVG;
        badge.className = "thought-step-badge badge--done";
        badge.textContent = "Done";
      } else if (status === "running") {
        row.classList.add("thought-step--running");
        icon.innerHTML = RUNNING_SVG;
        badge.className = "thought-step-badge badge--running";
        badge.textContent = "Running";
      } else {
        row.classList.add("thought-step--queued");
        icon.innerHTML = ICON_SVG;
        badge.className = "thought-step-badge badge--queued";
        badge.textContent = "Queued";
      }
    }

    function reset() {
      STEPS.forEach((s) => updateStep(s.id, "queued"));
    }

    function markAllStepsDone() {
      STEPS.forEach((s) => updateStep(s.id, "done"));
    }

    function advanceVisualToFinalizingRunning(cancelRef) {
      if (!cancelRef || typeof cancelRef !== "object") cancelRef = { cancelled: false };
      buildPanel();
      updateStep(STEP_IDS[0], "running");
      const chain = async () => {
        for (let i = 0; i < STEP_IDS.length - 1; i++) {
          await new Promise((resolve) => setTimeout(resolve, LOADER_STEP_MS));
          if (cancelRef.cancelled) return;
          updateStep(STEP_IDS[i], "done");
          updateStep(STEP_IDS[i + 1], "running");
        }
      };
      return chain();
    }

    return {
      buildPanel,
      updateStep,
      reset,
      markAllStepsDone,
      advanceVisualToFinalizingRunning,
      STEPS,
      STEP_IDS,
    };
  }

  root.TV.thoughtProcessLoader = {
    LOADER_STEP_MS,
    STEPS,
    STEP_IDS,
    createInstance,
  };
})();
