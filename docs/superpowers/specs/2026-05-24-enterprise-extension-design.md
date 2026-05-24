# Enterprise Mode — Chrome Extension Design Spec
**Date:** 2026-05-24  
**Status:** Approved  
**Scope:** Phase 1 — Enterprise auth integration + guardrail-aware enhance pipeline

---

## 1. Context

The Velocity Chrome extension currently supports a single consumer (B2C) mode. This spec defines how to add an enterprise (B2B) mode that connects to the enterprise server at `https://velocityenterprise.toteminteractive.in`.

### Enterprise Server Stack (mapped from live server)

| Layer | URL Path | Port | Tech |
|---|---|---|---|
| NestJS backend | `/backend/` | 3000 | Auth, users, guardrails, teams, audit |
| FastAPI Python | `/prompt/` | 3002 | Enhancement, content moderation |
| React frontend | `/frontend/` | 8081 | Admin web UI (not used by extension) |

### Enterprise-specific features (available via API)
- **Guardrails** — org-level prompt moderation: ALLOW / WARN / REDACT / BLOCK / REQUIRE_CONFIRMATION / REQUIRE_APPROVAL
- **GuardrailApprovalQueue** — blocked prompts routed to admin review
- **Context Packs** — org-uploaded files that feed enterprise prompt context
- **Prompt Collections** — org-scoped saved prompt library
- **Teams + RBAC** — ADMIN / SUBADMIN / USER roles with 15 granular permissions
- **Audit Logs** — every action logged per enterprise
- **Policy Governance** — rule toggle states per scope

### Out of scope for Phase 1
Context Packs, Prompt Collections, Teams UI, Audit Logs, Analytics — these are Phase 2+ features. Phase 1 focuses exclusively on auth integration and the guardrail-aware enhance pipeline.

---

## 2. Core Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Enterprise registration | Web only (admin registers on web frontend) | Multi-field onboarding unsuitable for extension |
| Enterprise login UX | Inline form in side panel | No OAuth dance required; avoids dependency on web frontend bridge |
| Dual session storage | Parallel namespaced keys (`ent_*` / `con_*`) | Allows instant mode switch without re-auth |
| Active mode cache | In-memory variable in service worker | Avoids async storage I/O on every token resolve |
| Token refresh | Singleton in-flight promise (dedup) | Prevents race condition on concurrent enhance calls |
| Guardrail pipeline | Full 6-outcome DAG | All DecisionActionType values from NestJS schema handled |

---

## 3. File Structure Changes

```
IMPORTANT/Sidebar_extension/
├── core/
│   ├── storage-keys.js          MODIFY — add ent_* key constants
│   ├── sidebar-flow.js          MODIFY — add 4-state machine + transition helpers
│   └── token-manager.js         MODIFY — mode-aware prefix, enterprise refresh dedup
├── panel/
│   ├── bootstrap.js             MODIFY — route to enterprise shell on SIDEBAR_FLOW=enterprise
│   ├── consumer/                UNTOUCHED
│   └── enterprise/
│       ├── sidebar.html         EXISTS (shell) — wire up
│       ├── sidebar.js           EXISTS (shell) — implement state controller
│       ├── enterprise-auth-view.js      NEW
│       └── enterprise-enhance-view.js   NEW
├── features/
│   └── enterprise-enhance-flow.js       NEW
└── background.js                MODIFY — in-memory mode cache + enterprise message handlers
```

**Key invariant:** Consumer and enterprise tokens live under separate namespaces. Switching modes never deletes the other session's tokens. The consumer enhance flow is untouched.

---

## 4. Storage Keys

### New keys added to `TV.STORAGE_KEYS`

```js
// Enterprise session
ENT_ACCESS_TOKEN:     "ent_accessToken",
ENT_REFRESH_TOKEN:    "ent_refreshToken",
ENT_ACCESS_EXP:       "ent_accessTokenExpiresAt",
ENT_USER_ID:          "ent_userId",
ENT_ENTERPRISE_ID:    "ent_enterpriseId",
ENT_USER_NAME:        "ent_userName",
ENT_USER_EMAIL:       "ent_userEmail",
ENT_ROLE_TYPES:       "ent_roleTypes",

// Pending guardrail approval (persisted across panel close/reopen)
ENT_PENDING_APPROVAL: "ent_pendingApproval",
// shape: { queueId, promptExcerpt, submittedAt } | null
```

Existing consumer keys (`accessToken`, `refreshToken`, etc.) are unchanged.

---

## 5. Session State Machine

### States

| State | Description |
|---|---|
| `CONSUMER_ONLY` | Consumer tokens valid, enterprise tokens absent |
| `ENTERPRISE_ONLY` | Enterprise tokens valid, consumer tokens absent |
| `BOTH_ACTIVE` | Both sessions valid simultaneously |
| `SWITCHING` | Transient during mode flip (in-memory only) |

### Transitions

```
any state           + enterprise_login_success  → ENTERPRISE_ONLY or BOTH_ACTIVE
BOTH_ACTIVE         + enterprise_logout         → CONSUMER_ONLY
BOTH_ACTIVE         + consumer_logout           → ENTERPRISE_ONLY
ENTERPRISE_ONLY     + ent_refresh_fail          → show inline AUTH view (ent tokens cleared)
BOTH_ACTIVE         + ent_refresh_fail          → CONSUMER_ONLY + "Enterprise session expired" banner
```

---

## 6. Auth Flow

### Sign-up modal change

The existing welcome/sign-up view gains one new button: **"Enterprise Login"**. Clicking it:
1. Writes `velocity_sidebar_flow = "enterprise"` to storage
2. Re-renders panel into enterprise shell
3. Shows `AUTH` view (inline login form)

### Enterprise login form (`enterprise-auth-view.js`)

```
┌──────────────────────────────────────┐
│  Velocity Enterprise                 │
│                                      │
│  Email _____________________________│
│  Password __________________________│
│                                      │
│  [ Login ]                           │
│                                      │
│  Forgot password? →                  │  opens /frontend/ in new tab
│  ← Back to consumer login            │  clears ent flow, returns consumer panel
└──────────────────────────────────────┘
```

### Login API call

```
POST https://velocityenterprise.toteminteractive.in/backend/auth/login
Body: { email, password }

Response: {
  accessToken,
  refreshToken,
  expiresIn,          // 900 (15 minutes)
  user: { id, enterpriseId, name, email, roleTypes }
}
```

### On login success — storage writes

```js
chrome.storage.local.set({
  ent_accessToken:          accessToken,
  ent_refreshToken:         refreshToken,
  ent_accessTokenExpiresAt: Date.now() + expiresIn * 1000,
  ent_userId:               user.id,
  ent_enterpriseId:         user.enterpriseId,
  ent_userName:             user.name,
  ent_userEmail:            user.email,
  ent_roleTypes:            user.roleTypes,
  velocity_sidebar_flow:    "enterprise"
})
// update in-memory cache in service worker
_activeMode = "enterprise"
```

### Token refresh

Enterprise access tokens expire in 15 minutes. Refresh is lazy (triggered before any API call).

```
ensureFreshEnterpriseToken():
  if (_entRefreshPromise) return _entRefreshPromise        // dedup concurrent calls
  if (ent_accessTokenExpiresAt - now > 60_000) return stored token  // still fresh (>1min buffer)

  _entRefreshPromise = POST /backend/auth/refresh { refreshToken: ent_refreshToken }
    on success → store ent_accessToken + ent_accessTokenExpiresAt
    on 401     → clear all ent_* tokens → transition to ENTERPRISE_LOGGED_OUT → show AUTH view
    finally    → _entRefreshPromise = null
```

### Logout

```
POST /backend/auth/logout
  Authorization: Bearer ent_accessToken
  Body: { refreshToken: ent_refreshToken }

Then: chrome.storage.local.remove(all ent_* keys)
      _activeMode = "consumer" (if con_ tokens exist) or "none"
```

---

## 7. Guardrail + Enhance Pipeline

### Full DAG

```
User submits prompt
  │
  ▼
[1] ensureFreshEnterpriseToken()
  │
  ▼
[2] POST /backend/guardrail/check-prompt
    { prompt, contentType: "CHAT_PROMPT", enterpriseId }
    Authorization: Bearer ent_accessToken
  │
  ├── ALLOW ──────────────────────────────────────────────► [E] stream enhance
  │
  ├── WARN
  │     show: warning banner with violation reason
  │     [ Proceed anyway ] → ────────────────────────────► [E] stream enhance
  │     [ Cancel ]         → back to composer
  │
  ├── REQUIRE_CONFIRMATION
  │     show: confirmation modal
  │     [ Confirm ] ──────────────────────────────────────► [E] stream enhance
  │     [ Cancel ]  → back to composer
  │
  ├── REDACT
  │     show: redacted prompt text in composer
  │     message: "Sensitive content was removed"
  │     [ Enhance with redacted ] ──────────────────────► [E] stream enhance (redacted text)
  │     [ Cancel ] → back to composer
  │
  ├── BLOCK (terminal)
  │     show: hard block UI
  │     message: "This prompt violates company policy"
  │     No enhance path. Store queueId if returned.
  │
  └── REQUIRE_APPROVAL (terminal)
        POST to GuardrailApprovalQueue handled by backend
        Store: ent_pendingApproval = { queueId, promptExcerpt, submittedAt }
        Show: "Sent for admin review" state
        No enhance path now.

[E] POST /prompt/enhance/stream
    { prompt, enterpriseId, userId, ... }
    Authorization: Bearer ent_accessToken
    (SSE streaming response — same handler as consumer stream)
```

### `enterprise-enhance-flow.js` interface

```js
async function enterpriseEnhance(prompt, callbacks) {
  // callbacks: {
  //   onWarning(guardrail, proceedFn),
  //   onConfirm(guardrail, proceedFn),
  //   onRedact(redactedPrompt, enhanceFn),
  //   onBlock(guardrail),
  //   onApproval(guardrail),
  //   onStream(chunk),
  //   onComplete(fullText),
  //   onError(err)
  // }
}
```

The callback pattern keeps UI concerns out of the flow file. `enterprise-enhance-view.js` owns all rendering; `enterprise-enhance-flow.js` owns all API logic.

---

## 8. Panel UI State Management

### View states (owned by `enterprise/sidebar.js`)

| View | File | Condition |
|---|---|---|
| `AUTH` | `enterprise-auth-view.js` | No valid enterprise tokens |
| `MAIN` | inline in `sidebar.js` | Valid tokens, idle |
| `GUARDRAIL` | `enterprise-enhance-view.js` | Guardrail outcome pending user action |
| `LOADING` | inline spinner | Token refresh or guardrail check in-flight |

### Boot sequence

```
bootstrap.js reads velocity_sidebar_flow
  → "enterprise" → load enterprise/sidebar.js

enterprise/sidebar.js on init:
  1. Read ent_accessToken + ent_accessTokenExpiresAt
  2. Token absent or expired (no refresh token) → render AUTH view
  3. Token present (or refreshable)             → render MAIN view
  4. After MAIN render: check ent_pendingApproval
     → present → show "Awaiting admin review" banner
```

### Mode switcher (BOTH_ACTIVE state only)

A toggle appears in the enterprise panel header only when both sessions are active:

```
[ Consumer ←→ Enterprise ]  logout
```

Switching:
1. Writes new `velocity_sidebar_flow` to storage
2. Updates `_activeMode` in service worker memory
3. Reloads panel via `bootstrap.js`
4. No token data is modified

---

## 9. Background.js Changes

### In-memory mode cache

```js
// Initialised once on service worker startup
let _activeMode = TV.SidebarFlow.CONSUMER;
let _entRefreshPromise = null;

chrome.storage.local.get(TV.STORAGE_KEYS.SIDEBAR_FLOW, (r) => {
  _activeMode = TV.normalizeSidebarFlow(r[TV.STORAGE_KEYS.SIDEBAR_FLOW]);
});

// Updated on every mode switch message
TV.tokenManager.getActiveMode = () => _activeMode;
```

### New message handlers

| Message type | Handler |
|---|---|
| `TV_ENTERPRISE_LOGIN_SUCCESS` | Store ent_* tokens, update `_activeMode`, open MAIN view |
| `TV_ENTERPRISE_LOGOUT` | Call logout API, clear ent_* keys, update `_activeMode` |
| `TV_ENTERPRISE_MODE_SWITCH` | Update `velocity_sidebar_flow`, update `_activeMode`, reload panel |
| `TV_ENTERPRISE_ENHANCE` | Call `enterpriseEnhance()`, relay guardrail outcome + stream back to panel |

---

## 10. API Reference (Enterprise Server)

### Auth endpoints (`/backend/auth/`)
| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/login` | None | Email + password login |
| POST | `/refresh` | None | Refresh access token |
| POST | `/logout` | Bearer | Invalidate tokens |
| POST | `/forgot-password` | None | Trigger reset email |

### Guardrail endpoint
| Method | Path | Auth | Body |
|---|---|---|---|
| POST | `/backend/guardrail/check-prompt` | Bearer | `{ prompt, contentType, enterpriseId }` |

Response shape:
```json
{
  "allowed": true | false,
  "decision": "ALLOW" | "WARN" | "REDACT" | "BLOCK" | "REQUIRE_CONFIRMATION" | "REQUIRE_APPROVAL",
  "queueId": "string | null",
  "violations": [...],
  "redactedPrompt": "string | null"
}
```

### Enhance endpoint
| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/prompt/enhance/stream` | Bearer | SSE streaming, same shape as consumer |

---

## 11. What Is Not Changing

- `features/consumer-enhance-flow.js` — untouched
- `features/consumer-clarify-refine.js` — untouched
- `panel/consumer/` — all files untouched
- `api/enhance.py`, `api/refine.py` — consumer Python backend untouched
- Manifest permissions — no new permissions needed
- Consumer token storage keys — untouched, no migration required
