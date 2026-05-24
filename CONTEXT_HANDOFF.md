# Velocity Enterprise Extension — Full Context Handoff

**For:** New Claude Sonnet 4.6 session (medium thinking effort)  
**Date written:** 2026-05-24  
**Project dir:** `C:\Users\Arjun\Desktop\ThinkVelocity`  
**Branch:** `Production`

This document is the complete context of everything discovered, decided, and built in the previous session. Read all sections before writing a single line of code. Structured using the DSA Problem-Solving Stack so nothing is missed.

---

## STEP 1 — UNDERSTAND: What is this project?

**Velocity** is a Chrome extension (side panel) that enhances prompts before they are sent to AI platforms (ChatGPT, Claude, Gemini, etc.). It has two product lines:

- **Consumer (B2C)** — existing, fully working, uses `thinkvelocity.in` API
- **Enterprise (B2B)** — being added now, uses `velocityenterprise.toteminteractive.in`

**The task for the new session:** Implement Phase 1 of enterprise mode in the Chrome extension. A full design spec, goal checklist, and test cases already exist. The new session must write the implementation plan first, then implement.

**What has already been done (do NOT redo):**
- SSH'd into the enterprise EC2 server, mapped the full codebase
- Designed the full architecture (approved by user)
- Written design spec → `docs/superpowers/specs/2026-05-24-enterprise-extension-design.md`
- Written goal checklist → `GOAL.md`
- Written all test cases → `TEST_CASES.md`

**What still needs to be done:**
1. Create an implementation plan (invoke `superpowers:writing-plans` skill)
2. Implement all new/modified files per the design spec

---

## STEP 2 — CLASSIFY: System map

### Enterprise Server (live, accessible)

| Layer | Public URL path | Internal port | Tech |
|---|---|---|---|
| NestJS backend | `https://velocityenterprise.toteminteractive.in/backend/` | 3000 | Auth, users, guardrails, teams, audit |
| FastAPI Python | `https://velocityenterprise.toteminteractive.in/prompt/` | 3002 | Enhancement, moderation |
| React frontend | `https://velocityenterprise.toteminteractive.in/frontend/` | 8081 | Admin web UI (extension does NOT use this) |

**SSH access:**
```
Key: C:\Users\Arjun\Downloads\fr-img-tes-ap-south (1).pem
User: ubuntu (NOT ec2-user)
Host: 13.233.86.137
Command: ssh -i /tmp/ec2key.pem ubuntu@13.233.86.137
Docker containers: enterprise-backend, prompt-enhance, velocity-frontend
```

**Enterprise auth — no OAuth, plain email + password:**
```
POST /backend/auth/login
Body: { email, password }
Response: { accessToken (15min JWT), refreshToken (7d), expiresIn: 900,
            user: { id, enterpriseId, name, email, roleTypes } }

POST /backend/auth/refresh
Body: { refreshToken }

POST /backend/auth/logout
Header: Authorization: Bearer <accessToken>
Body: { refreshToken }
```

**JWT payload:** `{ userId, enterpriseId, name, email, roleTypes }`

**Guardrail check:**
```
POST /backend/guardrail/check-prompt
Header: Authorization: Bearer <ent_accessToken>
Body: { prompt, contentType: "CHAT_PROMPT", enterpriseId }
Response: {
  allowed: boolean,
  decision: "ALLOW"|"WARN"|"REDACT"|"BLOCK"|"REQUIRE_CONFIRMATION"|"REQUIRE_APPROVAL",
  queueId: string | null,
  violations: [...],
  redactedPrompt: string | null
}
```

**Enterprise enhance:**
```
POST /prompt/enhance/stream
Header: Authorization: Bearer <ent_accessToken>
Body: { prompt, enterpriseId, userId, ... }
Response: SSE streaming (same format as consumer stream)
```

---

## STEP 3 — BRUTE FORCE: Current extension state (what exists)

### Extension root: `IMPORTANT/Sidebar_extension/`

**Key existing files:**

| File | Status | Notes |
|---|---|---|
| `manifest.json` | Exists | MV3, version 3.9.0, side panel at `panel/bootstrap.html` |
| `background.js` | Exists, modified | Service worker. Has auth, token manager calls, message handlers. Needs enterprise handlers added. |
| `core/storage-keys.js` | Exists | Already has `SIDEBAR_FLOW`, `GUEST_FREE_USED`. Needs `ent_*` keys added. |
| `core/sidebar-flow.js` | Exists | Already has `TV.SidebarFlow.CONSUMER` / `.ENTERPRISE` and `normalizeSidebarFlow()`. Needs 4-state machine added. |
| `core/token-manager.js` | Exists (inferred) | Has `getApiBase()`, `storeAuthTokens()`, `ensureFreshAccessToken()`. Needs mode-aware prefix + enterprise refresh dedup. |
| `panel/bootstrap.html` | Exists | Entry point |
| `panel/bootstrap.js` | Exists | Routes panel view. Needs enterprise routing added. |
| `panel/consumer/` | Exists, complete | DO NOT TOUCH. All consumer UI. |
| `panel/enterprise/sidebar.html` | Exists (shell) | Empty shell, needs wiring |
| `panel/enterprise/sidebar.js` | Exists (shell) | Empty shell, needs implementing |
| `panel/enterprise/sidebar.css` | Exists | Style shell |
| `features/consumer-enhance-flow.js` | Exists | Consumer enhance. DO NOT TOUCH. |
| `features/consumer-clarify-refine.js` | Exists, modified | Consumer refine. DO NOT TOUCH. |

**New files to create:**

| File | Purpose |
|---|---|
| `panel/enterprise/enterprise-auth-view.js` | Inline email+password login form |
| `panel/enterprise/enterprise-enhance-view.js` | Guardrail outcome UI (all 6 states) |
| `features/enterprise-enhance-flow.js` | Guardrail → enhance DAG logic |

---

## STEP 4 — OPTIMIZE: All design decisions (final, approved)

### A. Storage keys — new keys to add to `core/storage-keys.js`

```js
ENT_ACCESS_TOKEN:     "ent_accessToken",
ENT_REFRESH_TOKEN:    "ent_refreshToken",
ENT_ACCESS_EXP:       "ent_accessTokenExpiresAt",
ENT_USER_ID:          "ent_userId",
ENT_ENTERPRISE_ID:    "ent_enterpriseId",
ENT_USER_NAME:        "ent_userName",
ENT_USER_EMAIL:       "ent_userEmail",
ENT_ROLE_TYPES:       "ent_roleTypes",
ENT_PENDING_APPROVAL: "ent_pendingApproval",
// shape: { queueId, promptExcerpt, submittedAt } | null
```

Consumer keys (`accessToken`, `refreshToken`, etc.) are UNCHANGED. No migration needed.

### B. Session state machine — add to `core/sidebar-flow.js`

```
States:
  CONSUMER_ONLY      con_ tokens valid, ent_ absent
  ENTERPRISE_ONLY    ent_ tokens valid, con_ absent
  BOTH_ACTIVE        both valid simultaneously
  SWITCHING          transient during mode flip (in-memory only)

Transitions:
  enterprise_login_success  → any state      → ENTERPRISE_ONLY or BOTH_ACTIVE
  enterprise_logout         → BOTH_ACTIVE    → CONSUMER_ONLY
  consumer_logout           → BOTH_ACTIVE    → ENTERPRISE_ONLY
  ent_refresh_fail          → ENTERPRISE_ONLY → show AUTH view (clear ent tokens)
  ent_refresh_fail          → BOTH_ACTIVE    → CONSUMER_ONLY + banner
```

### C. In-memory mode cache — add to `background.js`

```js
// Init once on service worker startup — avoids async storage I/O on every token resolve
let _activeMode = TV.SidebarFlow.CONSUMER;
let _entRefreshPromise = null;  // dedup concurrent refresh calls

chrome.storage.local.get(TV.STORAGE_KEYS.SIDEBAR_FLOW, (r) => {
  _activeMode = TV.normalizeSidebarFlow(r[TV.STORAGE_KEYS.SIDEBAR_FLOW]);
});
TV.tokenManager.getActiveMode = () => _activeMode;
```

### D. Enterprise token refresh — deduplication pattern

```js
async function ensureFreshEnterpriseToken() {
  // 1. dedup: if refresh already in-flight, return same promise
  if (_entRefreshPromise) return _entRefreshPromise;
  
  const exp = await getStoredValue(TV.STORAGE_KEYS.ENT_ACCESS_EXP);
  // 2. still fresh (>60s buffer) — return stored token directly
  if (exp - Date.now() > 60_000) return getStoredValue(TV.STORAGE_KEYS.ENT_ACCESS_TOKEN);
  
  // 3. needs refresh
  _entRefreshPromise = doEnterpriseRefresh()
    .then(({ accessToken, expiresIn }) => {
      chrome.storage.local.set({
        [TV.STORAGE_KEYS.ENT_ACCESS_TOKEN]: accessToken,
        [TV.STORAGE_KEYS.ENT_ACCESS_EXP]: Date.now() + expiresIn * 1000,
      });
      return accessToken;
    })
    .catch(() => {
      // clear ent tokens → trigger AUTH view
      chrome.storage.local.remove(Object.values(ENT_KEYS));
      _activeMode = TV.SidebarFlow.CONSUMER;
    })
    .finally(() => { _entRefreshPromise = null; });
  
  return _entRefreshPromise;
}
```

### E. Guardrail + enhance pipeline — `features/enterprise-enhance-flow.js`

```
prompt submitted
  → ensureFreshEnterpriseToken()
  → POST /backend/guardrail/check-prompt
      ALLOW               → POST /prompt/enhance/stream (SSE)
      WARN                → callbacks.onWarning(result, proceedFn)
      REQUIRE_CONFIRMATION→ callbacks.onConfirm(result, proceedFn)
      REDACT              → callbacks.onRedact(result.redactedPrompt, enhanceFn)
      BLOCK               → callbacks.onBlock(result)   [terminal]
      REQUIRE_APPROVAL    → handleApprovalQueue(result) [terminal]
                            stores ent_pendingApproval = { queueId, promptExcerpt, submittedAt }
```

Function signature:
```js
async function enterpriseEnhance(prompt, callbacks) {
  // callbacks: { onWarning, onConfirm, onRedact, onBlock, onApproval, onStream, onComplete, onError }
}
```

### F. Panel boot sequence — `panel/bootstrap.js` change

```
read velocity_sidebar_flow
  → "enterprise" → load panel/enterprise/sidebar.js
  → "consumer"   → existing consumer load (unchanged)

enterprise/sidebar.js on init:
  1. read ent_accessToken + ent_accessTokenExpiresAt
  2. absent or no refresh token → render AUTH view
  3. present                    → render MAIN view
  4. check ent_pendingApproval  → if set, show banner
```

### G. Enterprise panel views

```
AUTH view     → enterprise-auth-view.js
  Fields: email, password, Login button
  Links: "Forgot password?" (opens /frontend/ in new tab), "← Back to consumer"

MAIN view     → enterprise/sidebar.js
  Header: enterprise branding + logout + mode switcher (only if BOTH_ACTIVE)
  Body: compose + enhance (calls enterpriseEnhance())

GUARDRAIL overlay → enterprise-enhance-view.js
  WARN:               warning banner + [Proceed anyway] [Cancel]
  REQUIRE_CONFIRMATION: modal + [Confirm] [Cancel]
  REDACT:             redacted prompt + "Sensitive content removed" + [Enhance with redacted] [Cancel]
  BLOCK:              hard block message (no proceed)
  REQUIRE_APPROVAL:   "Sent for admin review" (no proceed)

LOADING view  → inline spinner in sidebar.js
```

### H. New background.js message handlers

| Message | Action |
|---|---|
| `TV_ENTERPRISE_LOGIN_SUCCESS` | Store ent_* tokens, set `_activeMode = "enterprise"`, open MAIN view |
| `TV_ENTERPRISE_LOGOUT` | Call `/backend/auth/logout`, clear ent_* keys, update `_activeMode` |
| `TV_ENTERPRISE_MODE_SWITCH` | Write `velocity_sidebar_flow`, update `_activeMode`, reload panel |
| `TV_ENTERPRISE_ENHANCE` | Call `enterpriseEnhance()`, relay guardrail outcome + stream to panel |

---

## STEP 5 — IMPLEMENT: File change summary (what to write)

### Files to MODIFY (surgical changes only, do not refactor consumer logic):

**`core/storage-keys.js`** — append 9 new `ent_*` keys to `TV.STORAGE_KEYS`

**`core/sidebar-flow.js`** — append 4-state machine class/object and transition helpers after existing `normalizeSidebarFlow`

**`core/token-manager.js`** — add `ensureFreshEnterpriseToken()` function; add `getActiveMode()` hook; existing consumer methods untouched

**`panel/bootstrap.js`** — add `if (flow === 'enterprise')` branch to load enterprise shell; existing consumer branch untouched

**`panel/enterprise/sidebar.js`** — implement: boot sequence, view state controller (AUTH/MAIN/GUARDRAIL/LOADING), mode switcher, pending approval banner

**`background.js`** — add in-memory mode cache init block at top; add 4 new message handler cases

### Files to CREATE:

**`panel/enterprise/enterprise-auth-view.js`** — login form renderer + submit handler (calls `/backend/auth/login`, posts `TV_ENTERPRISE_LOGIN_SUCCESS` to background)

**`panel/enterprise/enterprise-enhance-view.js`** — renders all 6 guardrail outcome states; receives outcome from sidebar.js; fires proceed/cancel callbacks back

**`features/enterprise-enhance-flow.js`** — `enterpriseEnhance(prompt, callbacks)` — guardrail check → route → enhance stream

---

## STEP 6 — VERIFY: Reference documents in the repo

All of these are committed on branch `Production`:

| File | Purpose |
|---|---|
| `docs/superpowers/specs/2026-05-24-enterprise-extension-design.md` | Full design spec with all decisions |
| `GOAL.md` | End-user goal + team test checklist (goals + test cases together) |
| `TEST_CASES.md` | Detailed test cases with steps, expected results, unit test stubs |

Before writing any code, read the design spec. It is the source of truth.

---

## STEP 7 — REFLECT: Key invariants to never violate

1. **Consumer flow is untouched.** No modification to `panel/consumer/`, `features/consumer-enhance-flow.js`, or `features/consumer-clarify-refine.js`. If a change touches those files, stop and reconsider.

2. **Enterprise tokens are namespaced.** Every enterprise storage key starts with `ent_`. Consumer keys have no prefix. They never overlap. This is the isolation guarantee.

3. **Active mode is in-memory in the service worker.** `_activeMode` is the hot-path read. `chrome.storage.local` is the persistence layer. Never read `SIDEBAR_FLOW` from storage on every API call — use `TV.tokenManager.getActiveMode()`.

4. **Guardrail check is never bypassable.** Even on network error, enterprise enhance must NOT proceed silently. Show an error and block. A silent bypass is a security violation.

5. **REQUIRE_APPROVAL is terminal.** Do not add a proceed path. The prompt goes to admin queue. Extension shows status only.

6. **Token refresh is deduplicated.** `_entRefreshPromise` singleton. Two concurrent calls must share one HTTP request. Failing this causes a storage race condition.

---

## First prompt for the new session

Copy-paste this exactly as the first message in the new chat:

---

> I'm continuing work on the Velocity Chrome extension enterprise mode integration. Full context is in `CONTEXT_HANDOFF.md` at the project root `C:\Users\Arjun\Desktop\ThinkVelocity`. Please read that file first, then read `docs/superpowers/specs/2026-05-24-enterprise-extension-design.md`.
>
> Everything has been designed and approved. The design spec, GOAL.md, and TEST_CASES.md are all committed on branch `Production`.
>
> Your first task is to invoke the `superpowers:writing-plans` skill to create a detailed step-by-step implementation plan for Phase 1. The plan should cover every file that needs to be modified or created, in the correct dependency order (e.g. storage-keys before token-manager, token-manager before enhance-flow). After the plan is approved, we will implement file by file.
>
> Do not write any code yet — plan first.

---

## Quick reference: important paths

```
Project root:     C:\Users\Arjun\Desktop\ThinkVelocity\
Extension:        IMPORTANT/Sidebar_extension/
Design spec:      docs/superpowers/specs/2026-05-24-enterprise-extension-design.md
Goal checklist:   GOAL.md
Test cases:       TEST_CASES.md
This file:        CONTEXT_HANDOFF.md

Enterprise server base URL: https://velocityenterprise.toteminteractive.in
Auth login endpoint:        /backend/auth/login
Guardrail endpoint:         /backend/guardrail/check-prompt
Enhance endpoint:           /prompt/enhance/stream
```
