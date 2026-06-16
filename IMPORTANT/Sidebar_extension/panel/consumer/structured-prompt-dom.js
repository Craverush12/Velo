/**
 * Mirrors Vel-Next StructuredPromptContent.jsx — preprocess + safe DOM (no innerHTML injection).
 * Used by Context "User Input" and Output enhanced/refined body (same regex rules as v-chat FormattedMessage).
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  function preprocessMessageContent(content) {
    const pf = root.TV.promptFormat;
    if (pf && typeof pf.preprocessMessageContent === "function") {
      return pf.preprocessMessageContent(content);
    }
    return String(content || "").trim();
  }

  function appendInlineTo(parent, text) {
    if (!text) return;
    const boldRegex = /\*\*([^*]+)\*\*/g;
    let last = 0;
    let m;
    while ((m = boldRegex.exec(text)) !== null) {
      if (m.index > last) {
        parent.appendChild(document.createTextNode(text.slice(last, m.index)));
      }
      const strong = document.createElement("strong");
      strong.className = "fmt-strong";
      strong.textContent = m[1];
      parent.appendChild(strong);
      last = m.index + m[0].length;
    }
    if (last < text.length) {
      parent.appendChild(document.createTextNode(text.slice(last)));
    }
  }

  /**
   * @param {HTMLElement} container — cleared and receives .formatted-content tree
   * @param {string} content
   */
  function appendFormatted(container, content) {
    while (container.firstChild) container.removeChild(container.firstChild);
    if (!content) return;

    const wrap = document.createElement("div");
    wrap.className = "formatted-content";

    const processed = preprocessMessageContent(content);
    const lines = processed.split("\n");
    const currentParagraph = [];

    function flushParagraph() {
      if (currentParagraph.length === 0) return;
      const p = document.createElement("p");
      p.className = "fmt-paragraph";
      appendInlineTo(p, currentParagraph.join(" "));
      wrap.appendChild(p);
      currentParagraph.length = 0;
    }

    lines.forEach((originalLine) => {
      let line = originalLine.trim();
      const indentMatch = originalLine.match(/^(\s+)/);
      const indentLevel = indentMatch ? Math.floor(indentMatch[1].length / 2) : 0;

      const numberedMatch = line.match(/^(\d+)\.\s+(.+)$/);
      if (numberedMatch) {
        flushParagraph();
        const row = document.createElement("div");
        row.className = "fmt-num-row";
        row.style.marginLeft = `${indentLevel * 1.5}rem`;
        const num = document.createElement("span");
        num.className = "fmt-num";
        num.textContent = `${numberedMatch[1]}.`;
        const body = document.createElement("span");
        body.className = "fmt-num-body";
        appendInlineTo(body, numberedMatch[2]);
        row.appendChild(num);
        row.appendChild(body);
        wrap.appendChild(row);
        return;
      }

      const bulletMatch = line.match(/^[•\-\*]\s+(.+)$/);
      if (bulletMatch) {
        flushParagraph();
        const row = document.createElement("div");
        row.className = "fmt-bullet-row";
        row.style.marginLeft = `${indentLevel * 1.5}rem`;
        const bullet = document.createElement("span");
        bullet.className =
          indentLevel > 0 ? "fmt-bullet fmt-bullet--nested" : "fmt-bullet";
        bullet.textContent = "●";
        const body = document.createElement("span");
        body.className = "fmt-bullet-body";
        appendInlineTo(body, bulletMatch[1]);
        row.appendChild(bullet);
        row.appendChild(body);
        wrap.appendChild(row);
        return;
      }

      const headerMatch = line.match(/^\*\*([^*]+)\*\*:?\s*(.*)$/);
      if (headerMatch) {
        flushParagraph();
        const head = document.createElement("div");
        head.className = "fmt-section-head";
        head.textContent = headerMatch[1];
        wrap.appendChild(head);
        const body = headerMatch[2] && headerMatch[2].trim();
        if (body) {
          const p = document.createElement("p");
          p.className = "fmt-paragraph";
          appendInlineTo(p, body);
          wrap.appendChild(p);
        }
        return;
      }

      if (line === "") {
        flushParagraph();
        return;
      }

      currentParagraph.push(line);
    });

    flushParagraph();
    container.appendChild(wrap);
  }

  function formatForExternalPaste(content) {
    const pf = root.TV.promptFormat;
    if (pf && typeof pf.formatForExternalPaste === "function") {
      return pf.formatForExternalPaste(content);
    }
    return preprocessMessageContent(content);
  }

  root.TV.structuredPromptDom = {
    preprocessMessageContent,
    appendFormatted,
    formatForExternalPaste,
  };
})();
