/**
 * Inject enhanced prompt into the active browser tab (Extension-new parity).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  function pageInjectPromptFn(prompt, platformKey, isPro) {
    const selectors = {
      openai: ['textarea[data-id="root"]', 'textarea[placeholder*="Message"]', 'div[contenteditable="true"]', 'textarea'],
      anthropic: ['textarea', 'div[contenteditable="true"]'],
      google: ['textarea', 'div[contenteditable="true"]'],
      perplexity: ['textarea', 'div[contenteditable="true"]'],
      mistral: ['textarea', 'div[contenteditable="true"]'],
      grok: ['textarea', 'div[contenteditable="true"]'],
      bolt: ['textarea', 'div[contenteditable="true"]'],
      suno: ['textarea', 'div[contenteditable="true"]'],
      lovable: ['textarea', 'div[contenteditable="true"]'],
      replit: ['textarea', 'div[contenteditable="true"]'],
      vercel: ['textarea', 'div[contenteditable="true"]'],
    };

    const INSERT_ANIM_STYLE_ID = "velocity-insert-anim-style";
    const INSERT_ANIM_CLASS = "velocity-prompt-just-inserted";

    function ensureInsertAnimationStyles() {
      if (document.getElementById(INSERT_ANIM_STYLE_ID)) return;
      const style = document.createElement("style");
      style.id = INSERT_ANIM_STYLE_ID;
      // `box-shadow` follows the element's border-radius, so to round the gold
      // halo we set an explicit radius via `--velocity-anim-radius` (computed
      // per target as max(existing, 18px) so platforms that already round
      // their prompt container keep their natural curvature).
      style.textContent = `
        @keyframes velocityPromptGlowGold {
          0%   { box-shadow: 0 0 0 0 rgba(238, 193, 60, 0); }
          18%  { box-shadow: 0 0 0 3px rgba(238, 193, 60, 0.55),
                              0 0 28px 6px rgba(245, 200, 66, 0.65),
                              0 0 60px 14px rgba(238, 193, 60, 0.35); }
          55%  { box-shadow: 0 0 0 2px rgba(238, 193, 60, 0.4),
                              0 0 36px 8px rgba(242, 207, 106, 0.5),
                              0 0 72px 18px rgba(238, 193, 60, 0.22); }
          100% { box-shadow: 0 0 0 0 rgba(238, 193, 60, 0); }
        }
        .${INSERT_ANIM_CLASS} {
          animation: velocityPromptGlowGold 1100ms cubic-bezier(0.22, 0.61, 0.36, 1) 1;
          border-radius: var(--velocity-anim-radius, 18px) !important;
          will-change: box-shadow;
        }
        @media (prefers-reduced-motion: reduce) {
          .${INSERT_ANIM_CLASS} { animation: none !important; }
        }
      `;
      try {
        (document.head || document.documentElement).appendChild(style);
      } catch (_) {
        /* ignore — fallback path is unstyled */
      }
    }

    /**
     * Resolve the largest corner radius already present on the element and
     * round it up to a minimum of 26px so the gold halo never reads as a
     * sharp rectangle around a container that ships flat corners. Modern
     * chat composers tend to land in the 16–28px range, so this keeps the
     * halo visually consistent across platforms.
     */
    function pickAnimationRadius(el) {
      const MIN_RADIUS_PX = 26;
      try {
        const cs = window.getComputedStyle(el);
        const candidates = [
          cs.borderTopLeftRadius,
          cs.borderTopRightRadius,
          cs.borderBottomLeftRadius,
          cs.borderBottomRightRadius,
        ];
        let maxRadius = 0;
        for (const raw of candidates) {
          const n = parseFloat(raw);
          if (Number.isFinite(n) && n > maxRadius) maxRadius = n;
        }
        return Math.max(MIN_RADIUS_PX, maxRadius);
      } catch (_) {
        return MIN_RADIUS_PX;
      }
    }

    /**
     * Pick the visible container that wraps the *whole prompt area* (input +
     * toolbar + send button), not just the inner textarea. Prefers an
     * already-rounded ancestor (the composer "pill") over a flat-cornered
     * outer form so the gold halo follows the natural curvature of the host
     * page instead of drawing a sharp rectangle around suggestion chips.
     */
    function findPromptContainer(inputEl) {
      if (!inputEl) return null;
      const inputRect = inputEl.getBoundingClientRect();
      const maxH = window.innerHeight * 0.7;

      function radiusOf(el) {
        try {
          const cs = window.getComputedStyle(el);
          const candidates = [
            cs.borderTopLeftRadius,
            cs.borderTopRightRadius,
            cs.borderBottomLeftRadius,
            cs.borderBottomRightRadius,
          ];
          let max = 0;
          for (const raw of candidates) {
            const n = parseFloat(raw);
            if (Number.isFinite(n) && n > max) max = n;
          }
          return max;
        } catch (_) {
          return 0;
        }
      }

      let rounded = null;
      let firstBigger = null;
      let node = inputEl.parentElement;
      let hops = 0;
      while (node && hops < 7) {
        const rect = node.getBoundingClientRect();
        const grewWidth = rect.width >= inputRect.width + 16;
        const grewHeight = rect.height >= inputRect.height + 8;
        const reasonableHeight = rect.height > 0 && rect.height < maxH;
        if ((grewWidth || grewHeight) && reasonableHeight) {
          if (!firstBigger) firstBigger = node;
          if (!rounded && radiusOf(node) >= 8) {
            rounded = node;
            break;
          }
        }
        node = node.parentElement;
        hops += 1;
      }
      if (rounded) return rounded;

      const form = inputEl.closest && inputEl.closest("form");
      if (form && form.getBoundingClientRect().height < window.innerHeight * 0.85) {
        return form;
      }
      return firstBigger || inputEl;
    }

    function playInsertAnimation(inputEl) {
      if (!isPro) return;
      const target = findPromptContainer(inputEl) || inputEl;
      if (!target || !target.classList) return;
      try {
        ensureInsertAnimationStyles();
        const radiusPx = pickAnimationRadius(target);
        target.style.setProperty("--velocity-anim-radius", `${radiusPx}px`);
        target.classList.remove(INSERT_ANIM_CLASS);
        // Force reflow so re-adding the class re-triggers the keyframes
        // when the prompt is inserted into the same field twice in a row.
        // eslint-disable-next-line no-unused-expressions
        target.offsetWidth;
        target.classList.add(INSERT_ANIM_CLASS);
        const cleanup = () => {
          target.classList.remove(INSERT_ANIM_CLASS);
          target.style.removeProperty("--velocity-anim-radius");
          target.removeEventListener("animationend", cleanup);
        };
        target.addEventListener("animationend", cleanup, { once: true });
        setTimeout(cleanup, 1600);
      } catch (_) {}
    }

    function visible(el) {
      if (!el) return false;
      const r = el.getBoundingClientRect();
      if (r.width < 8 || r.height < 8) return false;
      const st = window.getComputedStyle(el);
      return st.display !== "none" && st.visibility !== "hidden";
    }

    function findInput() {
      const list = selectors[platformKey] || selectors.openai;
      for (const sel of list) {
        let nodes;
        try {
          nodes = document.querySelectorAll(sel);
        } catch (_) {
          continue;
        }
        for (const el of nodes) {
          if (visible(el)) return el;
        }
      }
      const fallbacks = ["textarea", "div[contenteditable=\"true\"]", '[role="textbox"]'];
      for (const sel of fallbacks) {
        const nodes = document.querySelectorAll(sel);
        for (const el of nodes) {
          if (visible(el)) return el;
        }
      }
      return null;
    }

    function setValue(el, text) {
      const t = String(text || "").slice(0, 50000);
      try {
        el.focus();
      } catch (_) {}
      if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
        const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const set = Object.getOwnPropertyDescriptor(proto, "value")?.set;
        if (set) set.call(el, t);
        else el.value = t;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
        el.dispatchEvent(new Event("keyup", { bubbles: true }));
      } else if (el.isContentEditable || el.getAttribute("contenteditable") === "true") {
        let inserted = false;
        try {
          document.execCommand("selectAll", false, null);
          document.execCommand("delete", false, null);
          inserted = document.execCommand("insertText", false, t);
        } catch (_) {}
        if (!inserted || String(el.innerText || el.textContent || "").trim() !== t.trim()) {
          el.textContent = "";
          el.textContent = t;
          el.innerText = t;
        }
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
        el.dispatchEvent(new Event("keyup", { bubbles: true }));
      } else {
        el.textContent = t;
        el.dispatchEvent(new Event("input", { bubbles: true }));
      }
    }

    const el = findInput();
    if (!el) return false;
    setValue(el, prompt);
    playInsertAnimation(el);
    return true;
  }

  function formatPromptForInject(prompt) {
    const raw = String(prompt || "").trim();
    if (!raw) return "";
    const pf = root.TV.promptFormat;
    if (pf && typeof pf.formatForExternalPaste === "function") {
      return pf.formatForExternalPaste(raw);
    }
    return raw;
  }

  /**
   * @param {string} prompt
   * @param {{ isPro?: boolean }} [options] Pro users get the gold insert glow on the
   *   surrounding prompt container; non-pro users get a silent insert.
   */
  async function injectActiveTab(prompt, options) {
    const text = formatPromptForInject(prompt);
    if (!text) return { success: false, error: "No prompt text" };

    let tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tabs || !tabs[0]) {
      tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    }
    const tab = tabs && tabs[0];
    const pa = root.TV.platformPromptActions;
    if (!tab || !tab.id || !pa || !pa.isTabScriptable(tab.url)) {
      return { success: false, error: "Open a supported chat page in your browser tab first." };
    }

    const platformKey = pa.platformKeyFromUrl(tab.url);
    if (!platformKey) {
      return { success: false, error: "This page does not support direct insert. Use Open In." };
    }

    const isPro = Boolean(options && options.isPro);
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: pageInjectPromptFn,
        args: [text, platformKey, isPro],
      });
      const ok = Boolean(results && results[0] && results[0].result);
      return ok
        ? { success: true, platform: platformKey }
        : { success: false, error: "No text field found on this page." };
    } catch (e) {
      return { success: false, error: e.message || String(e) };
    }
  }

  function clearOpenInStorage() {
    return chrome.storage.local.remove(["inject_prompt", "target_provider", "inject_timestamp"]);
  }

  function scheduleOpenInTabInjection(tabId, text, platformKey, options) {
    if (!tabId || !text) return;
    const key = platformKey || "openai";
    const isPro = Boolean(options && options.isPro);
    let finished = false;

    function finish() {
      if (finished) return;
      finished = true;
      void clearOpenInStorage();
    }

    async function attempt() {
      if (finished) return true;
      try {
        const tab = await chrome.tabs.get(tabId);
        const pa = root.TV.platformPromptActions;
        if (!tab || !tab.url || !pa || !pa.isTabScriptable(tab.url)) {
          return false;
        }
        const results = await chrome.scripting.executeScript({
          target: { tabId },
          func: pageInjectPromptFn,
          args: [text, key, isPro],
        });
        if (results && results[0] && results[0].result) {
          finish();
          return true;
        }
      } catch (_) {}
      return false;
    }

    const onUpdated = (id, info) => {
      if (finished || id !== tabId) return;
      if (info.status === "complete" || info.status === "loading") {
        void attempt();
      }
    };

    chrome.tabs.onUpdated.addListener(onUpdated);
    const delays = [600, 1200, 2200, 3500, 5500, 8000, 11000];
    const timers = delays.map((ms) =>
      setTimeout(() => {
        void attempt().then((ok) => {
          if (ok) chrome.tabs.onUpdated.removeListener(onUpdated);
        });
      }, ms)
    );
    setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(onUpdated);
      timers.forEach((t) => clearTimeout(t));
    }, 13000);
  }

  /**
   * @param {string} prompt
   * @param {string} platformKey
   * @param {{ isPro?: boolean }} [options]
   */
  async function openInPlatform(prompt, platformKey, options) {
    const text = formatPromptForInject(prompt);
    if (!text) return { success: false, error: "No prompt text" };
    const pa = root.TV.platformPromptActions;
    const key = platformKey || "openai";
    const isPro = Boolean(options && options.isPro);

    // Build the per-platform launch URL with the prompt embedded as v-chat does
    // (`?q=`, `?prompt=`, `#prompt=`). The scheduled in-page injection still
    // runs as a fallback in case the platform doesn't honor the URL param.
    let url;
    if (pa && typeof pa.buildPromptUrl === "function") {
      url = pa.buildPromptUrl(key, text);
    } else {
      const urls = pa && pa.PROVIDER_URLS;
      url = (urls && urls[key]) || (urls && urls.openai) || "https://chat.openai.com/";
    }

    await chrome.storage.local.set({
      inject_prompt: text,
      target_provider: key,
      inject_timestamp: Date.now(),
    });

    const tab = await chrome.tabs.create({ url, active: true });
    if (tab && tab.id) {
      scheduleOpenInTabInjection(tab.id, text, key, { isPro });
    }
    return { success: true, platform: key, url, tabId: tab && tab.id };
  }

  root.TV.consumerPlatformInject = {
    injectActiveTab,
    openInPlatform,
    scheduleOpenInTabInjection,
  };
})();
