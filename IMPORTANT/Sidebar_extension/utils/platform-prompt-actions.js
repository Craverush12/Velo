/**
 * Platform insert / open-in config (Extension-new parity).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const OPEN_IN_PLATFORMS = [
    { key: "openai", label: "ChatGPT", icon: "https://thinkvelocity.in/next-assets/chatgpt_colored.png" },
    { key: "anthropic", label: "Claude", icon: "https://thinkvelocity.in/next-assets/claude_colored.png" },
    { key: "google", label: "Gemini", icon: "https://thinkvelocity.in/next-assets/gemini-color.png" },
    { key: "grok", label: "Grok", icon: "https://thinkvelocity.in/next-assets/grok_colored.png" },
    { key: "mistral", label: "Mistral", icon: "https://thinkvelocity.in/next-assets/mistral_colored.png" },
    { key: "perplexity", label: "Perplexity", icon: "https://thinkvelocity.in/next-assets/perplexity_logo.png" },
    { key: "bolt", label: "Bolt", icon: "https://thinkvelocity.in/next-assets/bolt_colored.png" },
    { key: "suno", label: "Suno", icon: "https://thinkvelocity.in/next-assets/suno_logo.png" },
    { key: "lovable", label: "Lovable", icon: "https://thinkvelocity.in/next-assets/lovable_colored.png" },
    { key: "replit", label: "Replit", icon: "https://thinkvelocity.in/next-assets/replit_icon.png" },
    { key: "vercel", label: "v0", icon: "https://thinkvelocity.in/next-assets/v0_colored.png" },
  ];

  // NOTE: prefer the canonical, non-redirecting hostname for each provider so
  // the embedded prompt query param survives. `chat.openai.com` 301-redirects
  // to `chatgpt.com` and the redirect drops the `?q=` payload, so users land
  // on an empty ChatGPT input — i.e. "Open In looked like it didn't work."
  const PROVIDER_URLS = {
    openai: "https://chatgpt.com/",
    anthropic: "https://claude.ai/new",
    google: "https://gemini.google.com/app",
    grok: "https://grok.com/",
    mistral: "https://chat.mistral.ai/chat",
    perplexity: "https://www.perplexity.ai/",
    gamma: "https://gamma.app/create/generate",
    bolt: "https://bolt.new/",
    suno: "https://suno.com/create",
    lovable: "https://lovable.dev/",
    replit: "https://replit.com/",
    vercel: "https://v0.dev/",
    appalchemy: "https://appalchemy.ai/",
    flow: "https://labs.google/",
  };

  // Maximum length of the encoded prompt we will embed in the URL. Long
  // prompts can blow past browser URL length limits, so anything longer than
  // this falls back to the base URL and we rely on the scripted in-page
  // injector to fill the prompt instead. Matches v-chat's behavior in spirit
  // while staying defensive about URL caps (Chrome ~32k, but practical sites
  // start to misbehave well before that).
  const MAX_URL_PROMPT_LENGTH = 6000;

  // Per-platform URL builders that embed the (encoded) prompt directly in the
  // landing URL, mirroring how Vel-Next "v-chat" OpenInDropdown launches each
  // provider so the prompt is pre-filled on arrival.
  const PROMPT_URL_BUILDERS = {
    openai: (p) => `https://chatgpt.com/?q=${encodeURIComponent(p)}`,
    anthropic: (p) => `https://claude.ai/new?q=${encodeURIComponent(p)}`,
    google: (p) => `https://gemini.google.com/app?q=${encodeURIComponent(p)}`,
    mistral: (p) => `https://chat.mistral.ai/chat?q=${encodeURIComponent(p)}`,
    grok: (p) => `https://grok.com/?q=${encodeURIComponent(p)}`,
    bolt: (p) => `https://bolt.new/?prompt=${encodeURIComponent(p)}`,
    lovable: (p) => `https://lovable.dev/?prompt=${encodeURIComponent(p)}`,
    vercel: (p) => `https://v0.dev/?q=${encodeURIComponent(p)}`,
    gamma: (p) => `https://gamma.app/create/generate?prompt=${encodeURIComponent(p)}`,
    appalchemy: (p) => `https://appalchemy.ai/?prompt=${encodeURIComponent(p)}`,
    flow: (p) => `https://labs.google/?q=${encodeURIComponent(p)}`,
  };

  /**
   * Build the launch URL for an Open-In-Platform action.
   * Falls back to the provider's base URL if no builder exists or the prompt
   * is too long to embed safely. The in-page scripted injector still runs
   * after the tab opens, so the prompt always ends up in the input field.
   */
  function buildPromptUrl(key, prompt) {
    const base = PROVIDER_URLS[key] || PROVIDER_URLS.openai;
    const trimmed = String(prompt || "").trim();
    const builder = PROMPT_URL_BUILDERS[key];
    if (!builder || !trimmed) return base;
    if (encodeURIComponent(trimmed).length > MAX_URL_PROMPT_LENGTH) {
      return base;
    }
    try {
      return builder(trimmed);
    } catch (_) {
      return base;
    }
  }

  const URL_PATTERNS = [
    { key: "openai", re: /^https:\/\/(chat\.openai\.com|chatgpt\.com)/ },
    { key: "anthropic", re: /^https:\/\/claude\.ai/ },
    { key: "google", re: /^https:\/\/gemini\.google\.com/ },
    { key: "perplexity", re: /^https:\/\/(www\.)?perplexity\.ai/ },
    { key: "mistral", re: /^https:\/\/(www\.)?chat\.mistral\.ai/ },
    { key: "gamma", re: /^https:\/\/(www\.)?gamma\.app/ },
    { key: "bolt", re: /^https:\/\/(www\.)?bolt\.new/ },
    { key: "grok", re: /^https:\/\/(www\.)?grok\.com/ },
    { key: "suno", re: /^https:\/\/(www\.)?suno\.com/ },
    { key: "lovable", re: /^https:\/\/(www\.)?lovable\.dev/ },
    { key: "replit", re: /^https:\/\/(www\.)?replit\.com/ },
    { key: "vercel", re: /^https:\/\/(www\.)?v0\.(dev|app)/ },
    { key: "appalchemy", re: /^https:\/\/(www\.)?appalchemy\.ai/ },
  ];

  function platformKeyFromUrl(url) {
    const u = String(url || "");
    for (const p of URL_PATTERNS) {
      if (p.re.test(u)) return p.key;
    }
    return null;
  }

  function getPlatform(key) {
    return OPEN_IN_PLATFORMS.find((p) => p.key === key) || OPEN_IN_PLATFORMS[0];
  }

  function isTabScriptable(url) {
    const u = String(url || "");
    if (!u) return false;
    if (u.startsWith("chrome://") || u.startsWith("chrome-extension://") || u.startsWith("edge://")) {
      return false;
    }
    return u.startsWith("http://") || u.startsWith("https://");
  }

  root.TV.platformPromptActions = {
    OPEN_IN_PLATFORMS,
    PROVIDER_URLS,
    PROMPT_URL_BUILDERS,
    MAX_URL_PROMPT_LENGTH,
    platformKeyFromUrl,
    getPlatform,
    isTabScriptable,
    buildPromptUrl,
  };
})();
