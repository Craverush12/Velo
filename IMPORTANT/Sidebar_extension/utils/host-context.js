/**
 * Map active browser tab URLs to Velocity host / collection / open-in keys.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const HOST_RULES = [
    { hostKey: "chatgpt", aiType: "chatgpt", openInKey: "openai", label: "ChatGPT", patterns: [/chat\.openai\.com/i, /chatgpt\.com/i] },
    { hostKey: "claude", aiType: "claude", openInKey: "anthropic", label: "Claude", patterns: [/claude\.ai/i] },
    { hostKey: "google", aiType: "gemini", openInKey: "google", label: "Gemini", patterns: [/gemini\.google\.com/i] },
    { hostKey: "perplexity", aiType: "perplexity", openInKey: "perplexity", label: "Perplexity", patterns: [/perplexity\.ai/i] },
    { hostKey: "mistral", aiType: "mistral", openInKey: "mistral", label: "Mistral", patterns: [/chat\.mistral\.ai/i] },
    { hostKey: "grok", aiType: "grok", openInKey: "grok", label: "Grok", patterns: [/grok\.com/i] },
    { hostKey: "suno", aiType: "suno", openInKey: "suno", label: "Suno", patterns: [/suno\.com/i] },
    { hostKey: "bolt", aiType: "bolt", openInKey: "bolt", label: "Bolt", patterns: [/bolt\.new/i] },
    { hostKey: "lovable", aiType: "lovable", openInKey: "lovable", label: "Lovable", patterns: [/lovable\.dev/i] },
    { hostKey: "replit", aiType: "replit", openInKey: "replit", label: "Replit", patterns: [/replit\.com/i] },
    { hostKey: "vercel", aiType: "vercel", openInKey: "vercel", label: "v0", patterns: [/v0\.dev/i, /v0\.app/i] },
    { hostKey: "gamma", aiType: "gamma", openInKey: "gamma", label: "Gamma", patterns: [/gamma\.app/i] },
  ];

  function detectHostFromUrl(urlStr) {
    const href = String(urlStr || "").trim();
    if (!href) return null;
    try {
      const u = new URL(href);
      if (u.protocol !== "https:" && u.protocol !== "http:") return null;
      const host = u.hostname.replace(/^www\./i, "");
      for (const rule of HOST_RULES) {
        if (rule.patterns.some((re) => re.test(host) || re.test(href))) {
          return {
            hostKey: rule.hostKey,
            aiType: rule.aiType,
            openInKey: rule.openInKey,
            label: rule.label,
            platformFeedId: `pl-${rule.aiType}`,
          };
        }
      }
    } catch (_) {}
    return null;
  }

  function normalizeAiType(value) {
    const t = String(value || "").toLowerCase().trim();
    if (!t) return "";
    if (t === "openai" || t === "chatgpt") return "chatgpt";
    if (t === "anthropic") return "claude";
    if (t === "google" || t === "gemini") return "gemini";
    return t;
  }

  root.TV.hostContext = {
    HOST_RULES,
    detectHostFromUrl,
    normalizeAiType,
  };
})();
