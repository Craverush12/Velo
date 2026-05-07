# Velocity MCP — Design Spec
**Date:** 2026-05-08  
**Status:** Approved for implementation

---

## 1. Product Vision

Velocity MCP is an AI-agnostic memory and prompt engineering layer that plugs into every AI conversation surface the user works in. It does three things:

- **Starts** every session with the user's full context injected — no re-explaining yourself
- **Verifies** every prompt before it's sent — transforms vague input into precision-engineered output
- **Remembers** everything across sessions, surfaces, and models — building a personal AI identity that travels with you

One MCP server. Works in Claude Code, Claude Desktop, Cursor, Windsurf, and any future MCP-compatible client.

---

## 2. Architecture

### Approach: FastAPI-native MCP

The existing FastAPI server gains a `/mcp` Streamable HTTP endpoint implementing the MCP protocol over SSE. A thin stdio shim (`mcp_stdio.py`, ~60 lines) proxies stdio MCP calls to that endpoint.

```
AI Surface (Claude Code, Claude Desktop, Cursor…)
        │
        ▼
┌───────────────────────────────┐
│  stdio transport              │  → mcp_stdio.py → FastAPI /mcp
│  HTTP/SSE transport           │  → FastAPI /mcp directly
└───────────────────────────────┘
        │
        ▼
┌───────────────────────────────┐
│  FastAPI MCP router           │  /mcp endpoint
│  4 MCP tools (see §4)        │
└───────────────────────────────┘
        │
        ▼
┌───────────────────────────────┐
│  Existing FastAPI routes      │  POST /enhance, POST /refine,
│  + existing logic             │  GET /context/{id}, PATCH /context/{id}
│  Safety · Quality ceiling     │
│  Normalization · Groq SDK     │
└───────────────────────────────┘
        │
        ▼
┌──────────────┐   ┌─────────────────────────────┐
│ storage/data │   │ Groq · llama-3.3-70b         │
│ JSON files   │   │ JSON mode · streaming        │
└──────────────┘   └─────────────────────────────┘
```

**Why this approach:** Zero code duplication. Every piece of existing logic — LLM calls, quality ceiling, safety redaction, segment normalization, storage — is reused unchanged. The MCP layer is purely a new entry point.

**Constraint:** The stdio shim requires FastAPI to be running. Acceptable for local dev. Users start the server once (`python main.py`) and connect.

---

## 3. Identity

**Config-time, set once.** `VELOCITY_USER_ID` is set in the MCP server config when the user installs Velocity. Every tool call is automatically scoped to that identity. No per-call user_id parameter.

```json
{
  "mcpServers": {
    "velocity": {
      "command": "python",
      "args": ["mcp_stdio.py"],
      "env": {
        "VELOCITY_USER_ID": "arjun",
        "VELOCITY_API_URL": "http://localhost:8000"
      }
    }
  }
}
```

For Claude Code, this goes in `.claude/settings.json`. For Claude Desktop, in `claude_desktop_config.json`.

---

## 4. MCP Tools

All tools resolve `VELOCITY_USER_ID` from environment — never passed by caller.

### 4.1 `enhance_prompt`
**Trigger:** On demand  
**Maps to:** `POST /enhance`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prompt` | string | ✓ | Raw prompt to enhance |
| `target_ai` | string | — | claude · chatgpt · cursor · gemini · bolt · etc. |

**Returns:** Full annotated card — see §6.1

---

### 4.2 `refine_prompt`
**Trigger:** On demand, after enhance_prompt produces clarification questions  
**Maps to:** `POST /refine`

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `original_prompt` | string | ✓ | The original raw prompt |
| `clarification_qa` | array | ✓ | `[{question, answer}]` pairs from enhance output |

**Returns:** Refined annotated card identical in structure to enhance output, plus `key_additions` list

---

### 4.3 `get_my_context`
**Trigger:** On demand  
**Maps to:** `GET /context/{user_id}`

No parameters. Returns signal feed card — see §6.3

---

### 4.4 `inject_context`
**Trigger:** On demand, or auto-called by Claude when the MCP tool description instructs it to call this tool at the start of every conversation (Claude follows tool description instructions reliably)  
**Maps to:** `GET /context/{user_id}` (read-only, formatted for injection)

No parameters. Returns a plain-text block the AI prepends to its session context — see §6.2

---

## 5. Transport

### stdio (Claude Code + Claude Desktop)

`mcp_stdio.py` — thin proxy, no business logic:
- Reads JSON-RPC messages from stdin
- Routes to `VELOCITY_API_URL/mcp`
- Writes responses to stdout
- Handles `initialize`, `tools/list`, `tools/call` methods

### HTTP/SSE (all other clients)

New FastAPI router at `/mcp`:
- `GET /mcp` — MCP server info + capabilities
- `POST /mcp` — JSON-RPC tool dispatch
- `GET /mcp/sse` — SSE stream for streaming tool responses

Uses the `mcp` Python SDK (Anthropic's official package). Mounts alongside existing routers in `main.py`.

---

## 6. Card Surfaces (UI)

All cards follow the Figma **Inline card** pattern exactly: branded header, content body, action footer. Light and dark mode both supported (inherit from host AI surface).

### 6.1 `enhance_prompt` card

**Loading state:**
- Velocity logo + name in header
- Amber pulsing dot + "Engineering…" label
- Three skeleton bars animating

**Result state — content in this order:**

1. **Quality jump bar** — `0.22 → 0.86 · +64 pts · 5 techniques` — green gradient, prominent
2. **Before / After** — stacked rows: original prompt (red tint, labelled "Before") above enhanced prompt (green tint, labelled "After"), monospace font
3. **What Velocity added** — 2–3 insight rows explaining WHY each key technique matters in plain English (not just naming it)
4. **Technique chips** — color-coded pills: Persona Injection (indigo), Chain of Thought (amber), Output Format (emerald), Constraint Definition (rose), Context Framing (violet), etc.

**Footer actions:** Copy prompt (primary) · ✦ Refine further (accent) · 🧠 My context (ghost, right-aligned)

---

### 6.2 `inject_context` card

Fires at session start. Renders as a compact ambient banner (not a full card) inline in the first AI message:

- Pulsing indigo dot
- `[Persona label] · [top domains] · [session count] sessions · [output style preference]`
- Final line: **"No need to re-explain yourself."**

The AI's opening message acknowledges the loaded context and asks what the user is building.

---

### 6.3 `get_my_context` card

**Header:** Velocity Signals · `{N} sessions · {N} domains`

**Section 1 — Token efficiency strip** (green tint, always first):
- Heading: "Token efficiency" + badge: "{savings_pct}% fewer tokens spent" (computed from total_tokens_saved / estimated_without_velocity)
- 3-stat grid: Prompts Enhanced · Tokens Used · Tokens Saved
- Comparison bar: "Without Velocity" (full red) vs "With Velocity" (38% green fill)
- Note: "First-shot accuracy {N}% → fewer retries, less waste"

**Section 2 — Signal list** (3 signals max, each with icon + title + sub + tag):
- Pattern signals: building sprint, domain shift, framework preference forming
- Gap signals: output format missing, no constraint definition, low quality trend
- Positive signals: quality improving, new domain unlocked, streak

**Section 3 — Recent sessions** (last 3, each row):
- Session summary · token savings for that session (green, monospace) · relative timestamp

**Footer actions:** Inject into session (primary) · Reset context (ghost)

---

## 7. Token Savings Calculation

Token savings are estimated, not exact. The formula stored per session:

```
saved = (avg_tokens_without_velocity) - (tokens_used_by_enhance_call)

avg_tokens_without_velocity = estimated from retry rate:
  base_prompt_tokens × (1 + avg_retries_for_quality_score)
  where avg_retries = (1 - quality_score) × 2.5  (empirical constant)

tokens_used_by_enhance_call = tracked from Groq response body (usage.prompt_tokens + usage.completion_tokens)
```

Per-session savings stored in `recent_context[].tokens_saved` in the user JSON. Cumulative totals computed on read.

---

## 8. Storage Changes

Additions to `storage/store.py` and the user JSON schema:

```python
# New fields on each recent_context entry
{
  "intent": "...",
  "domain": "...",
  "summary": "...",
  "framework": "...",
  "placeholder_count": 0,
  "tokens_used": 420,      # NEW: tokens consumed by this enhance call
  "tokens_saved": 680,     # NEW: estimated savings vs unenhanced
  "at": "..."
}

# New top-level fields
{
  "total_tokens_used": 4200,   # NEW: running total
  "total_tokens_saved": 11100  # NEW: running total
}
```

---

## 9. New Files

| File | Purpose |
|------|---------|
| `mcp_stdio.py` | stdio shim — proxies to FastAPI /mcp |
| `api/mcp.py` | FastAPI MCP router — tool dispatch |
| `core/mcp_tools.py` | Tool definitions + response formatters |

### Modified Files

| File | Change |
|------|--------|
| `main.py` | Mount `api/mcp.py` router |
| `storage/store.py` | Add token tracking fields |
| `api/enhance.py` | Capture and store Groq token usage |

---

## 10. Installation UX

After `pip install mcp`, user runs one command:

```bash
python mcp_stdio.py --install
```

This auto-detects Claude Code vs Claude Desktop and writes the correct config block. Prints the config path and confirms connection.

---

## 11. Out of Scope (v1)

- Cloud hosting / remote MCP server (local only)
- Multi-user / team contexts
- ChatGPT native plugin (awaiting OpenAI MCP support GA)
- Web UI changes (existing `static/index.html` unchanged)
- Streaming tool responses (enhance returns full result on done, not chunk-by-chunk)
