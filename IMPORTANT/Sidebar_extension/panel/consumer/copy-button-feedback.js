/**
 * Brief "Copied" flash on icon copy buttons.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  function flash(btn, opts) {
    if (!btn || btn.dataset.copyFlashing === "1") return;
    const o = opts || {};
    const duration = Number(o.durationMs) > 0 ? Number(o.durationMs) : 1800;
    const label = o.label || "Copied";
    const copiedClass = o.copiedClass || "icon-chip-btn--copied";

    btn.dataset.copyFlashing = "1";
    const prevHtml = btn.innerHTML;
    const prevTitle = btn.title;
    const prevAria = btn.getAttribute("aria-label");

    btn.classList.add(copiedClass);
    btn.title = label;
    btn.setAttribute("aria-label", label);
    btn.innerHTML = `<span class="copy-flash-label">${label}</span>`;

    window.setTimeout(() => {
      btn.innerHTML = prevHtml;
      btn.title = prevTitle || "";
      if (prevAria) btn.setAttribute("aria-label", prevAria);
      else btn.removeAttribute("aria-label");
      btn.classList.remove(copiedClass);
      delete btn.dataset.copyFlashing;
    }, duration);
  }

  root.TV.copyButtonFeedback = { flash };
})();
