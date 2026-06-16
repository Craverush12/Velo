/**
 * Lite port of Extension-new/utils/localStorageSync.js for service worker + panel.
 * Syncs non-sensitive UI state into ThinkVelocity page localStorage when
 * localStorage is unavailable in the current extension context.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};
  const LS_KEYS = {
    USER_ID: "userId",
    REMAINING_USAGE: "remainingUsage",
    TRIAL_LEFT: "trialLeft",
  };
  const LEGACY_AUTH_KEYS = [
    "accessToken",
    "refreshToken",
    "accessTokenExpiresAt",
    "refreshTokenExpiresAt",
    "token",
  ];

  function unwrapStringifiedValue(value) {
    if (value === null || value === undefined) return value;
    if (typeof value === "string") {
      if (value.startsWith('"') && value.endsWith('"')) {
        try {
          const parsed = JSON.parse(value);
          if (typeof parsed === "string") return unwrapStringifiedValue(parsed);
          return parsed;
        } catch (e) {
          return value;
        }
      }
      return value;
    }
    return value;
  }

  function getStorageValue(val) {
    if (val === null || val === undefined) return null;
    if (typeof val === "string") return val;
    if (typeof val === "number" || typeof val === "boolean") return String(val);
    return JSON.stringify(val);
  }

  function isAllowedPageSyncUrl(url) {
    if (!url || typeof url !== "string") return false;
    try {
      const u = new URL(url);
      if (u.protocol !== "https:" && u.protocol !== "http:") return false;
      if (u.hostname === "thinkvelocity.in" || u.hostname.endsWith(".thinkvelocity.in")) {
        return true;
      }
      return u.hostname === "localhost" && u.port === "3002";
    } catch (e) {
      return false;
    }
  }

  function injectLocalStorageSet(key, value) {
    const storageValue = getStorageValue(value);
    if (typeof chrome === "undefined" || !chrome.tabs || !chrome.scripting) return;
    chrome.tabs.query({}, (tabs) => {
      tabs.forEach((tab) => {
        if (!tab.id || !isAllowedPageSyncUrl(tab.url)) return;
        try {
          chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: (k, v) => {
              try {
                if (v === null || v === undefined) localStorage.removeItem(k);
                else localStorage.setItem(k, v);
              } catch (e) {}
            },
            args: [key, storageValue],
          }).catch(() => {});
        } catch (e) {}
      });
    });
  }

  function injectLocalStorageRemove(key) {
    if (typeof chrome === "undefined" || !chrome.tabs || !chrome.scripting) return;
    chrome.tabs.query({}, (tabs) => {
      tabs.forEach((tab) => {
        if (!tab.id || !isAllowedPageSyncUrl(tab.url)) return;
        try {
          chrome.scripting.executeScript({
            target: { tabId: tab.id },
            func: (k) => {
              try {
                localStorage.removeItem(k);
              } catch (e) {}
            },
            args: [key],
          }).catch(() => {});
        } catch (e) {}
      });
    });
  }

  function setLocalStorageItem(key, value) {
    try {
      value = unwrapStringifiedValue(value);
      const storageValue = getStorageValue(value);
      if (typeof localStorage !== "undefined") {
        if (storageValue === null) localStorage.removeItem(key);
        else localStorage.setItem(key, storageValue);
      } else {
        injectLocalStorageSet(key, value);
      }
    } catch (error) {
      console.warn("[localStorageSync-lite] set failed:", key, error);
    }
  }

  function removeLocalStorageItem(key) {
    try {
      if (typeof localStorage !== "undefined") {
        localStorage.removeItem(key);
      } else {
        injectLocalStorageRemove(key);
      }
    } catch (error) {
      console.warn("[localStorageSync-lite] remove failed:", key, error);
    }
  }

  function syncUserIdToLocalStorage(userId) {
    if (userId) setLocalStorageItem(LS_KEYS.USER_ID, unwrapStringifiedValue(userId));
    else removeLocalStorageItem(LS_KEYS.USER_ID);
  }

  function syncAccessTokenToLocalStorage(accessToken, expiresAt) {
    LEGACY_AUTH_KEYS.forEach((key) => removeLocalStorageItem(key));
  }

  function syncRefreshTokenToLocalStorage(refreshToken, expiresAt) {
    LEGACY_AUTH_KEYS.forEach((key) => removeLocalStorageItem(key));
  }

  function syncAllChromeStorageToLocalStorage(chromeStorageData) {
    if (!chromeStorageData || typeof chromeStorageData !== "object") return;
    try {
      if (chromeStorageData.userId !== undefined) {
        syncUserIdToLocalStorage(chromeStorageData.userId);
      }
      LEGACY_AUTH_KEYS.forEach((key) => removeLocalStorageItem(key));
      if (chromeStorageData.remainingUsage !== undefined) {
        if (chromeStorageData.remainingUsage !== null && chromeStorageData.remainingUsage !== undefined) {
          setLocalStorageItem(LS_KEYS.REMAINING_USAGE, chromeStorageData.remainingUsage);
        } else {
          removeLocalStorageItem(LS_KEYS.REMAINING_USAGE);
        }
      }
      if (chromeStorageData.trialLeft !== undefined) {
        if (chromeStorageData.trialLeft !== null && chromeStorageData.trialLeft !== undefined) {
          setLocalStorageItem(LS_KEYS.TRIAL_LEFT, chromeStorageData.trialLeft);
        } else {
          removeLocalStorageItem(LS_KEYS.TRIAL_LEFT);
        }
      }
    } catch (e) {}
  }

  async function syncChromeStorageToLocalStorage() {
    try {
      const chromeData = await root.TV.chromeStorage.get([
        "userId",
        "remainingUsage",
        "trialLeft",
      ]);
      syncAllChromeStorageToLocalStorage(chromeData);
      return chromeData;
    } catch (error) {
      return null;
    }
  }

  function clearLocalStorageSyncKeys() {
    Object.values(LS_KEYS).forEach((key) => removeLocalStorageItem(key));
    LEGACY_AUTH_KEYS.forEach((key) => removeLocalStorageItem(key));
  }

  function clearAllExtensionData() {
    clearLocalStorageSyncKeys();
    const platformKeys = [
      "userName",
      "userEmail",
      "chatgpt_user_id",
      "VelocityChatGPTExtractor_session",
      "velocity_extension_data",
      "velocity_user_data",
    ];
    platformKeys.forEach((key) => removeLocalStorageItem(key));
    if (typeof localStorage !== "undefined") {
      try {
        Object.keys(localStorage).forEach((key) => {
          if (
            key.includes("velocity") ||
            key.includes("Velocity") ||
            key.includes("extractor")
          ) {
            localStorage.removeItem(key);
          }
        });
      } catch (e) {}
    }
  }

  root.TV.localStorageSync = {
    syncAccessTokenToLocalStorage,
    syncRefreshTokenToLocalStorage,
    syncChromeStorageToLocalStorage,
    clearAllExtensionData,
    removeLocalStorageItem,
  };
})();
