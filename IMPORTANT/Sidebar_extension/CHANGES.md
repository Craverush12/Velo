# Velocity Execution Plan & Checklist — Sidebar Extension

**Product:** ThinkVelocity Chrome side panel (`Sidebar_extension/`)  
**Stakeholder plan (phases & main tasks):** [`EXECUTION_PLAN.md`](./EXECUTION_PLAN.md)  
**Design plan (light theme):** [`DESIGN_EXECUTION.md`](./DESIGN_EXECUTION.md)  
**This file:** Engineering QA checklist (technical detail)  
**Reference implementation:** `Extension-new/` (parity target, not modified in place)  
**Architecture:** Vanilla JS, MV3, `globalThis.TV` modules — see `.cursor/skills/extension-architecture-js-only/SKILL.md`  
**Deep reference:** [`SUMMARY.md`](./SUMMARY.md) (auth, messaging, file map)

Use this sheet to track delivery, QA, and release. Check boxes as you verify in a loaded unpacked extension.

---

## Status legend

| Symbol | Meaning |
|--------|---------|
| `[x]` | Done — implemented and smoke-tested |
| `[~]` | Partial — core shipped; follow-ups remain |
| `[ ]` | Not started / backlog |

---

## North star

Ship a **standalone consumer side panel** that matches Extension-new capabilities where the user expects them:

1. Sign in via ThinkVelocity web → tokens sync to extension  
2. Enhance prompt → thought process → **Output** with structured body  
3. **Refine** via Suggestions Q&A → Versions history  
4. **Insert in Chat** (composer) + **Open In** (external AI tabs)  
5. Prompt Library, Collections, Memories with Pro/usage gates  
6. Free vs Pro visual tier without breaking cyan session chrome  
7. **On-page Velocity button** + **draggable enhancement popup** on AI chat sites (Phase 6 — see [`EXECUTION_PLAN.md`](./EXECUTION_PLAN.md))

---

## Phase 7 — Light mode design (not started)

> Full design checklist: **[`DESIGN_EXECUTION.md`](./DESIGN_EXECUTION.md)**

| Area | Summary | Status |
|------|---------|--------|
| Shared tokens | `theme-tokens.css`, default `data-theme="light"` | `[ ]` |
| Side panel | Shell, composer, Output, library on light surfaces | `[ ]` |
| Injection button | White pill, cyan ring, black label, light dropdown | `[ ]` |
| Enhancement popup | `#F3F4F6` shell, light tabs, light enhance box, Accept CTA | `[ ]` |

---

## Phase 6 — Draggable button & enhancement popup (not started)

> **Extension-new source of truth** + full task tables: **[`EXECUTION_PLAN.md`](./EXECUTION_PLAN.md)** (§2 button anatomy, §3 popup anatomy, §5 implementation tasks)

| # | Task | Status | Extension-new reference |
|---|------|--------|-------------------------|
| 6.1 | Manifest: content-script bundle + `platforms.js` + CSS + assets | `[ ]` | `Extension-new/manifest.json` |
| 6.2 | Injection button: Enhance prompt + dropdown (Pin/Snooze/Profile/modes) | `[ ]` | `Button/js/input-injection.js` |
| 6.3 | Popup: header drag, centered/`lastPopupPosition`, Enhance+Refine tabs | `[ ]` | `Button/js/velocityPopupBox.js` |
| 6.4 | Enhance tab: skeleton → streamed text → editable area | `[ ]` | `buildEnhanceContent`, `triggerEnhanceAPI` |
| 6.5 | Actions: Like/Dislike/Copy/**Accept** (insert into host input) | `[ ]` | `buildEnhanceButtons`, `flashInsertEffect` |
| 6.6 | Background: `useService` + `velocityEnhanceChunk` / `velocityEnhanceComplete` | `[ ]` | `Extension-new/background.js`, `api.js` |

**Phase 6 QA (summary)**

- [ ] `.velocity-injection-button-container` shows near input when typing (ChatGPT / Claude / Gemini)  
- [ ] Left click **Enhance prompt** → popup opens (button hidden); usage consumed via `useService` equivalent  
- [ ] **Drag header** moves popup; position remembered (`lastPopupPosition`)  
- [ ] Skeleton loader → enhanced text in popup  
- [ ] **Accept** inserts into host chat input (not side panel)  
- [ ] **Panel** opens Chrome side panel  

---

## Phase 0 — Foundation & auth

| # | Task | Status | Key files |
|---|------|--------|-----------|
| 0.1 | MV3 manifest: side panel, storage, tabs, scripting | `[x]` | `manifest.json` |
| 0.2 | Bootstrap router: consumer vs enterprise flow | `[x]` | `panel/bootstrap.*`, `core/sidebar-flow.js` |
| 0.3 | Login bridge from thinkvelocity.in | `[x]` | `content/login-bridge.js` |
| 0.4 | Token manager + chrome storage adapter | `[x]` | `utils/token-manager.js`, `utils/chrome-storage.js` |
| 0.5 | Auth snapshot + sidebar auth state | `[x]` | `state/sidebar-auth-state.js`, `background.js` |
| 0.6 | Hosted page opens (profile, library, collections) | `[x]` | `sidebar-hosted-nav.js`, `TV_OPEN_HOSTED_PAGE` |
| 0.7 | Default **login view** when signed out (not home flash) | `[x]` | `sidebar.js`, `sidebar.html` |
| 0.8 | Enterprise shell placeholder | `[~]` | `panel/enterprise/` |

**Phase 0 QA**

- [ ] Load unpacked → side panel opens  
- [ ] Signed out → login view; Open login opens tracked `/login`  
- [ ] Sign in on site → Refresh / auto snapshot → home/session UI  
- [ ] Logout clears flow + tokens  

---

## Phase 1 — Enhance session (core loop)

| # | Task | Status | Key files |
|---|------|--------|-----------|
| 1.1 | Enhance SSE flow (quality → save → stream → save enhanced) | `[x]` | `features/consumer-enhance-flow.js` |
| 1.2 | Thought process loader card + disabled action row | `[x]` | `thought-process.js`, `sidebar.html`, `sidebar.css` |
| 1.3 | Session shell: tabs Output / Suggestions / Context / Versions | `[x]` | `sidebar.js` |
| 1.4 | `app-shell--in-session` + slim session composer | `[x]` | `sidebar.js`, `composer-bar.js`, `sidebar.css` |
| 1.5 | Composer: mode/attach popups (CSS-only positioning) | `[x]` | `composer-bar.js`, `sidebar.css` |
| 1.6 | Mic / send swap + clear textarea after enhance | `[x]` | `composer-bar.js` |
| 1.7 | Output: ORIGINAL collapsible + inline preview | `[x]` | `output-view.js` |
| 1.8 | Output: structured ENHANCED body (FormattedMessage parity) | `[x]` | `structured-prompt-dom.js` |
| 1.9 | Versions tab: Enhanced → Refined N → Original | `[x]` | `versions-view.js` |
| 1.10 | Suggestions: history scroll + active Q panel + composer bar | `[x]` | `suggestions-view.js` |
| 1.11 | Clarify `/clarify` + Refine `/refine` + save refined API #3 | `[x]` | `features/consumer-clarify-refine.js` |
| 1.12 | Billing tick after enhance (`/status/{id}/use`) | `[x]` | `consumer-enhance-flow.js` |
| 1.13 | Context capture tab | `[~]` | `context-view.js` |
| 1.14 | Voice input (offscreen + mic permission) | `[~]` | `offscreen/`, `consumer-voice-transcribe.js` |

**Phase 1 QA**

- [ ] Submit prompt → thought steps → Output shows ENHANCED  
- [ ] ORIGINAL expands/collapses; preview truncates cleanly  
- [ ] Refine → Suggestions → answer Qs → refined text on Output + Versions  
- [ ] Versions “Use in Output” updates active display  
- [ ] Leaving Suggestions restores main composer  
- [ ] Mode dropdown + attach menu not clipped in side panel  

---

## Phase 2 — Output actions & platform inject

| # | Task | Status | Key files |
|---|------|--------|-----------|
| 2.1 | **Insert in Chat** → active tab chat input (ChatGPT, etc.); composer fallback | `[x]` | `sidebar.js`, `consumer-platform-inject.js` |
| 2.2 | **Refine** pill below card → Suggestions tab | `[x]` | `output-view.js` |
| 2.3 | **Open In** dropdown + platform list | `[x]` | `output-view.js`, `utils/platform-prompt-actions.js` |
| 2.4 | Background `TV_CONSUMER_OPEN_IN_PLATFORM` | `[x]` | `background.js`, `features/consumer-platform-inject.js` |
| 2.5 | `content/platform-injection.js` on AI host URLs | `[x]` | `manifest.json`, `content/platform-injection.js` |
| 2.6 | Host permissions for ChatGPT, Claude, Gemini, etc. | `[x]` | `manifest.json` |
| 2.7 | Active-tab inject handler `TV_CONSUMER_INSERT_ACTIVE_TAB` | `[x]` | `background.js` (optional UX — no Output button yet) |
| 2.8 | Open In: first-click opens default without menu (optional) | `[ ]` | `output-view.js` |
| 2.9 | Header **Save** (bookmark) on enhanced card | `[ ]` | `output-view.js` |

**Phase 2 QA**

- [ ] **Insert in Chat** inserts into active tab (e.g. ChatGPT); fallback to sidebar composer on unsupported tab  
- [ ] **Refine** switches to Suggestions with session loaded  
- [ ] **Open In** → ChatGPT (or pick platform) → new tab → prompt injected  
- [ ] Edit (pencil) copies enhanced text into composer  
- [ ] Copy icon flashes “Copied”  
- [ ] Pro user sees **PRO ENHANCED** label + gold card border in session  

---

## Phase 3 — Subscription, usage & theming

| # | Task | Status | Key files |
|---|------|--------|-----------|
| 3.1 | Fetch `/status/{userId}` for remaining usage | `[x]` | `background.js`, `utils/usage-access.js` |
| 3.2 | Gate enhance at 0 remaining | `[x]` | `composer-bar.js`, `consumer-enhance-flow.js` |
| 3.3 | Usage limit banner above composer (full width) | `[x]` | `usage-limit-banner.js`, `sidebar.css` |
| 3.4 | Decrement usage after successful enhance | `[x]` | `composer-bar.js` |
| 3.5 | Pro vs free theme: gold scoped (not global cyan override) | `[x]` | `subscription-theme.js`, `sidebar.css` |
| 3.6 | Pro paywall on library detail (taller card) | `[x]` | `prompt-library-view.js` |
| 3.7 | Library Pro-only prompt sanitization | `[x]` | `utils/subscription-access.js` |

**Phase 3 QA**

- [ ] Free user at 0 usage → banner + enhance blocked  
- [ ] Successful enhance → remaining count decreases  
- [ ] Pro trial / paid: gold profile ring, session composer border, PRO ENHANCED card  
- [ ] Tabs / library filters stay cyan in session  

---

## Phase 4 — Prompt Library, Collections, Memories

| # | Task | Status | Key files |
|---|------|--------|-----------|
| 4.1 | Prompt Library in-panel (list + detail modal) | `[x]` | `prompt-library-view.js`, `data/prompt-library.json` |
| 4.2 | Copy + **Open in chat** from library (no QUICK badges) | `[x]` | `prompt-library-view.js`, `copy-button-feedback.js` |
| 4.3 | Prompt Book (enhanced prompts from API) | `[x]` | `collection-memory-views.js`, `prompt-book-detail-view.js` |
| 4.4 | Collections list + create collection | `[x]` | `collection-memory-views.js`, `consumer-library-fetch.js` |
| 4.5 | Memories list + editor | `[x]` | `memory-editor-view.js` |
| 4.6 | Library navigation without auth-refresh → home bug | `[x]` | `prompt-library-view.js`, `sidebar.js` |
| 4.7 | “Prompt Library” header in shell | `[x]` | `sidebar.html` |
| 4.8 | Rail → hosted web for library/collections (vs in-panel toggle) | `[~]` | `sidebar-hosted-nav.js` — confirm product intent |
| 4.9 | Auto essence: extract chat JSON on AI sites → ContextEngine after 5 messages | `[x]` | `content/platform-conversation-extractor.js`, `essence-smart-trigger.js`, `essence-trigger.js`, `docs/ESSENCE_FLOW.md` |

**Phase 4 QA**

- [ ] Open library from rail → stays on library view (no login flash)  
- [ ] Copy prompt → feedback toast/class  
- [ ] Open in chat → composer filled  
- [ ] Pro-only prompt → paywall; upgrade CTA  
- [ ] Collections / memories API load + empty states  
- [ ] Chat 5+ messages on ChatGPT while signed in → service worker `[TV_ESSENCE] ✅` → Memory list updates  

---

## Phase 5 — Polish, parity & release

| # | Task | Status | Notes |
|---|------|--------|-------|
| 5.1 | Feedback thumbs → `TV_CONSUMER_FEEDBACK` | `[x]` | Output + session |
| 5.2 | Duplicate `id="authHint"` removed | `[x]` | `sidebar.html` |
| 5.3 | Analytics / PostHog in sidebar | `[ ]` | Extension-new has mixpanel/posthog |
| 5.4 | Extension context API (page context for enhance) | `[~]` | `extension-context-api.js` |
| 5.5 | Error toasts / user-visible inject failures | `[ ]` | Open In failures only `console.warn` today |
| 5.6 | CHANGES + SUMMARY kept in sync each milestone | `[~]` | This file |
| 5.7 | Version bump + Chrome Web Store listing | `[ ]` | `manifest.json` → `1.4.7` |
| 5.8 | E2E test matrix (manual or TestSprite) | `[ ]` | |

**Pre-release checklist**

- [ ] `manifest.json` permissions match all `fetch` / `scripting` targets  
- [ ] CSP `connect-src` + `img-src` include API + platform icon CDN  
- [ ] No secrets in repo; tokens only in `chrome.storage`  
- [ ] Reload extension after every manifest / background change  
- [ ] Smoke test on **staging** + **production** API base  
- [ ] Free, Pro trial, and paid Pro accounts  
- [ ] Windows + Chrome ≥ 116  

---

## Shipped change log (by area)

Quick reference for what landed in code (newest first).

### Injection modal — markdown rendering + paste-friendly Apply/Copy

- **Display fix:** the enhance API returns raw markdown (e.g. `**Industry Context**: …`, `1. …`, `- …`). The modal previously rendered this with `plainTextToEditorHtml` (escape + `<br>`), so users saw literal `**asterisks**`. Replaced with `TV.structuredPromptDom.appendFormatted(editor, improvedText)` — the same renderer the side panel's Output tab uses. Bold spans become `<strong class="fmt-strong">`, `**Section**:` becomes `<div class="fmt-section-head">`, `1. ` becomes a `fmt-num-row`, `- ` becomes a `fmt-bullet-row`.
- **Apply/Copy fix:** chat inputs (ChatGPT, Claude, Gemini, …) render plain text and would otherwise show literal `**` and `#` markers when the enhanced prompt was pasted. `onApplyClick` and `onCopyClick` now pipe `improvedText` through `TV.promptFormat.formatForExternalPaste(text)` before invoking the host-input write callback (`writeInputText` → `VelocityPlatformInject.injectText`) or `navigator.clipboard.writeText`. Result: platforms receive clean paragraphs / `Section:` heads / `- bullet` lists with no leftover markdown markers.
- **Edit mode:** swapped the in-place `contenteditable` edit (which would have let users edit the rendered DOM directly and lose structure on save) for a proper raw-markdown `<textarea data-editor-textarea>` overlay. Clicking edit replaces the structured view with the textarea pre-filled with `improvedText`; clicking edit again (or Ctrl+Enter / Apply) commits the textarea value back to `improvedText` and re-renders the structured view via `renderEditorView`.
- **CSS:** added dark-theme `.fmt-*` styles to `button/css/injection-modal.css` mirroring `panel/consumer/sidebar.css` `.out-enhanced-body .fmt-*` rules (section heads in `--vm-cyan`, num/bullet markers in cyan, strong in `--vm-text`, paragraphs with 12px bottom margin). Pro mode (`.is-pro`) re-tints section heads + markers in `--vm-pro-gold`. Added `.velocity-injection-modal-editor-textarea` (transparent textarea filling the editor area, vertical resize, no border, focuses inside the cyan outline of `.is-editing`).
- **Manifest:** added `panel/consumer/structured-prompt-dom.js` to the host-platforms content script JS block (loaded immediately after `utils/prompt-format.js`, on which it depends).
- **Files touched:** `button/js/injection-modal.js`, `button/css/injection-modal.css`, `manifest.json`. The shared renderer (`panel/consumer/structured-prompt-dom.js`) and formatter (`utils/prompt-format.js`) were already in the repo and remain the single source of truth.

### Injection modal — dark theme (sidebar parity)

- `.velocity-injection-modal-root` design tokens in `button/css/velocity-theme.css` re-skinned to the consumer sidebar palette (`--tv-bg #101010`, `--tv-surface-1 #181818`, `--tv-surface-2 #232323`, `--tv-text #fff`, `--tv-text-secondary #bac9cc`, brand cyan `#19d8e6`, `--vel-border rgba(255,255,255,0.1)`, Pro gold `#eec13c`). Replaces the previous light "Improve/Refine" card (`#ffffff` / `#1a1d21` text) so the popup matches the side panel instead of looking pasted on top.
- `--vm-shadow` reworked to layer the sidebar's cyan glow + ring + drop shadow on dark (`0 24px 56px rgba(0,0,0,0.6), 0 0 0 1px rgba(83,234,253,0.22), inset 0 0 22px rgba(83,234,253,0.08)`).
- `button/css/injection-modal.css` targeted dark-mode adjustments where literals would have leaked:
  - Active tab now uses `--vm-surface-2` + `var(--vm-border-strong)` instead of hard-coded `#d0d5db`.
  - Close-button hover red strengthened (`rgba(239,68,68,0.18)` + `#fca5a5`) so the destructive state is visible against `#101010`.
  - Primary CTAs (`Apply`, `feedback-send`, `btn-primary`) now use dark text `#061018` on the cyan fill, matching the sidebar's `var(--vel-cyan)` buttons; hover lifted to the brighter `#58f5ff` with stronger glow.
  - Pro-mode (`.is-pro`) shadows + active-tab border re-mapped from the old desaturated gold `rgba(201,162,39,…)` to the sidebar's brighter `rgba(238,193,60,…)`.
- No JS changes — `injection-modal.js` has no inline color styles, and `features/injection-pro-theme.js` only toggles the `is-pro` class.

### Injection bar — removed Collection, aligned hover toolbar

- `button/js/injection-button.js`: dropped the **Collection** button from the hover-expandable area. Removed `collectionBtn` creation, `appendChild`, click handler, the `COLLECTION_ICON_PATH` constant, and the `HOSTED_LINKS.collections` entry; `isLibraryHidden()` now only hides the library button. File-level docstring updated to reflect the new layout: `[ 🎙 Voice ] [ Prompt Library ]` flanking `[ ✨ Improve ] [ ⋮⋮ Drag ]`.
- No CSS changes required — `.velocity-injection-expandable` was already designed for two left-extending buttons (`display: flex; gap: 6px;`, `max-width: 84px` ≈ 2×36px + 6px gap + breathing room). The staggered entrance animations on `:nth-child(1)` / `:nth-child(2)` now correctly drive Voice → Library.
- Sidebar collection view in `panel/consumer/collection-memory-views.js` is unaffected — the injection bar's `HOSTED_LINKS` constant was the only call site.

### Uninstall feedback URL

- `background.js`: registers `chrome.runtime.setUninstallURL("https://thinkvelocity.in/reviews/?utm_source=chrome_extension&utm_medium=uninstall")` so removing the extension from `chrome://extensions` opens the Velocity reviews/feedback page.
- New `configureUninstallUrl()` helper is invoked at top-level on every service-worker boot **and** inside both `chrome.runtime.onInstalled` and `chrome.runtime.onStartup` listeners. Top-level invocation guards against MV3's short-lived worker dropping the URL after restarts/manifest updates.
- UTM (`source=chrome_extension`, `medium=uninstall`) lets the reviews page distinguish uninstall traffic from organic visits. The page already renders a "We're sorry to see you go!" feedback form for this flow ([thinkvelocity.in/reviews](https://thinkvelocity.in/reviews/)).
- Errors normalized through `chrome.runtime.lastError` + a single structured `console.warn`; no new manifest permission needed.

### Side-panel launcher (right-edge floating trigger)

- New floating launcher pinned to the right edge of supported LLM host pages. Click opens the Velocity side panel via the existing `TV_OPEN_SIDE_PANEL` action.
- **Background fix (user gesture):** `TV_OPEN_SIDE_PANEL` now kicks off `chrome.sidePanel.open()` synchronously via a new `beginOpenSidePanelForSender(sender)` helper, before any `await`. Storage writes run in parallel via `Promise.all` so they no longer push the open call past Chrome's user-gesture window. Previously the awaited `chrome.storage.local.set` ran first and Chrome silently rejected the side-panel open because the gesture had been consumed.
- Drag handling fix: pointer capture is now explicitly released and drag listeners are cleaned up on `pointerup`, `pointercancel`, window blur, or a short watchdog timeout. This prevents the launcher from getting stuck in a dragging state where hover/click stops working after repositioning.
- `button/js/side-panel-launcher.js` — single-responsibility UI module; reads platform from `VelocityHostPlatforms`, sends a sender-validated message, no API/storage logic.
- `button/css/side-panel-launcher.css` — pill UI matching the inline injection button: flat `#181818` surface, `--vel-injection-elev` drop+inner-highlight shadow (no cyan halo ring on the body), 22px Velocity logo with the same cyan drop-shadow filter, and DM Sans typography. Slides out on hover to reveal "Open Velocity / Side panel" label.
- Vertical drag handle (six dots) repositions the launcher along the right edge; position persisted per session in `velocity_launcher_position`.
- Per-session hide (× tab → `velocity_launcher_hidden`) with a thin restore handle at the right edge to bring it back.
- One-time discovery pulse per session (`velocity_launcher_pulse_seen`).
- Manifest: appended `button/js/side-panel-launcher.js` and `button/css/side-panel-launcher.css` to the host-platforms content script block. Independent from the in-line injection bar (which still hugs the chat input).

### Output tab (mockup alignment)

- Card header: Edit, bookmark (stub), Copy  
- Footer: thumbs + **Insert in Chat** (cyan pill)  
- Below card: **Refine** + **Open In** (platform menu)  
- Label: **PRO ENHANCED** when `app-shell--theme-pro` + in session  

### Essence / memory auto-capture (ChatGPT, Claude, Gemini)

- `content/chatgpt-extractor.js`, `claude-extractor.js`, `gemini-extractor.js` — DOM → JSON (from Extension)  
- `content/essence-smart-trigger.js` — throttled ContextEngine triggers  
- `content/context-engine-bridge.js` — MAIN ↔ service worker  
- `features/essence-context-engine.js` — `processConversationContext` → ContextEngine + `velocity_essence_last_stored_at`  
- `features/extracted-conversation-store.js` — `TV.extractedConversationStore` mirrors compact extraction summary into `chrome.storage.local` (`velocity_last_extracted_summary`, `velocity_extracted_by_platform`)
- `core/storage-keys.js` — centralizes `LAST_EXTRACTED_SUMMARY`, `EXTRACTED_BY_PLATFORM`, and the page-localStorage key reference (`PAGE_LOCAL_KEYS`)
- `docs/ESSENCE_FLOW.md` — pipeline reference (incl. new §5.1 storage table)
- **Quiet mode (perf):** all three extractors run silently by default. `Logger.log/info/warn` and the bare `log/warn/info` console helpers are gated behind `localStorage.velocity_sidebar_debug === '1'` (set in the **host page** DevTools, not the service worker). Errors and key success messages still print.
- **Extraction storm fix (perf):** `SmartTracker.start` and `performSmartExtraction` early-return when `DataCache.isConversationPage()` is false (no `/c/<id>`, `/chat/<id>`, etc.). `handleUrlChange` no longer treats `home → home` pushState as a chat refresh. Removes the `session_<base64>_<ts>` fake-chat upserts and dozens of strategy-scan log lines per pushState on the AI tab.
- **Extractor throttle (perf, applied to all three extractors):** `extractConversation()` now has a per-page throttle (`__VELOCITY_THROTTLE`). Rules:
  - Skip immediately on non-conversation URLs (home / new-chat).
  - Rate-limit duplicate scans of the same URL to one every `MIN_INTERVAL_MS = 800ms` — returns the previous result instead of re-scanning.
  - After `EMPTY_STREAK_LIMIT = 3` consecutive empty results, **freeze** extraction for `FREEZE_MS = 30s`. The streak resets on any URL change or first non-empty result.
  - Result is cached in `__VELOCITY_THROTTLE.lastResult` so SmartTrigger / URL-refresh paths share the same scan.
- **Reduced URL-change retry pressure:** `handleUrlChange` retry loop dropped from `5×1000ms` (8×500ms when fixing) to `3×1200ms` (4×750ms), and now aborts mid-cycle if the user navigates away from the chat. Diagnostic "All messages filtered out!" 8-line warn block is gated behind `CONFIG.VERBOSE` (DevTools stack traces from that block were a measurable lag source on ChatGPT new-chat pages).
- **ContextEngine 400 fix:** `features/essence-context-engine.js` now coerces `user.accessTokenExpiresAt` to an ISO-8601 string (numbers like `1779268855000` from `chrome.storage.local` were rejected by Pydantic with `Input should be a valid string [type=string_type, input_type=int]`). Strings pass through; null/empty becomes `null`.
- **Streaming-wait re-entry guard (perf):** `DataCache.waitForStreamingComplete` in all three extractors now coalesces concurrent callers into a single 200ms poll loop. Previously every ChatGPT/Claude/Gemini DOM mutation burst spawned a fresh poll loop (visible in DevTools as a thousand-frame `check @ ...` stack chain that ran until streaming ended or the 60s timeout). New callers are queued onto the existing loop via `_waitForStreamingCompleteActive` + `_streamingCallbacks` and flushed together.
- **Bridge timeout cleanup (UX):** `essence-smart-trigger.js` now stores the 30s `setTimeout` id and clears it inside `handleBridgeResponse`. Previously a real HTTP response (success or 4xx/5xx) would still fire a misleading `⏰ Bridge response timeout` 30s later.
- **5xx logging:** ContextEngine 5xx responses now log a single concise warn (`ContextEngine server error (will retry on next eligible trigger)`) instead of the full HTML/JSON body. The existing `MAX_RETRIES=3` exponential backoff in `features/essence-context-engine.js` (~1s, 2s, 4s) is unchanged.
- Manifest: separate MAIN/ISOLATED content scripts on the three chat hosts  

### Platform inject

- `utils/platform-prompt-actions.js` — URLs, patterns, open-in list  
- `features/consumer-platform-inject.js` — tab inject + open tab  
- `content/platform-injection.js` — storage-driven inject on AI pages  
- Actions: `TV_CONSUMER_OPEN_IN_PLATFORM`, `TV_CONSUMER_INSERT_ACTIVE_TAB`  

### Composer & shell

- CSS-only mode/attach positioning (no broken `fixed` in side panel)  
- Session composer hides attach/mode; mic+send always visible in session  
- Textarea cleared after enhance  

### API alignment (Extension-new)

| Endpoint | Notes |
|----------|--------|
| `POST /dev/test/clarify` | `{ prompt, user_id, auth_token }` |
| `POST /dev/test/refine` | `{ prompt, qa_pairs, user_id, auth_token }` → `enhanced_prompt` |
| `POST …/prompt/refine-prompt` | API #3 after refine |
| `POST …/status/{id}/use` | Fire-and-forget after enhance |

### Auth & navigation fixes

- Login view default when signed out  
- `render()` → home only on **first** login (`justAuthed`)  
- Removed `authRef.refresh()` from library `onShown()`  
- Skip login overlay when `wasLoggedIn` during loading  

---

## File index (consumer panel)

| File | Role |
|------|------|
| `panel/consumer/sidebar.html` | Shell, views, composer dock, session tabs |
| `panel/consumer/sidebar.js` | Auth, navigation, session, output callbacks |
| `panel/consumer/sidebar.css` | All consumer styles |
| `panel/consumer/composer-bar.js` | Enhance, mode, attach, usage gate |
| `panel/consumer/output-view.js` | ORIGINAL + ENHANCED + session actions |
| `panel/consumer/suggestions-view.js` | Clarify/refine Q&A UI |
| `panel/consumer/versions-view.js` | Version cards + Use in Output |
| `panel/consumer/thought-process.js` | Enhance loader steps |
| `panel/consumer/prompt-library-view.js` | In-panel library |
| `panel/consumer/collection-memory-views.js` | Prompt book, collections, memories |
| `panel/consumer/subscription-theme.js` | Pro/free shell classes |
| `panel/consumer/usage-limit-banner.js` | Usage strip |
| `background.js` | Message router + `importScripts` chain |
| `manifest.json` | Permissions, CSP, content scripts |

---

## Messaging actions (consumer)

| Action | Purpose |
|--------|---------|
| `TV_CONSUMER_ENHANCE` | Run enhance flow |
| `TV_CONSUMER_CLARIFY` | MCQ / clarify |
| `TV_CONSUMER_REFINE` | Refine with Q&A |
| `TV_CONSUMER_FEEDBACK` | Like/dislike |
| `TV_CONSUMER_OPEN_IN_PLATFORM` | New tab + inject prompt |
| `TV_CONSUMER_INSERT_ACTIVE_TAB` | Inject into active tab |
| `TV_CONSUMER_LIST_*` | Library, collections, memories CRUD |
| `TV_AUTH_*` | Snapshot, login, logout |

---

## How to use this sheet

1. **Sprint planning** — Pull unchecked items from Phases 5–6 into your tracker; use **[`EXECUTION_PLAN.md`](./EXECUTION_PLAN.md)** for Phase 6 build order.  
2. **PR review** — Confirm the phase QA boxes for touched areas.  
3. **Release** — Complete **Pre-release checklist**; bump `manifest.json` version.  
4. **Onboarding** — Read **North star** + **Phase 0–2**; use **SUMMARY.md** for auth/token details.  
5. **Button + popup work** — Start with **EXECUTION_PLAN.md §4** (reference: `Extension-new/Button/js/input-injection.js`, `velocityPopupBox.js`).  

---

*Last updated: May 22 2026 — injection modal markdown rendering + paste-friendly Apply/Copy; modal re-skinned to sidebar dark theme; Collection button removed from injection hover toolbar; uninstall feedback URL registered to thinkvelocity.in/reviews.*

*May 22 2026 — v-chat parity pass:* Added `assets/VEL_LOGO2.png` (circular cyan Velocity badge) and rebuilt `icon16/32/48/128.png` from it so the Chrome toolbar icon, side-panel welcome hero, and home brand-mark all match the v-chat header logo. Pulled the v-chat sidebar nav icons (`Promptbook_icon.png`, `Memory_icon.png`, `Personalize_icon.png`) into `assets/` and wired them through CSS `mask-image` on `railLibrary` / `railCollection` / `railMemories`, repainting their native white silhouettes into the Velocity cyan accent (mode dropdown labels/icons — `Quick`, `Deep build`, `Studio`, `Max quality` — already matched v-chat). New chat is now a cyan `+` SVG, and all rail glyphs (new chat, library, collection, memory, invite, profile initials) sit on transparent buttons with no chip border or background — only the icon paints in cyan. Bottom cluster order is **Pro → Gift → Profile**, with `railUpgrade` reduced to a gold-on-black `Pro` text pill (gold border, gold text, black surface) and `syncRailUpsells` in `sidebar.js` keeping the pill visible until the auth snapshot confirms a Pro user.

*May 22 2026 — composer mic/send polish:* The mic and send buttons in the prompt composer are now **distinct, side-by-side controls** rather than two buttons fighting for the same 36×36 slot. `.composer-primary-action` is now a flex row (`gap: 6px`), `.action-switch-btn.is-hidden` collapses with `display: none` so the row shrinks back to just the mic, and the in-session slot uses `width: auto` so both buttons stay reachable while running an enhance/refine. The mic is restyled as a **cyan-outlined ghost** (1.5px cyan border, near-transparent fill, cyan mic glyph — `filter: none` because the PNG ships in cyan) while the send button keeps its **solid cyan filled disc** with a soft cyan glow, making the primary CTA visually dominant. Listening / transcribing states keep their red / cyan tinted fills. `setPrimaryActionMode(mode, { hideMic })` in `composer-bar.js` now only collapses the mic when usage is exhausted; otherwise the mic stays visible alongside the send, so the user can dictate more text without first closing the composer. Voice transcription `onTranscript` was hardened to **re-fetch the live `#promptInput`** each call (avoids stale closure refs across view re-renders), **always append** with a normalized space (`existing + " " + transcript`, never replacing whatever the user already typed), then refocus the textarea and move the caret to the end so the user can keep editing.

### Multi-step tutorial & onboarding popups

- **Install tutorial page redesign (`panel/tutorial/`):** Now a multi-step walkthrough (3 steps) with auto-switching video. `tutorial.html` adds `data-step` attrs on `<li>` elements, step indicator dots (`.tutorial-step-dot`), and "Next" button alongside "Start Prompting" CTA. `tutorial.js` implements `updateStep(step)` which toggles `.is-active` on steps/dots, swaps the `<source>` video, and shows Next vs Try button based on current step. Keyboard navigation: ArrowLeft/Right to move, Enter to proceed/submit. Videos: `tutorialvideo_step1.mov`, `tutorialvideo_step2.mov`, `tutorialvideo_step3.mov` in `assets/Extension videos/`.
- **In-page tutorial overlay (`button/js/injection-popups.js`):** Same 3-step tutorial rendered as a full-screen overlay on AI chat hosts. `showTutorialOverlay(opts)` builds a `.velocity-tutorial-overlay` with `.velocity-tutorial-card` containing:
  - Step list with connectors (`.velocity-tutorial-step-connector.is-passed` for completed)
  - Video carousel (`.velocity-tutorial-video-el.is-active`) with dot indicators
  - "Next" / "Start Prompting" button row
  - Blob-URL video loading via `TV_FETCH_PACKAGED_RESOURCE` to bypass host CSPs (chatgpt.com, claude.ai, etc. block `chrome-extension://` media-src). Background handler base64-encodes the packaged video file; content script decodes and creates `blob:` URL.
- **First-enhance celebration popup:** `showFirstEnhancePopup(opts)` — bottom-right dialog "You just enhanced your first prompt!" with confetti animation. Auto-fades after `FIRST_ENHANCE_FADE_MS = 3000ms`. One-shot global (caller gates via storage).
- **Daily-limit reached popup:** `showDailyLimitPopup(opts)` — gold-themed upsell "Daily limit reached!" with Pro upgrade CTA linking to `thinkvelocity.in/?source=extension&…`. Stays until dismissed.
- **Like-reward incentive popup:** `showLikeRewardPopup(opts)` — "Glad you loved it!" invite-a-friend upsell triggered by thumbs-up on any host. Auto-fades after `LIKE_REWARD_FADE_MS = 5500ms`. CTA opens `thinkvelocity.in/chat?invite=1&…`. One-shot via caller (injection-modal gates with storage).
- **CSS (`button/css/injection-popups.css`):** Full dark-theme popup styles — `.velocity-popup-layer`, `.velocity-popup`, `.velocity-popup--first-enhance`, `.velocity-popup--daily-limit`, `.velocity-popup--like-reward`. Tutorial overlay styles — `.velocity-tutorial-overlay`, `.velocity-tutorial-card`, `.velocity-tutorial-step.is-active`, `.velocity-tutorial-step-connector.is-passed`, `.velocity-tutorial-video`, `.velocity-tutorial-video-dot.is-active`.
- **Background handler (`background.js`):** Added `TV_FETCH_PACKAGED_RESOURCE` action to read packaged extension files as base64 for content-script blob consumption (required for CSP-blocked video playback on chat hosts).

### Suggestions view & composer sync fix

- **Voice mic icon color:** `.voice-mic-img` CSS filter updated from `filter: none` to the cyan colorization filter (`brightness(0) saturate(100%) invert(79%) sepia(47%) saturate(1000%) hue-rotate(131deg) brightness(101%) contrast(97%)`) matching the accent color. The PNG ships as a black silhouette; the filter transforms it to `#19d8e6` cyan.
- **Q&A answer sync fix (`suggestions-view.js`):** `syncComposerFromAnswers()` logic updated — previously returned early if `_composerUserEditing && _refineComposerActive`, blocking sync even when answers existed. Now returns early only if `answeredCount === 0`, ensuring Q&A summary always populates the composer when answers are present. `_composerUserEditing` is reset to `false` when `answeredCount > 0` so subsequent syncs work correctly.
- **Send/Refine button visibility:** Implicitly fixed by the sync fix — `canSubmitRefine()` returns true when `_answers` has entries, which previously wasn't reached due to the early-return bug.

### Prompt book detail view state fix

- **Split-view bug:** Clicking "Use in Chat" from a prompt book card detail sometimes showed both `viewCollections` and `viewOutput` simultaneously due to cleanup order issues.
- **Fix 1 (`prompt-book-detail-view.js`):** Reordered `insertIntoChat()` to call `closeDetail()` before invoking `onInsertPrompt` callback, ensuring popup closes before session transition.
- **Fix 2 (`sidebar.js`):** Added explicit cleanup in `showSessionShell()` — calls `consumerPromptBookDetailView.close()` and `consumerPromptLibraryView.closeDetail()` (wrapped in try-catch) to force-close any open detail popups before switching to session view.
- **Fix 3 (`prompt-library-view.js`):** Exposed internal `closePromptDetail()` as public `closeDetail()` method for cleanup access from sidebar.
