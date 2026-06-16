/**
 * Storage adapter: all chrome.storage.local reads/writes for auth go through here.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  root.TV.chromeStorage = {
    get(keys) {
      return new Promise((resolve) => {
        chrome.storage.local.get(keys, (result) => {
          resolve(result || {});
        });
      });
    },

    set(values) {
      return new Promise((resolve, reject) => {
        chrome.storage.local.set(values, () => {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
            return;
          }
          resolve();
        });
      });
    },

    remove(keys) {
      return new Promise((resolve, reject) => {
        chrome.storage.local.remove(keys, () => {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
            return;
          }
          resolve();
        });
      });
    },
  };
})();
