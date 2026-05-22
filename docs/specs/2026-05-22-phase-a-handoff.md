# ThinkVelocity — Phase A Handoff
**Date:** 2026-05-22  
**Session:** UI unification + modes + model picker + Google Workspace integration  
**Status:** Ready for implementation in a fresh session

---

## What was done in the session that created this doc

1. **Deployed to production** — AWS Lightsail `13.234.212.59`, nginx → Docker container at `api.thinkvelocity.in`
2. **Synced all new API modules** — `api/agentic.py`, `api/connectors.py`, `api/profile.py`, `api/neuro.py`, `api/personalization.py` + corresponding core files
3. **Profile page redesigned** — removed clashing dark `--velocity-*` theme, rebuilt with app theme, added tab UX (Questionnaire / Import Data), exposed auto-ingest API
4. **Global responsiveness** — mobile sidebar with hamburger toggle, breakpoints at 860px + 600px
5. **Version tab** — added to sidebar, documents all features end-to-end
6. **Server deployment workflow** — `tar | ssh → docker compose build → docker compose up -d`; static files can be hot-patched with `docker cp`

---

## Deployment info

| Item | Value |
|------|-------|
| Server | AWS Lightsail, Ubuntu, `13.234.212.59` |
| SSH key | `C:\Users\Arjun\Desktop\ThinkVelocity\velo-python.pem` |
| SSH user | `ubuntu` |
| App dir (server) | `/opt/thinkvelocity/` |
| Container name | `thinkvelocity-thinkvelocity-1` |
| Public URL | `https://api.thinkvelocity.in` |
| Live domain via | nginx → `127.0.0.1:8000` → Docker |
| Deploy command | `cd /opt/thinkvelocity && sudo docker compose build && sudo docker compose up -d` |
| Hot-patch static | `sudo docker cp static/index.html thinkvelocity-thinkvelocity-1:/app/static/index.html` |

---

## Current architecture snapshot

```
FastAPI (main.py, version 2.0.0)
├── /enhance              — technique-annotated prompt enhancement
├── /refine               — iterative refinement loop
├── /intent/confirm       — intent detection (domain, goal, techniques)
├── /context/:userId      — memory read/write (flat JSON in /data)
├── /cothinker/*          — voice loop (Whisper → turn → finalize)
├── /agentic/chat         — streaming SSE chat
├── /connectors/query     — Google Workspace (Gmail/Calendar/Drive) via Groq Responses API
├── /neuro/score          — cognitive scoring rubric
├── /personalization/:uid/extract — preference extraction
├── /profile/auto-ingest  — LLM parses raw text → persona
├── /mcp/*                — MCP stdio server
└── /diagnostics/*        — health checks

LLM: Groq SDK — llama-3.3-70b-versatile (default)
Storage: flat JSON files in /data (STORAGE_PATH env var)
Internal modes: "normal" | "caveman" (defined in core/contracts.py + core/prompt_modes.py)
```

---

## The full 6-subsystem plan

| Phase | # | Subsystem | Status |
|-------|---|-----------|--------|
| A | 1 | UI unification: Enhance + CoThinker single interface | **TODO** |
| A | 2 | Compare with intent confirmation + multi-model picker (Groq catalog) | **TODO** |
| A | 3 | User-facing modes: Research / Fast Build / Media (map to internal) | **TODO** |
| A | 4 | Google Workspace woven into Enhance + CoThinker (context injection) | **TODO** |
| B | 5 | Embeddings — semantic retrieval, replace flat-JSON context | later |
| B | 6 | PostgreSQL — schema, migrations, data migration from JSON | later |
| B | 7 | Cron jobs — proactive suggestions, auto prompts (depends on #6) | later |

---

## Phase A — detailed spec

### A1 · UI unification

**Goal:** The sidebar no longer has separate "Enhance" and "CoThinker" buttons. There is one workspace. At the top of the workspace is a two-option selector:

```
[ ✦ Enhance ]   [ 🎙 CoThinker ]
```

Clicking switches the input area. Everything else (mode strip, output, details panel) stays the same. The existing `setEnhMode('enhance')` / `setEnhMode('cothinker')` JS already handles most of this — just remove the duplicate sidebar entry and make the in-workspace toggle the canonical control.

**Remove from sidebar:** the separate CoThinker and Chat (agentic) nav buttons.  
**Add to workspace header:** a clean two-tab mode switcher (Enhance / CoThinker).  
The Chat/Agentic mode can remain as an `enhTab` inside the workspace since it's already there.

---

### A2 · Compare with intent confirmation + model picker

**Current:** Compare runs two models back to back, no intent check first.  
**New:**
1. Before running compare, if intent hasn't been confirmed yet for the current prompt, run `POST /intent/confirm` and show the Q&A panel (already exists as `intent-qa-panel`). User answers, then compare proceeds.
2. The compare modal/UI shows a **model picker** — let user choose which two Groq models to compare.

**Groq models to expose (as of May 2026):**

| Model ID | Label | Best for |
|----------|-------|----------|
| `llama-3.3-70b-versatile` | Llama 3.3 70B | General (default) |
| `llama-3.1-8b-instant` | Llama 3.1 8B | Fast / lightweight |
| `llama3-70b-8192` | Llama 3 70B | Balanced |
| `llama3-8b-8192` | Llama 3 8B | Fast |
| `mixtral-8x7b-32768` | Mixtral 8x7B | Long context |
| `gemma2-9b-it` | Gemma 2 9B | Concise |
| `qwen-qwq-32b` | Qwen QwQ 32B | Reasoning/research |
| `deepseek-r1-distill-llama-70b` | DeepSeek R1 70B | Deep reasoning |
| `compound-beta` | Compound Beta | Agentic/web search |

Backend: add `model_override: str | None` to `EnhanceRequest` so the caller can specify which Groq model to use. In `core/llm.py`, accept `model` param and pass to Groq client.

---

### A3 · User-facing modes: Research / Fast Build / Media

**Current internal modes:** `"normal"` | `"caveman"`  
**New user-facing modes (displayed in UI):** Research · Fast Build · Media

**Mapping:**

| User-facing | Internal mode | Behaviour change |
|-------------|--------------|------------------|
| Research | `normal` | Max depth, citations style, chain-of-thought, academic tone overlay |
| Fast Build | `normal` | Speed-optimised: shorter prompts, code-first, minimal explanation |
| Media | `caveman` | Visual/creative: punchy, sensory language, no jargon overlay |

Implementation:
- Add `"research"`, `"fast_build"`, `"media"` to `PROMPT_MODE_VALUES` in `core/contracts.py`
- Add overlay prompt files: `core/prompts/enhance_research_overlay.md`, `enhance_fast_build_overlay.md`, `enhance_media_overlay.md`
- Update `core/prompt_modes.py` to load overlays for new modes
- UI: replace the internal "Normal / Caveman" mode strip with "Research / Fast Build / Media" tabs

---

### A4 · Google Workspace woven into Enhance + CoThinker

**Current:** Connectors are a completely separate page (`/connectors/query`). User has to go there separately and results don't flow into enhancement.

**New:** When Google Workspace is connected (OAuth token present in localStorage), a small "Context from Workspace" toggle appears above the enhance input. When on:
- Before calling `/enhance`, the frontend calls `/connectors/context-gather` (new endpoint) with the user's prompt
- The backend queries Gmail/Calendar/Drive for relevant context snippets (short summaries, no full email bodies)
- The snippets are injected as additional context into the enhance request (`context_override` field)
- Same flow for CoThinker finalize step

**New backend endpoint:** `POST /connectors/context-gather`  
Input: `{ prompt, access_token, connectors: ["gmail","calendar","drive"] }`  
Output: `{ snippets: [{ source, summary, relevance }] }`  
Logic: runs parallel queries to each enabled connector, returns top-3 most relevant snippets.

**Auth:** OAuth token stored in browser localStorage only (no server-side storage). User pastes it manually for now (same as current connector page).

---

## Key files to read before implementing

```
static/index.html          — entire frontend (single file, ~4500 lines)
core/contracts.py          — PromptMode, TargetAI, PROMPT_MODE_VALUES
core/prompt_modes.py       — PromptBundle, overlay loading logic
core/llm.py                — complete(), stream_completion(), agentic_stream()
api/enhance.py             — EnhanceRequest, enhance endpoint
api/connectors.py          — connector_query endpoint
core/prompts/enhance_system.md     — base enhance prompt
core/prompts/enhance_caveman_overlay.md  — caveman overlay pattern to follow
```

---

## Copy-paste prompt for fresh Claude session

See the section below — this is the exact prompt to paste.
