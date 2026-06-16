/**
 * Per-host chat input selectors (from Extension-new/platforms.js).
 * @global VelocityHostPlatforms
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;

  const platforms = {
    chatgpt: {
      name: "ChatGPT",
      urlPattern: /^https:\/\/(chat\.openai\.com|chatgpt\.com)\/.*/,
      textAreaSelector:
        '#prompt-textarea, textarea[placeholder*="Message"], [contenteditable="true"][role="textbox"], textarea',
      wrapperSelector: '[data-testid="composer"], .composer-container, .chat-input-container',
      buttonAnchor: { align: "right", top: -48 },
    },
    claude: {
      name: "Claude",
      urlPattern: /^https:\/\/claude\.ai\/.*/,
      textAreaSelector: 'div[contenteditable="true"][role="textbox"], .ProseMirror, textarea',
      wrapperSelector:
        'form[data-testid="composer"], .composer-container, [data-testid="composer"], .input-area-container',
      buttonAnchor: { align: "right", top: -48 },
    },
    google: {
      name: "Gemini",
      urlPattern: /^https:\/\/gemini\.google\.com\/.*/,
      textAreaSelector: '.ql-editor[contenteditable="true"], textarea, [contenteditable="true"]',
      wrapperSelector: ".gemini-input-wrapper, .chat-input-container, [data-testid=\"input-container\"]",
      buttonAnchor: { align: "center", top: -52 },
    },
    mistral: {
      name: "Mistral",
      urlPattern: /^https:\/\/chat\.mistral\.ai\/.*/,
      textAreaSelector: 'textarea[placeholder*="Ask"], textarea, [contenteditable="true"]',
      wrapperSelector: ".mistral-input-container, .chat-input-wrapper",
      buttonAnchor: { align: "right", top: -48 },
    },
    perplexity: {
      name: "Perplexity",
      urlPattern: /^https:\/\/(www\.)?perplexity\.ai\/.*/,
      textAreaSelector: "textarea, [contenteditable=\"true\"], [role=\"textbox\"]",
      wrapperSelector: ".perplexity-input-container, [data-testid=\"input-container\"], form[role=\"search\"]",
      buttonAnchor: { align: "center", top: -52 },
    },
    grok: {
      name: "Grok",
      urlPattern: /^https:\/\/(www\.)?grok\.com\/.*/,
      textAreaSelector: "textarea, [contenteditable=\"true\"]",
      wrapperSelector: ".grok-input-wrapper, [data-testid=\"input-wrapper\"]",
      buttonAnchor: { align: "right", top: -48 },
    },
    bolt: {
      name: "Bolt",
      urlPattern: /^https:\/\/bolt\.new\/.*/,
      textAreaSelector: "textarea, [contenteditable=\"true\"]",
      wrapperSelector: ".input-container, .main-input-area",
      buttonAnchor: { align: "right", top: -48 },
    },
    suno: {
      name: "Suno",
      urlPattern: /^https:\/\/(www\.)?suno\.com\/.*/,
      textAreaSelector: "textarea, [contenteditable=\"true\"]",
      wrapperSelector: "form[data-testid=\"song-form\"], .song-description-area",
      buttonAnchor: { align: "right", top: -48 },
    },
    lovable: {
      name: "Lovable",
      urlPattern: /^https:\/\/(www\.)?lovable\.dev\/.*/,
      textAreaSelector: "textarea, [contenteditable=\"true\"]",
      wrapperSelector: ".lovable-input-wrapper, .input-container",
      buttonAnchor: { align: "right", top: -48 },
    },
    replit: {
      name: "Replit",
      urlPattern: /^https:\/\/(www\.)?replit\.com\/.*/,
      textAreaSelector: "textarea, [contenteditable=\"true\"], [role=\"textbox\"]",
      wrapperSelector: "form, [data-testid=\"input-area\"], [class*=\"composer\" i]",
      buttonAnchor: { align: "left", top: -52 },
    },
    vercel: {
      name: "v0",
      urlPattern: /^https:\/\/v0\.(dev|app)\/.*/,
      textAreaSelector: "textarea, [contenteditable=\"true\"]",
      wrapperSelector: ".prompt-container, [data-testid=\"prompt-wrapper\"]",
      buttonAnchor: { align: "right", top: -48 },
    },
    gamma: {
      name: "Gamma",
      urlPattern: /^https:\/\/gamma\.app\/.*/,
      textAreaSelector: "textarea, [contenteditable=\"true\"]",
      wrapperSelector: '[data-testid="composer"], .input-container, form',
      buttonAnchor: { align: "right", top: -48 },
    },
    hera: {
      name: "Hera",
      urlPattern: /^https:\/\/(www\.)?hera\.video\/.*/,
      textAreaSelector:
        'textarea, [contenteditable="true"], input[type="text"][placeholder*="prompt" i], input[type="text"][placeholder*="describe" i]',
      wrapperSelector:
        '.hera-input-container, .prompt-container, [data-testid="input-container"], [data-testid="prompt-container"], .input-wrapper, .prompt-wrapper, form',
      buttonAnchor: { align: "right", top: -48 },
    },
    flow: {
      name: "Flow",
      urlPattern: /^https:\/\/labs\.google\/fx\/tools\/flow\/.*/,
      textAreaSelector: 'textarea, [contenteditable="true"]',
      wrapperSelector:
        '.flow-input-container, .input-wrapper, [data-testid="input-container"], .chat-input-container',
      buttonAnchor: { align: "right", top: -48 },
    },
    kimi: {
      name: "Kimi",
      urlPattern: /^https:\/\/(www\.)?kimi\.com\/.*/,
      textAreaSelector:
        'textarea, [contenteditable="true"], input[type="text"][placeholder*="prompt" i], input[type="text"][placeholder*="idea" i]',
      wrapperSelector:
        'form, [class*="chat-input" i], [class*="input-container" i], [class*="composer" i], [class*="message-input" i]',
      buttonAnchor: { align: "right", top: -48 },
    },
    emergent: {
      name: "Emergent",
      urlPattern: /^https:\/\/app\.emergent\.sh\/.*/,
      textAreaSelector: 'textarea, [contenteditable="true"], input[type="text"]',
      wrapperSelector:
        '.bg-textarea-controls-bg, [class*="textarea-controls" i], [class*="bg-textarea" i]',
      buttonAnchor: { align: "right", top: -48 },
    },
  };

  function detectPlatform() {
    const href = location.href;
    for (const key of Object.keys(platforms)) {
      if (platforms[key].urlPattern.test(href)) return key;
    }
    return null;
  }

  function getPlatform(key) {
    return platforms[key] || null;
  }

  function findChatInput(platformKey) {
    const cfg = getPlatform(platformKey);
    const selectors = cfg
      ? cfg.textAreaSelector.split(",").map((s) => s.trim())
      : ["textarea", '[contenteditable="true"]', '[role="textbox"]'];

    function visible(el) {
      if (!el || !el.getBoundingClientRect) return false;
      const r = el.getBoundingClientRect();
      if (r.width < 24 || r.height < 16) return false;
      const st = window.getComputedStyle(el);
      return st.display !== "none" && st.visibility !== "hidden" && parseFloat(st.opacity || "1") > 0.05;
    }

    const active = document.activeElement;
    if (active && visible(active) && matchInput(active, selectors)) return active;

    for (const sel of selectors) {
      let nodes;
      try {
        nodes = document.querySelectorAll(sel);
      } catch (_) {
        continue;
      }
      for (const el of nodes) {
        if (visible(el) && !el.closest(".velocity-injection-bar")) return el;
      }
    }
    return null;
  }

  function matchInput(el, selectors) {
    if (!el) return false;
    for (const sel of selectors) {
      try {
        if (el.matches(sel)) return true;
      } catch (_) {}
    }
    const tag = el.tagName;
    return tag === "TEXTAREA" || tag === "INPUT" || el.isContentEditable;
  }

  root.VelocityHostPlatforms = {
    platforms,
    detectPlatform,
    getPlatform,
    findChatInput,
  };
})();
