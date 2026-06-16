/**
 * Prompt text formatting for external paste / platform inject (Output-tab parity).
 * Pure string ops — safe for service worker via importScripts.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const SECTION_LABELS = [
    "Prompt",
    "Requirements",
    "Output Format",
    "Output",
    "Success Criteria",
    "Tone",
    "Role",
    "Context",
    "Industry Context",
    "Methodology",
    "Constraints",
    "Goal",
    "Instructions",
    "Task",
    "Background",
    "Format",
    "Examples",
    "Notes",
    "Steps",
  ];

  function preprocessMessageContent(content) {
    if (!content) return "";
    let text = typeof content === "string" ? content : String(content);
    text = text.replace(/\u00A0/g, " ");
    text = text.replace(/[\u2012\u2013\u2014\u2015\u2212\uFE58\uFE63\uFF0D]/g, "-");
    text = text.replace(/\s*\|\s+(\*\*[^*]+\*\*\s*:)/g, "\n\n$1");
    text = text.replace(/\s+-\s+(\*\*[^*]+\*\*\s*:)/g, "\n\n$1");
    text = text.replace(/([^\n])\s*-\s+(\*\*[^*]+\*\*\s*:)/g, "$1\n\n$2");
    text = text.replace(/([^\n])\s+(\*\*[^*]+\*\*\s*:)/g, "$1\n\n$2");
    SECTION_LABELS.forEach((label) => {
      const re = new RegExp(`([^\\n])\\s+(${label}\\s*:)`, "gi");
      text = text.replace(re, "$1\n\n$2");
    });
    text = text.replace(/(\S)\s+(\d+)\.\s+\*\*/g, "$1\n\n$2. **");
    text = text.replace(/(\S)\s+(\d+)\.\s+/g, "$1\n\n$2. ");
    text = text.replace(/(\S)\s+([•\-\*])\s+/g, "$1\n\n$2 ");
    text = text.replace(/\n{3,}/g, "\n\n");
    return text.trim();
  }

  /**
   * Strip Markdown syntax characters while preserving prose, line breaks,
   * bullets (`- item`) and numbered lists (`1. item`). Used to emit a
   * paste-friendly plain-text version of an enhanced prompt for platforms
   * that would otherwise render the asterisks/hashes literally.
   */
  function stripMarkdownSyntax(content) {
    if (!content) return "";
    let text = String(content);

    // Fenced code blocks: keep inner content, drop fences + language tag.
    text = text.replace(/```[A-Za-z0-9_-]*\r?\n?([\s\S]*?)```/g, (_m, body) => body);

    // Inline code: drop backticks around short spans (single backtick).
    text = text.replace(/`([^`\n]+)`/g, "$1");

    // Bold: **text** and __text__ (multi-pass to handle nested doublings).
    for (let i = 0; i < 3; i += 1) {
      const before = text;
      text = text.replace(/\*\*([\s\S]+?)\*\*/g, "$1");
      text = text.replace(/__([^_\n]+?)__/g, "$1");
      if (text === before) break;
    }

    // Italic: *text* (only when wrapping prose, not list bullets or **leftovers).
    text = text.replace(/(^|[^*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)/g, "$1$2");

    // Italic underscores: _text_ only when bracketed by word boundaries so
    // we never break snake_case identifiers or URLs.
    text = text.replace(/(^|[\s(])_(?=\S)([^_\n]+?)(?<=\S)_(?=[\s).,;:!?]|$)/g, "$1$2");

    // Strikethrough.
    text = text.replace(/~~([\s\S]+?)~~/g, "$1");

    // Markdown links / images → keep visible text only.
    text = text.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, "$1");
    text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1");

    // Per-line markers (headings, blockquotes, horizontal rules).
    text = text
      .split("\n")
      .map((line) => {
        let l = line.replace(/^\s{0,3}#{1,6}\s+/, "");
        l = l.replace(/^\s{0,3}>\s?/, "");
        if (/^\s*([-*_]\s*){3,}\s*$/.test(l)) return "";
        return l;
      })
      .join("\n");

    // Sweep any leftover stray asterisks now that emphasis/bold are gone.
    text = text.replace(/\*/g, "");

    // Collapse 3+ blank lines back to 2.
    text = text.replace(/\n{3,}/g, "\n\n");

    return text.trim();
  }

  function matchPlainSectionLabel(line) {
    for (let i = 0; i < SECTION_LABELS.length; i += 1) {
      const label = SECTION_LABELS[i];
      const re = new RegExp(`^${label.replace(/\s+/g, "\\s+")}\\s*:\\s*(.*)$`, "i");
      const m = line.match(re);
      if (m) {
        return { label, rest: m[1] || "" };
      }
    }
    return null;
  }

  /**
   * Format enhanced prompt for ChatGPT / Claude / etc. — same structure as Output tab.
   * Uses markdown section headers and list line breaks platforms understand.
   */
  function formatForExternalPaste(content) {
    if (!content) return "";
    const processed = preprocessMessageContent(content);
    const lines = processed.split("\n");
    const out = [];
    const paragraph = [];

    function flushParagraph() {
      if (paragraph.length === 0) return;
      if (out.length > 0 && out[out.length - 1] !== "") out.push("");
      out.push(paragraph.join(" "));
      paragraph.length = 0;
    }

    function pushSectionHead(title, inlineBody) {
      flushParagraph();
      if (out.length > 0) out.push("");
      out.push(`${title.trim()}:`);
      const body = inlineBody && String(inlineBody).trim();
      if (body) out.push(body);
    }

    lines.forEach((originalLine) => {
      const line = originalLine.trim();
      const indentMatch = originalLine.match(/^(\s+)/);
      const indent = indentMatch ? "  ".repeat(Math.floor(indentMatch[1].length / 2)) : "";

      if (line === "") {
        flushParagraph();
        return;
      }

      const numberedMatch = line.match(/^(\d+)\.\s+(.+)$/);
      if (numberedMatch) {
        flushParagraph();
        out.push(`${indent}${numberedMatch[1]}. ${numberedMatch[2]}`);
        return;
      }

      const bulletMatch = line.match(/^[•\-\*]\s+(.+)$/);
      if (bulletMatch) {
        flushParagraph();
        out.push(`${indent}- ${bulletMatch[1]}`);
        return;
      }

      const headerMatch = line.match(/^\*\*([^*]+)\*\*:?\s*(.*)$/);
      if (headerMatch) {
        pushSectionHead(headerMatch[1], headerMatch[2]);
        return;
      }

      const plainSection = matchPlainSectionLabel(line);
      if (plainSection) {
        pushSectionHead(plainSection.label, plainSection.rest);
        return;
      }

      paragraph.push(line);
    });

    flushParagraph();
    const structured = out.join("\n").replace(/\n{3,}/g, "\n\n").trim();
    return stripMarkdownSyntax(structured);
  }

  root.TV.promptFormat = {
    preprocessMessageContent,
    formatForExternalPaste,
    stripMarkdownSyntax,
  };
})();
