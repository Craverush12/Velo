# Release Notes – Version 3.9.0

**Velocity: The Prompt Co-Pilot**

This release introduces the Velocity Side Panel as a first-class workspace, an in-page Improve modal that lives directly on your favorite AI chat sites, a floating side-panel launcher, voice capture, persistent conversation memory, and a Prompt Library / Collections / Memories suite — turning Velocity from a one-shot prompt enhancer into a full prompt co-pilot you can drive with one click or one keystroke.

---

## New Features

### Velocity Side Panel

A standalone Chrome side panel is now the home base for the entire Velocity workflow. Sign in once at thinkvelocity.in and your tokens sync automatically into the extension — the panel then exposes home, enhance, suggestions, output, versions, library, prompt book, collections, memories, and a context tab in a single dockable surface.

- Bound to `Ctrl+Shift+V` (Windows) / `Cmd+Shift+V` (macOS).
- Signed-out users land on a login view (no "home flash"); first successful login transitions straight into the session UI.
- Logout clears tokens and flow state cleanly.

### Floating Side-Panel Launcher

A right-edge floating pill follows you across every supported AI chat host and opens the Velocity side panel in one click — no need to dig through the toolbar.

- Drag the six-dot handle vertically to reposition along the right edge; position persists per session.
- Per-tab close (`×`) with a slim restore handle to bring the launcher back.
- One-time discovery pulse per session so new users notice it on first visit.
- Matches the injection-bar pill style: flat `#181818` surface, cyan-glow Velocity logo, DM Sans typography.

### In-Page Injection Bar + Improve Modal

Velocity now surfaces a floating pill near the chat input on every supported AI site. The pill stays compact by default; hovering expands it to reveal a **Voice** and **Prompt Library** button alongside the always-visible **Improve** and drag-dots core.

- Click ✨ Improve to enhance whatever is in the host chat input directly through an in-page modal — no context switch.
- Modal opens centered, drag the six-dot handle to move it anywhere, expand button (`⤢`) toggles a full-screen view.
- Inline tabs ready for Improve / Refine workflows; toolbar exposes Edit, Save-to-Collection, and Copy.
- Composer bar exposes thumbs Like / Dislike (with reason capture on dislike) and an **Apply** CTA (Ctrl+Enter) that writes the enhanced prompt straight into the host chat box.

### Intelligent Prompt Rendering & Paste

The enhanced prompt is rendered the same way it appears in the side panel's Output tab: bold strong spans, cyan section heads, cyan bullet / numbered markers, paragraph spacing — no more raw `**asterisks**` showing in the body.

- **Apply** / **Copy** / **Insert in Chat** all route through a paste-friendly formatter that strips markdown markers while preserving structure (`Section:` heads, `- bullets`, `1.` numbered, paragraph breaks).
- Result: ChatGPT, Claude, Gemini, Mistral, Grok, Bolt.new, V0, Gamma, Lovable, Replit, Suno, Perplexity, Kimi, Emergent, and Hera all receive clean prose every time.
- Edit mode swaps the structured view for a raw-markdown textarea so power users can hand-tune the markdown; saving re-renders the structured view.

### Voice Capture

A microphone button on the injection bar (and `Alt+V` hotkey) opens the side panel directly in voice-transcribe mode.

- Offscreen document hosts the mic so permission survives navigation between tabs.
- Dedicated mic-permission view in the side panel for first-run grant.
- Recording state is reflected on the injection bar (red pulse) and the side-panel composer.

### Enhance Session: Thought Process → Output → Refine → Versions

Submitting a prompt now drives a five-step **Thought Process** loader (Understanding → Generating → Adding context → Quality check → Finalizing) followed by a structured **Output** card.

- ENHANCED body uses the shared FormattedMessage renderer (sections, bullets, strong, numbered lists).
- ORIGINAL collapsible block with inline preview truncation.
- **Refine** pill below the Output card drops you into a **Suggestions** Q&A loop (clarify → refine).
- **Versions** tab maintains a full history: Enhanced → Refined 1 → Refined N → Original; any version can be promoted back via "Use in Output".
- Server-sent-events streaming so first content appears in under a second.

### Open In Any Supported Platform

From the Output card, the **Open In** dropdown launches a new tab on a chosen platform and auto-injects the enhanced prompt into its chat input.

- Supported: ChatGPT, Claude, Gemini, Mistral, Grok, Perplexity, Bolt.new, V0, Gamma, Lovable, Replit, Suno, Kimi, Emergent, Hera, plus Google Labs.
- A complementary **Insert in Chat** action injects into the current active tab when it already is one of those hosts; otherwise the prompt falls back to the side panel composer.

### Prompt Library, Prompt Book, Collections & Memories

A complete prompt-management surface lives inside the side panel.

- **Prompt Library** — in-panel list and detail modal; copy or open in chat in one click.
- **Prompt Book** — your enhanced prompts saved via the bookmark action.
- **Collections** — list, create, and organize prompts.
- **Memories** — list and inline editor.
- Pro paywall on premium-only library prompts with an integrated upgrade CTA.

### Auto-Essence Conversation Memory (ChatGPT, Claude, Gemini)

After five messages on a supported chat, Velocity quietly extracts the conversation, runs it through the ContextEngine, and stores a compact summary your future enhancements can lean on.

- Per-platform extractors with shared smart-trigger throttling.
- Stored under `velocity_last_extracted_summary` + `velocity_extracted_by_platform` keys; reachable in the side panel Memory list.
- All processing is silent by default — host-page DevTools opt-in via `localStorage.velocity_sidebar_debug = "1"` for diagnostics.

### Uninstall Feedback Page

If a user removes Velocity from `chrome://extensions`, Chrome now opens a feedback page at `thinkvelocity.in/reviews` so the team can listen and improve.

- Tagged with `utm_source=chrome_extension&utm_medium=uninstall` for clean attribution.
- Re-applied on every service-worker boot so the URL survives manifest updates.

---

## Performance & Reliability

### MV3-Safe User-Gesture Handling

`chrome.sidePanel.open()` is invoked synchronously from the launcher message handler **before** any `await`, with snapshot persistence running in parallel via `Promise.all`. Chrome no longer rejects the open call with "user gesture consumed".

### Smarter Memory Capture

- Per-page extraction throttle: one scan per URL every 800 ms; freeze for 30 s after three consecutive empty scans.
- Streaming-wait coalescing: concurrent callers share a single 200 ms poll loop instead of spawning a new one per DOM mutation burst.
- URL-change retries dropped from 5 × 1000 ms to 3 × 1200 ms and abort mid-cycle when the user navigates away from the chat.
- Removes the previous "extraction storm" on ChatGPT new-chat / pushState navigation.

### Context Engine Hardening

- `accessTokenExpiresAt` is coerced to ISO-8601 strings before sending — server Pydantic validation no longer rejects numeric epoch values with `string_type`.
- Bridge `setTimeout` ids are tracked and cleared on response, so successful or 4xx/5xx responses no longer surface misleading "Bridge response timeout" warnings 30 s later.
- 5xx responses emit a single concise warn; the existing three-attempt exponential backoff (~1 s, 2 s, 4 s) is unchanged.

### Quieter by Default

All per-platform extractor logging is gated behind `localStorage.velocity_sidebar_debug === "1"` on the host page (not the service worker). Errors and key successes still print; the per-frame `check @ …` stack chains are gone.

---

## UI & Interaction Updates

### Dark-Theme Parity Across All Surfaces

The in-page Improve modal now uses the exact sidebar palette — deep `#101010` surface, `#181818` / `#232323` elevation, brand cyan `#19D8E6`, Pro gold `#EEC13C`, DM Sans typography. The modal feels like a piece of the sidebar instead of a light card pasted on top of a dark site.

- Active tab uses a brighter rgba border so state reads on dark backgrounds.
- Close button hover strengthened (`#fca5a5` on red-tinted surface) for visibility on `#101010`.
- Primary CTAs (`Apply`, `Send Feedback`, Sign-in wall) use dark text on cyan to match the sidebar's primary buttons.
- Pro mode re-tints all accents to the brighter gold family (`#EEC13C` / `#F5C842`).

### Injection Bar — Tightened Hover Toolbar

The hover-expandable strip now shows exactly two buttons — Voice and Prompt Library — flanking the Improve / drag-dots core. The redundant Collection button was removed; the 84 px expandable footprint, 6 px gap, and staggered entrance animations are back to their original tuning.

### Welcome Coachmark

After install, a one-shot coachmark anchors itself to the injection bar with a "Click this button to instantly enhance your prompt with AI" message. Auto-dismisses after 14 s; the install tutorial's "Try Velocity" CTA re-arms it as a safety net so no user misses the cue.

### Composer & Session Polish

- Mode and attach popups now use CSS-only absolute positioning — no more clipped menus inside the side panel.
- Session composer keeps mic + send always visible; attach and mode hide once a session is active so the focus stays on the conversation.
- Textarea clears after a successful enhance.

### Pro vs Free Theming

Pro accounts get a gold composer border, gold profile ring, **PRO ENHANCED** card label, and gold accents on the in-page modal. Tabs and library filters intentionally stay cyan so chrome remains consistent across tiers.

### Usage Banner

A full-width banner above the composer surfaces remaining free enhancements; gating kicks in at zero remaining (Enhance button disabled, upgrade CTA shown).

---

## Bug Fixes

- Login view defaults when signed out — no flash of "home" before the auth state resolves.
- `render()` only forces home view on the **first** login (`justAuthed` flag) so refresh-loops no longer kick users back to home.
- Removed `authRef.refresh()` from prompt-library `onShown()` — library navigation no longer bounces back to home.
- Login overlay no longer flashes when `wasLoggedIn` is true during initial loading.
- Duplicate `id="authHint"` removed from `sidebar.html`.
- Floating launcher drag listeners are explicitly released on pointerup, pointercancel, window blur, or a watchdog timeout — launcher can no longer get stuck in a dragging state.
- Side-panel open via the launcher no longer fails silently due to user-gesture-consumed errors.
- Improve modal Apply now produces paste-friendly text on every supported chat platform.
- In-page modal no longer shows literal `**` markers around section heads.
- Active tab in the Improve modal uses a dark-theme-compatible border (was hard-coded `#d0d5db`).

### Additional Fixes

- Pro mode gold shadows re-mapped from the old desaturated `rgba(201,162,39,…)` to the brighter sidebar gold family `rgba(238,193,60,…)`.
- Modal close-hover red strengthened so the destructive state is visible on the dark surface.
- Removed the unused Collection hosted-page deep-link constant from the injection bar.
- Modal feedback-send and primary buttons use dark text on cyan (consistent with the sidebar's primary buttons).
- Manifest content-script ordering: structured prompt renderer loads after `prompt-format.js` so the modal always has both helpers available.
- "All messages filtered out!" diagnostic block now gated behind `CONFIG.VERBOSE` — DevTools stack traces from that block were a measurable lag source on ChatGPT new-chat pages.

### Recent Updates

- New 3-step tutorial with video walkthroughs (standalone page + in-page overlay)
- First-enhance celebration, daily-limit, and like-reward popups
- Voice mic icon now cyan; Q&A answers sync to composer correctly
- Fixed split view bug in prompt book "Use in Chat"
