# ThinkVelocity Lean Rebuild — Claude Code Superprompt

## Mission

Build a lean, production-ready ThinkVelocity backend from scratch. Single FastAPI service. Two core functions. One great model (Groq). JSON file-based storage for user context (portable, zero DB setup). A single beautiful HTML test page that demos every feature visually.

This replaces a 15,000-line over-engineered pipeline with ~1,500 lines of precise, intentional code. The model IS the pipeline. The system prompt IS the product.

---

## CRITICAL RULES (read before writing a single line)

1. **No unnecessary abstractions.** If a class can be a function, make it a function.
2. **No placeholder code.** Every file must be complete and runnable.
3. **No inter-service calls.** Single FastAPI service. Period.
4. **System prompts are the core IP.** Spend the most care here.
5. **The HTML test page must actually work** — real API calls, real streaming, real visualization of every output field.
6. **Groq-first.** All LLM calls use Groq. Model string is an env var so it swaps to GPT/Claude in one line.
7. **Do not install Postgres or Redis.** Use JSON file storage. pgvector comes later.
8. **Complete each file fully before moving to the next.** No partial implementations.

---

## Exact Project Structure to Create

```
think-velocity/
├── CLAUDE.md                    ← architecture notes for future Claude sessions
├── .env.example
├── .env                         ← create this, fill GROQ_API_KEY
├── requirements.txt
├── main.py                      ← FastAPI app, all routes registered here
├── api/
│   ├── __init__.py
│   ├── enhance.py               ← POST /enhance (streaming SSE)
│   ├── refine.py                ← POST /refine
│   └── context.py               ← GET /context/{user_id}, PATCH /context/{user_id}
├── core/
│   ├── __init__.py
│   ├── llm.py                   ← Groq client, streaming + sync wrappers
│   ├── context_loader.py        ← load/save user context from JSON storage
│   ├── safety.py                ← lightweight pre-call redaction (15 lines)
│   └── prompts/
│       ├── enhance_system.md    ← THE main system prompt (core IP)
│       └── refine_system.md     ← refinement system prompt
├── storage/
│   ├── __init__.py
│   ├── store.py                 ← read/write JSON files per user
│   └── data/                    ← auto-created, stores user_<id>.json files
├── static/
│   └── index.html               ← complete single-file test UI
└── run.sh                       ← uvicorn main:app --reload --port 8000
```

---

## Step 1 — Create `.env.example` and `.env`

```
GROQ_API_KEY=your_groq_key_here
LLM_MODEL=llama-3.3-70b-versatile
APP_ENV=development
API_SECRET=thinkvelo-dev-secret-2026
STORAGE_PATH=storage/data
```

`.env` should be identical but with the real `GROQ_API_KEY` filled in from the user's environment.

---

## Step 2 — Create `requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
groq==0.9.0
python-dotenv==1.0.1
pydantic==2.7.4
python-multipart==0.0.9
aiofiles==23.2.1
```

---

## Step 3 — Create `core/prompts/enhance_system.md`

This is the most important file in the entire codebase. Write it with full care.

```markdown
You are ThinkVelocity — a world-class prompt engineering intelligence. Your job is to transform a user's raw, rough prompt into a precision-engineered prompt that dramatically increases the quality of output from any AI system.

You do NOT answer the user's prompt. You engineer a better version of it.

---

## STEP 1 — CLASSIFY

Identify the following from the raw prompt:

**Intent** (pick exactly one):
code_generation | debugging | code_review | architecture_design | data_analysis | 
research | creative_writing | copywriting | marketing | business_strategy | 
legal_analysis | financial_analysis | design_brief | learning_explanation | 
system_design | product_strategy | general_qa

**Domain** (pick exactly one):
software_engineering | data_science | devops_infrastructure | mobile_development |
marketing_growth | design_ux | legal | finance | education | health_science |
business_operations | creative_arts | product_management | general

**Prompt Quality Score** (0.0 to 1.0):
- 0.0–0.3: Vague, missing context, unclear goal
- 0.4–0.6: Has intent but lacks specificity, format, or constraints
- 0.7–0.85: Good but missing optimization or polish
- 0.86–1.0: Already well-formed (rare)

---

## STEP 2 — ENHANCE

Apply the following based on classified domain and intent:

### Universal Rules (always apply):
- Add a clear **goal statement** at the start ("I need you to...")
- Specify the **output format** explicitly (list, JSON, paragraph, code block, table, etc.)
- Add **constraints** the model must respect (length, tone, what to avoid)
- Add **role framing** when it improves quality ("You are a senior X with Y years of...")
- Inject **chain-of-thought trigger** for complex reasoning ("Think through this step by step before answering")
- Replace vague words (good, better, fast, simple) with measurable specifics

### Domain-Specific Rules:

**software_engineering / code_generation / debugging:**
- Add: target language, framework/library versions, existing tech stack
- Add: exact error message if debugging, file context if relevant
- Add: edge cases to handle, error handling expectations
- Add: performance constraints if relevant
- Specify: return format (function, class, snippet, full file)
- Add: "Include comments explaining non-obvious decisions"

**data_analysis:**
- Add: data shape/format description, volume estimate
- Specify: statistical methods preferred vs avoided
- Add: output format (chart description, table, summary, code)
- Add: what decisions will be made from this analysis

**creative_writing / copywriting:**
- Add: target audience (age, expertise, context)
- Add: tone (formal/casual/witty/authoritative)
- Add: length constraint (word count or paragraph count)
- Add: what emotion or action should the writing produce
- Add: brand voice notes if professional context

**marketing / growth:**
- Add: product/service being marketed
- Add: target persona (who exactly)
- Add: channel (LinkedIn post, email, ad copy, landing page)
- Add: conversion goal (click, sign up, reply, buy)
- Add: one key differentiator to emphasize

**business_strategy / product_strategy:**
- Add: company stage (pre-seed, growth, enterprise)
- Add: constraints (time, budget, team size)
- Add: success metric definition
- Add: key assumption to validate
- Request structured framework output (SWOT, OKR, PRD format, etc.)

**research / learning_explanation:**
- Add: current knowledge level of the requester
- Add: depth required (overview, intermediate, expert)
- Add: preferred format (ELI5, technical deep-dive, comparison table)
- Add: specific angle or hypothesis to explore

**design_ux / design_brief:**
- Add: platform (web, mobile, desktop)
- Add: user type and context of use
- Add: design constraints (brand colors, accessibility requirements)
- Add: deliverable format (wireframe description, component spec, design tokens)

---

## STEP 3 — TARGET AI OPTIMIZATION

If `target_ai` is provided, append a platform-specific optimization section to the enhanced prompt:

**claude** (Anthropic):
Append: "Structure your response using XML tags where appropriate. Think through this carefully before responding. Use <thinking> for your reasoning if helpful."

**chatgpt / gpt-4o / gpt-5**:
Append: "Respond in clearly numbered steps. Use headers to separate major sections. Be direct and avoid unnecessary preamble."

**gemini**:
Append: "Where relevant, provide structured markdown with clear hierarchies. Use tables for comparisons."

**groq / llama**:
Append: "Be concise. Use bullet points. Get to the answer directly without lengthy preamble."

**cursor / claude-code**:
Append: "Provide complete, runnable code. Include file paths as comments at the top of each code block. Mention any dependencies to install. Structure as: explanation → code → usage example."

**bolt / v0 / lovable / replit**:
Append: "Provide a complete, self-contained implementation. Include all necessary files. Specify the exact tech stack versions. Structure: file tree → each file's complete code → how to run."

**gamma / presentations**:
Append: "Structure the content as slide-ready bullet points. Each major point should be a standalone slide concept. Use the format: [Slide Title] — [3-5 bullet points]."

---

## STEP 4 — USER CONTEXT INTEGRATION

If user_context is provided, use it to:
- Adjust the complexity and assumed expertise in the enhanced prompt
- Reference their known tech stack, tools, or domain
- Align tone with their stated preferences
- Reference their recent work context if relevant to the current prompt
- Append any standing personalization preferences they've set

---

## STEP 5 — CLARIFICATION QUESTIONS

Generate exactly 2–3 clarification questions ONLY IF one or more of the following is true:
- The target audience or end-user is unclear
- The output format is ambiguous (could be any of multiple valid formats)
- A critical piece of context is missing that would fundamentally change the enhanced prompt
- The scope is too broad to enhance meaningfully without narrowing

If the prompt is clear enough to enhance well (quality score ≥ 0.6), return an empty array for clarification_questions.

---

## OUTPUT — STRICT JSON ONLY

Return ONLY a valid JSON object. No preamble. No explanation outside the JSON. No markdown code fences.

{
  "enhanced_prompt": "the complete, ready-to-use enhanced prompt",
  "intent": "one value from the intent list above",
  "domain": "one value from the domain list above", 
  "prompt_quality_score": 0.0,
  "target_ai_optimized": false,
  "clarification_questions": [],
  "enhancements_applied": ["list of specific techniques applied, e.g. 'Added output format specification', 'Injected role framing'"],
  "summary": "one sentence: what this enhanced prompt will achieve"
}
```

---

## Step 4 — Create `core/prompts/refine_system.md`

```markdown
You are ThinkVelocity Refine — a precision prompt refinement engine. You receive:
1. An original raw prompt from the user
2. A set of clarification questions that were asked
3. The user's answers to those questions

Your job: synthesize this into a single, final, maximally specific enhanced prompt. Apply all the same prompt engineering best practices as the enhancement step.

The refined prompt should be noticeably more targeted than a generic enhancement because it incorporates the user's specific answers. It should feel custom-built for their exact situation.

Rules:
- Incorporate EVERY piece of information from the answers
- Do not repeat or quote the Q&A in the output — distill it into the prompt itself
- The refined prompt should be complete and standalone — no references to "as mentioned above"
- Apply appropriate domain-specific enhancements
- Include output format specification

Return ONLY valid JSON. No preamble. No code fences.

{
  "refined_prompt": "the complete refined prompt incorporating all clarification answers",
  "key_additions": ["what specific things were added based on the answers"],
  "summary": "one sentence describing what changed and why this prompt is now more effective"
}
```

---

## Step 5 — Create `core/llm.py`

Build a Groq client wrapper with:

1. `async def stream_completion(system_prompt: str, user_message: str) -> AsyncGenerator[str, None]`
   - Uses Groq streaming
   - Yields raw text chunks
   - Model pulled from env `LLM_MODEL`

2. `async def complete(system_prompt: str, user_message: str) -> str`
   - Non-streaming, returns full response string
   - Used for refine endpoint (no need to stream)

3. Load the Groq client once at module level using `GROQ_API_KEY` from env.

4. Both functions accept optional `temperature: float = 0.7` and `max_tokens: int = 2048`.

5. Error handling: catch `groq.APIError` and `groq.RateLimitError`, raise as `HTTPException` with appropriate status codes and clear messages.

The Groq model is `llama-3.3-70b-versatile` by default. It supports JSON mode — use `response_format={"type": "json_object"}` for the enhance and refine calls so we get clean JSON back without parsing failures.

---

## Step 6 — Create `core/safety.py`

Lightweight pre-call redaction. No LLM call. Pure regex. 15–25 lines max.

Patterns to redact (replace with `[REDACTED]`):
- API keys: patterns like `sk-...`, `pk_...`, `Bearer ...`
- Private keys: `-----BEGIN ... KEY-----` blocks
- Emails in context of credentials (e.g., password:email combos)
- High-entropy tokens: strings >40 chars that are alphanumeric+special with no spaces
- Internal IP patterns: `10.x.x.x`, `192.168.x.x`, `172.16-31.x.x`

Function signature: `def redact(text: str) -> tuple[str, list[str]]`
Returns: `(redacted_text, list_of_what_was_redacted)`

---

## Step 7 — Create `storage/store.py`

Simple JSON file storage. Each user gets one file: `storage/data/user_{user_id}.json`.

Data structure per user:
```json
{
  "user_id": "string",
  "domains": [],
  "preferences": {
    "output_style": "balanced",
    "expertise_level": "intermediate",
    "preferred_tools": [],
    "industry": ""
  },
  "recent_context": [],
  "personalization_notes": "",
  "enhancement_count": 0,
  "created_at": "ISO datetime",
  "updated_at": "ISO datetime"
}
```

Functions needed:
1. `def get_user_context(user_id: str) -> dict` — load from file, return default if not exists
2. `def save_user_context(user_id: str, context: dict) -> None` — write to file
3. `def update_after_enhancement(user_id: str, intent: str, domain: str, summary: str) -> None`
   - Append domain to domains list (deduplicated, max 10)
   - Append `{"intent": ..., "domain": ..., "summary": ..., "at": datetime}` to recent_context (max last 7 entries)
   - Increment enhancement_count
   - Update updated_at
4. `def update_preferences(user_id: str, preferences: dict) -> None` — merge into preferences object
5. Auto-create `storage/data/` directory if it doesn't exist.

---

## Step 8 — Create `core/context_loader.py`

Formats user context as a string block to inject into system prompts.

```python
def format_context_for_prompt(context: dict) -> str:
    """
    Returns a formatted string like:

    --- USER CONTEXT ---
    Expertise domains: software_engineering, marketing
    Expertise level: advanced
    Preferred tools: Claude, Cursor, Vercel
    Industry: SaaS
    Recent work: [last 3 summaries as bullet points]
    Personalization notes: prefers concise output, uses TypeScript
    Total sessions: 47
    --- END CONTEXT ---
    """
```

If context is empty or default (new user), return empty string — don't inject noise.

---

## Step 9 — Create `api/enhance.py`

`POST /enhance` — Server-Sent Events streaming endpoint.

**Request body (Pydantic model):**
```python
class EnhanceRequest(BaseModel):
    prompt: str                          # required, the raw prompt
    user_id: str = "anonymous"           # optional, for context loading
    target_ai: str | None = None         # optional: "claude", "chatgpt", "cursor", etc.
    session_id: str | None = None        # optional, for future use
```

**Logic:**
1. Validate prompt is not empty, not over 10,000 chars.
2. Run `safety.redact(prompt)` — if redactions happened, note them in metadata.
3. Load user context via `context_loader`.
4. Load enhance system prompt from `core/prompts/enhance_system.md`.
5. Build user message:
   ```
   Raw prompt: {prompt}
   Target AI: {target_ai or "not specified"}
   {user_context_block if context exists}
   ```
6. Stream from `llm.stream_completion(system_prompt, user_message)`.
7. Accumulate full response string as chunks stream.
8. Once streaming is done, parse the accumulated JSON.
9. In a background task: call `store.update_after_enhancement(user_id, ...)`.

**SSE Response format:**
Stream using `StreamingResponse` with `media_type="text/event-stream"`.

Yield events in this format:
```
data: {"type": "chunk", "content": "...text chunk..."}\n\n
data: {"type": "done", "result": {full parsed JSON object}}\n\n
```

If JSON parsing fails, yield:
```
data: {"type": "error", "message": "Failed to parse enhancement output", "raw": "..."}\n\n
```

Add CORS headers to allow the HTML test page to call this.

---

## Step 10 — Create `api/refine.py`

`POST /refine` — Non-streaming, returns JSON directly.

**Request body:**
```python
class RefineRequest(BaseModel):
    original_prompt: str
    clarification_qa: list[dict]   # [{"question": "...", "answer": "..."}, ...]
    user_id: str = "anonymous"
    target_ai: str | None = None
```

**Logic:**
1. Load refine system prompt.
2. Build user message:
   ```
   Original prompt: {original_prompt}
   Target AI: {target_ai or "not specified"}
   
   Clarification Q&A:
   Q1: {question}
   A1: {answer}
   Q2: ...
   ```
3. Call `llm.complete(system_prompt, user_message)`.
4. Parse JSON response.
5. Return parsed result directly.

**Response:**
```json
{
  "refined_prompt": "...",
  "key_additions": ["...", "..."],
  "summary": "..."
}
```

---

## Step 11 — Create `api/context.py`

Two endpoints:

**GET /context/{user_id}**
Returns the user's full context object from JSON storage.

**PATCH /context/{user_id}**
Request body:
```python
class ContextUpdateRequest(BaseModel):
    personalization_notes: str | None = None
    preferences: dict | None = None
```
Merges into existing context. Returns updated context.

---

## Step 12 — Create `main.py`

```python
# FastAPI app setup
# Register all routers
# CORS middleware — allow all origins (dev mode)
# Serve static/index.html at GET /
# Health endpoint at GET /health
# Startup: ensure storage/data/ directory exists
```

Include:
- `from fastapi.staticfiles import StaticFiles`
- `from fastapi.responses import FileResponse`
- Mount `/static` for any static files
- Serve `index.html` at root `GET /`
- `/health` returns `{"status": "ok", "model": os.getenv("LLM_MODEL"), "env": os.getenv("APP_ENV")}`

---

## Step 13 — Create `static/index.html`

**This is the most visible part. Build it to be exceptional.**

Single HTML file. No build step. Vanilla JS. Fetch API for HTTP calls. EventSource API for SSE streaming.

### Aesthetic Direction:
Dark theme. Terminal-meets-luxury. Deep navy/charcoal background (`#0a0a0f`). Electric indigo accent (`#6366f1`). Warm gold for highlights (`#f59e0b`). Monospace font for prompts (JetBrains Mono via Google Fonts), clean sans-serif for UI (DM Sans). Subtle gradient mesh backgrounds. Smooth animations on state transitions.

### Layout — Three Panels:

**Panel 1: INPUT (left, 35% width)**
- Large textarea for raw prompt
- Dropdown: Target AI selector (Claude, ChatGPT, GPT-4o, Gemini, Groq/Llama, Cursor, Bolt/V0, Not specified)
- Input: User ID (defaults to "demo-user")
- "Enhance →" button (primary, full width)
- "Clear" button
- Small status indicator showing connection state

**Panel 2: OUTPUT (center, 40% width)**
- Title: "Enhanced Prompt"
- Streaming text display — monospace font, text appears character by character as SSE streams in
- Below the enhanced prompt, show metadata badges in a flex-wrap grid:
  - Intent badge (color-coded by category)
  - Domain badge
  - Quality score as a small progress bar (0–100%)
  - "Target AI Optimized ✓" badge if true
- Enhancements applied: collapsible list of what was done
- Summary: italic, smaller, below everything

**Panel 3: REFINE (right, 25% width)**
- Only shows when clarification_questions is non-empty (hidden by default)
- Title: "Clarify to Refine"
- Shows each clarification question with an input field below it
- "Refine Prompt →" button
- When refinement runs, show the refined prompt in an expandable card below
- Below that, show key_additions as bullet points

### Additional UI Features:
- Streaming indicator: animated dots while streaming is active ("Enhancing...")
- Copy button on both enhanced_prompt and refined_prompt outputs
- Toast notification system (top-right, auto-dismiss after 3s) for copy confirmations and errors
- "Load Example" button that pre-fills the textarea with 4 cycling example prompts (cycle on each click):
  1. `"write me a function to parse JSON"`
  2. `"help me market my new app"`
  3. `"explain machine learning"`
  4. `"i need to improve my website conversion rate"`
- Enhancement history: below Panel 2, a horizontal scroll of the last 5 enhanced prompts as small cards (stored in localStorage). Click to reload into input.
- Stats bar at top: total enhancements in this session, avg quality score, most common domain detected

### Visual Details:
- Smooth fade-in on page load (opacity 0 → 1, 600ms)
- Panel borders: subtle 1px with rgba white opacity
- Textarea and inputs: semi-transparent dark fills with focus glow in indigo
- Buttons: gradient bg (indigo to purple), subtle box shadow, hover scale 1.02
- Badges: pill-shaped, each domain/intent has its own color (define 8–10 distinct colors)
- The streaming text area should have a blinking cursor while streaming
- On mobile: panels stack vertically

### JavaScript Structure:
```javascript
// State
let currentSession = { enhancementCount: 0, avgQuality: 0, domains: [] };
let lastResult = null;
let history = JSON.parse(localStorage.getItem('tv_history') || '[]');

// Core: streamEnhancement()
// - Opens EventSource or uses fetch with ReadableStream
// - Parses SSE events
// - Updates UI in real-time as chunks arrive
// - On "done" event: renders metadata, shows refine panel if questions exist

// Core: refinePrompt()
// - Collects Q&A from refine panel inputs
// - POST to /refine
// - Shows result in refine panel

// Core: updateContext()
// - PATCH /context/{user_id} with preferences

// Utility: copyToClipboard(text)
// Utility: showToast(message, type)
// Utility: addToHistory(result)
// Utility: renderHistory()
// Utility: cycleExamplePrompt()
```

Use `fetch` with `ReadableStream` for SSE rather than `EventSource` so you can POST (EventSource only supports GET). Implement SSE parsing manually — split on `\n\n`, parse `data:` prefix, JSON parse the payload.

---

## Step 14 — Create `CLAUDE.md`

```markdown
# ThinkVelocity — Architecture Notes for Claude

## What This Is
Lean prompt engineering SaaS. Single FastAPI service. Two core functions.
The system prompt IS the product. The model IS the pipeline.

## Core Principle
Do not add complexity without a specific, justified reason.
One LLM call handles: classification, enhancement, target AI optimization,
clarification generation, context integration. No orchestration layers.

## Tech Stack
- FastAPI + Groq (llama-3.3-70b-versatile by default)
- JSON file storage (storage/data/) — swap to Postgres by replacing store.py
- No Redis, no Postgres, no inter-service calls in v1

## Key Files
- core/prompts/enhance_system.md — the main system prompt (modify with care)
- core/llm.py — all LLM interaction
- storage/store.py — all persistence
- static/index.html — complete test UI

## Adding a New LLM Provider
1. Update core/llm.py to add new client
2. Change LLM_MODEL env var
3. That's it

## Adding Postgres
1. Replace storage/store.py with postgres-backed implementation
2. Add DATABASE_URL to .env
3. Run migration (create user_context table matching the JSON schema)
4. Zero changes to API layer

## Enterprise Feature Flags
When adding enterprise:
1. Add org_id to request models
2. Add context_packs table / file
3. In context_loader.py: if org_id → load and inject context pack
4. Add API_SECRET validation middleware in main.py
5. Scope all storage reads/writes by org_id

## DO NOT
- Add more FastAPI services
- Add embedding services
- Add separate classification endpoints
- Add orchestration layers
- Break the streaming SSE contract
```

---

## Step 15 — Create `run.sh`

```bash
#!/bin/bash
echo "Starting ThinkVelocity..."
echo "Model: $LLM_MODEL"
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Make it executable.

---

## Build Execution Order

Execute in this exact order. Complete each step fully before the next:

1. Create directory structure (all directories with `__init__.py` files)
2. `.env.example` and `.env`
3. `requirements.txt`
4. `core/prompts/enhance_system.md` — write with full care, this is the product
5. `core/prompts/refine_system.md`
6. `core/safety.py`
7. `storage/store.py` + create `storage/data/.gitkeep`
8. `core/llm.py`
9. `core/context_loader.py`
10. `api/__init__.py`, `api/enhance.py`, `api/refine.py`, `api/context.py`
11. `main.py`
12. `static/index.html` — build this with full aesthetic care
13. `CLAUDE.md`
14. `run.sh`

After all files are created:
- Run `pip install -r requirements.txt`
- Run `python main.py` or `bash run.sh` to verify startup
- Report any import errors and fix them immediately
- Confirm the server starts on port 8000 and `/health` returns 200

---

## Final Verification Checklist

Before declaring done:

- [ ] `GET /` serves the HTML test page
- [ ] `GET /health` returns JSON with model name
- [ ] `POST /enhance` with `{"prompt": "write a python function to sort a list"}` returns SSE stream with valid JSON in the `done` event
- [ ] The `done` event JSON has all fields: `enhanced_prompt`, `intent`, `domain`, `prompt_quality_score`, `clarification_questions`, `enhancements_applied`, `summary`
- [ ] `POST /refine` works with a clarification Q&A payload
- [ ] `GET /context/demo-user` returns a user context object
- [ ] `PATCH /context/demo-user` with preferences updates the stored file
- [ ] `storage/data/user_demo-user.json` is created after first enhancement
- [ ] The HTML page loads without console errors
- [ ] Streaming text appears in the output panel as chunks arrive
- [ ] Metadata badges render correctly after stream completes
- [ ] Refine panel appears when clarification_questions is non-empty
- [ ] Copy buttons work
- [ ] Example prompt cycling works
- [ ] No Python import errors
- [ ] CORS is configured (HTML page calling the API works from browser)

---

## Common Mistakes to Avoid

1. **SSE with POST**: Do not use `EventSource` in the frontend (GET only). Use `fetch` + `ReadableStream`.
2. **JSON mode with Groq**: Pass `response_format={"type": "json_object"}` to ensure clean JSON. Also instruct the model in the system prompt to return only JSON.
3. **Async file I/O**: Storage reads/writes can be sync (they're fast JSON files). No need for `aiofiles` unless file uploads are added.
4. **CORS**: Must be added before the route registration in main.py, not after.
5. **Path resolution**: Load system prompts using `Path(__file__).parent / "prompts" / "enhance_system.md"` — not relative paths that break depending on where uvicorn is run from.
6. **Groq streaming**: The Groq Python SDK streaming works differently from OpenAI's — use `client.chat.completions.create(stream=True)` and iterate over `chunk.choices[0].delta.content`.
7. **Background tasks**: Use FastAPI's `BackgroundTasks` for the post-enhancement context update. Don't `await` it in the response path.
