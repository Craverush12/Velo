# Sidebar_extension — change log and logic reference

This document records what exists in **Sidebar_extension**, why each piece exists, and how login, tokens, and state connect (aligned with `.cursor/skills/extension-architecture-js-only`: vanilla JS, `globalThis.TV` modules, thin background routing, storage adapter pattern).

---

## Consumer vs Enterprise (side panel flows)

Chrome loads **`panel/bootstrap.html`** first (`manifest.json` → `side_panel.default_path`). That page reads **`TV.STORAGE_KEYS.SIDEBAR_FLOW`** (`velocity_sidebar_flow` in `chrome.storage.local`) and redirects to:

| Folder | When |
|--------|------|
| **`panel/consumer/`** | Flow is `consumer` (default) — B2C UI and (later) consumer APIs. |
| **`panel/enterprise/`** | Flow is `enterprise` — B2B shell; expand with enterprise-only UI and API clients here. |

**Naming:** `TV.SidebarFlow.CONSUMER` / `TV.SidebarFlow.ENTERPRISE` and `TV.normalizeSidebarFlow()` live in **`core/sidebar-flow.js`**. Aliases `org` / `b2b` normalize to enterprise.

**Setting flow from the website (login):**

- **Login → consumer reference UI:** Opening login from **`panel/consumer/`** calls `TV_AUTH_OPEN_LOGIN` with **`intendedSidebarFlow: consumer`**, so after sign-in the bootstrap router lands on the **consumer** shell (the shared B2C layout).
- **Login → enterprise:** From **`panel/enterprise/`**, `openLoginTab` passes **`intendedSidebarFlow: enterprise`** so the same login tab still records the B2B line.
- If `localStorage.velocitySidebarFlow` is set on the site, **`content/login-bridge.js`** forwards it on `storeUserData` as **`sidebarFlow`** only when non-empty.
- Background **updates** `velocity_sidebar_flow` from `storeUserData` **only when** `sidebarFlow` / `appFlow` is present, so routine token syncs without a flow field do **not** overwrite an existing choice set at open-login time.
- **Logout** (`clearUserData` / `TV_AUTH_LOGOUT`) **removes** `velocity_sidebar_flow` so the next session is re-resolved from the next login / bridge payload.

Each flow page (`consumer/sidebar.js`, `enterprise/sidebar.js`) reloads **`panel/bootstrap.html`** if the stored flow no longer matches the page (e.g. after login switches line).

---

## Post-login UI (side panel)

**Consumer** (`panel/consumer/sidebar.html`) is the **only** place for the **consumer reference UI** you shared (B2C chat layout: scrollable main + bottom-docked composer + right rail). **Enterprise** does not reuse that layout; it uses `panel/enterprise/` with its own shell until you design it.

**Consumer** layout details:

- **Main stage (left):** scrollable hero + prompt cards + “Load more…” + action row (thumbs / edit / refine — placeholders). **Composer** is fixed in a **bottom dock** (`footer.composer-dock`): textarea on top, then a toolbar (paperclip, **Model** dropdown, mic/send). There is **no signed-in banner**; account is reflected by **profile initials** on the rail. When **signed out** (or on error), a slim **session hint** appears above the composer with Open login / Refresh only.
- **Right icon rail:** top **toggle** (hides/shows the main stage), **New chat** (clears the prompt + active state), **Prompt library**, **Collection**, **Memories** (each opens a **tracked** ThinkVelocity URL in a new tab), and **Profile** at the bottom (initials from `userName` / email; opens profile like Extension-new).

**Hosted paths** (adjust if the web app routes differ):

| Rail button | Path | `utm_content` |
|-------------|------|----------------|
| Profile | `/profile?tab=profile` | `extension_open_profile` (same intent as Extension-new `openProfilePage`) |
| Prompt library | `/prompt-library` | `sidebar_prompt_library` |
| Collection | `/collections` | `sidebar_collections` |
| Memories | `/chat` | `sidebar_memories` (placeholder: Extension-new keeps memories in-panel; swap when a stable web URL exists) |

URLs are built with **`utils/thinkvelocity-urls.js`** (`TV.thinkvelocityUrls.buildThinkVelocityUrl`) — same query pattern as `Extension-new/background.js` `buildTrackedThinkVelocityUrl`. The background action **`TV_OPEN_HOSTED_PAGE`** validates `payload.path` (must start with `/`, not `//`) then `chrome.tabs.create`.

---

## What this extension does

1. **Toolbar icon** opens the Chrome **side panel** (`chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })`).
2. **Login sync**: On `thinkvelocity.in` (and `localhost:3002`), a **content script** mirrors the same behavior as `Extension-new/Extension/login-bridge.js`, forwarding site `localStorage` credentials to the background via `storeUserData` / `clearUserData`.
3. **Tokens**: Background uses **`utils/token-manager.js`** (logic aligned with `Extension-new/utils/tokenManager.js`) — `storeAuthTokens`, `clearAuthTokens`, refresh endpoint, `getApiBase`.
4. **Chrome → page localStorage**: **`utils/local-storage-sync-lite.js`** is a reduced port of `Extension-new/utils/localStorageSync.js` — when running in a service worker, token/user fields are pushed into tabs via `chrome.scripting.executeScript` where `localStorage` is unavailable.
5. **Side panel UI**: **`panel/bootstrap.html`** routes to **`panel/consumer/`** or **`panel/enterprise/`**. **`state/sidebar-auth-state.js`** + each flow’s `sidebar.js` load auth **snapshots** (including **`sidebarFlow`**) through runtime messages (no raw access token in the snapshot).

`Extension-new/` source files were **not** modified; behavior is **mirrored** under `Sidebar_extension/` for a standalone unpacked extension.

---

## File map

| Path | Role |
|------|------|
| `manifest.json` | MV3: `sidePanel`, `storage`, `tabs`, `scripting`, `host_permissions` for ThinkVelocity, CSP `connect-src` for token refresh, `content_scripts` for login bridge. |
| `background.js` | `importScripts` chain + side panel config + **single** `onMessage` router (auth + legacy bridge actions). |
| `core/storage-keys.js` | Stable `chrome.storage.local` key names (`TV.STORAGE_KEYS`), including **`SIDEBAR_FLOW`**. |
| `core/sidebar-flow.js` | **`TV.SidebarFlow`**, **`TV.normalizeSidebarFlow`**. |
| `panel/bootstrap.html` + `panel/bootstrap.js` | Side panel **entry**: read flow → `location.replace` consumer or enterprise shell. |
| `panel/consumer/sidebar.*` | B2C layout (scrollable main + bottom-docked composer, icon rail, hosted links; optional session hint when signed out). |
| `panel/enterprise/sidebar.*` | B2B placeholder shell + dev control to switch back to consumer. |
| `utils/chrome-storage.js` | **Storage adapter**: `TV.chromeStorage.get/set/remove` (Promises). |
| `utils/local-storage-sync-lite.js` | **`TV.localStorageSync`**: sync tokens / userId into `localStorage` (direct in panel, injected from SW). |
| `utils/token-manager.js` | **`TV.tokenManager`**: JWT expiry, `storeAuthTokens`, `clearAuthTokens`, `refreshAccessTokenUsingStored`, `ensureFreshAccessToken`, `getApiBase`. |
| `utils/thinkvelocity-urls.js` | **`TV.thinkvelocityUrls`**: tracked ThinkVelocity URLs + `isSafeHostedPath` for `TV_OPEN_HOSTED_PAGE`. |
| `features/consumer-enhance-flow.js` | **`TV.consumerEnhanceFlow.runEnhance`**: quality → save user prompt → `enhance/stream` SSE → save enhanced (aligned with Extension-new). |
| `content/login-bridge.js` | Same contract as Extension-new: `storeUserData` / `clearUserData` from thinkvelocity SPA + `storage` events. |
| `state/sidebar-auth-state.js` | **`TV.sidebarAuthState`**: subscribe/refresh/logout/open login/**openHostedPage**; snapshot includes **`sidebarFlow`**. |

---

## Module load order (service worker)

At the top of `background.js`:

```text
importScripts(
  "core/storage-keys.js",
  "core/sidebar-flow.js",
  "utils/chrome-storage.js",
  "utils/local-storage-sync-lite.js",
  "utils/token-manager.js",
  "utils/thinkvelocity-urls.js"
);
```

- **`chrome-storage.js`** must load before **`local-storage-sync-lite.js`** (sync reads via `TV.chromeStorage.get`).
- **`token-manager.js`** must load after **`local-storage-sync-lite.js`** (calls `TV.localStorageSync.*`).

All shared modules attach to **`globalThis.TV`** (same pattern as the skill’s `window.TV` recommendation; SW uses `globalThis`).

---

## Messaging contract (new actions)

Side panel and internal callers use:

| Field | Type | Notes |
|-------|------|--------|
| `action` | string | e.g. `TV_AUTH_GET_SNAPSHOT` |
| `payload` | object | Often `{}` |
| `requestId` | string | Correlates async `sendResponse` |

Response shape:

| Field | Notes |
|-------|--------|
| `success` | boolean |
| `requestId` | echoed or `null` |
| `data` | Present when `success` |
| `error` | `{ code, message, retryable }` when `!success` |

**Legacy bridge** messages (`storeUserData`, `clearUserData`) do **not** require `requestId`; the background still replies with the same envelope when `requestId` is omitted.

| Action | Handler behavior |
|--------|------------------|
| `storeUserData` | `TV.tokenManager.storeAuthTokens`, then `chrome.storage` user profile (and **`SIDEBAR_FLOW`** only if `sidebarFlow` / `appFlow` is non-empty), then `syncChromeStorageToLocalStorage`. |
| `clearUserData` | `TV.tokenManager.clearAuthTokens` + remove user + token + **`SIDEBAR_FLOW`** keys from `chrome.storage.local`. |
| `TV_AUTH_GET_SNAPSHOT` | Returns `{ isLoggedIn, userId, userEmail, userName, sidebarFlow }` (no access token string). |
| `TV_AUTH_LOGOUT` | Same as clear path (including **`SIDEBAR_FLOW`**) + returns fresh snapshot. |
| `TV_AUTH_OPEN_LOGIN` | Persists **`payload.intendedSidebarFlow`** (`consumer` \| `enterprise`) to `velocity_sidebar_flow`, then opens `/login` (tracked URL). **Consumer** panel uses default **consumer** (B2C “image page” flow); **enterprise** panel passes **enterprise**. |
| `TV_OPEN_HOSTED_PAGE` | `payload.path`, optional `payload.utmContent`, `payload.platform` → new tab on thinkvelocity.in. |
| `TV_CONSUMER_ENHANCE` | `payload.prompt`, optional `payload.mode` (`standard`/`best`/…) → **`TV.consumerEnhanceFlow.runEnhance`**; response `data.enhanced_prompt`. Consumer panel only. |

---

## Sender security (`isAuthMessageSenderAllowed`)

Runtime messages are accepted only if:

- `sender.id` is missing **or** equals this extension’s id, and  
- **Either** `sender.origin` is this extension’s `chrome-extension://` origin **or** the sender frame URL host is `thinkvelocity.in` / `*.thinkvelocity.in` / `localhost:3002`.

Unknown actions get `UNKNOWN_ACTION` error.

---

## Login flow (end-to-end)

1. User opens **ThinkVelocity** in a tab and signs in; the site writes tokens + user fields into **page** `localStorage` (same keys as production site).
2. **`content/login-bridge.js`** runs on those URLs, calls `forwardAuthIfPresent()` on load, **visibilitychange**, and **storage** for relevant keys.
3. If `accessToken` (or legacy `token`) **and** `userName`, `userId`, `userEmail` exist, it sends **`storeUserData`** to the background (same shape as `Extension-new`).
4. Background persists tokens via **`TV.tokenManager.storeAuthTokens`** (writes `chrome.storage.local`, updates expiry fields, triggers lite localStorage sync into tabs).
5. Side panel **Refresh state** runs **`TV_AUTH_GET_SNAPSHOT`**, which reads **chrome.storage** only and updates the UI.

Logout on the site clears `localStorage` → bridge sends **`clearUserData`** → background clears tokens and profile keys.

---

## Token refresh / API base

- **`TV.tokenManager.getApiBase()`** mirrors Extension-new: optional `apiBase` / `environment` overrides in storage, else infer from active tab hostname, else development base.
- **`/refresh-token`** is called with `fetch` from the **service worker**; `manifest.json` **CSP `connect-src`** includes ThinkVelocity hosts so refresh is allowed.

---

## Side panel behavior (unchanged core)

- **`configureSidePanelBehavior()`** sets `openPanelOnActionClick: true` on install, startup, and first load.
- Same pattern as **`Extension-new/background.js`** `configureSidePanelBehavior`.

---

## Chrome developer workflow

1. `chrome://extensions` → Developer mode → **Load unpacked** → select **`Sidebar_extension`** (folder containing `manifest.json`).
2. Pin the extension → **click toolbar icon** → side panel opens.
3. Open **https://thinkvelocity.in**, sign in, return to side panel → **Refresh state** should show signed-in summary.

---

## Quick checklist when changing auth

- [ ] Any new `chrome.storage` key is added to **`core/storage-keys.js`** and used only via **`TV.chromeStorage`** in SW code.
- [ ] Consumer vs enterprise: new UI lives under **`panel/consumer/`** or **`panel/enterprise/`**; **`panel/bootstrap.html`** stays the single `side_panel.default_path` unless you intentionally fork manifests.
- [ ] Token or user writes from SW still go through **`TV.tokenManager`** / **`TV.localStorageSync`** (no ad-hoc `chrome.storage.local` in UI scripts).
- [ ] New runtime `action`s validate **`requestId`** / **`payload`** and return normalized **`error`** objects.
- [ ] **`host_permissions`** and **`content_security_policy.connect-src`** include every origin **`fetch`** uses.

---

## Google Fonts

External Google Fonts were **not** added to the side panel HTML, to avoid extension-page CSP friction. Fonts use the **`--vel-font-family`** stack in **`panel/consumer/sidebar.css`**.

---

*Last updated: includes consumer/enterprise flow routing, login bridge flow forwarding, and bootstrap side panel entry.*
