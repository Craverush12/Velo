/**
 * Lightweight markdown-ish renderer used by the prompt detail popups
 * (Prompt Library + Prompt Book). Handles the small subset of markdown
 * that enhanced prompts actually contain so the popup body renders as
 * structured text instead of one wall of escaped characters.
 *
 * Supports:
 *   - `#`, `##`, `###` headings (start of line)
 *   - `- ` and `* ` bullet items (grouped into bullet blocks)
 *   - `1.` numbered items
 *   - `**bold**` inline
 *   - `*italic*` inline (single-asterisk pairs)
 *   - `` `code` `` inline
 *
 * It also normalises a common storage shape where enhanced prompts have
 * lost their newlines: sequences like ` - **Key**:` are split back into
 * separate bullet lines so the result is readable.
 *
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /**
   * Re-introduce line breaks the model intended but storage collapsed.
   * Conservative: only splits on patterns that are clearly list markers
   * or section labels.
   */
  function normalizeBlocks(raw) {
    let s = String(raw || "").replace(/\r\n?/g, "\n");
    s = s.replace(/[ \t]+-\s+\*\*/g, "\n- **");
    s = s.replace(/([.!?])\s+\*\*([^*\n]{1,80}?)\*\*\s*:/g, "$1\n\n**$2**:");
    s = s.replace(/\n{3,}/g, "\n\n");
    return s;
  }

  function renderInline(escapedText) {
    let out = escapedText;
    out = out.replace(
      /`([^`\n]+)`/g,
      (_, code) => `<code class="library-prompt-detail__md-code">${code}</code>`
    );
    out = out.replace(
      /\*\*([^*\n]+)\*\*/g,
      (_, b) => `<strong class="library-prompt-detail__md-b">${b}</strong>`
    );
    out = out.replace(
      /(^|[^*\w])\*([^*\n]+)\*(?!\*)/g,
      (_, pre, i) => `${pre}<em class="library-prompt-detail__md-i">${i}</em>`
    );
    return out;
  }

  function makeLi(content) {
    return `<li class="library-prompt-detail__md-li">${content}</li>`;
  }

  function flushList(out, listBuf, ordered) {
    if (!listBuf.length) return;
    const tag = ordered ? "ol" : "ul";
    const cls = ordered
      ? "library-prompt-detail__md-ol"
      : "library-prompt-detail__md-ul";
    out.push(`<${tag} class="${cls}">${listBuf.join("")}</${tag}>`);
    listBuf.length = 0;
  }

  function formatBlock(raw) {
    const text = normalizeBlocks(raw);
    if (!text.trim()) return "";

    const lines = text.split("\n");
    const out = [];
    const listBuf = [];
    let listOrdered = false;
    let inList = false;

    function closeList() {
      if (inList) {
        flushList(out, listBuf, listOrdered);
        inList = false;
      }
    }

    lines.forEach((line) => {
      const t = line.replace(/\s+$/, "");
      const trimmed = t.trim();

      if (!trimmed) {
        closeList();
        out.push('<p class="library-prompt-detail__md-sp">&nbsp;</p>');
        return;
      }

      const h3 = /^###\s+(.*)$/.exec(trimmed);
      if (h3) {
        closeList();
        out.push(
          `<p class="library-prompt-detail__md-h library-prompt-detail__md-h--3">${renderInline(escapeHtml(h3[1]))}</p>`
        );
        return;
      }
      const h2 = /^##\s+(.*)$/.exec(trimmed);
      if (h2) {
        closeList();
        out.push(
          `<p class="library-prompt-detail__md-h library-prompt-detail__md-h--2">${renderInline(escapeHtml(h2[1]))}</p>`
        );
        return;
      }
      const h1 = /^#\s+(.*)$/.exec(trimmed);
      if (h1) {
        closeList();
        out.push(
          `<p class="library-prompt-detail__md-h">${renderInline(escapeHtml(h1[1]))}</p>`
        );
        return;
      }

      const bullet = /^[-*]\s+(.*)$/.exec(trimmed);
      if (bullet) {
        if (!inList || listOrdered) {
          closeList();
          listOrdered = false;
          inList = true;
        }
        listBuf.push(makeLi(renderInline(escapeHtml(bullet[1]))));
        return;
      }

      const num = /^(\d+)\.\s+(.*)$/.exec(trimmed);
      if (num) {
        if (!inList || !listOrdered) {
          closeList();
          listOrdered = true;
          inList = true;
        }
        listBuf.push(makeLi(renderInline(escapeHtml(num[2]))));
        return;
      }

      closeList();
      out.push(
        `<p class="library-prompt-detail__md-p">${renderInline(escapeHtml(t))}</p>`
      );
    });

    closeList();
    return out.join("");
  }

  root.TV.promptMarkdown = {
    formatBlock,
    escapeHtml,
  };
})();
