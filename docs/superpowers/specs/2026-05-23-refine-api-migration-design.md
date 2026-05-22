# Refine API Migration: Extension → New api.thinkvelocity.in Endpoints

**Date:** 2026-05-23
**Scope:** Wire the extension's clarify/refine flow to the new `/refine/prepare` and `/refine/finalize` FastAPI endpoints, replacing the old `/dev/test/clarify` and `/dev/test/refine` endpoints.

---

## Background

The FastAPI backend (`api/refine.py`) exposes three new refine routes:

- `POST /refine` — base refine
- `POST /refine/prepare` — generates clarifying questions plus neuro state (replaces `/dev/test/clarify`)
- `POST /refine/finalize` — produces the refined prompt using Q&A answers and neuro state (replaces `/dev/test/refine`)

The extension currently calls only the old `/dev/test/` endpoints. The new endpoints are not called from the extension at all.

---

## Goal

Transparently swap the extension's API calls to the new endpoints. The UI, message contract between views and background.js, and the `saveRefinedPrompt` persistence flow all stay unchanged.

---

## Architecture

### Call chain (unchanged shape, new internals)

```
suggestions-view.js
  load(session)
    → sendMsg("TV_CONSUMER_CLARIFY", { original: session.original, enhanced: session.enhanced })

background.js  [TV_CONSUMER_CLARIFY handler]
  → TV.consumerClarifyRefine.clarify(payload.original, payload.enhanced)

consumer-clarify-refine.js  clarify(original, enhanced)
  → POST https://api.thinkvelocity.in/refine/prepare
  ← { questions, neuro_state, context_patterns, first_pass_enhancement }
  → stores { neuro_state, context_patterns } in module-level _prepareState
  ← returns { success: true, data: { questions: [{id, question, options}] } }
      (same shape background.js and suggestions-view.js already expect)

-------- user answers questions --------

suggestions-view.js
  runRefineRequest(qaArray)
    → sendMsg("TV_CONSUMER_REFINE", { original, enhanced, qaArray })  ← unchanged

background.js  [TV_CONSUMER_REFINE handler]
  → TV.consumerClarifyRefine.refine(payload.original, payload.enhanced, payload.qaArray)

consumer-clarify-refine.js  refine(original, enhanced, qaArray)
  → reads _prepareState.neuro_state, _prepareState.context_patterns
  → POST https://api.thinkvelocity.in/refine/finalize
  ← { refined_prompt, annotated_segments, ... }
  → fire-and-forget saveRefinedPrompt() (unchanged)
  ← returns { success: true, data: { refined_prompt } }
      (same shape suggestions-view.js already expects)
```

---

## Components

### 1. `features/consumer-clarify-refine.js`

**Constants — update URLs:**
```
FASTAPI_BASE  = "https://api.thinkvelocity.in"        // was /dev/test
PREPARE_URL   = `${FASTAPI_BASE}/refine/prepare`       // replaces CLARIFY_URL
FINALIZE_URL  = `${FASTAPI_BASE}/refine/finalize`      // replaces REFINE_URL
```
Keep `REFINE_SAVE_URL`, `FEEDBACK_URL`, `REVIEWS_URL` unchanged.

**New module-level state:**
```js
let _prepareState = { neuro_state: null, context_patterns: [] };
```
Stored in memory (not chrome.storage). Scoped to the most recent prepare call. Cleared at the start of each `clarify()` call.

**`clarify(original, enhanced)` — signature change + new request:**
- Accepts `(original, enhanced)` instead of `(prompt)`
- Request body:
  ```json
  { "original_prompt": original, "previous_enhanced_prompt": enhanced || null, "user_id": "..." }
  ```
  No `auth_token` field (new API uses Bearer header like other routes).
- Stores `json.neuro_state` and `json.context_patterns` into `_prepareState`.
- Normalises questions: new response already returns `{ questions: [{id, question, options}] }` — the `normaliseQuestions` function is simplified to handle this shape directly, with the old MCQ fallback kept for safety.
- Clears the old `clarifyInputToken` / `clarifyOutputToken` chrome.storage writes (new API does not return tokens in that shape; `saveRefinedPrompt` token fields will be `null`).

**`refine(original, enhanced, qaArray)` — new request:**
- Reads `_prepareState.neuro_state` and `_prepareState.context_patterns`.
- Request body:
  ```json
  {
    "original_prompt": original,
    "previous_enhanced_prompt": enhanced || null,
    "clarification_qa": [{ "question": "...", "answer": "..." }],
    "neuro_state": _prepareState.neuro_state || null,
    "context_patterns": _prepareState.context_patterns || []
  }
  ```
- Result field: reads `json.refined_prompt` first (new API primary field), then falls back to `json.enhanced_prompt` for backward compatibility.
- `saveRefinedPrompt` call is unchanged; token fields default to `null` (new API does not return token counts).

### 2. `panel/consumer/suggestions-view.js`

One line changes in `load(session)` (line ~795):

```js
// Before:
const promptForClarify = (session && (session.displayPrompt || session.enhanced || session.original)) || "";
const res = await sendMsg("TV_CONSUMER_CLARIFY", { prompt: promptForClarify });

// After:
const res = await sendMsg("TV_CONSUMER_CLARIFY", {
  original: (session && session.original) || "",
  enhanced: (session && session.enhanced) || "",
});
```

No other changes in this file.

### 3. `background.js`

One line changes in the `TV_CONSUMER_CLARIFY` handler (~line 1334):

```js
// Before:
const result = await TV.consumerClarifyRefine.clarify(payload.prompt);

// After:
const result = await TV.consumerClarifyRefine.clarify(payload.original, payload.enhanced);
```

No other changes in this file.

---

## Request/Response Mapping

| Step | Old | New |
|------|-----|-----|
| Clarify URL | `https://api.thinkvelocity.in/dev/test/clarify` | `https://api.thinkvelocity.in/refine/prepare` |
| Clarify body | `{ prompt, user_id, auth_token }` | `{ original_prompt, previous_enhanced_prompt, user_id }` |
| Auth style | body field `auth_token` | `Authorization: Bearer <token>` header |
| Questions path | `json.mcq_questions[].question_text` / `json.questions` | `json.questions[].question` |
| Options path | `q.answer_options` | `q.options` |
| Refine URL | `https://api.thinkvelocity.in/dev/test/refine` | `https://api.thinkvelocity.in/refine/finalize` |
| Refine body | `{ prompt, qa_pairs, user_id, auth_token }` | `{ original_prompt, previous_enhanced_prompt, clarification_qa, neuro_state, context_patterns }` |
| Refined text | `json.enhanced_prompt \|\| json.refined_prompt` | `json.refined_prompt` (primary), fallback `json.enhanced_prompt` |
| Token tracking | `json.tokens.input_tokens` etc. | Not returned; `saveRefinedPrompt` token fields = `null` |

---

## Error Handling

- If `/refine/prepare` fails, `clarify()` returns `{ success: false, error }` — same as before. The suggestions view shows no questions (empty state), which is existing behaviour.
- If `_prepareState` is empty when `refine()` is called (e.g. user skipped clarify), `neuro_state: null` and `context_patterns: []` are sent. The backend handles null `neuro_state` gracefully (it generates its own via `fallback_goal_state`).
- The `saveRefinedPrompt` fire-and-forget call is never allowed to fail the main refine result — unchanged from current behaviour.

---

## Out of Scope

- Surfacing `annotated_segments`, `quality_delta`, `framework_used`, or `why_it_matters` in the UI.
- Using `first_pass_enhancement` from the prepare response.
- The `/refine` (base) endpoint — only `prepare` and `finalize` are wired in this change.
- Any changes to the enterprise sidebar, injection modal, or MCP tools.

---

## Files Changed

| File | Change |
|------|--------|
| `IMPORTANT/Sidebar_extension/features/consumer-clarify-refine.js` | New URLs, new request bodies, updated `normaliseQuestions`, module-level `_prepareState`, auth header |
| `IMPORTANT/Sidebar_extension/panel/consumer/suggestions-view.js` | Pass `original` + `enhanced` instead of single `prompt` in `TV_CONSUMER_CLARIFY` message |
| `IMPORTANT/Sidebar_extension/background.js` | Forward `payload.original` + `payload.enhanced` to `clarify()` |

No manifest changes. No new files. No CSS changes.
