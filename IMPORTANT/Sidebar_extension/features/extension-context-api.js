/**
 * POST /extension/context/capture (Extension-new / Postman "03 Extension capture").
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
   * @param {object} payload - Backend-specific JSON (attachments, page extract, etc.)
   */
  async function postContextCapture(payload) {
    const TV = root.TV;
    const accessToken = await TV.tokenManager.ensureFreshAccessToken(false);
    const base = await TV.tokenManager.getApiBase();
    const url = joinUrl(base, "/extension/context/capture");
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify(payload && typeof payload === "object" ? payload : {}),
    });
    const text = await res.text().catch(() => "");
    let json = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch (e) {
      json = null;
    }
    if (!res.ok) {
      return {
        success: false,
        error: (json && (json.message || json.error)) || text.slice(0, 200) || `HTTP ${res.status}`,
      };
    }
    return { success: true, data: json || { ok: true } };
  }

  root.TV.extensionContextApi = {
    postContextCapture,
  };
})();
