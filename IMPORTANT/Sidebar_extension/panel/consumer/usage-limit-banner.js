/**
 * Inline “out of prompts” banner above the composer (Vel-Next chat parity).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const $ = (id) => document.getElementById(id);

  function applyShellClass(exhausted) {
    const shell = $("appShell");
    if (!shell) return;
    shell.classList.toggle("app-shell--usage-exhausted", Boolean(exhausted));
  }

  function applyComposerDisabled(exhausted) {
    const sendBtn = $("btnComposerSend");
    const ta = $("promptInput");
    if (sendBtn) {
      if (exhausted) {
        sendBtn.disabled = true;
        sendBtn.title = "You have run out of free prompts";
        sendBtn.setAttribute("aria-label", "Enhance prompt unavailable. Out of free prompts");
      }
    }
    if (ta && exhausted) {
      ta.setAttribute("aria-disabled", "true");
    } else if (ta) {
      ta.removeAttribute("aria-disabled");
    }
    if (root.TV.consumerComposerBar && typeof root.TV.consumerComposerBar.refreshSendState === "function") {
      root.TV.consumerComposerBar.refreshSendState();
    }
  }

  function render(s) {
    const banner = $("usageLimitBanner");
    if (!banner) return;

    const show =
      s &&
      s.isLoggedIn &&
      !s.loading &&
      !s.error &&
      Boolean(s.isUsageExhausted);

    if (show) banner.removeAttribute("hidden");
    else banner.setAttribute("hidden", "");

    applyShellClass(show);
    applyComposerDisabled(show);
  }

  root.TV.consumerUsageLimitBanner = {
    init(authState) {
      if (!authState || typeof authState.subscribe !== "function") return;
      const upgradeBtn = $("usageLimitBannerUpgrade");
      if (upgradeBtn) {
        upgradeBtn.addEventListener("click", () => {
          void authState.openHostedPage("/pricing", "sidebar_usage_limit_banner");
        });
      }
      authState.subscribe(render);
      render(authState.getSnapshot());
    },
    render,
  };
})();
