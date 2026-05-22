# Refine API Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the extension's clarify/refine flow to the new `api.thinkvelocity.in` endpoints (`/refine/prepare` and `/refine/finalize`), replacing the old `/dev/test/clarify` and `/dev/test/refine` routes.

**Architecture:** Three surgical file edits in a coordinated chain. The API layer (`consumer-clarify-refine.js`) gets new URLs and request/response mapping. The view (`suggestions-view.js`) is updated to pass both `original` and `enhanced` prompts. The background message handler (`background.js`) forwards both fields to the API layer. No new files, no UI changes, no manifest changes.

**Tech Stack:** Chrome Extension (Manifest V3), Vanilla JS (IIFE modules), `chrome.runtime.sendMessage`, Fetch API, `chrome.storage.local`

---

## File Map

| File | Change |
|------|--------|
| `IMPORTANT/Sidebar_extension/features/consumer-clarify-refine.js` | New URLs, new request bodies, updated `normaliseQuestions`, module-level `_prepareState`, auth via Bearer header |
| `IMPORTANT/Sidebar_extension/panel/consumer/suggestions-view.js` | Line ~795: send `{ original, enhanced }` instead of `{ prompt }` in `TV_CONSUMER_CLARIFY` message |
| `IMPORTANT/Sidebar_extension/background.js` | Line ~1334: forward `payload.original` + `payload.enhanced` to `clarify()` |

---

## Task 1: Update `consumer-clarify-refine.js` — URLs, `_prepareState`, and `clarify()`

**Files:**
- Modify: `IMPORTANT/Sidebar_extension/features/consumer-clarify-refine.js:1-30` (constants + new state)
- Modify: `IMPORTANT/Sidebar_extension/features/consumer-clarify-refine.js:65-100` (`clarify` function)
- Modify: `IMPORTANT/Sidebar_extension/features/consumer-clarify-refine.js:31-63` (`normaliseQuestions`)

### Context

The file currently opens with these constants:

```js
const FASTAPI_BASE    = "https://api.thinkvelocity.in/dev/test";
const BACKEND_URL     = "https://thinkvelocity.in/backend-V1-D";
const CLARIFY_URL     = `${FASTAPI_BASE}/clarify`;
const REFINE_URL      = `${FASTAPI_BASE}/refine`;
const REFINE_SAVE_URL = `${BACKEND_URL}/prompt/refine-prompt`;
const FEEDBACK_URL    = `${BACKEND_URL}/prompt/insert-feedback`;
const REVIEWS_URL     = `${BACKEND_URL}/reviews`;
```

And `clarify(prompt)` POSTs `{ prompt, user_id, auth_token }` to `CLARIFY_URL`.

- [ ] **Step 1: Replace the URL constants and add `_prepareState`**

Open `IMPORTANT/Sidebar_extension/features/consumer-clarify-refine.js`.

Replace the block that begins `const FASTAPI_BASE` and ends `const REVIEWS_URL` (lines 13–19 in the current file) with:

```js
const _API_BASE       = "https://api.thinkvelocity.in";
const BACKEND_URL     = "https://thinkvelocity.in/backend-V1-D";
const PREPARE_URL     = `${_API_BASE}/refine/prepare`;
const FINALIZE_URL    = `${_API_BASE}/refine/finalize`;
const REFINE_SAVE_URL = `${BACKEND_URL}/prompt/refine-prompt`;
const FEEDBACK_URL    = `${BACKEND_URL}/prompt/insert-feedback`;
const REVIEWS_URL     = `${BACKEND_URL}/reviews`;

/** State carried from the most recent prepare call into the finalize call. */
let _prepareState = { neuro_state: null, context_patterns: [] };
```

- [ ] **Step 2: Replace `normaliseQuestions` to handle the new response shape**

The current `normaliseQuestions(json)` handles MCQ format (`mcq_questions[].question_text`). The new `/refine/prepare` response returns `{ questions: [{id, question, options}] }` directly. Replace the entire `normaliseQuestions` function (currently lines 32–63) with the version below, which handles the new shape first and falls back to the old shape:

```js
// Normalise prepare/clarify response into [{ id, question, options }]
function normaliseQuestions(json) {
  // New format: { questions: [{ id, question, options }] }
  const newList = json.questions || (json.data && json.data.questions);
  if (Array.isArray(newList) && newList.length && typeof newList[0].question === "string") {
    return newList.map((q, i) => ({
      id: q.id != null ? q.id : i,
      question: q.question || "",
      options: Array.isArray(q.options) ? q.options : [],
    }));
  }

  // Legacy format A: { mcq_questions: [{ question_text, answer_options }] }
  const mcqList = json.mcq_questions || (json.data && json.data.mcq_questions);
  if (Array.isArray(mcqList) && mcqList.length) {
    return mcqList.map((q, i) => ({
      id: q.question_id || i,
      question: q.question_text || q.question || "",
      options: Array.isArray(q.answer_options) ? q.answer_options : [],
    }));
  }

  // Legacy format B: { questions: ["q1","q2"], options: [["a","b"],["c","d"]] }
  const rawQs   = (json.data && json.data.questions) || [];
  const rawOpts = (json.data && json.data.options)   || null;
  if (Array.isArray(rawQs) && rawQs.length && typeof rawQs[0] === "string" && Array.isArray(rawOpts)) {
    return rawQs.map((text, i) => ({
      id: i,
      question: text,
      options: Array.isArray(rawOpts[i]) ? rawOpts[i] : [],
    }));
  }

  return [];
}
```

- [ ] **Step 3: Replace the `clarify` function**

Find the current `async function clarify(prompt)` (starts around line 65) and replace the entire function with:

```js
async function clarify(original, enhanced) {
  const promptText = String(original || "").trim();
  if (!promptText) {
    return { success: false, error: "Prompt is required" };
  }

  // Reset prepare state so a stale neuro_state is never sent on a subsequent refine.
  _prepareState = { neuro_state: null, context_patterns: [] };

  try {
    const { userId, accessToken } = await getAuth();
    const body = {
      original_prompt: promptText,
      user_id: userId,
    };
    const enhancedText = String(enhanced || "").trim();
    if (enhancedText) {
      body.previous_enhanced_prompt = enhancedText;
    }

    const headers = { "Content-Type": "application/json" };
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

    const res = await fetch(PREPARE_URL, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      return { success: false, error: json.message || json.detail || json.error || `HTTP ${res.status}` };
    }

    // Persist prepare context for the upcoming finalize call.
    _prepareState = {
      neuro_state:      json.neuro_state      || null,
      context_patterns: json.context_patterns || [],
    };

    const questions = normaliseQuestions(json);
    return { success: true, data: { questions } };
  } catch (err) {
    return { success: false, error: err.message || String(err) };
  }
}
```

- [ ] **Step 4: Verify the file saves without syntax errors**

Open a terminal in the project root and run:

```bash
node --check "IMPORTANT/Sidebar_extension/features/consumer-clarify-refine.js"
```

Expected output: no output (exit code 0). If you see a SyntaxError, fix it before continuing.

- [ ] **Step 5: Commit Task 1 changes**

```bash
git add "IMPORTANT/Sidebar_extension/features/consumer-clarify-refine.js"
git commit -m "feat(extension): update clarify() to call /refine/prepare

- Replace /dev/test/clarify URL with /refine/prepare
- Accept (original, enhanced) args instead of single prompt
- Store neuro_state and context_patterns in _prepareState
- Update normaliseQuestions to handle new response shape first"
```

---

## Task 2: Update `consumer-clarify-refine.js` — `refine()` function

**Files:**
- Modify: `IMPORTANT/Sidebar_extension/features/consumer-clarify-refine.js` (`refine` function, currently lines ~158–197)

### Context

The current `refine(original, enhanced, qaArray)` POSTs `{ prompt, qa_pairs, user_id, auth_token }` to `REFINE_URL` and reads `json.enhanced_prompt || json.refined_prompt` from the response.

- [ ] **Step 1: Replace the `refine` function**

Find `async function refine(original, enhanced, qaArray)` and replace the entire function with:

```js
async function refine(original, enhanced, qaArray) {
  const promptToRefine = String(enhanced || original || "").trim();
  if (!promptToRefine) {
    return { success: false, error: "A prompt is required to refine" };
  }
  try {
    const { userId, accessToken } = await getAuth();
    const body = {
      original_prompt:           String(original || "").trim() || promptToRefine,
      previous_enhanced_prompt:  String(enhanced || "").trim() || null,
      clarification_qa:          Array.isArray(qaArray) ? qaArray : [],
      user_id:                   userId,
      neuro_state:               _prepareState.neuro_state    || null,
      context_patterns:          _prepareState.context_patterns || [],
    };

    const headers = { "Content-Type": "application/json" };
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

    const res = await fetch(FINALIZE_URL, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      return { success: false, error: json.message || json.detail || json.error || `HTTP ${res.status}` };
    }

    // New API returns refined_prompt; fall back to enhanced_prompt for safety.
    const refined =
      json.refined_prompt  ||
      (json.data && (json.data.refined_prompt || json.data.enhanced_prompt)) ||
      json.enhanced_prompt ||
      "";

    // Token counts are not returned by the new API; pass nulls so saveRefinedPrompt
    // still fires (it guards on promptId, not tokens).
    const refineTokens = {};

    // API #3 — persist refined prompt (fire-and-forget; never blocks the UI)
    void saveRefinedPrompt(refined, Array.isArray(qaArray) ? qaArray : [], refineTokens);

    return { success: true, data: { refined_prompt: refined } };
  } catch (err) {
    return { success: false, error: err.message || String(err) };
  }
}
```

- [ ] **Step 2: Verify the file saves without syntax errors**

```bash
node --check "IMPORTANT/Sidebar_extension/features/consumer-clarify-refine.js"
```

Expected: no output (exit code 0).

- [ ] **Step 3: Commit Task 2 changes**

```bash
git add "IMPORTANT/Sidebar_extension/features/consumer-clarify-refine.js"
git commit -m "feat(extension): update refine() to call /refine/finalize

- Replace /dev/test/refine URL with /refine/finalize
- Send clarification_qa (new field name) + neuro_state + context_patterns
- Read refined_prompt from response (was enhanced_prompt)
- Token fields default to null (new API does not return them)"
```

---

## Task 3: Update `suggestions-view.js` — pass both prompts in clarify message

**Files:**
- Modify: `IMPORTANT/Sidebar_extension/panel/consumer/suggestions-view.js:793-797`

### Context

The current `load(session)` function sends:

```js
const promptForClarify = (session && (session.displayPrompt || session.enhanced || session.original)) || "";
const res = await sendMsg("TV_CONSUMER_CLARIFY", { prompt: promptForClarify });
```

The new `clarify(original, enhanced)` signature needs both fields separately so `/refine/prepare` receives the full context.

- [ ] **Step 1: Update the clarify message in `load(session)`**

Open `IMPORTANT/Sidebar_extension/panel/consumer/suggestions-view.js`.

Find the two lines shown above inside `async function load(session)` (around lines 793–796) and replace them with:

```js
const res = await sendMsg("TV_CONSUMER_CLARIFY", {
  original: (session && session.original) || "",
  enhanced: (session && session.enhanced) || "",
});
```

The `promptForClarify` variable is no longer needed — remove it. Do not change anything else in `load()`.

- [ ] **Step 2: Verify the file saves without syntax errors**

```bash
node --check "IMPORTANT/Sidebar_extension/panel/consumer/suggestions-view.js"
```

Expected: no output (exit code 0).

- [ ] **Step 3: Commit Task 3 changes**

```bash
git add "IMPORTANT/Sidebar_extension/panel/consumer/suggestions-view.js"
git commit -m "feat(extension): pass original+enhanced in TV_CONSUMER_CLARIFY message

Required for /refine/prepare which needs both prompts separately"
```

---

## Task 4: Update `background.js` — forward both fields to `clarify()`

**Files:**
- Modify: `IMPORTANT/Sidebar_extension/background.js:1322-1353` (`TV_CONSUMER_CLARIFY` handler)

### Context

The current handler calls:

```js
const result = await TV.consumerClarifyRefine.clarify(payload.prompt);
```

`clarify()` now takes `(original, enhanced)`.

- [ ] **Step 1: Update the `TV_CONSUMER_CLARIFY` handler**

Open `IMPORTANT/Sidebar_extension/background.js`.

Find this exact line inside the `TV_CONSUMER_CLARIFY` block (~line 1334):

```js
const result = await TV.consumerClarifyRefine.clarify(payload.prompt);
```

Replace it with:

```js
const result = await TV.consumerClarifyRefine.clarify(payload.original, payload.enhanced);
```

That is the only change in this file.

- [ ] **Step 2: Verify the file saves without syntax errors**

```bash
node --check "IMPORTANT/Sidebar_extension/background.js"
```

Expected: no output (exit code 0).

- [ ] **Step 3: Commit Task 4 changes**

```bash
git add "IMPORTANT/Sidebar_extension/background.js"
git commit -m "feat(extension): forward original+enhanced to clarify() in background handler"
```

---

## Task 5: End-to-end verification in the browser

No code changes in this task — it is a manual smoke test to confirm the wired flow works before the change is considered complete.

### Prerequisites

- The FastAPI server is running locally on `http://localhost:8000` **or** `api.thinkvelocity.in` is accessible.
- The extension is loaded in Chrome via `chrome://extensions` → **Load unpacked** → point to `IMPORTANT/Sidebar_extension/`.

- [ ] **Step 1: Reload the extension**

Go to `chrome://extensions`, find the ThinkVelocity extension, and click the reload (↺) button. This clears any cached module state.

- [ ] **Step 2: Open DevTools on the background service worker**

On `chrome://extensions`, click **"Service Worker"** next to the extension. This opens DevTools on the background script. Keep the Console tab visible.

- [ ] **Step 3: Trigger the clarify flow**

Open the extension side panel on any page. Type a prompt in the composer and click **Refine** (the sparkle / improve button). This fires `TV_CONSUMER_CLARIFY`.

**Expected in the background Console:**
- No `[consumer-clarify-refine]` errors.
- No `CLARIFY_FAILED` or `CLARIFY_ERROR` messages.

**Expected in the Network tab (filter by `refine`):**
- A `POST` request to `https://api.thinkvelocity.in/refine/prepare` with status `200`.
- The request body contains `original_prompt` and optionally `previous_enhanced_prompt`.
- The response contains a `questions` array.

- [ ] **Step 4: Answer a question and submit refine**

Answer at least one clarifying question in the suggestions view and click **Send** in the composer bar.

**Expected in the background Console:**
- No `REFINE_FAILED` or `REFINE_ERROR` messages.

**Expected in the Network tab:**
- A `POST` request to `https://api.thinkvelocity.in/refine/finalize` with status `200`.
- The request body contains `clarification_qa`, `neuro_state`, and `context_patterns`.
- The response contains `refined_prompt`.

**Expected in the UI:**
- The Output view appears and shows the refined prompt — identical behaviour to before the migration.

- [ ] **Step 5: Verify the old `/dev/test/` endpoints are NOT called**

In the Network tab, filter by `dev/test`. Confirm zero requests appear during the clarify + refine flow.

- [ ] **Step 6: Commit verification note**

```bash
git commit --allow-empty -m "chore: e2e verified — extension calls /refine/prepare and /refine/finalize"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** All three files listed in the spec are touched. Both endpoint changes (`PREPARE_URL`, `FINALIZE_URL`) covered. `_prepareState` module variable added. `normaliseQuestions` updated. `suggestions-view.js` passes `original + enhanced`. `background.js` forwards both fields. `saveRefinedPrompt`, `sendFeedback`, `submitWrittenFeedback` unchanged. Token fields default to null.
- [x] **No placeholders:** Every step has exact code, exact file paths, exact terminal commands with expected output.
- [x] **Type consistency:** `_prepareState.neuro_state` used consistently in both Task 1 and Task 2. `clarify(original, enhanced)` defined in Task 1, forwarded in Task 3 and Task 4. `clarification_qa` array in Task 2 matches `[{question, answer}]` shape produced by `buildQaArray()` in `suggestions-view.js` (unchanged).
- [x] **Auth style:** New endpoints use `Authorization: Bearer <token>` header (matching all other routes in `consumer-enhance-flow.js`). The old `auth_token` body field is removed.
- [x] **Fallback safety:** `neuro_state: null` is valid — `api/refine.py` line 465 calls `fallback_goal_state()` when neuro state generation fails or is null.
