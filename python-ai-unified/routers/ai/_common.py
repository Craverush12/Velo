"""Shared helpers and base models for the /ai/* router group.

These utilities mirror the real working patterns from the lean app
(``core/llm.py``, ``api/enhance.py``, ``api/refine.py``) so the unified
service behaves faithfully to canonical Server 3 (prompt-enhance).

All Groq JSON completions go through :func:`groq_json` which enforces the
project rule ``response_format={"type": "json_object"}``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from shared.groq_client import groq_pool
from shared.settings import settings

# ---------------------------------------------------------------------------
# Prompt-mode / target-ai normalization (mirrors core/contracts.py)
# ---------------------------------------------------------------------------

PROMPT_MODE_VALUES = ("normal", "caveman", "research", "fast_build", "media")

TARGET_AI_VALUES = (
    "claude",
    "chatgpt",
    "gpt-5",
    "gemini",
    "groq",
    "compound_mini",
    "cursor",
    "bolt",
    "replit",
    "gamma",
    "midjourney",
)

_MODE_ALIASES = {
    "default": "normal",
    "standard": "normal",
    "base": "normal",
    "cave": "caveman",
    "caveman_mode": "caveman",
    "cavemanmode": "caveman",
    "fast": "fast_build",
    "build": "fast_build",
    "fastbuild": "fast_build",
    "research_mode": "research",
    "media_mode": "media",
    "creative": "media",
}

_TARGET_AI_ALIASES = {
    "gpt4o": "chatgpt",
    "gpt-4o": "chatgpt",
    "gpt-4": "chatgpt",
    "openai": "chatgpt",
    "llama": "groq",
    "groq/llama": "groq",
    "claude-code": "cursor",
    "claude code": "cursor",
    "v0": "bolt",
    "lovable": "bolt",
    "image-gen": "midjourney",
    "image_gen": "midjourney",
    "presentations": "gamma",
    "compound-mini": "compound_mini",
    "groq/compound-mini": "compound_mini",
    "groq/compound": "compound_mini",
    "compound": "compound_mini",
}


def normalize_prompt_mode(value: str | None) -> str:
    if value is None:
        return "normal"
    normalized = value.strip().lower().replace("-", "_")
    if not normalized:
        return "normal"
    normalized = _MODE_ALIASES.get(normalized, normalized)
    if normalized not in PROMPT_MODE_VALUES:
        raise ValueError(f"prompt_mode must be one of: {', '.join(PROMPT_MODE_VALUES)}")
    return normalized


def normalize_target_ai(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    normalized = _TARGET_AI_ALIASES.get(normalized, normalized)
    if normalized not in TARGET_AI_VALUES:
        raise ValueError(f"target_ai must be one of: {', '.join(TARGET_AI_VALUES)}")
    return normalized


# ---------------------------------------------------------------------------
# JSON parsing / Groq helpers
# ---------------------------------------------------------------------------

_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def parse_json_object(raw: str) -> dict[str, Any]:
    """Parse a JSON object from an LLM response, tolerating stray text/fences.

    Mirrors ``core/output_validator.parse_json_object`` semantics: try a
    straight parse, then fall back to extracting the first ``{...}`` block.
    """
    if not raw or not raw.strip():
        raise HTTPException(status_code=502, detail="LLM returned an empty response")
    text = raw.strip()
    # Strip markdown code fences if present.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_OBJECT_RE.search(text)
        if not match:
            raise HTTPException(status_code=502, detail="LLM returned no JSON object")
        try:
            parsed = json.loads(match.group())
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail=f"LLM returned unparseable JSON: {exc}")
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="LLM JSON response is not an object")
    return parsed


async def groq_json(
    system_prompt: str,
    user_message: str,
    *,
    temperature: float = 0.7,
    model: str | None = None,
) -> dict[str, Any]:
    """Run a non-streaming Groq chat completion that returns a JSON object.

    Always enforces ``response_format={"type": "json_object"}`` per project
    rule. Uses the shared ``groq_pool`` so key rotation is centralized.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    try:
        raw = await groq_pool.async_chat(
            messages,
            model=model,
            response_format={"type": "json_object"},
            temperature=temperature,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize upstream client errors
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc
    content = _extract_content(raw)
    return parse_json_object(content)


async def groq_text(
    system_prompt: str,
    user_message: str,
    *,
    temperature: float = 0.7,
    model: str | None = None,
) -> str:
    """Run a non-streaming Groq chat completion returning raw text (no JSON enforced)."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    try:
        raw = await groq_pool.async_chat(messages, model=model, temperature=temperature)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc
    return _extract_content(raw)


def _extract_content(raw: Any) -> str:
    """Normalize a groq_pool response into a content string.

    The shared client may return a plain string or an OpenAI/Groq-style
    response object. Handle both defensively.
    """
    if isinstance(raw, str):
        return raw
    # OpenAI/Groq SDK style: response.choices[0].message.content
    choices = getattr(raw, "choices", None)
    if choices:
        message = getattr(choices[0], "message", None)
        if message is not None:
            content = getattr(message, "content", None)
            if content is not None:
                return content
    if isinstance(raw, dict):
        choices = raw.get("choices")
        if choices:
            msg = choices[0].get("message") or {}
            if msg.get("content") is not None:
                return msg["content"]
        if raw.get("content") is not None:
            return raw["content"]
    return str(raw)


def sse(event: dict[str, Any]) -> str:
    """Serialize a dict as a Server-Sent-Events ``data:`` frame."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def default_model() -> str | None:
    """Resolve the default Groq model from shared settings."""
    return getattr(settings, "groq_model", None) or getattr(settings, "GROQ_MODEL", None)
