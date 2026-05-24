/**
 * Token + API base helpers (aligned with Extension-new/utils/tokenManager.js).
 * Depends on TV.chromeStorage and TV.localStorageSync.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const API_BASES_BY_ENV = {
    production: "https://thinkvelocity.in/api/v1",
    staging: "https://staging.thinkvelocity.in/api/v1",
    development: "https://thinkvelocity.in/backend-V1-D",
  };
  const DEFAULT_API_BASE = API_BASES_BY_ENV.development;
  const REFRESH_ENDPOINT = "/refresh-token";
  const FREE_TRIAL_TOKEN = "free-trial";
  const TOKEN_EXPIRY_SKEW_MS = 15 * 1000;

  const STORAGE_KEYS = {
    ACCESS_TOKEN: "accessToken",
    REFRESH_TOKEN: "refreshToken",
    ACCESS_EXP: "accessTokenExpiresAt",
    REFRESH_EXP: "refreshTokenExpiresAt",
  };

  let API_BASES = [DEFAULT_API_BASE];

  async function detectEnvironment() {
    try {
      const stored = await root.TV.chromeStorage.get(["environment"]);
      if (stored.environment && API_BASES_BY_ENV[stored.environment]) {
        return stored.environment;
      }
      if (typeof chrome !== "undefined" && chrome.tabs) {
        try {
          const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
          if (tabs && tabs.length > 0 && tabs[0].url) {
            const hostname = new URL(tabs[0].url).hostname;
            if (
              hostname.includes("thinkvelocity.in") &&
              !hostname.includes("dev") &&
              !hostname.includes("staging") &&
              !hostname.includes("test")
            ) {
              return "production";
            }
            if (hostname.includes("staging") || hostname.includes("test")) {
              return "staging";
            }
          }
        } catch (e) {}
      }
      return "development";
    } catch (error) {
      return "development";
    }
  }

  async function getApiBase() {
    try {
      const stored = await root.TV.chromeStorage.get(["apiBase", "environment"]);
      if (stored.apiBase) return stored.apiBase;
      const env = await detectEnvironment();
      return API_BASES_BY_ENV[env] || DEFAULT_API_BASE;
    } catch (error) {
      return DEFAULT_API_BASE;
    }
  }

  function decodeJwt(token) {
    try {
      const [, payload] = token.split(".");
      if (!payload) return null;
      const decoded = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
      return JSON.parse(decoded);
    } catch (error) {
      return null;
    }
  }

  function extractExpiry(token) {
    const decoded = decodeJwt(token);
    if (!decoded?.exp) return null;
    return decoded.exp * 1000;
  }

  function isExpired(expiry) {
    if (!expiry) return true;
    return Date.now() >= expiry - TOKEN_EXPIRY_SKEW_MS;
  }

  async function getStoredTokens() {
    const data = await root.TV.chromeStorage.get([
      STORAGE_KEYS.ACCESS_TOKEN,
      STORAGE_KEYS.REFRESH_TOKEN,
      STORAGE_KEYS.ACCESS_EXP,
      STORAGE_KEYS.REFRESH_EXP,
    ]);
    return {
      accessToken: data[STORAGE_KEYS.ACCESS_TOKEN] || null,
      refreshToken: data[STORAGE_KEYS.REFRESH_TOKEN] || null,
      accessTokenExpiresAt: data[STORAGE_KEYS.ACCESS_EXP] || null,
      refreshTokenExpiresAt: data[STORAGE_KEYS.REFRESH_EXP] || null,
    };
  }

  async function storeAuthTokens({ accessToken, refreshToken }) {
    const updates = {};

    if (accessToken) {
      updates[STORAGE_KEYS.ACCESS_TOKEN] = accessToken;
      const accessExpiry = extractExpiry(accessToken);
      updates[STORAGE_KEYS.ACCESS_EXP] = accessExpiry || null;
    }

    if (refreshToken) {
      updates[STORAGE_KEYS.REFRESH_TOKEN] = refreshToken;
      const refreshExpiry = extractExpiry(refreshToken);
      updates[STORAGE_KEYS.REFRESH_EXP] = refreshExpiry || null;
    }

    if (Object.keys(updates).length === 0) {
      return getStoredTokens();
    }

    await root.TV.chromeStorage.set(updates);
    const storedTokens = await getStoredTokens();
    try {
      await root.TV.localStorageSync.syncChromeStorageToLocalStorage();
    } catch (error) {
      console.warn("[token-manager] syncChromeStorageToLocalStorage failed:", error);
    }
    return storedTokens;
  }

  async function clearAuthTokens() {
    await root.TV.chromeStorage.remove([
      STORAGE_KEYS.ACCESS_TOKEN,
      STORAGE_KEYS.REFRESH_TOKEN,
      STORAGE_KEYS.ACCESS_EXP,
      STORAGE_KEYS.REFRESH_EXP,
    ]);
    root.TV.localStorageSync.clearAllExtensionData();
    if (typeof chrome !== "undefined" && chrome.tabs) {
      chrome.tabs.query({}, (tabs) => {
        tabs.forEach((tab) => {
          if (tab.url && (tab.url.startsWith("http://") || tab.url.startsWith("https://"))) {
            try {
              chrome.tabs
                .sendMessage(tab.id, { type: "CLEANUP_EXTENSION_DATA", source: "logout" })
                .catch(() => {});
            } catch (e) {}
          }
        });
      });
    }
  }

  async function callRefreshEndpoint(refreshToken) {
    if (!refreshToken) throw new Error("NO_REFRESH_TOKEN");
    const apiBase = await getApiBase();
    API_BASES = [apiBase];
    let lastError;
    for (const base of API_BASES) {
      try {
        const response = await fetch(`${base}${REFRESH_ENDPOINT}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refreshToken }),
        });
        if (!response.ok) {
          const errorText = await response.text().catch(() => "");
          throw new Error(`Refresh failed (${response.status}): ${errorText || "Unknown error"}`);
        }
        return await response.json();
      } catch (error) {
        lastError = error;
        const isNetworkError =
          error?.name === "TypeError" || error?.message?.includes("Failed to fetch");
        if (!isNetworkError) break;
      }
    }
    throw lastError || new Error("Unable to refresh access token");
  }

  async function refreshAccessTokenUsingStored() {
    const tokens = await getStoredTokens();
    if (!tokens.refreshToken) throw new Error("NO_REFRESH_TOKEN");
    if (tokens.refreshTokenExpiresAt && isExpired(tokens.refreshTokenExpiresAt)) {
      throw new Error("REFRESH_TOKEN_EXPIRED");
    }
    const response = await callRefreshEndpoint(tokens.refreshToken);
    const updates = { accessToken: response.accessToken };
    if (response.refreshToken) updates.refreshToken = response.refreshToken;
    await storeAuthTokens(updates);
    return {
      accessToken: response.accessToken,
      refreshToken: response.refreshToken || tokens.refreshToken,
    };
  }

  async function ensureFreshAccessToken(forceRefresh) {
    const tokens = await getStoredTokens();
    if (!tokens.accessToken && !tokens.refreshToken) throw new Error("NO_TOKENS");
    if (
      !forceRefresh &&
      tokens.accessToken &&
      !isExpired(tokens.accessTokenExpiresAt)
    ) {
      return tokens.accessToken;
    }
    const refreshed = await refreshAccessTokenUsingStored();
    return refreshed.accessToken;
  }

  const ENT_BASE = "https://velocityenterprise.toteminteractive.in";
  const ENT_REFRESH_ENDPOINT = "/backend/auth/refresh";
  const ENT_ACCESS_BUFFER_MS = 60 * 1000; // refresh when <60s remaining

  let _entRefreshPromise = null;

  async function getEntStoredTokens() {
    const SK = root.TV.STORAGE_KEYS;
    const data = await root.TV.chromeStorage.get([
      SK.ENT_ACCESS_TOKEN, SK.ENT_REFRESH_TOKEN, SK.ENT_ACCESS_EXP,
    ]);
    return {
      accessToken:  data[SK.ENT_ACCESS_TOKEN]  || null,
      refreshToken: data[SK.ENT_REFRESH_TOKEN] || null,
      expiresAt:    data[SK.ENT_ACCESS_EXP]    || null,
    };
  }

  async function doEnterpriseRefresh(refreshToken) {
    const res = await fetch(`${ENT_BASE}${ENT_REFRESH_ENDPOINT}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refreshToken }),
    });
    if (!res.ok) {
      const msg = await res.text().catch(() => "");
      const err = new Error(`ENT_REFRESH_FAILED: ${res.status} ${msg}`);
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  async function ensureFreshEnterpriseToken() {
    // Dedup: assign synchronously before any await so concurrent callers
    // share this promise rather than each starting a new refresh cycle.
    if (_entRefreshPromise) return _entRefreshPromise;

    _entRefreshPromise = (async () => {
      const tokens = await getEntStoredTokens();
      if (!tokens.refreshToken && !tokens.accessToken) {
        throw new Error("ENT_NO_TOKENS");
      }

      // Still fresh with >60s buffer → return immediately.
      if (tokens.accessToken && tokens.expiresAt) {
        const remaining = Number(tokens.expiresAt) - Date.now();
        if (remaining > ENT_ACCESS_BUFFER_MS) return tokens.accessToken;
      }

      if (!tokens.refreshToken) throw new Error("ENT_NO_REFRESH_TOKEN");

      const json = await doEnterpriseRefresh(tokens.refreshToken);
      const SK = root.TV.STORAGE_KEYS;
      const expiresIn = json.expiresIn || 900;
      const patch = {
        [SK.ENT_ACCESS_TOKEN]: json.accessToken,
        [SK.ENT_ACCESS_EXP]: Date.now() + expiresIn * 1000,
      };
      // Handle refresh token rotation if the server issues a new one.
      if (json.refreshToken) patch[SK.ENT_REFRESH_TOKEN] = json.refreshToken;
      await root.TV.chromeStorage.set(patch);
      return json.accessToken;
    })()
      .catch(async (err) => {
        // 401 = refresh token expired → clear full enterprise session.
        if (err.status === 401) {
          await clearEnterpriseTokens().catch(() => {});
        }
        throw err;
      })
      .finally(() => { _entRefreshPromise = null; });

    return _entRefreshPromise;
  }

  async function clearEnterpriseTokens() {
    const SK = root.TV.STORAGE_KEYS;
    await root.TV.chromeStorage.remove([
      SK.ENT_ACCESS_TOKEN, SK.ENT_REFRESH_TOKEN, SK.ENT_ACCESS_EXP,
      SK.ENT_USER_ID, SK.ENT_ENTERPRISE_ID, SK.ENT_USER_NAME,
      SK.ENT_USER_EMAIL, SK.ENT_ROLE_TYPES, SK.ENT_PENDING_APPROVAL,
    ]);
  }

  root.TV.tokenManager = {
    getApiBase,
    getStoredTokens,
    storeAuthTokens,
    clearAuthTokens,
    refreshAccessTokenUsingStored,
    ensureFreshAccessToken,
    FREE_TRIAL_TOKEN,
    ensureFreshEnterpriseToken,
    clearEnterpriseTokens,
    getEntStoredTokens,
    ENT_BASE,
    // Placeholder — background.js sets this after importScripts loads this module.
    getActiveMode: function () { return "consumer"; },
  };
})();
