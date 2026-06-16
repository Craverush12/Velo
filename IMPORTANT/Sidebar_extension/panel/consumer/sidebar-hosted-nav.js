/**
 * Preview limits + tracked ThinkVelocity URLs for sidebar list surfaces.
 * @global TV
 */
(function () {
  const root = typeof globalThis !== "undefined" ? globalThis : window;
  root.TV = root.TV || {};

  const PREVIEW_LIMIT = 20;

  /** Vel-Next `/chat` — library, Prompt Book, and Memory share one page via `?tab=`. */
  const LINKS = {
    library: { path: "/chat?tab=library", utm: "sidebar_prompt_library" },
    collections: { path: "/chat?tab=prompt-book", utm: "sidebar_collections" },
    memory: { path: "/chat?tab=memory", utm: "sidebar_memories" },
  };

  async function openHosted(key, authState) {
    const cfg = LINKS[key];
    if (!cfg) return;
    if (!authState || typeof authState.openHostedPage !== "function") {
      console.warn("[sidebar-hosted-nav] authState.openHostedPage missing");
      return;
    }
    try {
      await authState.openHostedPage(cfg.path, cfg.utm);
    } catch (e) {
      console.warn("[sidebar-hosted-nav] openHosted failed:", e);
    }
  }

  async function openCollection(collectionId, authState) {
    const id = String(collectionId || "").trim();
    if (!id) return;
    if (!authState || typeof authState.openHostedPage !== "function") {
      console.warn("[sidebar-hosted-nav] authState.openHostedPage missing");
      return;
    }
    const path = `/chat?tab=prompt-book&collection=${encodeURIComponent(id)}`;
    try {
      await authState.openHostedPage(path, "sidebar_collection_open");
    } catch (e) {
      console.warn("[sidebar-hosted-nav] openCollection failed:", e);
    }
  }

  function setViewMoreVisible(btnId, show) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    btn.hidden = !show;
  }

  function wireViewMoreButton(btnId, key, authState) {
    const btn = document.getElementById(btnId);
    if (!btn || btn.dataset.bound) return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => {
      void openHosted(key, authState);
    });
  }

  root.TV.sidebarHostedNav = {
    PREVIEW_LIMIT,
    LINKS,
    openHosted,
    openCollection,
    setViewMoreVisible,
    wireViewMoreButton,
  };
})();
