/**
 * Consistent titles for saved / enhanced prompts in sidebar lists.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  function truncate(text, max) {
    const t = String(text || "").replace(/\s+/g, " ").trim();
    if (t.length <= max) return t;
    return `${t.slice(0, Math.max(0, max - 1))}…`;
  }

  function stripHashPrefix(text) {
    return String(text || "")
      .replace(/^#+\s*/, "")
      .trim();
  }

  function firstMeaningfulLine(text) {
    const lines = String(text || "")
      .split(/\n/)
      .map((l) => l.trim())
      .filter(Boolean);
    return lines[0] || "";
  }

  function isGenericTitle(title) {
    if (!title) return true;
    const t = String(title).toLowerCase().trim();
    return (
      t === "summary" ||
      t === "# summary" ||
      t === "untitled" ||
      t === "saved prompt" ||
      t === "prompt" ||
      /^option\s*[a-d0-9]/i.test(t) ||
      t.length < 3
    );
  }

  function extractMeaningfulTitle(text, maxLen) {
    if (!text) return "";
    const cleaned = String(text)
      .replace(/^#+\s*/gm, "")
      .replace(/\*\*/g, "")
      .trim();
    const lines = cleaned.split(/\n/).map((l) => l.trim()).filter(Boolean);
    for (const line of lines) {
      if (line.length > 10 && !/^(summary|overview|introduction|context|background)$/i.test(line)) {
        return truncate(line, maxLen);
      }
    }
    return lines[0] ? truncate(lines[0], maxLen) : "";
  }

  /**
   * @param {{ title?: string, userPrompt?: string, user_prompt?: string, body?: string, preview?: string, aiType?: string, ai_type?: string }} item
   */
  function formatSavedPromptTitle(item, opts) {
    const options = opts && typeof opts === "object" ? opts : {};
    const maxLen = options.maxLen != null ? options.maxLen : 72;
    const withHash = options.withHash !== false;

    const apiTitle = stripHashPrefix(item && (item.title || ""));
    const userPrompt = String(
      (item && (item.userPrompt || item.user_prompt)) || ""
    ).trim();
    const body = String((item && (item.body || item.preview)) || "").trim();

    let base = "";

    if (userPrompt && !isGenericTitle(userPrompt)) {
      base = extractMeaningfulTitle(userPrompt, maxLen);
    }

    if (!base && apiTitle && !isGenericTitle(apiTitle)) {
      base = truncate(apiTitle, maxLen);
    }

    if (!base && body) {
      base = extractMeaningfulTitle(body, maxLen);
    }

    if (!base) {
      base = "Enhanced prompt";
    }

    base = stripHashPrefix(base);

    if (withHash && !base.startsWith("#")) {
      return `# ${base}`;
    }
    return base;
  }

  root.TV.promptDisplayTitle = {
    formatSavedPromptTitle,
    stripHashPrefix,
    truncate,
  };
})();
