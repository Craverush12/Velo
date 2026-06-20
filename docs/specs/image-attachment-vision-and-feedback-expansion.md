# Spec: Image Attachment Vision + Feedback Notification Expansion

**Date:** 2026-06-17  
**Status:** Backend (python-ai-unified) already live on server. Extension + Node changes below need implementing.  
**Owner:** Frontend / Node developer

---

## 1. Context

Two separate things are covered in this spec:

1. **Image attachments in enhance** — when a user attaches an image, it is currently silently ignored. The backend now supports vision processing via Groq Llama 4 Scout. The extension and Node backend need to wire the image data through.

2. **Richer Slack feedback notifications** — the feedback Slack message was expanded with onboarding persona, token trace, conversation thread, and larger prompt snippets. The Node change is already live on the server via hotpatch. It needs to be committed to source.

---

## 2. Image Attachment Vision — Extension Changes

### 2a. `Sidebar_extension/panel/consumer/composer-bar.js`

**What:** When a user attaches an image file, read it as base64 and store it in the attachment item. Currently non-text files (including images) fall through to `[Binary or large file: ...]` and carry no content — they are silently skipped by the backend.

**Where to apply:** The `fileToAttachmentItem` function and the constants at the top.

---

**Change 1 — add `MAX_IMAGE_BYTES` constant** (add after the existing `MAX_FILE_TEXT_BYTES` line):

```js
// BEFORE
const MAX_FILE_TEXT_BYTES = 400 * 1024;
const MAX_PREVIEW_CHARS = 4000;

// AFTER
const MAX_FILE_TEXT_BYTES = 400 * 1024;
const MAX_IMAGE_BYTES = 4 * 1024 * 1024; // 4 MB cap for vision
const MAX_PREVIEW_CHARS = 4000;
```

---

**Change 2 — add `readFileAsBase64` helper** (add right after the existing `readFileAsText` function):

```js
function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      // result is "data:<mime>;base64,<data>" — strip the prefix
      const result = String(r.result || "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}
```

---

**Change 3 — update `fileToAttachmentItem`** to handle images:

```js
// BEFORE
async function fileToAttachmentItem(file, fromFolder) {
  const id = `file-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  const base = {
    id,
    kind: "file",
    label: (fromFolder ? file.webkitRelativePath || file.name : file.name).slice(0, 200),
    name: file.name,
    size: file.size,
    mimeType: file.type || "application/octet-stream",
    addedAt: Date.now(),
  };
  const textLike = isTextLike(file.name, file.type);
  if (textLike && file.size <= MAX_FILE_TEXT_BYTES) {
    try {
      const text = await readFileAsText(file);
      base.textContent = text.slice(0, MAX_FILE_TEXT_BYTES);
      base.preview = base.textContent.slice(0, MAX_PREVIEW_CHARS);
    } catch {
      base.preview = "[Could not read file as text]";
    }
  } else {
    base.preview = `[Binary or large file: ${file.name}]`;
  }
  return base;
}

// AFTER
async function fileToAttachmentItem(file, fromFolder) {
  const id = `file-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  const mimeType = file.type || "application/octet-stream";
  const base = {
    id,
    kind: "file",
    label: (fromFolder ? file.webkitRelativePath || file.name : file.name).slice(0, 200),
    name: file.name,
    size: file.size,
    mimeType,
    addedAt: Date.now(),
  };
  const textLike = isTextLike(file.name, file.type);
  const isImage = mimeType.startsWith("image/");
  if (textLike && file.size <= MAX_FILE_TEXT_BYTES) {
    try {
      const text = await readFileAsText(file);
      base.textContent = text.slice(0, MAX_FILE_TEXT_BYTES);
      base.preview = base.textContent.slice(0, MAX_PREVIEW_CHARS);
    } catch {
      base.preview = "[Could not read file as text]";
    }
  } else if (isImage && file.size <= MAX_IMAGE_BYTES) {
    try {
      base.imageData = await readFileAsBase64(file);
      base.preview = `[Image: ${file.name}]`;
    } catch {
      base.preview = `[Image: ${file.name} — could not read]`;
    }
  } else {
    base.preview = `[Binary or large file: ${file.name}]`;
  }
  return base;
}
```

---

### 2b. `Sidebar_extension/features/consumer-enhance-flow.js`

**What:** `buildRequestBody` never reads the attachment cache from `chrome.storage.local`, so attachments are never sent to the enhance endpoint at all. This adds that wiring.

**Where to apply:** The `buildRequestBody` function.

```js
// BEFORE
async function buildRequestBody(userPrompt, selectedStyle, userData, quality, prefs) {
  const finalMode = modeToApi(selectedStyle);
  const normalizedUserId = normalizeUserId(userData.userId) || "free-trial";
  const body = {
    prompt: userPrompt,
    chat_history: ["", "", ""],
    context: { mode: finalMode },
    target_ai: "",
    domain: quality.domain || "",
    user_id: normalizedUserId,
    auth_token: userData.accessToken,
    intent: quality.intent || "",
    intent_description: quality.intent_description || "",
  };
  if (prefs && Object.keys(prefs).length) {
    body.user_context = { preferences: prefs };
  }
  return body;
}

// AFTER
async function buildRequestBody(userPrompt, selectedStyle, userData, quality, prefs) {
  const finalMode = modeToApi(selectedStyle);
  const normalizedUserId = normalizeUserId(userData.userId) || "free-trial";
  const body = {
    prompt: userPrompt,
    chat_history: ["", "", ""],
    context: { mode: finalMode },
    target_ai: "",
    domain: quality.domain || "",
    user_id: normalizedUserId,
    auth_token: userData.accessToken,
    intent: quality.intent || "",
    intent_description: quality.intent_description || "",
  };
  if (prefs && Object.keys(prefs).length) {
    body.user_context = { preferences: prefs };
  }

  // Read cached attachments (set by composer-bar) and forward to enhance.
  try {
    const stored = await chrome.storage.local.get(["velocity_context_attachments_meta"]);
    const cached = Array.isArray(stored.velocity_context_attachments_meta)
      ? stored.velocity_context_attachments_meta
      : [];
    if (cached.length) {
      body.attachments = cached.map((item) => {
        const att = { name: item.name || item.label || "attachment", mime_type: item.mimeType || "" };
        if (item.textContent) att.text = item.textContent;
        if (item.imageData)   att.image_data = item.imageData;
        return att;
      });
    }
  } catch (_) { /* non-fatal — enhance proceeds without attachments */ }

  return body;
}
```

**Key contract with the backend:**
- Text files → `{ name, mime_type, text }` — already supported by backend
- Image files → `{ name, mime_type, image_data }` — backend now calls Groq vision on this and converts it to a text description before passing to enhance

---

## 3. Feedback Notification Expansion — Node Backend

**File:** `backend-V1/controllers/promptControllers/feedbackController.js`

This change is **already live on the server via hotpatch** (`docker cp` + `docker restart tv-node-backend` on 2026-06-17). It needs to be committed to source so it survives the next Docker image rebuild.

### What changed

**`resolvePromptFeedbackContext`** — 4 new DB queries added on top of the original 2:

| Query | New fields returned |
|---|---|
| `usertable` (existing, extended) | + `created_at` for account age |
| `onboarding_data` (new) | `occupation`, `use_case`, `ai_familiarity`, `llm_platform` |
| `save_enhance_prompt` COUNT (new) | `totalEnhances`, `lifetimeDislikes` per user |
| `user_prompts` JOIN `save_enhance_prompt` on `conversation_id` (new) | `conversationThread` — up to 8 prompts in same session |

**`notifyPromptFeedbackSlack`** — 4 new Slack sections added:

| Section | Content |
|---|---|
| **Trace details** | `complexity`, `user_status`, `input_token / output_token / total_token`, timestamp of the enhance, `metadata` JSON if non-empty |
| **User profile** | occupation, use case, AI familiarity, main LLM, account age in days, total enhances, lifetime dislike count |
| **Refinement Q&A** (refine kind only) | All 4 question/answer pairs the user provided during refinement |
| **Conversation thread** | All prompts in the same `conversation_id`, ordered chronologically |

Prompt/output snippets also increased from **600 → 1200 chars**.

### Source of truth

The live file content is already in `FullCodebase/ThinkVelocity/backend-V1/controllers/promptControllers/feedbackController.js` in this repo — lines 1–321 cover all changed functions (`resolvePromptFeedbackContext` and `notifyPromptFeedbackSlack`). Everything from line 322 onward (`saveEnhancedPromptFeedback`, `saveRefinedPromptFeedback`, `getEnhancedPromptsByFeedback`, `getRefinedPromptsByFeedback`) is unchanged.

**No schema migrations needed** — all new queries read from existing tables (`onboarding_data`, `usertable`, `save_enhance_prompt`, `user_prompts`).

To re-hotpatch if the container is ever rebuilt:
```bash
docker cp feedbackController.js tv-node-backend:/app/controllers/promptControllers/feedbackController.js
docker restart tv-node-backend
```

---

## 4. Backend Changes Already Live (python-ai-unified)

These are documented here for completeness. No action needed from the frontend/Node developer.

**File:** `python-ai-unified/routers/ai/enhance.py`

- Added `import os` to imports
- Added `async def _describe_image_with_vision(image_data, mime_type, user_id)` — calls `meta-llama/llama-4-scout-17b-16e-instruct` on Groq with the base64 image, returns a text description
- `_to_local` changed from `def` to `async def`
- Attachment loop updated: detects `mime_type.startswith("image/")` + `image_data` present → awaits vision call → uses description as text; otherwise falls back to existing text handling
- Both `_generate(...)` call sites updated to `await _to_local(...)`
- Container rebuilt and restarted on 2026-06-17, health confirmed ✅

---

## 5. What Still Needs Doing (not in this spec)

- **Extract page bug** — the `TV_EXTRACT_PAGE_MARKDOWN` / `TV_EXTRACT_PAGE_CONTEXT` background script message handlers fail silently on some pages (nothing reaches the server). Needs investigation in the extension background script. No server changes required.
- **Extension release** — the composer-bar + enhance-flow changes need packaging and a new Chrome Web Store submission to reach users.
