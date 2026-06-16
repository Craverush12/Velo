/**
 * Authenticated prompt library + public memory list for consumer sidebar.
 * Runs in the service worker (importScripts). Uses TV.tokenManager + TV.chromeStorage.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : global;
  root.TV = root.TV || {};

  function joinUrl(base, path) {
    const b = String(base || "").replace(/\/$/, "");
    const p = path.startsWith("/") ? path : `/${path}`;
    return `${b}${p}`;
  }

  /**
   * Public processed-context list — Vel-Next `NEXT_PUBLIC_PROCESSED_CONTEXT_PUBLIC_URL` and
   * Extension-new `PROCESSED_CONTEXT_PUBLIC_URL` use this path on production (not `.../api/v1/...` alone).
   */
  const TV_PROCESSED_CONTEXT_PUBLIC_USER_PROD =
    "https://thinkvelocity.in/backend-V1-D/api/v1/processed-context/public/user";

  function sanitizeApiErrorText(text) {
    const t = String(text || "").trim();
    if (!t) return "Request failed";
    if (/^\s*</.test(t) || /<!DOCTYPE/i.test(t) || /<html[\s>]/i.test(t)) {
      return "Server returned a web page instead of JSON (check API URL).";
    }
    return t.length > 220 ? `${t.slice(0, 219)}…` : t;
  }

  /**
   * Extension-new `BACKEND_PROMPT_BASE_URL` = `https://thinkvelocity.in/backend-V1-D` + `/prompt/...`.
   * Vel `apiClient` uses `API_BASE_URL` without `/api/v1` for these routes. Production `apiBase`
   * `https://thinkvelocity.in/api/v1` would wrongly hit `/api/v1/prompt/...` (404).
   */
  function resolveThinkVelocityPromptMountBase(apiBase) {
    const b = String(apiBase || "").replace(/\/$/, "");
    if (!b) return "https://thinkvelocity.in/backend-V1-D";
    try {
      const abs = b.startsWith("http://") || b.startsWith("https://") ? b : `https://${b}`;
      const u = new URL(abs);
      const h = u.hostname.replace(/^www\./i, "");
      if (h !== "thinkvelocity.in") return b;
      if (b.toLowerCase().includes("backend-v1-d")) {
        if (/\/api\/v1$/i.test(b)) return b.replace(/\/api\/v1$/i, "");
        return b;
      }
      return "https://thinkvelocity.in/backend-V1-D";
    } catch (e) {
      return b;
    }
  }

  function resolveProcessedContextBaseUrl(apiBase) {
    const publicPrefix = resolveProcessedContextPublicUserPrefix(apiBase);
    if (publicPrefix.includes("/public/user")) {
      return publicPrefix.split("/public/user")[0];
    }
    const b = String(apiBase || "").replace(/\/$/, "");
    if (!b) return "https://thinkvelocity.in/backend-V1-D/api/v1/processed-context";
    if (/\/api\/v1$/i.test(b)) return `${b}/processed-context`;
    return `${b}/api/v1/processed-context`;
  }

  async function getConsumerUserId() {
    const TV = root.TV;
    const keys = await TV.chromeStorage.get([TV.STORAGE_KEYS.USER_ID]);
    return String(keys[TV.STORAGE_KEYS.USER_ID] || "").trim();
  }

  function resolveProcessedContextPublicUserPrefix(apiBase) {
    const b = String(apiBase || "").replace(/\/$/, "");
    if (!b) return TV_PROCESSED_CONTEXT_PUBLIC_USER_PROD;
    try {
      const abs = b.startsWith("http://") || b.startsWith("https://") ? b : `https://${b}`;
      const u = new URL(abs);
      const h = u.hostname.replace(/^www\./i, "");
      if (h === "thinkvelocity.in" && !b.toLowerCase().includes("backend-v1-d")) {
        return TV_PROCESSED_CONTEXT_PUBLIC_USER_PROD;
      }
    } catch (e) {}
    if (/\/api\/v1$/i.test(b)) return `${b}/processed-context/public/user`;
    return `${b}/api/v1/processed-context/public/user`;
  }

  function truncate(s, max) {
    const t = (s || "").replace(/\s+/g, " ").trim();
    if (t.length <= max) return t;
    return `${t.slice(0, max - 1)}…`;
  }

  function firstHashTitle(text) {
    const line = (text || "").split("\n")[0].trim() || "Saved prompt";
    const withHash = line.startsWith("#") ? line : `# ${truncate(line, 56)}`;
    return truncate(withHash, 72);
  }

  function unwrapListPayload(json) {
    if (!json || typeof json !== "object") return [];
    const d = json.data != null ? json.data : json;
    if (Array.isArray(d)) return d;
    if (Array.isArray(d.items)) return d.items;
    if (Array.isArray(d.collections)) return d.collections;
    if (Array.isArray(d.prompts)) return d.prompts;
    if (Array.isArray(d.rows)) return d.rows;
    if (Array.isArray(d.results)) return d.results;
    if (Array.isArray(d.memories)) return d.memories;
    if (Array.isArray(d.contexts)) return d.contexts;
    return [];
  }

  function unwrapMeta(json, fallbackLen) {
    const d = json && json.data != null ? json.data : json || {};
    const total = typeof d.total === "number" ? d.total : typeof d.count === "number" ? d.count : null;
    const page = typeof d.page === "number" ? d.page : typeof d.currentPage === "number" ? d.currentPage : null;
    const hasMore =
      typeof d.hasMore === "boolean"
        ? d.hasMore
        : typeof d.has_next === "boolean"
          ? d.has_next
          : total != null && page != null && fallbackLen != null
            ? page * (d.limit || fallbackLen) < total
            : null;
    return { total, page, hasMore };
  }

  async function listCollections() {
    const TV = root.TV;
    const accessToken = await TV.tokenManager.ensureFreshAccessToken(false);
    const base = await TV.tokenManager.getApiBase();
    const promptBase = resolveThinkVelocityPromptMountBase(base);
    /** Vel-Next `v-chat.jsx` / PromptGrid: `GET /prompt/collections?limit=1000&page=1` on backend-V1-D mount. */
    const url = `${joinUrl(promptBase, "/prompt/collections")}?limit=1000&page=1`;
    const res = await fetch(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
    });
    const text = await res.text().catch(() => "");
    let json = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch (e) {
      json = null;
    }
    if (!res.ok) {
      const raw = (json && (json.message || json.error)) || text || `HTTP ${res.status}`;
      return { success: false, error: sanitizeApiErrorText(typeof raw === "string" ? raw : String(raw)) };
    }
    const ct = (res.headers && res.headers.get && res.headers.get("content-type")) || "";
    if (text && !ct.includes("application/json") && /^\s*</.test(text)) {
      return { success: false, error: "Collections API returned HTML instead of JSON." };
    }
    const d = json && json.data != null ? json.data : json;
    const raw = Array.isArray(d && d.collections) ? d.collections : unwrapListPayload(json);
    const items = raw.map((c) => ({
      id: c.collection_id || c.collectionId || c.id || c._id,
      name: c.name || c.title || "Untitled",
      count: c.prompt_count ?? c.promptCount ?? c.count ?? (Array.isArray(c.prompts) ? c.prompts.length : null),
    }));
    return { success: true, data: { items } };
  }

  async function listEnhancedPrompts(page, limit) {
    const TV = root.TV;
    const pageN = Math.max(1, parseInt(String(page || 1), 10) || 1);
    const limitN = Math.min(1000, Math.max(1, parseInt(String(limit || 15), 10) || 15));
    const accessToken = await TV.tokenManager.ensureFreshAccessToken(false);
    const keys = await TV.chromeStorage.get([TV.STORAGE_KEYS.USER_ID]);
    const userId = keys[TV.STORAGE_KEYS.USER_ID] || "";
    if (!userId) {
      return { success: false, error: "Missing user id" };
    }
    const base = await TV.tokenManager.getApiBase();
    const promptBase = resolveThinkVelocityPromptMountBase(base);
    /** Vel-Next `PromptGrid.jsx`: `GET /prompt/enhanced-prompts/user/:userId?page=&limit=` */
    const path = `/prompt/enhanced-prompts/user/${encodeURIComponent(userId)}`;
    const url = `${joinUrl(promptBase, path)}?page=${pageN}&limit=${limitN}`;
    const res = await fetch(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
    });
    const text = await res.text().catch(() => "");
    let json = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch (e) {
      json = null;
    }
    if (!res.ok) {
      const raw = (json && (json.message || json.error)) || text || `HTTP ${res.status}`;
      return { success: false, error: sanitizeApiErrorText(typeof raw === "string" ? raw : String(raw)) };
    }
    const ctEn = (res.headers && res.headers.get && res.headers.get("content-type")) || "";
    if (text && !ctEn.includes("application/json") && /^\s*</.test(text)) {
      return { success: false, error: "Prompt history API returned HTML instead of JSON." };
    }
    const d = json && json.data != null ? json.data : json;
    const raw = Array.isArray(d && d.enhanced_prompts) ? d.enhanced_prompts : unwrapListPayload(json);
    const meta = unwrapMeta(json, raw.length);
    let hasMore = meta.hasMore;
    if (hasMore == null) {
      hasMore = raw.length >= limitN;
    }
    const items = raw.map((r) => {
      const userPrompt = String(r.user_prompt || r.userPrompt || "").trim();
      const body = String(r.enhanced_prompt || r.enhancedPrompt || r.body || r.text || "").trim();
      const mode = r.mode || r.enhancement_mode || r.style || r.enhancementMode || "quick";
      const titleItem = {
        title: r.title,
        userPrompt,
        user_prompt: userPrompt,
        body,
        preview: truncate(userPrompt || body, 220),
        aiType: (r.ai_type || r.aiType || "chatgpt").toLowerCase(),
      };
      // Prompt-book cards already style the title as a heading, so emit a
      // clean plain-text title without the literal `# ` markdown prefix.
      const formatTitle =
        root.TV.promptDisplayTitle && typeof root.TV.promptDisplayTitle.formatSavedPromptTitle === "function"
          ? root.TV.promptDisplayTitle.formatSavedPromptTitle(titleItem, { withHash: false })
          : firstHashTitle(userPrompt || body);
      // Run the body through the shared markdown stripper so previews show
      // clean prose (no stray `**bold**`, `__under__`, `[link](url)`, etc.)
      // — same formatter used for external-paste output.
      const pf = root.TV && root.TV.promptFormat;
      const rawPreviewSource = body || userPrompt;
      const previewText = pf && typeof pf.stripMarkdownSyntax === "function"
        ? pf.stripMarkdownSyntax(rawPreviewSource).replace(/\s+/g, " ").trim()
        : rawPreviewSource.replace(/^#+\s*/gm, "").replace(/\*\*/g, "").trim();
      return {
        id: r.id || r.enhanced_prompt_id || r.enhancedPromptId,
        title: formatTitle,
        preview: truncate(previewText, 220),
        userPrompt,
        body,
        tag: String(mode).toUpperCase(),
        aiType: (r.ai_type || r.aiType || "chatgpt").toLowerCase(),
      };
    });
    return { success: true, data: { items, page: pageN, limit: limitN, hasMore } };
  }

  async function listMemories(page, limit) {
    const TV = root.TV;
    const pageN = Math.max(1, parseInt(String(page || 1), 10) || 1);
    /** Vel-Next `MemoryPage.jsx` uses `limit=20` on the public list. */
    const limitN = Math.min(50, Math.max(1, parseInt(String(limit || 20), 10) || 20));
    const keys = await TV.chromeStorage.get([TV.STORAGE_KEYS.USER_ID]);
    const userId = keys[TV.STORAGE_KEYS.USER_ID] || "";
    if (!userId) {
      return { success: false, error: "Missing user id" };
    }
    const base = await TV.tokenManager.getApiBase();
    const prefix = resolveProcessedContextPublicUserPrefix(base);
    const userSeg = encodeURIComponent(String(userId).trim());
    /** First page matches Vel: `?limit=20` only; later pages add `&page=` if the API supports it. */
    let qs = `limit=${limitN}`;
    if (pageN > 1) qs += `&page=${pageN}`;
    const url = `${prefix}/${userSeg}?${qs}`;
    const res = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    const text = await res.text().catch(() => "");
    let json = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch (e) {
      json = null;
    }
    if (!res.ok) {
      const raw = (json && (json.message || json.error)) || text || `HTTP ${res.status}`;
      return { success: false, error: sanitizeApiErrorText(typeof raw === "string" ? raw : String(raw)) };
    }
    const ct = (res.headers && res.headers.get && res.headers.get("content-type")) || "";
    if (text && !ct.includes("application/json") && /^\s*</.test(text)) {
      return { success: false, error: "Memories API returned HTML instead of JSON." };
    }
    if (json == null && text && /^\s*</.test(text.trim())) {
      return { success: false, error: "Memories API returned a non-JSON response." };
    }
    const d = json && json.data != null ? json.data : json;
    const contexts = Array.isArray(d && d.contexts) ? d.contexts : [];
    /** Same filter as `MemoryPage.jsx` loadMemories */
    const filtered = contexts.filter(
      (ctx) => ctx && typeof ctx.essence === "string" && ctx.essence.trim() !== ""
    );
    const meta = unwrapMeta(json, filtered.length);
    let hasMore = meta.hasMore;
    if (hasMore == null) {
      hasMore = filtered.length >= limitN;
    }
    const items = filtered.map((ctx, i) => {
      const essence = String(ctx.essence).trim();
      const preview = truncate(essence, 240);
      return {
        id: ctx.id != null ? ctx.id : ctx._id != null ? ctx._id : `mem_${pageN}_${i}`,
        sessionId: ctx.sessionId != null ? ctx.sessionId : ctx.session_id != null ? ctx.session_id : null,
        text: essence,
        title: ctx.title || firstHashTitle(essence || "Memory"),
        preview,
        source: ctx.platform || "Velocity",
        timeAgo: ctx.processedAt || ctx.updatedAt || ctx.processed_at || "",
      };
    });
    return { success: true, data: { items, page: pageN, limit: limitN, hasMore } };
  }

  async function updateMemoryEssence(payload) {
    const p = payload && typeof payload === "object" ? payload : {};
    const id = p.id != null ? String(p.id) : "";
    const essence = String(p.essence || "").trim();
    if (!id || !essence) {
      return { success: false, error: "Memory id and text are required" };
    }
    const userId = await getConsumerUserId();
    if (!userId) {
      return { success: false, error: "Missing user id" };
    }
    const TV = root.TV;
    const base = resolveProcessedContextBaseUrl(await TV.tokenManager.getApiBase());
    const sessionId = p.sessionId != null ? String(p.sessionId).trim() : "";
    const userQ = `userId=${encodeURIComponent(userId)}`;
    const url = sessionId
      ? `${base}/session/${encodeURIComponent(sessionId)}/essence?${userQ}`
      : `${base}/${encodeURIComponent(id)}/essence?${userQ}`;
    const res = await fetch(url, {
      method: "PATCH",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({ essence }),
    });
    const text = await res.text().catch(() => "");
    let json = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch (e) {
      json = null;
    }
    if (!res.ok) {
      const raw = (json && (json.message || json.error)) || text || `HTTP ${res.status}`;
      return { success: false, error: sanitizeApiErrorText(typeof raw === "string" ? raw : String(raw)) };
    }
    return { success: true, data: { id, essence } };
  }

  async function deleteMemoryEssence(payload) {
    const p = payload && typeof payload === "object" ? payload : {};
    const id = p.id != null ? String(p.id) : "";
    if (!id) {
      return { success: false, error: "Memory id is required" };
    }
    const userId = await getConsumerUserId();
    if (!userId) {
      return { success: false, error: "Missing user id" };
    }
    const TV = root.TV;
    const base = resolveProcessedContextBaseUrl(await TV.tokenManager.getApiBase());
    const url = `${base}/${encodeURIComponent(id)}/essence?userId=${encodeURIComponent(userId)}`;
    const res = await fetch(url, { method: "DELETE", headers: { Accept: "application/json" } });
    const text = await res.text().catch(() => "");
    let json = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch (e) {
      json = null;
    }
    if (!res.ok) {
      const raw = (json && (json.message || json.error)) || text || `HTTP ${res.status}`;
      return { success: false, error: sanitizeApiErrorText(typeof raw === "string" ? raw : String(raw)) };
    }
    return { success: true, data: { id } };
  }

  async function createMemoryEssence(payload) {
    const p = payload && typeof payload === "object" ? payload : {};
    const essence = String(p.essence || "").trim();
    if (!essence) {
      return { success: false, error: "Memory text is required" };
    }
    const userId = await getConsumerUserId();
    if (!userId) {
      return { success: false, error: "Missing user id" };
    }
    const TV = root.TV;
    const base = resolveProcessedContextBaseUrl(await TV.tokenManager.getApiBase());
    const sessionId =
      p.sessionId != null && String(p.sessionId).trim()
        ? String(p.sessionId).trim()
        : `manual-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    const res = await fetch(`${base}/essence`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({
        userId,
        sessionId,
        essence,
        platform: String(p.platform || "velocity").trim() || "velocity",
      }),
    });
    const text = await res.text().catch(() => "");
    let json = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch (e) {
      json = null;
    }
    if (!res.ok) {
      const raw = (json && (json.message || json.error)) || text || `HTTP ${res.status}`;
      return { success: false, error: sanitizeApiErrorText(typeof raw === "string" ? raw : String(raw)) };
    }
    return { success: true, data: (json && json.data) || json || { sessionId } };
  }

  async function createCollection(name, options) {
    const n = String(name || "").trim();
    if (!n) {
      return { success: false, error: "Name is required" };
    }
    const opt = options && typeof options === "object" ? options : {};
    const TV = root.TV;
    const accessToken = await TV.tokenManager.ensureFreshAccessToken(false);
    const base = await TV.tokenManager.getApiBase();
    const promptBase = resolveThinkVelocityPromptMountBase(base);
    const url = joinUrl(promptBase, "/prompt/collections");
    /** Vel-Next `v-chat.jsx` `createAndAddToCollection` / PromptGrid: name, description, tag */
    const res = await fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        name: n,
        description: String(opt.description || "").trim() || "Enhanced prompt collection",
        tag: String(opt.tag || "Work").trim() || "Work",
      }),
    });
    const text = await res.text().catch(() => "");
    let json = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch (e) {
      json = null;
    }
    if (!res.ok) {
      const raw = (json && (json.message || json.error)) || text || `HTTP ${res.status}`;
      return { success: false, error: sanitizeApiErrorText(typeof raw === "string" ? raw : String(raw)) };
    }
    const created = (json && json.data) || json || {};
    const cid = created.collection_id || created.collectionId || created.id;
    return {
      success: true,
      data: {
        id: cid,
        name: created.name || n,
      },
    };
  }

  root.TV.consumerLibraryFetch = {
    listCollections,
    listEnhancedPrompts,
    listMemories,
    createCollection,
    updateMemoryEssence,
    deleteMemoryEssence,
    createMemoryEssence,
  };
})();
