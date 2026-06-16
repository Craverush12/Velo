/**
 * Install welcome popup — navigate steps, close tab or open hosted login.
 * @global TV (optional, from thinkvelocity-urls when loaded)
 */
(function () {
  const closeBtn = document.getElementById("tutorialClose");
  const nextBtn = document.getElementById("tutorialNextBtn");
  const tryBtn = document.getElementById("tutorialTryBtn");
  const videoEl = document.getElementById("tutorialVideo");
  const videoSource = document.getElementById("videoSource");
  const videoSection = document.querySelector(".tutorial-video");
  const steps = document.querySelectorAll(".tutorial-step");
  const dots = document.querySelectorAll(".tutorial-step-dot");

  const VIDEO_SOURCES = [
    "../../assets/Extension videos/tutorialvideo_step1.mp4",
    "../../assets/Extension videos/tutorialvideo_step2.mp4",
    "../../assets/Extension videos/tutorialvideo_step3.mp4"
  ];

  let currentStep = 1;
  const totalSteps = 3;

  const TRY_VELOCITY_URL = "https://chatgpt.com/";

  function updateStep(step) {
    currentStep = step;

    steps.forEach((el, i) => {
      el.classList.toggle("is-active", i + 1 === step);
    });

    dots.forEach((dot, i) => {
      dot.classList.toggle("is-active", i + 1 === step);
    });

    if (videoSource && videoEl) {
      videoSource.src = VIDEO_SOURCES[step - 1] || VIDEO_SOURCES[0];
      videoEl.load();
      videoEl.play().catch(() => {});
    }

    if (step === totalSteps) {
      if (nextBtn) nextBtn.style.display = "none";
      if (tryBtn) tryBtn.style.display = "inline-flex";
    } else {
      if (nextBtn) nextBtn.style.display = "inline-flex";
      if (tryBtn) tryBtn.style.display = "none";
    }
  }

  function goNext() {
    if (currentStep < totalSteps) {
      updateStep(currentStep + 1);
    }
  }

  function closeWelcomeTab() {
    if (!chrome || !chrome.tabs || typeof chrome.tabs.getCurrent !== "function") {
      window.close();
      return;
    }
    chrome.tabs.getCurrent((tab) => {
      if (tab && tab.id != null) {
        chrome.tabs.remove(tab.id);
        return;
      }
      window.close();
    });
  }

  function openChatPlatform() {
    const url = TRY_VELOCITY_URL;
    if (!chrome || !chrome.tabs || typeof chrome.tabs.create !== "function") {
      window.location.href = url;
      return;
    }
    if (tryBtn) tryBtn.disabled = true;
    try {
      if (chrome.storage && chrome.storage.local) {
        chrome.storage.local.set({ velocity_show_post_install_popup: true });
      }
    } catch (_) {}
    chrome.tabs.create({ url, active: true }, () => {
      closeWelcomeTab();
    });
  }

  function bindVideoFallback() {
    if (!videoEl || !videoSection) return;
    const markMissing = () => {
      videoSection.classList.add("is-video-missing");
    };
    videoEl.addEventListener("error", markMissing);
    if (videoEl.readyState === 0 && videoEl.networkState === HTMLMediaElement.NETWORK_NO_SOURCE) {
      markMissing();
    }
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", closeWelcomeTab);
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", goNext);
  }

  if (tryBtn) {
    tryBtn.addEventListener("click", openChatPlatform);
  }

  dots.forEach((dot, i) => {
    dot.addEventListener("click", () => {
      updateStep(i + 1);
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeWelcomeTab();
    }
    if (event.key === "ArrowRight" || event.key === "Enter") {
      if (currentStep < totalSteps) {
        goNext();
      } else {
        openChatPlatform();
      }
    }
    if (event.key === "ArrowLeft" && currentStep > 1) {
      updateStep(currentStep - 1);
    }
  });

  updateStep(1);
  bindVideoFallback();
})();
