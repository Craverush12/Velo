# Velocity Enterprise Extension — Test Cases

Maps 1:1 to GOAL.md sections. Each test has: prerequisites, steps, expected result, and pass/fail signal.

Manual tests are executable today by loading the unpacked extension in Chrome.  
Unit tests (marked `[UNIT]`) are logic-layer stubs that can be wired to Jest — no browser needed.

---

## Section 1 — Auth

---

### TC-AUTH-01 — Enterprise Login button visible on welcome screen
**Type:** Manual  
**Pre:** Extension installed, user not logged in (or fresh profile)  
**Steps:**
1. Click the Velocity toolbar icon to open the side panel
2. Observe the welcome / sign-up screen

**Expected:** "Enterprise Login" button is visible alongside the consumer sign-up/login options  
**Pass signal:** Button renders, is clickable, has correct label  
**Fail signal:** Button absent, hidden, or overlapped by other elements

---

### TC-AUTH-02 — Clicking Enterprise Login opens inline form (no tab redirect)
**Type:** Manual  
**Pre:** TC-AUTH-01 passing  
**Steps:**
1. Click "Enterprise Login"
2. Observe what happens in the side panel
3. Check Chrome tabs — count should not increase

**Expected:** Login form appears inside the side panel. No new browser tab opens.  
**Pass signal:** Form visible in panel, tab count unchanged  
**Fail signal:** New tab opens, or panel navigates away

---

### TC-AUTH-03 — Login form contains correct fields
**Type:** Manual  
**Pre:** TC-AUTH-02 passing  
**Steps:**
1. Open the enterprise login form
2. Inspect fields present

**Expected:** Email field, Password field, Login button, "Forgot password?" link, "← Back to consumer" link  
**Pass signal:** All 5 elements present and interactive  
**Fail signal:** Any element missing or non-interactive

---

### TC-AUTH-04 — Successful login transitions to enterprise workspace
**Type:** Manual  
**Pre:** Valid enterprise credentials available (registered via web admin)  
**Steps:**
1. Enter valid email and password
2. Click Login

**Expected:** Panel transitions to enterprise main view. Consumer view is not shown.  
**Pass signal:** Enterprise panel header/branding visible, compose/enhance UI present  
**Fail signal:** Consumer panel shown, error state, or infinite loading

---

### TC-AUTH-05 — Wrong password shows inline error
**Type:** Manual  
**Pre:** Enterprise login form open  
**Steps:**
1. Enter valid email, wrong password
2. Click Login

**Expected:** Error message appears inline (e.g. "Invalid email or password"). Form stays open.  
**Pass signal:** Error visible, no panel crash, user can retry  
**Fail signal:** Silent failure, panel crash, or generic unrelated error

---

### TC-AUTH-06 — Wrong email shows inline error
**Type:** Manual  
**Pre:** Enterprise login form open  
**Steps:**
1. Enter an email that does not exist in the enterprise, with any password
2. Click Login

**Expected:** Inline error message. Form stays open.  
**Pass signal:** Error visible  
**Fail signal:** Silent failure or crash

---

### TC-AUTH-07 — Empty fields show validation error before API call
**Type:** Manual  
**Pre:** Enterprise login form open  
**Steps:**
1. Leave email empty, enter a password, click Login
2. Then: enter email, leave password empty, click Login

**Expected:** Client-side validation error on the empty field in both cases. No network request fired.  
**Pass signal:** Error shown, no spinner, network tab shows no outgoing request  
**Fail signal:** Request fired anyway, or no error shown

---

### TC-AUTH-08 — Session persists across panel close/reopen
**Type:** Manual  
**Pre:** TC-AUTH-04 passing (logged in)  
**Steps:**
1. Close the side panel
2. Reopen it via toolbar icon

**Expected:** Enterprise main view shown immediately — no login form  
**Pass signal:** Enterprise panel loads without auth prompt  
**Fail signal:** Login form shown again

---

### TC-AUTH-09 — Session persists across browser restart
**Type:** Manual  
**Pre:** TC-AUTH-04 passing  
**Steps:**
1. Fully close and reopen Chrome
2. Open the side panel

**Expected:** Enterprise panel loads, user still logged in  
**Pass signal:** Enterprise main view shown  
**Fail signal:** Login form shown

---

### TC-AUTH-10 — Logout returns user to enterprise login form
**Type:** Manual  
**Pre:** Logged in to enterprise  
**Steps:**
1. Click logout in the panel header
2. Observe panel state

**Expected:** Enterprise login form shown (not consumer welcome screen)  
**Pass signal:** Enterprise login form visible, consumer panel not shown  
**Fail signal:** Consumer panel shown, or blank state

---

### TC-AUTH-11 — Logout clears all enterprise tokens from storage
**Type:** Manual  
**Pre:** Logged in to enterprise  
**Steps:**
1. Open DevTools → Application → Storage → Extension storage
2. Note ent_* keys present
3. Click logout
4. Re-check storage

**Expected:** All `ent_*` keys removed from storage  
**Pass signal:** No `ent_accessToken`, `ent_refreshToken`, etc. in storage  
**Fail signal:** Any ent_* key remains

---

### TC-AUTH-12 — Expired session shows "Session expired" message
**Type:** Manual  
**Pre:** Logged in to enterprise  
**Steps:**
1. In DevTools → Extension storage, manually delete `ent_refreshToken`
2. Set `ent_accessTokenExpiresAt` to a timestamp in the past
3. Close and reopen the panel OR trigger an enhance

**Expected:** Panel shows "Session expired — please log in again" message, then displays login form  
**Pass signal:** Message visible, login form shown  
**Fail signal:** Silent failure, broken state, consumer panel shown

---

### TC-AUTH-13 — Forgot password opens enterprise web portal in new tab
**Type:** Manual  
**Pre:** Enterprise login form open  
**Steps:**
1. Click "Forgot password?"

**Expected:** New browser tab opens to `https://velocityenterprise.toteminteractive.in/frontend/`  
**Pass signal:** Correct URL opens in new tab  
**Fail signal:** Nothing happens, wrong URL, or navigates panel away

---

### TC-AUTH-14 — Back to consumer returns to consumer panel
**Type:** Manual  
**Pre:** Enterprise login form open (user not yet logged in to enterprise)  
**Steps:**
1. Click "← Back to consumer"

**Expected:** Panel returns to consumer login/welcome screen. `velocity_sidebar_flow` in storage is cleared or set to "consumer".  
**Pass signal:** Consumer panel visible  
**Fail signal:** Enterprise form stays, blank state

---

### TC-AUTH-15 — Dual session: both accounts active simultaneously
**Type:** Manual  
**Pre:** Logged in to consumer account  
**Steps:**
1. Open side panel (consumer mode active)
2. Switch to enterprise mode and log in with enterprise credentials
3. Open DevTools → Extension storage

**Expected:** Both `accessToken` (consumer) and `ent_accessToken` (enterprise) present in storage. Mode switcher visible in panel header.  
**Pass signal:** Both token sets in storage, toggle visible  
**Fail signal:** Consumer tokens wiped, or enterprise login clears consumer session

---

### TC-AUTH-16 — Mode switch does not log out of either account
**Type:** Manual  
**Pre:** TC-AUTH-15 passing  
**Steps:**
1. Click mode switcher to switch from enterprise → consumer
2. Switch back from consumer → enterprise

**Expected:** Both transitions instant. No login forms shown. Storage unchanged.  
**Pass signal:** Both panels load without auth  
**Fail signal:** Any login form shown, tokens missing

---

### `[UNIT]` TC-AUTH-U01 — normalizeSidebarFlow handles all variants
```js
// TV.normalizeSidebarFlow
test("returns 'enterprise' for 'enterprise', 'org', 'b2b'", () => {
  expect(normalizeSidebarFlow("enterprise")).toBe("enterprise");
  expect(normalizeSidebarFlow("ENTERPRISE")).toBe("enterprise");
  expect(normalizeSidebarFlow("org")).toBe("enterprise");
  expect(normalizeSidebarFlow("b2b")).toBe("enterprise");
});
test("returns 'consumer' for anything else", () => {
  expect(normalizeSidebarFlow("consumer")).toBe("consumer");
  expect(normalizeSidebarFlow("")).toBe("consumer");
  expect(normalizeSidebarFlow(null)).toBe("consumer");
  expect(normalizeSidebarFlow(undefined)).toBe("consumer");
  expect(normalizeSidebarFlow("random")).toBe("consumer");
});
```

---

### `[UNIT]` TC-AUTH-U02 — Token expiry check uses 60s buffer
```js
// ensureFreshEnterpriseToken expiry logic
test("token considered fresh if >60s remaining", () => {
  const expiresAt = Date.now() + 120_000; // 2 minutes from now
  expect(isTokenFresh(expiresAt)).toBe(true);
});
test("token considered stale if <60s remaining", () => {
  const expiresAt = Date.now() + 30_000; // 30 seconds from now
  expect(isTokenFresh(expiresAt)).toBe(false);
});
test("token considered stale if already expired", () => {
  const expiresAt = Date.now() - 1000;
  expect(isTokenFresh(expiresAt)).toBe(false);
});
```

---

### `[UNIT]` TC-AUTH-U03 — Refresh deduplication: concurrent calls share one promise
```js
test("two concurrent ensureFresh calls share one refresh promise", async () => {
  const refreshSpy = jest.fn().mockResolvedValue({ accessToken: "new", expiresIn: 900 });
  
  const p1 = ensureFreshEnterpriseToken(/* stale token */, refreshSpy);
  const p2 = ensureFreshEnterpriseToken(/* stale token */, refreshSpy);
  
  await Promise.all([p1, p2]);
  expect(refreshSpy).toHaveBeenCalledTimes(1); // not 2
});
```

---

### `[UNIT]` TC-AUTH-U04 — Session state machine transitions
```js
// sessionState.js
test("enterprise_login_success from CONSUMER_ONLY → BOTH_ACTIVE", () => {
  const state = new SessionStateMachine("CONSUMER_ONLY");
  state.transition("enterprise_login_success");
  expect(state.current).toBe("BOTH_ACTIVE");
});
test("enterprise_logout from BOTH_ACTIVE → CONSUMER_ONLY", () => {
  const state = new SessionStateMachine("BOTH_ACTIVE");
  state.transition("enterprise_logout");
  expect(state.current).toBe("CONSUMER_ONLY");
});
test("ent_refresh_fail from ENTERPRISE_ONLY → clears ent tokens", () => {
  const state = new SessionStateMachine("ENTERPRISE_ONLY");
  state.transition("ent_refresh_fail");
  expect(state.current).toBe("AUTH_REQUIRED");
});
test("ent_refresh_fail from BOTH_ACTIVE → CONSUMER_ONLY", () => {
  const state = new SessionStateMachine("BOTH_ACTIVE");
  state.transition("ent_refresh_fail");
  expect(state.current).toBe("CONSUMER_ONLY");
});
```

---

## Section 2 — Enhance (Enterprise)

---

### TC-ENH-01 — Clean prompt enhances immediately with no extra steps
**Type:** Manual  
**Pre:** Logged in to enterprise, a guardrail-safe prompt ready  
**Steps:**
1. Type a safe prompt (e.g. "Write a product description for running shoes")
2. Click Enhance

**Expected:** Guardrail check fires silently, enhancement streams immediately. No warning overlay, no modal.  
**Pass signal:** Output streams in, no interruption  
**Fail signal:** Unexpected warning, timeout, or no output

---

### TC-ENH-02 — Warned prompt shows reason and Proceed/Cancel options
**Type:** Manual  
**Pre:** Logged in, access to a prompt that triggers WARN on the enterprise guardrail  
**Steps:**
1. Submit a prompt that matches a WARN-level guardrail rule
2. Observe the panel

**Expected:** Warning banner appears with the violation reason. Two buttons visible: "Proceed anyway" and "Cancel".  
**Pass signal:** Banner visible with reason text, both buttons present  
**Fail signal:** Enhancement proceeds without warning, or hard block instead of warn

---

### TC-ENH-03 — Proceeding after warning enhances successfully
**Type:** Manual  
**Pre:** TC-ENH-02 — warning banner visible  
**Steps:**
1. Click "Proceed anyway"

**Expected:** Enhancement streams normally  
**Pass signal:** Output visible  
**Fail signal:** No output, error state

---

### TC-ENH-04 — Cancelling a warned prompt returns to composer
**Type:** Manual  
**Pre:** TC-ENH-02 — warning banner visible  
**Steps:**
1. Click "Cancel"

**Expected:** Warning dismissed, original prompt still in the composer, no enhancement  
**Pass signal:** Composer visible with original text, no output pane  
**Fail signal:** Prompt lost, blank state, or enhancement proceeds

---

### TC-ENH-05 — REQUIRE_CONFIRMATION shows modal before enhancing
**Type:** Manual  
**Pre:** Prompt that triggers REQUIRE_CONFIRMATION guardrail rule  
**Steps:**
1. Submit the prompt
2. Observe panel

**Expected:** Confirmation modal appears. Enhance does not start yet.  
**Pass signal:** Modal visible, no streaming output yet  
**Fail signal:** Enhancement starts without confirmation

---

### TC-ENH-06 — Confirming the modal enhances
**Type:** Manual  
**Pre:** TC-ENH-05 — confirmation modal visible  
**Steps:**
1. Click "Confirm"

**Expected:** Enhancement streams  
**Pass signal:** Output visible  
**Fail signal:** Nothing happens

---

### TC-ENH-07 — Redacted prompt shows cleaned version in composer
**Type:** Manual  
**Pre:** Prompt that triggers REDACT guardrail rule  
**Steps:**
1. Submit a prompt containing content that would be redacted
2. Observe panel

**Expected:** Panel shows the redacted version of the prompt with message "Sensitive content was removed". Two options: "Enhance with redacted" and "Cancel".  
**Pass signal:** Redacted text visible, original sensitive portion absent, both buttons present  
**Fail signal:** Original prompt shown unchanged, hard block instead of redact

---

### TC-ENH-08 — Enhancing with redacted prompt uses the cleaned text
**Type:** Manual  
**Pre:** TC-ENH-07 — redacted prompt shown  
**Steps:**
1. Click "Enhance with redacted"

**Expected:** Enhancement runs using the redacted (cleaned) prompt, not the original  
**Pass signal:** Output does not include the redacted content  
**Fail signal:** Original sensitive content appears in output

---

### TC-ENH-09 — Blocked prompt shows hard block, no enhance path
**Type:** Manual  
**Pre:** Prompt that triggers BLOCK guardrail rule  
**Steps:**
1. Submit the prompt
2. Observe panel

**Expected:** Hard block message shown (e.g. "This prompt violates company policy"). No "Proceed" option present.  
**Pass signal:** Block message visible, no proceed button, no enhancement  
**Fail signal:** Proceed button shown, enhancement runs, or silent failure

---

### TC-ENH-10 — REQUIRE_APPROVAL shows "Sent for admin review" state
**Type:** Manual  
**Pre:** Prompt that triggers REQUIRE_APPROVAL guardrail rule  
**Steps:**
1. Submit the prompt
2. Observe panel

**Expected:** "Sent for admin review" message shown. No enhance path. No error.  
**Pass signal:** Approval pending message visible  
**Fail signal:** Block message shown (wrong state), enhancement proceeds, or error

---

### TC-ENH-11 — Pending admin review persists across panel close/reopen
**Type:** Manual  
**Pre:** TC-ENH-10 passing — approval pending state shown  
**Steps:**
1. Close the side panel
2. Reopen it

**Expected:** "Awaiting admin review" banner visible in enterprise main panel  
**Pass signal:** Banner present on reopen  
**Fail signal:** Banner gone, no record of pending approval

---

### TC-ENH-12 — Enhancement output streams (not a single block load)
**Type:** Manual  
**Pre:** Logged in, clean prompt ready  
**Steps:**
1. Submit a long prompt for enhancement
2. Watch the output area

**Expected:** Text appears incrementally as the stream arrives — not all at once after a delay  
**Pass signal:** Visible streaming effect  
**Fail signal:** Long blank pause then full text appears

---

### TC-ENH-13 — Network failure on guardrail check shows retry option
**Type:** Manual  
**Pre:** Logged in. Simulate network failure (DevTools → Network → Offline)  
**Steps:**
1. Set network to offline
2. Submit a prompt for enhancement

**Expected:** Friendly error message shown (e.g. "Could not check prompt policy — check your connection"). Retry button or ability to try again.  
**Pass signal:** Error message and retry path visible  
**Fail signal:** Crash, blank state, or silent hang

---

### TC-ENH-14 — Network failure after guardrail pass (during enhance) shows retry
**Type:** Manual  
**Pre:** Logged in. Intercept the enhance stream specifically.  
**Steps:**
1. Allow the guardrail check to pass (online)
2. Cut network just as the enhance stream starts
3. Observe panel

**Expected:** Friendly error shown. User can try enhancing again.  
**Pass signal:** Error visible, composer still has prompt  
**Fail signal:** Partial output stuck, crash, or prompt lost

---

### `[UNIT]` TC-ENH-U01 — Guardrail decision router dispatches all 6 outcomes
```js
// enterprise-enhance-flow.js routing logic
const outcomes = ["ALLOW","WARN","REQUIRE_CONFIRMATION","REDACT","BLOCK","REQUIRE_APPROVAL"];

outcomes.forEach(decision => {
  test(`routes ${decision} to correct callback`, async () => {
    const callbacks = {
      onWarning: jest.fn(),
      onConfirm: jest.fn(),
      onRedact: jest.fn(),
      onBlock: jest.fn(),
      onApproval: jest.fn(),
      onStream: jest.fn(),
    };
    const mockGuardrail = jest.fn().mockResolvedValue({ decision, queueId: null, redactedPrompt: null });
    const mockEnhance = jest.fn().mockResolvedValue(null);

    await routeGuardrailDecision({ decision }, "prompt", callbacks, mockEnhance);

    switch (decision) {
      case "ALLOW":                expect(mockEnhance).toHaveBeenCalled(); break;
      case "WARN":                 expect(callbacks.onWarning).toHaveBeenCalled(); break;
      case "REQUIRE_CONFIRMATION": expect(callbacks.onConfirm).toHaveBeenCalled(); break;
      case "REDACT":               expect(callbacks.onRedact).toHaveBeenCalled(); break;
      case "BLOCK":                expect(callbacks.onBlock).toHaveBeenCalled(); break;
      case "REQUIRE_APPROVAL":     expect(callbacks.onApproval).toHaveBeenCalled(); break;
    }
  });
});
```

---

### `[UNIT]` TC-ENH-U02 — REQUIRE_APPROVAL writes ent_pendingApproval to storage
```js
test("approval outcome stores queueId and excerpt", async () => {
  const storageMock = { set: jest.fn() };
  const guardrailResult = { decision: "REQUIRE_APPROVAL", queueId: "99", prompt: "test prompt" };

  await handleApprovalQueue(guardrailResult, storageMock);

  expect(storageMock.set).toHaveBeenCalledWith(
    expect.objectContaining({
      ent_pendingApproval: expect.objectContaining({
        queueId: "99",
        promptExcerpt: expect.any(String),
        submittedAt: expect.any(Number),
      })
    })
  );
});
```

---

### `[UNIT]` TC-ENH-U03 — REDACT passes redactedPrompt (not original) to enhance
```js
test("enhance called with redactedPrompt on REDACT decision", async () => {
  const enhanceFn = jest.fn();
  const callbacks = { onRedact: (redacted, proceedFn) => proceedFn(redacted) };
  const guardrailResult = { decision: "REDACT", redactedPrompt: "cleaned version" };

  await routeGuardrailDecision(guardrailResult, "original dirty prompt", callbacks, enhanceFn);

  expect(enhanceFn).toHaveBeenCalledWith("cleaned version", expect.anything());
  expect(enhanceFn).not.toHaveBeenCalledWith("original dirty prompt", expect.anything());
});
```

---

## Section 3 — Mode Experience

---

### TC-MODE-01 — Enterprise panel has distinct branding from consumer
**Type:** Manual  
**Pre:** Logged in to enterprise  
**Steps:**
1. Open enterprise panel
2. Open consumer panel in a different Chrome profile (or compare screenshots)

**Expected:** Enterprise panel header/theme visually distinct (different label, colour, or logo treatment)  
**Pass signal:** Clear visual difference  
**Fail signal:** Identical appearance

---

### TC-MODE-02 — Mode switch is one click and instant
**Type:** Manual  
**Pre:** Both sessions active (TC-AUTH-15 passing)  
**Steps:**
1. In enterprise panel, click mode switcher toggle
2. Measure / observe transition time

**Expected:** Consumer panel loads in under 300ms. No loading spinner for the mode switch itself.  
**Pass signal:** Near-instant transition  
**Fail signal:** >1s delay, spinner, or broken state

---

### TC-MODE-03 — Mode switch does not log out of either account
**Type:** Manual  
**Pre:** TC-AUTH-15 passing  
**Steps:**
1. Switch enterprise → consumer → enterprise
2. After each switch, check DevTools storage

**Expected:** Both `accessToken` and `ent_accessToken` present in storage throughout  
**Pass signal:** No tokens removed during switching  
**Fail signal:** Either token set disappears

---

### TC-MODE-04 — Active mode remembered across browser restart
**Type:** Manual  
**Pre:** Mode set to enterprise  
**Steps:**
1. Fully close Chrome
2. Reopen, click Velocity toolbar icon

**Expected:** Enterprise panel loads (not consumer)  
**Pass signal:** Enterprise panel shown on first open  
**Fail signal:** Consumer panel shown, mode reset

---

### TC-MODE-05 — Mode switcher only visible when both sessions active
**Type:** Manual  
**Pre:** Only enterprise session active (no consumer login)  
**Steps:**
1. Open enterprise panel, look for mode switcher toggle

**Expected:** No mode switcher shown (single session, nothing to switch to)  
**Pass signal:** Toggle absent  
**Fail signal:** Toggle present but non-functional, or broken layout

---

## Section 4 — Edge Cases

---

### TC-EDGE-01 — Fresh install lands on login form (not broken state)
**Type:** Manual  
**Pre:** Clean Chrome profile, extension just installed  
**Steps:**
1. Open side panel

**Expected:** Welcome / sign-up screen shown. No JS errors in DevTools console.  
**Pass signal:** Welcome screen renders cleanly  
**Fail signal:** Blank panel, console errors, crash

---

### TC-EDGE-02 — Enterprise panel cold start with no tokens lands on login form
**Type:** Manual  
**Pre:** Extension installed, `velocity_sidebar_flow` manually set to "enterprise" in storage, no ent_* tokens  
**Steps:**
1. Open side panel

**Expected:** Enterprise login form shown immediately  
**Pass signal:** Login form rendered  
**Fail signal:** Blank state, error, consumer panel shown

---

### TC-EDGE-03 — Consumer mode unaffected by enterprise session
**Type:** Manual  
**Pre:** Both sessions active  
**Steps:**
1. Switch to consumer mode
2. Run a consumer enhance (e.g. on ChatGPT)
3. Verify it uses the consumer API, not the enterprise endpoint

**Expected:** Consumer enhance uses `thinkvelocity.in` API, not `velocityenterprise.toteminteractive.in`  
**Pass signal:** DevTools Network shows consumer endpoint called  
**Fail signal:** Enterprise endpoint called in consumer mode

---

### TC-EDGE-04 — Consumer mode works for users who never used enterprise
**Type:** Manual  
**Pre:** Fresh install, consumer login only  
**Steps:**
1. Log in as consumer
2. Use all consumer features normally

**Expected:** All consumer features work exactly as before. No enterprise-related errors.  
**Pass signal:** No regressions in consumer flow  
**Fail signal:** Any consumer feature broken, enterprise-related errors in console

---

### TC-EDGE-05 — Guardrail endpoint unreachable defaults to safe fallback
**Type:** Manual  
**Pre:** Logged in to enterprise. Block `velocityenterprise.toteminteractive.in` in DevTools or hosts.  
**Steps:**
1. Submit a prompt for enhancement

**Expected:** Friendly error shown: "Could not check prompt policy — check your connection." No silent failure, no enhancement proceeding without guardrail check.  
**Pass signal:** Error shown, enhancement blocked until connectivity restored  
**Fail signal:** Enhancement proceeds without guardrail check (security risk), or silent hang

---

### TC-EDGE-06 — Very long prompt is handled without truncation errors
**Type:** Manual  
**Pre:** Logged in to enterprise  
**Steps:**
1. Paste a 3000+ word prompt
2. Submit for enhancement

**Expected:** Guardrail check and enhancement both succeed (or fail gracefully with a clear message)  
**Pass signal:** No JS error, no silent truncation  
**Fail signal:** Crash, empty output, console error

---

### `[UNIT]` TC-EDGE-U01 — Storage key prefix isolation: ent_ keys never collide with consumer keys
```js
test("ent_ prefix keys do not overlap with consumer key names", () => {
  const consumerKeys = Object.values(TV.STORAGE_KEYS).filter(k => !k.startsWith("ent_"));
  const enterpriseKeys = Object.values(TV.STORAGE_KEYS).filter(k => k.startsWith("ent_"));

  const overlap = consumerKeys.filter(k => enterpriseKeys.includes(k));
  expect(overlap).toHaveLength(0);
});
```

---

### `[UNIT]` TC-EDGE-U02 — Active mode in-memory cache initialises from storage on startup
```js
test("_activeMode reads from storage on init, not hardcoded to consumer", async () => {
  const storageMock = { [TV.STORAGE_KEYS.SIDEBAR_FLOW]: "enterprise" };
  const mode = await initActiveModeFromStorage(storageMock);
  expect(mode).toBe("enterprise");
});
test("_activeMode defaults to consumer when storage key absent", async () => {
  const storageMock = {};
  const mode = await initActiveModeFromStorage(storageMock);
  expect(mode).toBe("consumer");
});
```

---

## Test Execution Checklist

Use this before every release candidate:

| Section | Manual Tests | Unit Tests |
|---|---|---|
| Auth | TC-AUTH-01 → TC-AUTH-16 | TC-AUTH-U01 → TC-AUTH-U04 |
| Enhance | TC-ENH-01 → TC-ENH-14 | TC-ENH-U01 → TC-ENH-U03 |
| Mode Experience | TC-MODE-01 → TC-MODE-05 | — |
| Edge Cases | TC-EDGE-01 → TC-EDGE-06 | TC-EDGE-U01 → TC-EDGE-U02 |

**Total:** 35 manual tests · 9 unit test suites

---

## Known Gaps (to address in Phase 2)

- No automated E2E tests (Puppeteer + chrome-extension testing harness)
- No load tests for guardrail endpoint under concurrent enhance calls
- No test for admin-side approval flow (out of extension scope, lives on web frontend)
- Context Packs, Collections, Teams — no tests until Phase 2 implementation
