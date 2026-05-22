# Fresh-session prompt — paste this exactly into a new Claude Code chat

---

You are working on **ThinkVelocity**, a self-hosted prompt engineering SaaS. Read `docs/specs/2026-05-22-phase-a-handoff.md` first — it has the full architecture snapshot, deployment info, and the detailed spec for everything below.

## Your task: implement Phase A (4 subsystems)

Work through these in order. Commit after each one.

---

### A1 — Unify the Enhance + CoThinker interface

**What to do:**
- Remove the separate CoThinker and Chat nav buttons from the sidebar (`static/index.html`)
- Keep a single "Enhance" nav entry that lands on the workspace
- The existing in-workspace mode tab strip (`enhTab-enhance`, `enhTab-cothinker`, `enhTab-chat`) is already correct — just make it the canonical control and style it more prominently as the primary workspace switcher
- The sidebar should have: Enhance, Memory, Profile, Connectors, Diagnostics, Version

**Files:** `static/index.html` only

---

### A2 — User-facing modes: Research / Fast Build / Media

**What to do (backend):**
1. In `core/contracts.py`: add `"research"`, `"fast_build"`, `"media"` to `PROMPT_MODE_VALUES` and `PromptMode` Literal
2. Add aliases in `normalize_prompt_mode`: `"fast"` → `"fast_build"`, `"build"` → `"fast_build"`
3. Create three overlay prompt files (model them on `core/prompts/enhance_caveman_overlay.md`):
   - `core/prompts/enhance_research_overlay.md` — academic depth, citations style, chain-of-thought, "assume expert reader"
   - `core/prompts/enhance_fast_build_overlay.md` — code-first, bullet points only, no preamble, minimal explanation, "ship it" energy
   - `core/prompts/enhance_media_overlay.md` — visual/sensory language, punchy, emotional hooks, no jargon, "make it land"
4. In `core/prompt_modes.py`: add `_OVERLAY_FILES` entries for the three new modes
5. In `api/enhance.py`: add `model_override: str | None = None` to `EnhanceRequest`; pass it through to `core/llm.py`
6. In `core/llm.py`: accept `model: str | None = None` in `complete()` and `stream_completion()`; use it instead of `_MODEL` when provided

**What to do (frontend):**
- Replace the current "Normal / Caveman" mode strip in the enhance workspace with three tabs: **Research · Fast Build · Media**
- Map them: Research → `research`, Fast Build → `fast_build`, Media → `media`
- Send the selected mode as `prompt_mode` in every `/enhance` and `/refine` call

---

### A3 — Compare with intent confirmation + model picker

**What to do (backend):**
- `model_override` from A2 backend is the only backend change needed here

**What to do (frontend):**
1. Before running a compare (when user clicks Compare), check if `state.lastIntent` is null or has low confidence
2. If intent not confirmed: run `POST /intent/confirm` first, show the existing `intent-qa-panel`, wait for user to submit answers, then proceed with compare
3. Add a **model picker** UI in the compare trigger area — two dropdowns (Model A, Model B), populated with this list:

```
llama-3.3-70b-versatile  →  "Llama 3.3 70B (default)"
llama-3.1-8b-instant     →  "Llama 3.1 8B (fast)"
llama3-70b-8192          →  "Llama 3 70B"
mixtral-8x7b-32768       →  "Mixtral 8x7B (long ctx)"
gemma2-9b-it             →  "Gemma 2 9B"
qwen-qwq-32b             →  "Qwen QwQ 32B (reasoning)"
deepseek-r1-distill-llama-70b → "DeepSeek R1 70B"
compound-beta            →  "Compound β (agentic)"
```

4. When compare runs, pass `model_override: "<selected model>"` in each of the two enhance requests

---

### A4 — Google Workspace context injection into Enhance + CoThinker

**What to do (backend):**
Add `POST /connectors/context-gather` to `api/connectors.py`:
- Input: `{ prompt: str, access_token: str, connectors: list[str] }`
- For each connector in the list, call the existing Groq Responses API pattern (same as `connector_query`) but with a short retrieval prompt: `"Find 2-3 short snippets most relevant to: {prompt}. Return as JSON array of {source, summary}."`
- Run connector calls in parallel with `asyncio.gather`
- Return: `{ snippets: [{ source: "Gmail", summary: "..." }, ...] }`

**What to do (frontend):**
1. Add a small "Workspace context" toggle row above the enhance input (only visible when `localStorage.getItem('ws_access_token')` is set)
2. Add a "Connect Google Workspace" button in the Connectors page that saves the token to localStorage — this is already partially there, just wire the save
3. When the toggle is on and user hits Enhance:
   - Call `POST /connectors/context-gather` with the prompt and token
   - Append the returned snippets as a `\n\n---\nWorkspace context:\n{snippets}` block to the prompt text before sending to `/enhance`
4. Same injection for CoThinker finalize step

---

## After all four are done

1. Commit all changes with a descriptive message
2. Deploy to the server:
```bash
# Sync code
tar czf - --exclude='.env' --exclude='.git' --exclude='__pycache__' --exclude='*.pem' --exclude='.claude' --exclude='storage/data' --exclude='*.pyc' . | ssh -i "C:/Users/Arjun/Desktop/ThinkVelocity/velo-python.pem" -o StrictHostKeyChecking=no ubuntu@13.234.212.59 "cd /opt/thinkvelocity && tar xzf -"

# Rebuild and restart
ssh -i "C:/Users/Arjun/Desktop/ThinkVelocity/velo-python.pem" -o StrictHostKeyChecking=no ubuntu@13.234.212.59 "cd /opt/thinkvelocity && sudo docker compose build && sudo docker compose up -d"

# Verify
ssh -i "C:/Users/Arjun/Desktop/ThinkVelocity/velo-python.pem" -o StrictHostKeyChecking=no ubuntu@13.234.212.59 "curl -s http://localhost:8000/health"
```

## Key constraints (from CLAUDE.md)
- No placeholder code — every file must be complete and runnable
- Single FastAPI app only
- System prompts live in `core/prompts/` as `.md` files, loaded with explicit UTF-8 decoding
- Use `response_format={"type": "json_object"}` on all Groq calls
- CORS must allow all origins
- LLM: Groq API via `groq` Python SDK. Key is in `.env` as `GROQ_API_KEY`
