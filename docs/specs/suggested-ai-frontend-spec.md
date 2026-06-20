# Frontend Spec: `suggested_ai` in Extension

## What the API now returns

`POST /ai/enhance/chat` response includes:
```json
{
  "enhanced_prompt": "...",
  "suggested_ai": "chatgpt"   // one of: chatgpt | claude | gemini
}
```

`suggested_ai` is derived from the user's declared platform → onboarding primary model → domain default. Never null — always one of the three values above.

---

## Files to change

### 1. `features/consumer-enhance-flow.js` — thread it through

In `runEnhance()`, the stream result lands at:
```js
const streamResult = await processStream(res);   // ~line 434
```

In the `return { success: true, data: { ... } }` block (~line 463), add:
```js
suggested_ai: streamResult.suggested_ai || null,
```

---

### 2. `panel/consumer/composer-bar.js` — pass to session

In the `startSession({...})` call (~line 904), add:
```js
suggested_ai: res.data.suggested_ai || null,
```

---

### 3. `panel/consumer/output-view.js` — use it

**Platform key mapping** (add near top of file or inside `show()`):
```js
const SUGGESTED_AI_KEY_MAP = {
  chatgpt: "openai",
  claude: "anthropic",
  gemini: "google",
};
```

These keys match what `openInPlatform()` in `consumer-platform-inject.js` expects.

**In `show(session)` (~line 650)**, before `wireActionRow`:
```js
if (session.suggested_ai && SUGGESTED_AI_KEY_MAP[session.suggested_ai]) {
  _openInPlatformKey = SUGGESTED_AI_KEY_MAP[session.suggested_ai];
}
```

**Badge** — in `buildOpenInWrap(session)` (~line 363), after the existing button HTML, conditionally render:
```js
if (session.suggested_ai) {
  // append a small chip: "Best for: ChatGPT" / "Best for: Claude" / "Best for: Gemini"
  const label = { chatgpt: "ChatGPT", claude: "Claude", gemini: "Gemini" }[session.suggested_ai] || session.suggested_ai;
  // add chip element with text `Best for: ${label}`
}
```

---

## Platform key cross-reference

| `suggested_ai` value | `_openInPlatformKey` | Label in badge |
|---|---|---|
| `chatgpt` | `openai` | ChatGPT |
| `claude` | `anthropic` | Claude |
| `gemini` | `google` | Gemini |

---

## Validation criteria

1. After an enhance call, `network` tab shows `suggested_ai` field in the `/ai/enhance/chat` response.
2. "Open In" dropdown default platform matches the suggested AI (not always OpenAI).
3. Badge "Best for: [Platform]" is visible on the Open In button.
4. Guest / anonymous users with `suggested_ai: null` fall back to the previous hardcoded "openai" default — no breakage.
