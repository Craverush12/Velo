(function () {
  const btn = document.getElementById("allowBtn");
  const status = document.getElementById("status");
  const closingNote = document.getElementById("closingNote");
  if (!btn || !status) return;

  function getReturnTarget() {
    const params = new URLSearchParams(window.location.search || "");
    const returnTabId = Number.parseInt(params.get("returnTabId") || "", 10);
    const returnWindowId = Number.parseInt(params.get("returnWindowId") || "", 10);
    return {
      tabId: Number.isInteger(returnTabId) ? returnTabId : null,
      windowId: Number.isInteger(returnWindowId) ? returnWindowId : null,
    };
  }

  async function returnToSourceTab() {
    const target = getReturnTarget();
    if (!target.tabId || !chrome.tabs) return;

    try {
      if (target.windowId && chrome.windows) {
        await chrome.windows.update(target.windowId, { focused: true });
      }
      await chrome.tabs.update(target.tabId, { active: true });
    } catch (err) {
      console.warn("[mic-permission] Could not restore source tab:", err);
    }
  }

  async function closePermissionTab() {
    try {
      if (chrome.tabs && chrome.tabs.getCurrent && chrome.tabs.remove) {
        const currentTab = await chrome.tabs.getCurrent();
        if (currentTab && Number.isInteger(currentTab.id)) {
          await chrome.tabs.remove(currentTab.id);
          return;
        }
      }
    } catch (_) {}

    try {
      window.close();
    } catch (_) {}
  }

  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Requesting…";
    status.className = "status info";
    status.textContent = "Waiting for browser permission prompt…";

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());

      try {
        if (chrome.storage && chrome.storage.local) {
          await chrome.storage.local.set({ micPermissionGranted: true });
        }
      } catch (_) {}

      status.className = "status success";
      status.textContent =
        "Microphone access granted. You can close this tab and use voice in the Velocity sidebar.";
      btn.textContent = "Permission granted";
      if (closingNote) {
        closingNote.textContent = "Returning to your original tab...";
      }

      setTimeout(async () => {
        await returnToSourceTab();
        await closePermissionTab();
      }, 800);
    } catch (err) {
      btn.disabled = false;
      btn.innerHTML = `
      <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
        <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5-3c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"/>
      </svg>
      Try again
    `;

      if (err && (err.name === "NotAllowedError" || err.name === "PermissionDeniedError")) {
        status.className = "status error";
        status.textContent =
          "Permission denied. Choose Allow when Chrome asks, or enable the microphone for this extension in site settings.";
      } else {
        status.className = "status error";
        status.textContent = err && err.message ? String(err.message) : "Could not access the microphone.";
      }
    }
  });
})();
