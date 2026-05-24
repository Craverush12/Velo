# Velocity Enterprise Extension — Goal & Test Checklist

End-user facing. Every item here should be true before Phase 1 ships.
Each goal has the team test cases directly beneath it — tick both when done.

---

## Auth

- [ ] A user seeing the extension for the first time can tap "Enterprise Login" on the welcome screen
  - [ ] **TC-AUTH-01** — Open fresh panel, confirm "Enterprise Login" button is visible and clickable

- [ ] The enterprise login form appears inside the side panel — no redirect to a browser tab
  - [ ] **TC-AUTH-02** — Click "Enterprise Login", confirm form appears in-panel and tab count does not increase

- [ ] Login form has all required fields and navigation links
  - [ ] **TC-AUTH-03** — Confirm email field, password field, Login button, "Forgot password?" link, and "← Back to consumer" link are all present

- [ ] A user can log in with their work email and password
  - [ ] **TC-AUTH-04** — Submit valid credentials, confirm enterprise workspace loads immediately

- [ ] A wrong password shows a clear error message inline
  - [ ] **TC-AUTH-05** — Submit valid email + wrong password, confirm inline error, form stays open
  - [ ] **TC-AUTH-06** — Submit unknown email + any password, confirm inline error

- [ ] Empty fields are caught client-side before any API call
  - [ ] **TC-AUTH-07** — Submit with empty email, then empty password; confirm validation error with no network request fired

- [ ] Session persists across panel close/reopen and browser restart
  - [ ] **TC-AUTH-08** — Close and reopen panel; confirm enterprise workspace loads without login prompt
  - [ ] **TC-AUTH-09** — Fully close and reopen Chrome; confirm enterprise panel loads

- [ ] A logged-in enterprise user can log out from the panel header
  - [ ] **TC-AUTH-10** — Click logout; confirm enterprise login form shown (not consumer screen)
  - [ ] **TC-AUTH-11** — After logout, check DevTools storage; confirm all `ent_*` keys removed

- [ ] If the session expires silently, the user sees "Session expired" and is returned to login
  - [ ] **TC-AUTH-12** — Manually expire tokens in DevTools storage; trigger enhance or reopen panel; confirm "Session expired" message and login form

- [ ] "Forgot password?" opens the enterprise web portal in a new tab
  - [ ] **TC-AUTH-13** — Click "Forgot password?"; confirm `velocityenterprise.toteminteractive.in/frontend/` opens in new tab

- [ ] "← Back to consumer" returns to consumer panel without logging into enterprise
  - [ ] **TC-AUTH-14** — Click "← Back to consumer" from enterprise login form; confirm consumer panel loads, `velocity_sidebar_flow` cleared

- [ ] A user who also has a consumer account can run both sessions simultaneously
  - [ ] **TC-AUTH-15** — Log into consumer, then log into enterprise; confirm both `accessToken` and `ent_accessToken` present in storage; confirm mode switcher visible in header

- [ ] Switching modes does not log either account out
  - [ ] **TC-AUTH-16** — Switch enterprise → consumer → enterprise; confirm no login forms shown, both token sets intact throughout

---

## Enhance (Enterprise)

- [ ] Pressing enhance sends the prompt through a guardrail policy check first
  - [ ] **TC-ENH-01** — Submit a clean prompt; confirm enhancement proceeds without interruption (guardrail check silent in background)

- [ ] A flagged prompt (WARN) shows reason and Proceed/Cancel options
  - [ ] **TC-ENH-02** — Submit a WARN-level prompt; confirm warning banner with violation reason and both buttons
  - [ ] **TC-ENH-03** — Click "Proceed anyway"; confirm enhancement streams
  - [ ] **TC-ENH-04** — Click "Cancel"; confirm original prompt remains in composer, no output

- [ ] A prompt requiring explicit confirmation (REQUIRE_CONFIRMATION) shows a modal
  - [ ] **TC-ENH-05** — Submit a REQUIRE_CONFIRMATION prompt; confirm modal appears, no streaming yet
  - [ ] **TC-ENH-06** — Click "Confirm"; confirm enhancement streams

- [ ] Sensitive content is redacted and shown before enhance (REDACT)
  - [ ] **TC-ENH-07** — Submit a REDACT-level prompt; confirm cleaned version shown with "Sensitive content was removed" and both buttons
  - [ ] **TC-ENH-08** — Click "Enhance with redacted"; confirm output does not contain the original sensitive text

- [ ] A blocked prompt shows a hard block with no enhance path (BLOCK)
  - [ ] **TC-ENH-09** — Submit a BLOCK-level prompt; confirm block message, no "Proceed" button, no enhancement

- [ ] A prompt requiring admin approval shows "Sent for admin review" (REQUIRE_APPROVAL)
  - [ ] **TC-ENH-10** — Submit a REQUIRE_APPROVAL prompt; confirm approval pending message, no enhance
  - [ ] **TC-ENH-11** — Close and reopen panel; confirm "Awaiting admin review" banner still visible

- [ ] Enhanced output streams incrementally (no single block load)
  - [ ] **TC-ENH-12** — Submit long clean prompt; confirm text appears progressively, not all at once

- [ ] Network failures are handled gracefully at both pipeline stages
  - [ ] **TC-ENH-13** — Set network offline; submit prompt; confirm friendly error + retry option on guardrail check failure
  - [ ] **TC-ENH-14** — Allow guardrail to pass, then cut network; confirm friendly error + composer still has prompt

---

## Mode Experience

- [ ] The enterprise panel looks and feels distinct from the consumer panel
  - [ ] **TC-MODE-01** — Compare enterprise and consumer panels visually; confirm distinct header/branding

- [ ] Switching modes is one click and instant
  - [ ] **TC-MODE-02** — Click mode switcher; confirm transition in under 300ms, no loading spinner

- [ ] Switching modes does not log out of either account
  - [ ] **TC-MODE-03** — Switch enterprise → consumer → enterprise; confirm both token sets remain in storage throughout

- [ ] The active mode is remembered across browser restarts
  - [ ] **TC-MODE-04** — Set mode to enterprise, fully close/reopen Chrome; confirm enterprise panel loads first

- [ ] Mode switcher only appears when both sessions are active
  - [ ] **TC-MODE-05** — With only enterprise session active, confirm mode switcher is not shown

---

## Edge Cases

- [ ] Opening the panel on a new device/profile with no stored session lands on login form, not a broken state
  - [ ] **TC-EDGE-01** — Fresh install, open panel; confirm welcome screen with no JS errors
  - [ ] **TC-EDGE-02** — Set `velocity_sidebar_flow = "enterprise"` in storage with no tokens; open panel; confirm enterprise login form

- [ ] The extension does not break consumer mode for users who never touch enterprise
  - [ ] **TC-EDGE-03** — Both sessions active; switch to consumer; trigger consumer enhance; confirm consumer API endpoint called (not enterprise)
  - [ ] **TC-EDGE-04** — Fresh consumer-only install; use all consumer features; confirm no regressions or enterprise-related errors

- [ ] Guardrail endpoint unreachable does not silently allow enhancement
  - [ ] **TC-EDGE-05** — Block enterprise host in DevTools; submit enterprise prompt; confirm friendly error shown and enhancement is blocked (no silent bypass)

- [ ] Very long prompts handled without truncation or crash
  - [ ] **TC-EDGE-06** — Submit 3000+ word prompt; confirm no JS error, no silent truncation, graceful success or failure message

---

## Unit Test Checklist (developer-facing, run before every PR merge)

- [ ] **TC-AUTH-U01** — `normalizeSidebarFlow` returns correct mode for all input variants including null/undefined
- [ ] **TC-AUTH-U02** — Token expiry check uses 60-second buffer correctly
- [ ] **TC-AUTH-U03** — Concurrent token refresh calls share one in-flight promise (no duplicate refresh requests)
- [ ] **TC-AUTH-U04** — Session state machine transitions match spec for all 5 defined paths
- [ ] **TC-ENH-U01** — Guardrail decision router calls correct callback for all 6 outcomes (ALLOW/WARN/REDACT/BLOCK/REQUIRE_CONFIRMATION/REQUIRE_APPROVAL)
- [ ] **TC-ENH-U02** — REQUIRE_APPROVAL writes `ent_pendingApproval` with correct shape to storage
- [ ] **TC-ENH-U03** — REDACT passes `redactedPrompt` (not original text) to the enhance function
- [ ] **TC-EDGE-U01** — `ent_*` storage keys do not overlap with any consumer key name
- [ ] **TC-EDGE-U02** — Active mode in-memory cache reads from storage on init, defaults to consumer when absent

---

## Phase 2 (not in scope now — listed to stay aligned)

- [ ] Context Packs — org-uploaded documents appear as context when enhancing
- [ ] Prompt Collections — org-shared prompt library browsable inside the panel
- [ ] Team switcher — user can switch active team context
- [ ] Prompt audit trail — user can see history of enterprise prompts and their moderation outcomes
- [ ] Analytics — admin can see usage stats (web frontend feature, not extension)
- [ ] Automated E2E tests (Puppeteer + chrome-extension harness)
