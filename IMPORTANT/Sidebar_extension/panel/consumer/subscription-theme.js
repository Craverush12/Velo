/**
 * Pro / Pro trial (gold) vs Free (cyan) — visual theme only (no copy changes).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const $ = (id) => document.getElementById(id);

  function tierMeta(snap) {
    const acc = root.TV.subscriptionAccess;
    if (!acc || typeof acc.getSubscriptionTierMeta !== "function") {
      return { theme: "guest", isGoldChrome: false, isPaidPro: false };
    }
    return acc.getSubscriptionTierMeta(snap && snap.subscriptionStatus);
  }

  function applyShellTheme(snap) {
    const shell = $("appShell");
    if (!shell) return;
    const meta = tierMeta(snap);
    const loggedIn = Boolean(snap && snap.isLoggedIn);
    const isGold = loggedIn && meta.isGoldChrome;
    const isFree = loggedIn && !isGold;

    shell.classList.toggle("app-shell--theme-pro", isGold);
    shell.classList.toggle("app-shell--theme-free", isFree);
    shell.classList.toggle("app-shell--tier-paid-pro", loggedIn && meta.isPaidPro);
    shell.classList.toggle("app-shell--tier-pro-trial", loggedIn && isGold && !meta.isPaidPro);
  }

  function applyPopupTheme(snap) {
    const popup = $("promptBookDetail");
    if (!popup) return;
    const meta = tierMeta(snap);
    const loggedIn = Boolean(snap && snap.isLoggedIn);
    popup.classList.toggle("prompt-book-detail--theme-pro", loggedIn && meta.isGoldChrome);
  }

  function applyProfileChrome(snap) {
    const btn = $("railProfile");
    if (!btn) return;

    btn.classList.remove("rail-btn-profile--pro", "rail-btn-profile--free", "rail-btn-profile--trial");
    btn.removeAttribute("data-tier-label");

    if (!snap || !snap.isLoggedIn) {
      btn.title = "Profile";
      return;
    }

    const meta = tierMeta(snap);
    if (meta.isPaidPro) {
      btn.classList.add("rail-btn-profile--pro");
    } else if (meta.isGoldChrome) {
      btn.classList.add("rail-btn-profile--trial");
    } else {
      btn.classList.add("rail-btn-profile--free");
    }
    btn.title = "Profile";
  }

  function apply(snap) {
    applyShellTheme(snap);
    applyProfileChrome(snap);
    applyPopupTheme(snap);
    if (root.TV.consumerComposerBar && typeof root.TV.consumerComposerBar.applySubscriptionTier === "function") {
      root.TV.consumerComposerBar.applySubscriptionTier(snap);
    }
    if (root.TV.outputView && typeof root.TV.outputView.refresh === "function") {
      root.TV.outputView.refresh();
    }
  }

  root.TV.consumerSubscriptionTheme = {
    init(authState) {
      if (!authState || typeof authState.subscribe !== "function") return;
      authState.subscribe((s) => apply(s));
      apply(authState.getSnapshot());
    },
    apply,
  };
})();
