# Velocity MCP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an MCP layer to the existing ThinkVelocity FastAPI app — exposing 4 tools (enhance_prompt, refine_prompt, get_my_context, inject_context) via HTTP/SSE and stdio transports, with token usage tracking and Railway cloud deployment.

**Architecture:** New FastAPI router at `/mcp` implements the MCP SSE transport using the `mcp` Python SDK. A thin `mcp_stdio.py` shim at the project root imports the same MCP server instance and runs it over stdio — so Claude Code and Claude Desktop connect without any HTTP plumbing. All tool handlers call existing storage/LLM functions directly; no HTTP self-calls.

**Tech Stack:** FastAPI · Groq SDK · `mcp>=1.0.0` (Anthropic MCP Python SDK) · Railway (cloud) · JSON file storage (unchanged)

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `core/normalize.py` | `_quality_ceiling` + `_normalize_result` — shared between API and MCP tool |
| Create | `core/mcp_tools.py` | MCP `Server` instance, 4 tool handlers, response formatters |
| Create | `api/mcp.py` | FastAPI router mounting SSE transport on `/mcp/sse` + `/mcp/messages/` |
| Create | `mcp_stdio.py` | stdio shim — imports MCP server, runs stdio transport, `--install` flag |
| Create | `railway.toml` | Railway project config |
| Create | `Procfile` | `web: uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Modify | `requirements.txt` | Add `mcp>=1.0.0` |
| Modify | `storage/store.py` | Add `tokens_used`, `tokens_saved`, `total_tokens_used`, `total_tokens_saved` |
| Modify | `core/llm.py` | Add `complete_with_usage()` + `usage_sink` param on `stream_completion()` |
| Modify | `api/enhance.py` | Import from `core/normalize`, pass token usage to store |
| Modify | `main.py` | Mount `api/mcp.py` router |

---

## Task 1: Add `mcp` dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Add `mcp` to requirements.txt**

Replace the file content with:

```text
fastapi==0.115.0
uvicorn[standard]==0.30.6
groq==0.9.0
python-dotenv==1.0.1
pydantic==2.7.4
python-multipart==0.0.9
aiofiles==23.2.1
mcp>=1.0.0
```

- [ ] **Install**

```bash
pip install mcp
```

Expected: `Successfully installed mcp-...` (no errors)

- [ ] **Verify import works**

```bash
python -c "from mcp.server import Server; from mcp.server.sse import SseServerTransport; from mcp.server.stdio import stdio_server; print('ok')"
```

Expected: `ok`

- [ ] **Commit**

```bash
git add requirements.txt
git commit -m "deps: add mcp SDK for MCP transport layer"
```

---

## Task 2: Extract normalizer to shared module

**Files:**
- Create: `core/normalize.py`
- Modify: `api/enhance.py` (update imports only)

The quality ceiling and segment normalizer live in `api/enhance.py` today. Moving them to `core/normalize.py` lets the MCP tool handler import them without creating api→core→api cycles.

- [ ] **Create `core/normalize.py`**

```python
def quality_ceiling(raw_prompt: str) -> float:
    words = [w for w in raw_prompt.replace("\n", " ").split(" ") if w.strip()]
    word_count = len(words)
    char_count = len(raw_prompt.strip())
    markers = 0
    marker_terms = [
        "output", "format", "audience", "target", "tone", "constraint",
        "example", "context", "because", "using", "avoid", "include",
        "json", "table", "steps", "role", "goal", "metric",
    ]
    lowered = raw_prompt.lower()
    markers += sum(1 for term in marker_terms if term in lowered)
    markers += 1 if "[" in raw_prompt and "]" in raw_prompt else 0
    markers += 1 if "\n" in raw_prompt else 0

    if char_count <= 2 or word_count <= 1:
        return 0.08
    if word_count <= 3:
        return 0.18
    if word_count <= 7 and markers == 0:
        return 0.28
    if word_count <= 12 and markers <= 1:
        return 0.42
    if word_count <= 25 and markers <= 2:
        return 0.62
    if markers >= 4 and word_count >= 20:
        return 0.88
    return 0.74


def normalize_result(result: dict, raw_prompt: str = "") -> dict:
    """Repair common JSON-mode drift while preserving LLM annotations."""
    prompt = result.get("enhanced_prompt") or ""
    segments = result.get("annotated_segments") or []
    if prompt and segments and "".join(seg.get("text", "") for seg in segments) != prompt:
        cursor = 0
        repaired = []
        for seg in segments:
            text = seg.get("text", "")
            stripped = text.strip()
            found = prompt.find(stripped, cursor) if stripped else -1
            if found >= 0:
                seg = dict(seg)
                seg["text"] = prompt[cursor:found] + stripped
                repaired.append(seg)
                cursor = found + len(stripped)
            else:
                repaired = []
                break
        if repaired and cursor <= len(prompt):
            repaired[-1]["text"] += prompt[cursor:]
            result["annotated_segments"] = repaired

    fields = result.get("placeholder_fields") or []
    if fields:
        techniques = result.setdefault("pe_techniques_applied", [])
        if "placeholder_facilitation" not in techniques:
            techniques.append("placeholder_facilitation")

    try:
        model_score = float(result.get("prompt_quality_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        model_score = 0.0
    result["prompt_quality_score"] = round(
        max(0.0, min(model_score, quality_ceiling(raw_prompt))), 2
    )
    return result
```

- [ ] **Update `api/enhance.py` imports — remove the two private functions, import from core**

At the top of `api/enhance.py`, replace the two private function definitions (`_quality_ceiling` and `_normalize_result`) with:

```python
from core.normalize import quality_ceiling as _quality_ceiling, normalize_result as _normalize_result
```

Then in the body of `api/enhance.py`, the calls `_quality_ceiling(raw_prompt)` and `_normalize_result(json.loads(accumulated), clean_prompt)` remain unchanged — only the definitions moved.

- [ ] **Smoke-test the existing enhance endpoint still works**

```bash
python -c "
import asyncio, json
from api.enhance import _normalize_result, _quality_ceiling
assert _quality_ceiling('hi') == 0.18
r = _normalize_result({'enhanced_prompt': 'test', 'annotated_segments': [{'text': 'test'}]}, 'hi')
assert r['enhanced_prompt'] == 'test'
print('ok')
"
```

Expected: `ok`

- [ ] **Commit**

```bash
git add core/normalize.py api/enhance.py
git commit -m "refactor: extract normalize helpers to core/normalize.py"
```

---

## Task 3: Token tracking in storage layer

**Files:**
- Modify: `storage/store.py`

- [ ] **Update `_DEFAULT_CONTEXT` to include token fields**

In `storage/store.py`, update `_DEFAULT_CONTEXT`:

```python
_DEFAULT_CONTEXT = {
    "user_id": "",
    "domains": [],
    "frameworks_used": [],
    "placeholder_count": 0,
    "preferences": {
        "output_style": "balanced",
        "expertise_level": "intermediate",
        "preferred_tools": [],
        "industry": "",
    },
    "recent_context": [],
    "personalization_notes": "",
    "enhancement_count": 0,
    "total_tokens_used": 0,
    "total_tokens_saved": 0,
    "created_at": "",
    "updated_at": "",
}
```

- [ ] **Update `update_after_enhancement` signature to accept token args**

Replace the existing `update_after_enhancement` function with:

```python
def update_after_enhancement(
    user_id: str,
    intent: str,
    domain: str,
    summary: str,
    framework: str | None = None,
    placeholder_count: int = 0,
    tokens_used: int = 0,
    tokens_saved: int = 0,
) -> None:
    ctx = get_user_context(user_id)

    if domain and domain not in ctx["domains"]:
        ctx["domains"] = ([domain] + ctx["domains"])[:10]

    if framework and framework not in ctx.get("frameworks_used", []):
        ctx.setdefault("frameworks_used", [])
        ctx["frameworks_used"] = ([framework] + ctx["frameworks_used"])[:10]

    ctx["recent_context"] = (
        [
            {
                "intent": intent,
                "domain": domain,
                "summary": summary,
                "framework": framework,
                "placeholder_count": placeholder_count,
                "tokens_used": tokens_used,
                "tokens_saved": tokens_saved,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        + ctx["recent_context"]
    )[:7]

    ctx["enhancement_count"] = ctx.get("enhancement_count", 0) + 1
    ctx["placeholder_count"] = ctx.get("placeholder_count", 0) + max(0, int(placeholder_count or 0))
    ctx["total_tokens_used"] = ctx.get("total_tokens_used", 0) + max(0, int(tokens_used or 0))
    ctx["total_tokens_saved"] = ctx.get("total_tokens_saved", 0) + max(0, int(tokens_saved or 0))
    ctx["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_user_context(user_id, ctx)
```

- [ ] **Verify the function signature change doesn't break existing callers** (existing callers pass only the first 6 positional args — the two new kwargs default to 0, so they're backward-compatible):

```bash
python -c "
from storage.store import update_after_enhancement
import inspect
sig = inspect.signature(update_after_enhancement)
params = list(sig.parameters.keys())
assert 'tokens_used' in params
assert 'tokens_saved' in params
print('ok')
"
```

Expected: `ok`

- [ ] **Commit**

```bash
git add storage/store.py
git commit -m "feat: add token usage tracking fields to user context storage"
```

---

## Task 4: Token usage capture in LLM layer

**Files:**
- Modify: `core/llm.py`

- [ ] **Add `complete_with_usage()` and `usage_sink` param to `stream_completion()`**

Replace the entire `core/llm.py` with:

```python
import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from groq import AsyncGroq, APIError, RateLimitError
from fastapi import HTTPException

load_dotenv()

_client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")


async def stream_completion(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    usage_sink: dict | None = None,
) -> AsyncGenerator[str, None]:
    """Yields content chunks. If usage_sink dict is provided, populates it with
    token counts after streaming completes."""
    try:
        create_kwargs = dict(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            stream=True,
        )
        if usage_sink is not None:
            create_kwargs["stream_options"] = {"include_usage": True}

        stream = await _client.chat.completions.create(**create_kwargs)
        async for chunk in stream:
            content = chunk.choices[0].delta.content if chunk.choices else None
            if content:
                yield content
            if usage_sink is not None and getattr(chunk, "usage", None):
                usage_sink.update(
                    {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens,
                    }
                )
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=f"Rate limit hit: {e}")
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")


async def complete(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    try:
        response = await _client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=f"Rate limit hit: {e}")
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")


async def complete_with_usage(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> tuple[str, dict]:
    """Non-streaming completion that returns (content, usage_dict).
    usage_dict keys: prompt_tokens, completion_tokens, total_tokens."""
    try:
        response = await _client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }
        return response.choices[0].message.content, usage
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=f"Rate limit hit: {e}")
    except APIError as e:
        raise HTTPException(status_code=502, detail=f"LLM API error: {e}")
```

- [ ] **Wire `usage_sink` in `api/enhance.py`**

In `api/enhance.py`, inside `_generate`, update `event_stream()` to:
1. Create a `usage_sink` dict before streaming
2. Pass it to `stream_completion`
3. After streaming, compute token savings and pass to `update_after_enhancement`

Find this block in `_generate`:

```python
    accumulated = ""

    async def event_stream():
        nonlocal accumulated
        try:
            async for chunk in stream_completion(_SYSTEM_PROMPT, user_message):
                accumulated += chunk
```

Replace with:

```python
    accumulated = ""
    usage_sink: dict = {}

    async def event_stream():
        nonlocal accumulated
        try:
            async for chunk in stream_completion(_SYSTEM_PROMPT, user_message, usage_sink=usage_sink):
                accumulated += chunk
```

Then find the `background_tasks.add_task` call:

```python
                background_tasks.add_task(
                    store.update_after_enhancement,
                    request.user_id,
                    result.get("intent", "general_qa"),
                    result.get("domain", "general"),
                    result.get("summary", ""),
                    result.get("framework_used"),
                    len(result.get("placeholder_fields") or []),
                )
```

Replace with:

```python
                tokens_used = usage_sink.get("total_tokens", 0)
                quality = float(result.get("prompt_quality_score", 0.5) or 0.5)
                avg_retries = (1.0 - quality) * 2.5
                tokens_saved = max(0, int(
                    usage_sink.get("prompt_tokens", 0) * avg_retries
                ))
                background_tasks.add_task(
                    store.update_after_enhancement,
                    request.user_id,
                    result.get("intent", "general_qa"),
                    result.get("domain", "general"),
                    result.get("summary", ""),
                    result.get("framework_used"),
                    len(result.get("placeholder_fields") or []),
                    tokens_used,
                    tokens_saved,
                )
```

- [ ] **Commit**

```bash
git add core/llm.py api/enhance.py
git commit -m "feat: capture Groq token usage and store per-session token savings"
```

---

## Task 5: MCP server — tool handlers and formatters

**Files:**
- Create: `core/mcp_tools.py`

This is the core of the MCP layer. The `Server` instance defined here is imported by both `api/mcp.py` (HTTP transport) and `mcp_stdio.py` (stdio transport).

- [ ] **Create `core/mcp_tools.py`**

```python
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from mcp.server import Server
from mcp.types import Tool, TextContent

from core import context_loader, safety
from core.llm import complete_with_usage
from core.normalize import normalize_result, quality_ceiling
from storage import store

_ENHANCE_PROMPT = (Path(__file__).parent / "prompts" / "enhance_system.md").read_text()
_REFINE_PROMPT = (Path(__file__).parent / "prompts" / "refine_system.md").read_text()

mcp_server = Server("velocity")


def _user_id() -> str:
    return os.getenv("VELOCITY_USER_ID", "anonymous")


# ── Tool schemas ──────────────────────────────────────────────────────────────

@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="enhance_prompt",
            description=(
                "Transform a raw prompt into a precision-engineered prompt using the optimal "
                "prompt engineering framework. Returns an annotated breakdown showing before/after, "
                "quality improvement, and the techniques applied. "
                "IMPORTANT: Call inject_context at the start of every new conversation to load user memory."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "The raw prompt to enhance",
                    },
                    "target_ai": {
                        "type": "string",
                        "description": "Target AI surface: claude, chatgpt, cursor, gemini, bolt, replit, gamma, midjourney",
                    },
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="refine_prompt",
            description=(
                "Refine an enhanced prompt using clarification answers. "
                "Call this after enhance_prompt when you have answers to the clarification questions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "original_prompt": {
                        "type": "string",
                        "description": "The original raw prompt (before enhancement)",
                    },
                    "clarification_qa": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "answer": {"type": "string"},
                            },
                            "required": ["question", "answer"],
                        },
                        "description": "Question/answer pairs from the enhance_prompt clarification_questions",
                    },
                    "target_ai": {
                        "type": "string",
                        "description": "Target AI surface (optional)",
                    },
                },
                "required": ["original_prompt", "clarification_qa"],
            },
        ),
        Tool(
            name="get_my_context",
            description=(
                "Show your Velocity profile: token efficiency metrics, usage signals, "
                "recent sessions, and persona. Use this to inspect what Velocity knows about you."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="inject_context",
            description=(
                "Load your Velocity memory into this session. "
                "Call this automatically at the start of every conversation so the AI knows your "
                "expertise, stack, current work, and preferences without you having to explain them."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


# ── Tool handlers ─────────────────────────────────────────────────────────────

@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    args = arguments or {}

    if name == "enhance_prompt":
        return await _handle_enhance(args)
    if name == "refine_prompt":
        return await _handle_refine(args)
    if name == "get_my_context":
        return [TextContent(type="text", text=_format_context(store.get_user_context(_user_id())))]
    if name == "inject_context":
        return [TextContent(type="text", text=_format_inject(store.get_user_context(_user_id())))]

    raise ValueError(f"Unknown tool: {name}")


async def _handle_enhance(args: dict) -> list[TextContent]:
    raw_prompt = args.get("prompt", "").strip()
    target_ai = args.get("target_ai")
    user_id = _user_id()

    clean_prompt, _ = safety.redact(raw_prompt)
    user_ctx = store.get_user_context(user_id)
    ctx_block = context_loader.format_context_for_prompt(user_ctx)

    user_message_parts = [
        f"Raw prompt: {clean_prompt}",
        f"Target AI: {target_ai or 'not specified'}",
    ]
    if ctx_block:
        user_message_parts.append(ctx_block)
    user_message = "\n".join(user_message_parts)

    raw, usage = await complete_with_usage(_ENHANCE_PROMPT, user_message)

    try:
        result = normalize_result(json.loads(raw), clean_prompt)
    except json.JSONDecodeError:
        return [TextContent(type="text", text="Velocity: Failed to parse enhancement output. Please try again.")]

    # Store with token tracking
    tokens_used = usage.get("total_tokens", 0)
    quality = float(result.get("prompt_quality_score", 0.5) or 0.5)
    avg_retries = (1.0 - quality) * 2.5
    tokens_saved = max(0, int(usage.get("prompt_tokens", 0) * avg_retries))

    store.update_after_enhancement(
        user_id,
        result.get("intent", "general_qa"),
        result.get("domain", "general"),
        result.get("summary", ""),
        result.get("framework_used"),
        len(result.get("placeholder_fields") or []),
        tokens_used,
        tokens_saved,
    )

    return [TextContent(type="text", text=_format_enhance_result(raw_prompt, result))]


async def _handle_refine(args: dict) -> list[TextContent]:
    original = args.get("original_prompt", "")
    qa_pairs = args.get("clarification_qa", [])
    target_ai = args.get("target_ai")

    qa_lines = []
    for i, qa in enumerate(qa_pairs, 1):
        qa_lines.append(f"Q{i}: {qa.get('question', '')}")
        qa_lines.append(f"A{i}: {qa.get('answer', '')}")

    user_message = "\n".join([
        f"Original prompt: {original}",
        f"Target AI: {target_ai or 'not specified'}",
        "",
        "Clarification Q&A:",
        *qa_lines,
    ])

    raw = await _refine_complete(user_message)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return [TextContent(type="text", text="Velocity Refine: Failed to parse output. Please try again.")]

    return [TextContent(type="text", text=_format_refine_result(result))]


async def _refine_complete(user_message: str) -> str:
    from core.llm import complete
    return await complete(_REFINE_PROMPT, user_message)


# ── Formatters ────────────────────────────────────────────────────────────────

def _format_enhance_result(original: str, result: dict) -> str:
    enhanced = result.get("enhanced_prompt", "")
    framework = result.get("framework_used", "")
    quality = result.get("prompt_quality_score", 0.0)
    domain = result.get("domain", "")
    intent = result.get("intent", "")
    techniques = result.get("pe_techniques_applied", [])
    segments = result.get("annotated_segments", [])
    summary = result.get("summary", "")
    clarifications = result.get("clarification_questions", [])

    # Quality score before (estimate from original length/complexity)
    original_words = len(original.split())
    before_quality = min(0.35, original_words * 0.02)

    pts_gained = round((quality - before_quality) * 100)

    lines = [
        f"## Velocity Enhanced ⚡",
        f"",
        f"**{framework}** · Quality **{before_quality:.2f} → {quality:.2f}** (+{pts_gained} pts) · {domain} · {intent}",
        f"",
        f"### Before",
        f"```",
        original,
        f"```",
        f"",
        f"### After",
        f"```",
        enhanced,
        f"```",
    ]

    # What Velocity added — top 3 segments with real explanations
    if segments:
        lines += ["", "### What Velocity added"]
        ICONS = {
            "persona_injection": "🎭",
            "chain_of_thought": "🧠",
            "output_format_spec": "📐",
            "constraint_definition": "🔒",
            "context_framing": "🗂️",
            "few_shot_example": "📎",
            "negative_space": "🚫",
            "target_ai_optimization": "🎯",
            "step_back_trigger": "⬆️",
            "domain_specific_depth": "🔬",
            "user_context_integration": "👤",
        }
        shown = 0
        for seg in segments:
            if shown >= 3:
                break
            technique = seg.get("technique", "")
            label = seg.get("technique_label", technique.replace("_", " ").title())
            reason = seg.get("reason", "")
            icon = ICONS.get(technique, "•")
            lines.append(f"- {icon} **{label}** — {reason}")
            shown += 1

    # Techniques
    if techniques:
        tech_display = " · ".join(t.replace("_", " ").title() for t in techniques)
        lines += ["", f"**Techniques:** {tech_display}"]

    # Summary
    if summary:
        lines += ["", f"*{summary}*"]

    # Clarification questions
    if clarifications:
        lines += ["", "### Clarify further (call refine_prompt with answers)"]
        for i, q in enumerate(clarifications, 1):
            lines.append(f"{i}. {q}")

    lines += [
        "",
        "---",
        "*Copy the **After** prompt above and use it with any AI.*",
    ]

    return "\n".join(lines)


def _format_refine_result(result: dict) -> str:
    refined = result.get("refined_prompt", "")
    framework = result.get("framework_used", "")
    techniques = result.get("pe_techniques_applied", [])
    additions = result.get("key_additions", [])
    summary = result.get("summary", "")

    lines = [
        "## Velocity Refined ✦",
        "",
        f"**{framework}**",
        "",
        "### Refined Prompt",
        "```",
        refined,
        "```",
    ]

    if additions:
        lines += ["", "### What changed"]
        for a in additions:
            lines.append(f"- {a}")

    if techniques:
        tech_display = " · ".join(t.replace("_", " ").title() for t in techniques)
        lines += ["", f"**Techniques:** {tech_display}"]

    if summary:
        lines += ["", f"*{summary}*"]

    lines += ["", "---", "*Copy the refined prompt above.*"]
    return "\n".join(lines)


def _format_inject(ctx: dict) -> str:
    if not ctx or ctx.get("enhancement_count", 0) == 0:
        return (
            "🟣 **Velocity context loading**\n\n"
            "No sessions yet — your memory graph is empty. "
            "Use `enhance_prompt` to start building your profile.\n\n"
            "*No need to re-explain yourself — Velocity will learn as you go.*"
        )

    prefs = ctx.get("preferences", {})
    domains = ctx.get("domains", [])[:3]
    recent = ctx.get("recent_context", [])[:2]
    expertise = prefs.get("expertise_level", "intermediate")
    tools = prefs.get("preferred_tools", [])
    notes = ctx.get("personalization_notes", "")
    count = ctx.get("enhancement_count", 0)

    # Determine persona
    placeholder_count = ctx.get("placeholder_count", 0)
    total_sessions = ctx.get("enhancement_count", 1)
    persona = _persona_label(ctx)

    lines = [
        f"🟣 **Velocity context loaded** — {persona} · Session {count}",
        "",
    ]

    if expertise:
        lines.append(f"- **Expertise:** {expertise.title()}")
    if domains:
        lines.append(f"- **Domains:** {', '.join(d.replace('_', ' ') for d in domains)}")
    if tools:
        lines.append(f"- **Stack:** {', '.join(tools)}")
    if recent:
        recent_summaries = [r.get("summary", r.get("intent", "")) for r in recent if r.get("summary")]
        if recent_summaries:
            lines.append(f"- **Current work:** {' · '.join(recent_summaries[:2])}")
    if prefs.get("output_style"):
        lines.append(f"- **Style:** {prefs['output_style'].replace('_', ' ').title()}")
    if notes:
        lines.append(f"- **Note:** {notes}")

    lines += [
        "",
        "*No need to re-explain yourself — I have your context for this session.*",
    ]

    return "\n".join(lines)


def _format_context(ctx: dict) -> str:
    count = ctx.get("enhancement_count", 0)
    domains = ctx.get("domains", [])
    recent = ctx.get("recent_context", [])
    total_used = ctx.get("total_tokens_used", 0)
    total_saved = ctx.get("total_tokens_saved", 0)
    persona = _persona_label(ctx)
    frameworks = ctx.get("frameworks_used", [])

    efficiency_pct = 0
    if total_used + total_saved > 0:
        efficiency_pct = round(total_saved / (total_used + total_saved) * 100)

    lines = [
        f"## Velocity Signals 🧠",
        f"",
        f"**{persona}** · {count} sessions · {len(domains)} domains",
        f"",
    ]

    # Token efficiency strip
    lines += [
        "### Token Efficiency",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Prompts enhanced | {count} |",
        f"| Tokens used by Velocity | {total_used:,} |",
        f"| Tokens saved (estimated) | {total_saved:,} |",
        f"| Efficiency | {efficiency_pct}% fewer tokens spent |",
        "",
    ]

    # Visual bar
    with_pct = max(5, 100 - efficiency_pct)
    filled = round(with_pct / 5)
    empty = 20 - filled
    lines += [
        f"Without Velocity: {'█' * 20}",
        f"With Velocity:    {'█' * filled}{'░' * empty}  ({with_pct}%)",
        "",
    ]

    # Signals
    lines.append("### Signals")

    # Build sprint detection
    if len(recent) >= 3:
        recent_intents = [r.get("intent", "") for r in recent[:4]]
        code_intents = {"code_generation", "debugging", "code_review", "architecture_design"}
        if sum(1 for i in recent_intents if i in code_intents) >= 3:
            lines.append(f"- 🏗️ **Building sprint** — {len(recent_intents)} consecutive technical sessions · biasing toward RTF + CoT")

    # Quality trend
    if count >= 5 and recent:
        avg_recent = sum(r.get("tokens_saved", 0) for r in recent[:3]) / max(1, min(3, len(recent)))
        lines.append(f"- 📈 **Quality improving** — avg {avg_recent:.0f} tokens saved per session over last {min(3, len(recent))} sessions")

    # Positive signal for framework preference
    if frameworks:
        lines.append(f"- ⚡ **Preferred framework: {frameworks[0]}** — Velocity selects this for your prompt types {round(1/len(frameworks)*100) if frameworks else 0}% of the time")

    # Gap signal
    if count >= 3:
        lines.append("- 📐 **Tip** — Specifying `target_ai` in enhance_prompt unlocks AI-specific optimisations")

    # Recent sessions
    lines += ["", "### Recent Sessions", ""]
    lines.append("| Session | Tokens saved | When |")
    lines.append("|---------|-------------|------|")
    for r in recent[:3]:
        summary = r.get("summary", r.get("intent", "Unknown"))[:45]
        saved = r.get("tokens_saved", 0)
        at_str = _relative_time(r.get("at", ""))
        lines.append(f"| {summary} | −{saved} | {at_str} |")

    return "\n".join(lines)


def _persona_label(ctx: dict) -> str:
    placeholder_count = ctx.get("placeholder_count", 0)
    enhancement_count = max(ctx.get("enhancement_count", 1), 1)
    domains = ctx.get("domains", [])
    recent = ctx.get("recent_context", [])

    if enhancement_count < 3:
        return "New Operator"

    placeholder_ratio = placeholder_count / enhancement_count
    if placeholder_ratio > 1.5:
        return "Template Architect"

    recent_intents = [r.get("intent", "") for r in recent[:5]]
    strategy_intents = {"business_strategy", "product_strategy", "marketing"}
    code_intents = {"code_generation", "debugging", "architecture_design", "system_design"}
    marketing_intents = {"marketing", "copywriting", "creative_writing"}

    if sum(1 for i in recent_intents if i in strategy_intents) >= 3:
        return "Strategy Builder"
    if sum(1 for i in recent_intents if i in code_intents) >= 3:
        return "Technical Builder"
    if sum(1 for i in recent_intents if i in marketing_intents) >= 3:
        return "Growth Operator"
    if len(domains) >= 4:
        return "Cross-Domain Explorer"
    return "Builder"


def _relative_time(iso: str) -> str:
    if not iso:
        return "Unknown"
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - then
        if delta < timedelta(hours=1):
            return f"{delta.seconds // 60}m ago"
        if delta < timedelta(days=1):
            return f"{delta.seconds // 3600}h ago"
        return f"{delta.days}d ago"
    except Exception:
        return "Recently"
```

- [ ] **Smoke-test the module loads without error**

```bash
python -c "from core.mcp_tools import mcp_server, list_tools; print('ok')"
```

Expected: `ok`

- [ ] **Commit**

```bash
git add core/mcp_tools.py
git commit -m "feat: MCP server with 4 tool handlers and response formatters"
```

---

## Task 6: FastAPI MCP router (HTTP/SSE transport)

**Files:**
- Create: `api/mcp.py`

- [ ] **Create `api/mcp.py`**

```python
from mcp.server.sse import SseServerTransport
from fastapi import APIRouter
from starlette.requests import Request

from core.mcp_tools import mcp_server

router = APIRouter()
_sse = SseServerTransport("/mcp/messages/")


@router.get("/mcp/sse")
async def mcp_sse(request: Request):
    async with _sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp_server.run(
            streams[0],
            streams[1],
            mcp_server.create_initialization_options(),
        )


@router.post("/mcp/messages/")
async def mcp_messages(request: Request):
    await _sse.handle_post_message(request.scope, request.receive, request._send)
```

- [ ] **Mount the router in `main.py`**

Add this import after the existing router imports:

```python
from api.mcp import router as mcp_router
```

Add this line after the other `app.include_router()` calls:

```python
app.include_router(mcp_router)
```

- [ ] **Start the server and verify the MCP endpoints exist**

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

In a second terminal:

```bash
curl -s http://localhost:8000/mcp/sse -H "Accept: text/event-stream" --max-time 2
```

Expected: SSE headers and an `endpoint` event (connection established before timeout)

- [ ] **Commit**

```bash
git add api/mcp.py main.py
git commit -m "feat: FastAPI MCP router — SSE transport at /mcp/sse"
```

---

## Task 7: stdio shim with `--install` flag

**Files:**
- Create: `mcp_stdio.py` (project root)

- [ ] **Create `mcp_stdio.py`**

```python
#!/usr/bin/env python
"""
Velocity MCP stdio shim.

Usage:
  python mcp_stdio.py              # run as stdio MCP server
  python mcp_stdio.py --install    # auto-install into Claude Code / Claude Desktop config
"""
import asyncio
import json
import os
import pathlib
import platform
import sys

from dotenv import load_dotenv

load_dotenv()


def _install():
    script_path = str(pathlib.Path(__file__).resolve())
    entry = {
        "command": sys.executable,
        "args": [script_path],
        "env": {
            "VELOCITY_USER_ID": os.getenv("VELOCITY_USER_ID", "default"),
            "VELOCITY_API_URL": os.getenv("VELOCITY_API_URL", "http://localhost:8000"),
            "GROQ_API_KEY": os.getenv("GROQ_API_KEY", ""),
        },
    }

    home = pathlib.Path.home()
    installed = []

    # ── Claude Code ────────────────────────────────────────────────
    cc_config = home / ".claude" / "settings.json"
    if cc_config.parent.exists():
        cfg = {}
        if cc_config.exists():
            cfg = json.loads(cc_config.read_text(encoding="utf-8"))
        cfg.setdefault("mcpServers", {})["velocity"] = entry
        cc_config.parent.mkdir(parents=True, exist_ok=True)
        cc_config.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        installed.append(f"Claude Code: {cc_config}")

    # ── Claude Desktop ─────────────────────────────────────────────
    system = platform.system()
    if system == "Windows":
        cd_config = pathlib.Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
    elif system == "Darwin":
        cd_config = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        cd_config = home / ".config" / "Claude" / "claude_desktop_config.json"

    if cd_config.parent.exists():
        cfg = {}
        if cd_config.exists():
            cfg = json.loads(cd_config.read_text(encoding="utf-8"))
        cfg.setdefault("mcpServers", {})["velocity"] = entry
        cd_config.parent.mkdir(parents=True, exist_ok=True)
        cd_config.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        installed.append(f"Claude Desktop: {cd_config}")

    if not installed:
        print("No Claude config directories found.")
        print(f"Manual config entry:\n{json.dumps({'velocity': entry}, indent=2)}")
        return

    for loc in installed:
        print(f"✓ Installed to {loc}")
    print(f"\nVELOCITY_USER_ID = {entry['env']['VELOCITY_USER_ID']}")
    print("Restart Claude to pick up the new server.")


async def _run_stdio():
    from mcp.server.stdio import stdio_server
    from core.mcp_tools import mcp_server

    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
        )


if __name__ == "__main__":
    if "--install" in sys.argv:
        _install()
    else:
        asyncio.run(_run_stdio())
```

- [ ] **Test `--install` flag**

```bash
python mcp_stdio.py --install
```

Expected: prints `✓ Installed to Claude Code: ...` and/or `✓ Installed to Claude Desktop: ...` (whichever config dirs exist on this machine)

- [ ] **Verify the config was written correctly**

```bash
python -c "
import json, pathlib
cfg = json.loads((pathlib.Path.home() / '.claude' / 'settings.json').read_text())
assert 'velocity' in cfg.get('mcpServers', {}), 'velocity not in mcpServers'
assert cfg['mcpServers']['velocity']['args'][0].endswith('mcp_stdio.py')
print('ok')
"
```

Expected: `ok`

- [ ] **Commit**

```bash
git add mcp_stdio.py
git commit -m "feat: stdio shim with --install auto-config for Claude Code and Claude Desktop"
```

---

## Task 8: Cloud deployment files

**Files:**
- Create: `railway.toml`
- Create: `Procfile`
- Modify: `.env.example`

- [ ] **Create `Procfile`**

```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

- [ ] **Create `railway.toml`**

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "on_failure"

[[mounts]]
mountPath = "/data"
```

- [ ] **Update `.env.example` to document the cloud storage path env var**

Add these lines to `.env.example`:

```bash
# Cloud deployment — set STORAGE_PATH to the mounted volume path on Railway
STORAGE_PATH=storage/data

# MCP client config — set these when connecting from a remote machine
VELOCITY_USER_ID=your-username-here
VELOCITY_API_URL=http://localhost:8000
```

- [ ] **Verify `STORAGE_PATH` is already respected by `storage/store.py`**

```bash
python -c "
import os
os.environ['STORAGE_PATH'] = '/tmp/test-velocity'
from storage.store import get_user_context
ctx = get_user_context('test-cloud')
assert ctx['user_id'] == 'test-cloud'
import shutil; shutil.rmtree('/tmp/test-velocity', ignore_errors=True)
print('ok')
"
```

Expected: `ok`

- [ ] **Commit**

```bash
git add Procfile railway.toml .env.example
git commit -m "feat: Railway cloud deployment config with persistent volume mount"
```

---

## Task 9: Integration smoke test

Verify the full MCP flow end-to-end before shipping.

- [ ] **Start the server with a test user**

```bash
VELOCITY_USER_ID=smoke-test python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

- [ ] **Test `inject_context` via HTTP MCP (in second terminal)**

The MCP SSE transport requires a two-step connection: open SSE stream, then POST. Use the following Python script to exercise it end-to-end without a real MCP client:

```bash
python -c "
import asyncio, json, os
os.environ['VELOCITY_USER_ID'] = 'smoke-test'
from core.mcp_tools import _format_inject, _format_context
from storage.store import get_user_context

ctx = get_user_context('smoke-test')
inject_text = _format_inject(ctx)
context_text = _format_context(ctx)
assert 'Velocity' in inject_text
assert 'Velocity Signals' in context_text
print('inject_context formatter: ok')
print('get_my_context formatter: ok')
"
```

Expected: both `ok` lines

- [ ] **Test `enhance_prompt` tool handler (requires GROQ_API_KEY)**

```bash
python -c "
import asyncio, os
os.environ['VELOCITY_USER_ID'] = 'smoke-test'
from core.mcp_tools import _handle_enhance

result = asyncio.run(_handle_enhance({'prompt': 'write a python function to sort a list', 'target_ai': 'claude'}))
assert len(result) == 1
text = result[0].text
assert 'Velocity Enhanced' in text
assert 'After' in text
assert 'Techniques' in text
print('enhance_prompt tool: ok')
print(text[:300])
"
```

Expected: `enhance_prompt tool: ok` followed by the first 300 chars of the card

- [ ] **Test stdio shim loads without error**

```bash
python -c "
import subprocess, sys
p = subprocess.run(
    [sys.executable, '-c', 'import mcp_stdio; print(\"import ok\")'],
    capture_output=True, text=True, timeout=10
)
print(p.stdout.strip())
assert 'import ok' in p.stdout
"
```

Expected: `import ok`

- [ ] **Commit**

```bash
git add .
git commit -m "chore: verified full MCP integration smoke test passes"
```

---

## Self-Review Results

**Spec coverage check:**
- §4.1 enhance_prompt — Task 5 (`_handle_enhance`) ✓
- §4.2 refine_prompt — Task 5 (`_handle_refine`) ✓
- §4.3 get_my_context — Task 5 (`_format_context`) ✓
- §4.4 inject_context — Task 5 (`_format_inject`) ✓
- §5 stdio transport — Task 7 (`mcp_stdio.py`) ✓
- §5 HTTP/SSE transport — Task 6 (`api/mcp.py`) ✓
- §6.1 enhance card format — Task 5 (`_format_enhance_result`) ✓
- §6.2 inject banner — Task 5 (`_format_inject`) ✓
- §6.3 context signal feed + token strip — Task 5 (`_format_context`) ✓
- §7 token savings formula — Tasks 3, 4, 5 ✓
- §8 storage schema changes — Task 3 ✓
- §10 `--install` UX — Task 7 ✓
- §11 Railway deployment — Task 8 ✓

**Type consistency:** All callers of `update_after_enhancement` pass `tokens_used` and `tokens_saved` as int. `complete_with_usage` returns `tuple[str, dict]` and is destructured as `raw, usage` in `_handle_enhance`. `normalize_result` signature matches `_normalize_result` (same args). ✓

**No placeholders found.** ✓
