(function () {
  try {
    const onLocalDev = location.hostname === "localhost" && location.port === "3002";
    const onProdDomain = location.hostname.includes("thinkvelocity.in");
    if (!onLocalDev && !onProdDomain) return;

    function forwardAuthIfPresent() {
      const accessToken = localStorage.getItem("accessToken");
      const token = localStorage.getItem("token");
      const userName = localStorage.getItem("userName");
      const userId = localStorage.getItem("userId");
      const userEmail = localStorage.getItem("userEmail");
      const refreshToken = localStorage.getItem("refreshToken");
      const velocitySidebarFlow = localStorage.getItem("velocitySidebarFlow");

      const authToken = accessToken || token;

      if (authToken && userName && userId && userEmail) {
        const payload = {
          action: "storeUserData",
          token: authToken,
          refreshToken,
          userName,
          userId,
          userEmail,
        };
        if (velocitySidebarFlow != null && String(velocitySidebarFlow).trim() !== "") {
          payload.sidebarFlow = velocitySidebarFlow;
        }
        chrome.runtime.sendMessage(payload, () => {});
      } else {
        chrome.runtime.sendMessage({ action: "clearUserData" }, () => {});
      }
    }

    function clearLocalStorage() {
      try {
        localStorage.removeItem("accessToken");
        localStorage.removeItem("token");
        localStorage.removeItem("userId");
        localStorage.removeItem("userName");
        localStorage.removeItem("userEmail");
        localStorage.removeItem("refreshToken");
      } catch (err) {}
    }

    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
      if (message.action === "clearLocalStorage") {
        clearLocalStorage();
        sendResponse({ success: true });
      }
    });

    forwardAuthIfPresent();
    document.addEventListener("visibilitychange", forwardAuthIfPresent);
    window.addEventListener("storage", (e) => {
      if (
        ["accessToken", "token", "userId", "userName", "userEmail", "refreshToken"].includes(e.key)
      ) {
        forwardAuthIfPresent();
      }
    });
  } catch (_) {}
})();
