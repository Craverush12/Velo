"""/ai/enhance/* — prompt enhancement (consumer extension + enterprise).

Source routes (canonical prompt-enhance / Server 3):
  - POST /enhance/stream  -> /ai/enhance/stream  (SSE; primary enhance endpoint)
  - POST /enhance/chat    -> /ai/enhance/chat    (chat-mode, non-streaming)

PER D-019: this router does NOT re-implement prompt/Groq logic. It REUSES this
monorepo's canonical pipeline — ``api.enhance._generate`` (which loads the real
``core/prompts/enhance_system.md`` and runs the full enhancement) — and adapts
its native ``chunk``/``done`` SSE events into the consumer extension's
``content``/``complete``/``[DONE]`` protocol. This mirrors the proven adapter in
``api/extension_bridge.py`` (the ``/dev/test/*`` layer), re-exposed under /ai/*.

Light rate-limiting is layered on via the shared Redis helper (degrades open).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

CONTEXT_SIMILARITY_THRESHOLD = 0.6  # gate for session-essence relevance

_PII_PATTERNS = [
    (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[PII:email]'),
    (r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PII:phone]'),
    (r'\b\d{3}-\d{2}-\d{4}\b', '[PII:ssn]'),
    (r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12})\b', '[PII:card]'),
    (r'\b(?:sk-|ghp_|gho_|AKIA|Bearer\s+)[A-Za-z0-9_\-]{16,}\b', '[PII:api_key]'),
]

# Fixed 2026-06-16: the original patterns (bare 'disregard', 'new instructions',
# 'ignore.{0,10}previous', etc.) matched ordinary business writing — "Please
# disregard the earlier draft", "Team received new instructions from
# leadership" — causing the ENTIRE attachment to be silently replaced with
# "[CONTENT REDACTED]" on a false positive (see DECISIONS.md / incident trace
# for user feedback this surfaced as "bad formatting": a meeting-notes
# attachment got wiped because the notes mentioned "new instructions from
# leadership"). Real injection attempts target the model directly — they
# pair the trigger word with "instructions"/"system prompt" in a directive
# structure. These patterns require that structure instead of a single
# common word anywhere in the text.
_INJECTION_PATTERNS = [
    r'ignore\s+(?:your|all|the|any)?\s*(?:previous|prior|above)\s+instructions?',
    r'disregard\s+(?:your|all|the|any)?\s*(?:previous|prior|above)\s+instructions?',
    r'forget\s+(?:your|all|the|any)?\s*(?:previous|prior|above)\s+instructions?',
    r'(?:reveal|show|print|output|disregard|ignore)\s+(?:me|us)?\s*(?:the\s+|your\s+)?system\s+prompt',
    r'\byou\s+are\s+now\s+(?:a|an|in|no longer)\b',
    r'(?:ignore|disregard|forget)\s+(?:everything|all)\s+(?:above|before|previously)\s+and\s+(?:follow|do|use)',
    r'new\s+instructions?\s*:\s*(?:ignore|disregard|you\s+must|you\s+are)',
]

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from shared.db import get_session
from shared.redis_cache import rate_limit_check
from shared.trace_db import write_trace

# Canonical logic from the monorepo (see local_app.py / D-019).
from local_app import EnhanceRequest as LocalEnhanceRequest, _generate, map_mode, AttachmentItem as LocalAttachmentItem

# In-process moderation pipeline (D-029 / D-030).
from routers.ai.moderation import _run_pipeline as _moderation_pipeline

router = APIRouter(tags=["enhance"])

ENHANCE_TOKEN_COST = 1
ENHANCE_RATE_LIMIT = 60  # requests per window
ENHANCE_RATE_WINDOW = 60  # seconds


class EnhanceRequest(BaseModel):
    """Consumer-extension enhance contract (mirrors extension_bridge.ExtEnhanceRequest).

    Exported for reuse by media.py. ``context.mode`` carries the extension mode
    label ("flash"/"best"/"build"/"media"/...) which maps to an internal prompt
    mode via local_app.map_mode.
    """

    prompt: str
    user_id: str = "anonymous"
    auth_token: str = ""
    context: dict[str, Any] = {}
    chat_history: list = []
    target_ai: str | None = None
    domain: str = ""
    intent: str = ""
    intent_description: str = ""
    user_context: dict[str, Any] = {}
    enterprise_id: Optional[str] = None
    # Attachments forwarded from the extension (file contents, clipboard text, etc.)
    attachments: list[dict[str, Any]] = []


async def _fetch_tenant_prompt_suffix(enterprise_id: str) -> str:
    """Fetch the per-tenant system prompt suffix from the tenants table.

    Queries ``tenants.prompt_suffix`` for the given enterprise_id. Returns the
    suffix string, or ``""`` on any error or when no suffix is configured.
    Degrades open — a missing suffix never blocks enhancement.

    Requires migration: IMPORTANT/migrations/add_tenant_prompt_suffix.sql
    """
    try:
        from shared.db import engine as _db_engine
        if _db_engine is None:
            return ""
        async with AsyncSession(_db_engine) as session:
            result = await session.execute(
                text(
                    "SELECT prompt_suffix FROM tenants "
                    "WHERE id = :eid AND prompt_suffix IS NOT NULL LIMIT 1"
                ),
                {"eid": enterprise_id},
            )
            row = result.first()
            suffix: str = row[0] if row and row[0] else ""
            if suffix:
                logger.info(
                    "tenant_prompt_suffix: loaded %d chars for enterprise_id=%s",
                    len(suffix),
                    enterprise_id,
                )
            return suffix
    except Exception:  # noqa: BLE001 — suffix fetch never blocks the enhance path
        return ""


async def _fetch_local_essences(user_id: str, query: str) -> list[str]:
    """Fetch essences from the local pgvector store. Returns [] on any failure."""
    try:
        from routers.context import search_contexts, ContextSearchRequest
        response = await search_contexts(
            ContextSearchRequest(user_id=user_id, query=query, limit=3)
        )
        results = response.results or []
        passed = [
            r for r in results
            if r.similarity >= CONTEXT_SIMILARITY_THRESHOLD
            and r.essence
            and r.essence != "User is working on a task."
        ]
        if len(results) > len(passed):
            logger.debug(
                "context_hint: gated %d low-relevance local essences (threshold=%.2f)",
                len(results) - len(passed), CONTEXT_SIMILARITY_THRESHOLD,
            )
        return [r.essence for r in passed]
    except Exception:
        return []


def _split_master_flow(essence: str) -> tuple[str, str | None]:
    master_match = re.search(
        r"MASTER:\s*(.*?)(?=FLOW:|$)", essence, re.DOTALL | re.IGNORECASE
    )
    flow_match = re.search(r"FLOW:\s*(.*)", essence, re.DOTALL | re.IGNORECASE)

    if not master_match and not flow_match:
        return essence.strip(), None

    user_goal = master_match.group(1).strip() if master_match else ""
    flow_text = flow_match.group(1).strip() if flow_match else ""
    if not flow_text:
        return user_goal, None

    bullets = [
        line.strip().lstrip("-*+").strip()
        for line in flow_text.splitlines()
        if line.strip()
    ]
    current_focus = "; ".join([line for line in bullets if line]) or None
    return user_goal, current_focus


async def _fetch_context_hint(user_id: str, query: str) -> str:
    """Fetch context from local pgvector + Supermemory in parallel.

    Returns a JSON string with structured session context + merged entities, or empty string on any
    failure. Degrades open — a missing context hint never blocks enhancement.

    Output shape (when results exist):
        {"session_context": {...}, "entities": {"frameworks": ["React"], "domain": "saas"}}
    """
    if not user_id or user_id == "anonymous":
        return ""
    try:
        import asyncio as _asyncio
        from shared.supermemory_client import search_memories as _sm_search
        from shared.settings import get_settings as _get_settings

        sm_enabled = bool(_get_settings().SUPERMEMORY_API_KEY)

        # Run local and Supermemory retrieval in parallel
        tasks = [_fetch_local_essences(user_id, query)]
        if sm_enabled:
            tasks.append(_sm_search(user_id, query, limit=3))

        results = await _asyncio.gather(*tasks, return_exceptions=True)
        local_essences: list[str] = results[0] if not isinstance(results[0], Exception) else []
        sm_snippets: list[str] = (results[1] if len(results) > 1 and not isinstance(results[1], Exception) else [])

        # Merge: local essences take precedence; Supermemory fills when local is empty
        if local_essences:
            essences = local_essences
            if sm_snippets:
                logger.debug("context_hint: local=%d sm=%d (local wins)", len(local_essences), len(sm_snippets))
        elif sm_snippets:
            # TODO: recency re-rank when search_memories returns metadata
            essences = sm_snippets
            logger.debug("context_hint: local empty, using %d supermemory snippets", len(sm_snippets))
        else:
            return ""

        # Extract and merge entities across all essences
        all_entities: dict = {}
        try:
            from routers.context import extract_entities
            for ess in essences:
                for k, v in extract_entities(ess).items():
                    if k == "frameworks":
                        existing = all_entities.get("frameworks", [])
                        all_entities["frameworks"] = list(dict.fromkeys(existing + v))
                    else:
                        all_entities.setdefault(k, v)
        except Exception:
            all_entities = {}

        try:
            from shared.taxonomy_bridge import map_context_domain, map_context_intent

            user_goal, current_focus = _split_master_flow(essences[0])
            context_intent = None
            context_domain = None
            session_context = {
                "user_goal": user_goal,
                "current_focus": current_focus,
                "context_intent": context_intent,
                "context_domain": context_domain,
                "enhance_domain_hint": (
                    map_context_domain(context_domain) if context_domain else None
                ),
                "enhance_intent_hint": (
                    map_context_intent(context_intent) if context_intent else None
                ),
                "frameworks": all_entities.get("frameworks", []),
            }
            hint: dict = {
                "session_context": session_context,
                "entities": all_entities,
            }
            return json.dumps(hint, ensure_ascii=False)
        except Exception:
            # Taxonomy bridge or JSON serialization failed — degrade to legacy pipe format
            return " | ".join(essences)
    except Exception:
        return ""


# NODE BACKEND DEPENDENCY (not yet implemented — see PERSONA_NODE_ENDPOINT_SPEC.md):
# GET {NODE_BACKEND_URL}/api/v1/personalization/public/{user_id}
# Public (no-auth), read-only, mirrors the existing processed-context/public/*
# pattern. Expected 200 response shape:
#   {"onboarding": {"llm_platform": str|null, "occupation": str|null,
#                    "ai_familiarity": str|null} | null,
#    "personalization": {"preferred_name": str|null, "professional_world": str|null,
#                         "velocity_traits": str|null, "personal_life": str|null,
#                         "hobbies": str|null, "primary_model": str|null} | null}
# 404 (user has neither row) is expected and treated as "no persona yet" — not an error.
async def _fetch_user_persona(user_id: str) -> str:
    """Fetch stable user persona (onboarding + personalization profile) from Postgres.

    Returns a compact JSON string for prompt injection, or "" on any failure /
    missing data / incognito. Degrades open — a missing persona never blocks
    enhancement or refinement. This is intentionally separate from
    _fetch_context_hint: persona is "who the user is" (stable across topics),
    context_hint is "what they're working on right now" (session-scoped).
    """
    if not user_id or user_id == "anonymous":
        return ""
    try:
        from shared.db import async_session_maker
        if async_session_maker is None:
            return ""

        persona: dict = {}

        async with async_session_maker() as session:
            ob_result = await session.execute(
                text(
                    "SELECT occupation, ai_familiarity, llm_platform"
                    " FROM onboarding_data WHERE user_id = :uid LIMIT 1"
                ),
                {"uid": user_id},
            )
            ob_row = ob_result.mappings().first()
            if ob_row:
                for key in ("occupation", "ai_familiarity", "llm_platform"):
                    val = ob_row.get(key)
                    if val:
                        persona[key] = val

            p_result = await session.execute(
                text(
                    "SELECT preferred_name, professional_world, velocity_traits,"
                    " personal_life, hobbies, primary_model"
                    " FROM personalization WHERE user_id = :uid LIMIT 1"
                ),
                {"uid": user_id},
            )
            p_row = p_result.mappings().first()
            if p_row:
                for key in (
                    "preferred_name", "professional_world", "velocity_traits",
                    "personal_life", "hobbies", "primary_model",
                ):
                    val = p_row.get(key)
                    if val:
                        persona[key] = val

        if not persona:
            return ""
        return json.dumps(persona, ensure_ascii=False)
    except Exception as exc:
        logger.debug("persona_hint: fetch failed for user=%s — %s", user_id, exc)
        return ""


def _sanitize_attachment_text_with_count(name: str, text: str, user_id: str) -> tuple[str, int]:
    """Sanitise attachment text before it reaches LLM infrastructure.

    Order of operations:
      1. Truncate to 8000 chars (bridge-layer limit; canonical side truncates at 5000).
      2. PII redaction — emails, phones, SSNs, card numbers, API keys.
      3. Prompt-injection detection — if matched, replace entire text with a
         policy-violation notice and log a WARNING.

    Returns (sanitized_text, pii_redacted_count) so callers can persist the
    redaction count for observability without re-running the regex passes.
    """
    # 1. Truncate
    if len(text) > 8000:
        text = text[:8000]

    # 2. PII redaction
    pii_count = 0
    for pattern, replacement in _PII_PATTERNS:
        new_text, n = re.subn(pattern, replacement, text, flags=re.IGNORECASE)
        pii_count += n
        text = new_text
    if pii_count > 0:
        logger.info(
            "attachment_pii: redacted %d PII instances in '%s' for user %s",
            pii_count, name, user_id,
        )

    # 3. Injection pattern check
    for pattern in _INJECTION_PATTERNS:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            logger.warning(
                "attachment_injection: prompt-injection pattern '%s' matched in attachment '%s' for user %s — redacting",
                pattern, name, user_id,
            )
            return "[CONTENT REDACTED: policy violation detected in attachment]", pii_count

    return text, pii_count


def _sanitize_attachment_text(name: str, text: str, user_id: str) -> str:
    """Sanitise attachment text before it reaches LLM infrastructure.

    Thin wrapper over ``_sanitize_attachment_text_with_count`` retained for
    backward compatibility with existing callers that only need the text.
    """
    sanitized, _pii_count = _sanitize_attachment_text_with_count(name, text, user_id)
    return sanitized


_ATTACHMENTS_TABLE_READY = False


async def _ensure_attachments_table(session: AsyncSession) -> None:
    """Best-effort creation of the attachments table (idempotent, IF NOT EXISTS).

    Mirrors the self-healing pattern in routers/ai/context_docs.py::_ensure_table.
    Runs once per process (cached via the module-level flag) since
    migrations/004_attachments_table.sql is expected to have already created
    this table in production.
    """
    global _ATTACHMENTS_TABLE_READY
    if _ATTACHMENTS_TABLE_READY:
        return
    try:
        await session.execute(
            text(
                "CREATE TABLE IF NOT EXISTS attachments ("
                " id BIGSERIAL PRIMARY KEY,"
                " user_id TEXT NOT NULL,"
                " session_id TEXT,"
                " filename TEXT,"
                " mime_type TEXT,"
                " sanitized_content TEXT NOT NULL,"
                " content_length INT NOT NULL DEFAULT 0,"
                " pii_redacted_count INT NOT NULL DEFAULT 0,"
                " created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        await session.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_attachments_user_created"
                " ON attachments (user_id, created_at DESC)"
            )
        )
        await session.commit()
        _ATTACHMENTS_TABLE_READY = True
    except Exception:  # noqa: BLE001 - table may already exist with prod schema
        await session.rollback()


async def _save_attachment(
    *,
    user_id: str,
    session_id: Optional[str],
    filename: str,
    sanitized_text: str,
    pii_redacted_count: int,
    mime_type: Optional[str] = None,
) -> None:
    """Persist a sanitized attachment to PostgreSQL. Fire-and-forget only.

    Stores ONLY the already-sanitized (PII-redacted, injection-checked) text —
    never the raw attachment content. Never raises: any failure (missing
    PG_CONNECTION, schema drift, connection error) is logged as a warning and
    swallowed so the enhance critical path is never affected.

    Intended to be scheduled via ``asyncio.create_task`` right after
    ``_sanitize_attachment_text`` is called, mirroring the Supermemory
    shadow-write pattern in routers/context.py (Step 11b).
    """
    try:
        from shared.db import async_session_maker

        if async_session_maker is None:
            logger.warning(
                "_save_attachment: PG_CONNECTION not configured — skipping persist for user=%s",
                user_id,
            )
            return

        async with async_session_maker() as session:
            await _ensure_attachments_table(session)
            await session.execute(
                text(
                    "INSERT INTO attachments"
                    " (user_id, session_id, filename, mime_type, sanitized_content,"
                    "  content_length, pii_redacted_count)"
                    " VALUES (:uid, :sid, :fn, :mt, :content, :clen, :pii)"
                ),
                {
                    "uid": user_id,
                    "sid": session_id,
                    "fn": filename or None,
                    "mt": mime_type,
                    "content": sanitized_text,
                    "clen": len(sanitized_text or ""),
                    "pii": pii_redacted_count,
                },
            )
            await session.commit()
        logger.info(
            "_save_attachment: persisted attachment '%s' for user=%s session=%s (%d chars, %d pii redactions)",
            filename, user_id, session_id, len(sanitized_text or ""), pii_redacted_count,
        )
    except Exception as exc:  # noqa: BLE001 - persistence must never block/raise into enhance path
        logger.warning(
            "_save_attachment: failed to persist attachment '%s' for user=%s (%s)",
            filename, user_id, exc,
        )


def _to_local(
    req: EnhanceRequest,
    *,
    force_media: bool = False,
    context_hint: str = "",
    persona_hint: str = "",
) -> LocalEnhanceRequest:
    """Translate the extension request into the canonical EnhanceRequest."""
    mode = "media" if force_media else map_mode(req.context.get("mode"))
    session_id = (
        (req.context.get("session_id") or req.context.get("sessionId"))
        if isinstance(req.context, dict)
        else None
    )

    attachments: list[LocalAttachmentItem] = []
    for a in (req.attachments or []):
        if not isinstance(a, dict) or not a.get("text"):
            continue
        name = a.get("name", "")
        raw_text = a.get("text", "")
        sanitized_text, pii_count = _sanitize_attachment_text_with_count(name, raw_text, req.user_id)
        attachments.append(LocalAttachmentItem(name=name, text=sanitized_text))

        # Fire-and-forget persistence — mirrors the Supermemory shadow-write
        # pattern in routers/context.py (Step 11b). Never blocks/fails enhance.
        try:
            asyncio.create_task(
                _save_attachment(
                    user_id=req.user_id,
                    session_id=session_id,
                    filename=name,
                    sanitized_text=sanitized_text,
                    pii_redacted_count=pii_count,
                    mime_type=a.get("mime_type") or a.get("type"),
                )
            )
        except Exception:  # noqa: BLE001 - scheduling failure must never affect enhance
            logger.warning("_to_local: failed to schedule attachment persistence for user=%s", req.user_id)

    return LocalEnhanceRequest(
        prompt=req.prompt,
        user_id=req.user_id,
        target_ai=req.target_ai or None,
        prompt_mode=mode,
        attachments=attachments,
        context_hint=context_hint,
        persona_hint=persona_hint,
    )


async def _adapt_stream(
    inner_resp: StreamingResponse,
    *,
    extra_meta: dict[str, Any] | None = None,
    trace_id: str | None = None,
    trace_ctx: dict[str, Any] | None = None,
):
    """Adapt the canonical chunk/done SSE → extension content/complete/[DONE].

    ``extra_meta`` is merged into the ``metadata`` field of the ``complete``
    event. Used to propagate moderation annotations (``redacted``, ``warning``)
    to the client without altering consumer paths (extra_meta is None / {} there).

    ``trace_id`` and ``trace_ctx`` are optional — when provided, the ``complete``
    event will include the trace_id field and a fire-and-forget Postgres trace
    write is scheduled (parity with enhance_chat).
    """
    async for raw_chunk in inner_resp.body_iterator:
        if isinstance(raw_chunk, bytes):
            raw_chunk = raw_chunk.decode("utf-8")
        for line in raw_chunk.split("\n"):
            line = line.strip()
            if not line.startswith("data:"):
                continue
            raw_json = line[5:].strip()
            if not raw_json:
                continue
            try:
                event = json.loads(raw_json)
            except json.JSONDecodeError:
                continue

            ev_type = event.get("type")
            if ev_type == "chunk":
                yield "data: " + json.dumps(
                    {"type": "content", "chunk": event.get("content", "")}
                ) + "\n\n"
            elif ev_type == "done":
                result = event.get("result", {})
                metadata: dict[str, Any] = {
                    "domain": result.get("domain", ""),
                    "intent": result.get("intent", ""),
                    "intent_description": result.get("summary", ""),
                    "complexity": result.get("complexity", "medium"),
                }
                if extra_meta:
                    metadata.update(extra_meta)

                if trace_id:
                    metadata["trace_id"] = trace_id

                # Fire-and-forget Postgres trace for the streaming path (parity
                # with enhance_chat). Never awaited, never blocks the stream.
                if trace_id and trace_ctx is not None:
                    try:
                        asyncio.create_task(write_trace({
                            "trace_id": trace_id,
                            "flow": "enhance_stream",
                            "status": "completed",
                            "user_id": trace_ctx.get("user_id") or "anonymous",
                            "prompt_mode": trace_ctx.get("mode") or "",
                            "target_ai": trace_ctx.get("target_ai"),
                            "domain": result.get("domain"),
                            "intent": result.get("intent"),
                            "context_hint": trace_ctx.get("context_hint"),
                            "persona_hint": trace_ctx.get("persona_hint"),
                            "suggested_ai": trace_ctx.get("suggested_ai"),
                            "before_after": {
                                "before": trace_ctx.get("raw_prompt", ""),
                                "after": result.get("enhanced_prompt", ""),
                            },
                            "output": {
                                "final_text": result.get("enhanced_prompt", ""),
                                "quality_score": result.get("prompt_quality_score"),
                            },
                        }))
                    except Exception:  # noqa: BLE001
                        pass

                yield "data: " + json.dumps(
                    {
                        "type": "complete",
                        "enhanced_prompt": result.get("enhanced_prompt", ""),
                        "annotated_segments": result.get("annotated_segments", []),
                        "performance": {"processing_time_ms": 0},
                        "metadata": metadata,
                        "trace_id": trace_id,
                    }
                ) + "\n\n"
                yield "data: [DONE]\n\n"
            elif ev_type == "error":
                yield "data: " + json.dumps(
                    {"type": "error", "message": event.get("message", "")}
                ) + "\n\n"


async def _rate_guard(req: EnhanceRequest, http_request: Request) -> None:
    client = http_request.client.host if http_request.client else "unknown"
    allowed = await rate_limit_check(
        f"ai:enhance:rl:{req.user_id}:{client}",
        limit=ENHANCE_RATE_LIMIT,
        window_seconds=ENHANCE_RATE_WINDOW,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


async def _apply_enterprise_moderation(
    request: EnhanceRequest,
) -> tuple[str, dict[str, Any] | None]:
    """Run the in-process moderation pipeline for enterprise requests (D-029/D-030).

    Returns (effective_prompt, extra_metadata_fields).
    - effective_prompt: the prompt to pass to _generate (may be redacted).
    - extra_metadata_fields: dict to merge into the complete event metadata,
      or None if the caller should abort and stream the returned error event.

    When this function raises _ModerationBlock the caller must stream that
    event and return without calling _generate.

    Consumer requests (enterprise_id is None) bypass this entirely.
    """
    if request.enterprise_id is None:
        return request.prompt, {}

    try:
        verdict = await _moderation_pipeline(
            request.prompt,
            enterprise_id=request.enterprise_id,
            user_id=request.user_id,
            policy_rules=None,
            strict_mode=False,
        )
    except Exception:
        # D-030: fail-closed on any moderation exception.
        raise _ModerationBlock(
            json.dumps({
                "type": "error",
                "code": "moderation_unavailable",
                "message": "Enterprise policy check unavailable. Request blocked.",
                "guardrail": "moderation_unavailable",
            })
        )

    decision = verdict.get("decision", "ALLOW")

    if decision == "BLOCK":
        raise _ModerationBlock(
            json.dumps({
                "type": "error",
                "code": "policy_block",
                "message": "Your request was blocked by enterprise policy.",
                "guardrail": verdict.get("reason", decision),
            })
        )

    if decision in ("REQUIRE_CONFIRMATION", "REQUIRE_APPROVAL"):
        raise _ModerationBlock(
            json.dumps({
                "type": "error",
                "code": "policy_block",
                "message": "Your request was blocked by enterprise policy.",
                "guardrail": verdict.get("reason", decision),
            })
        )

    if decision == "REDACT":
        redacted_text = verdict.get("redacted_text") or request.prompt
        return redacted_text, {"redacted": True}

    if decision == "WARN":
        return request.prompt, {"warning": verdict.get("reason", "Borderline content flagged by enterprise policy.")}

    # ALLOW — proceed normally.
    return request.prompt, {}


class _ModerationBlock(Exception):
    """Raised when moderation requires the request to be blocked.

    ``args[0]`` is the JSON-serialised SSE error payload (without the
    ``data: `` prefix or trailing newlines).
    """


def _error_sse_stream(error_json: str):
    """Async generator that yields a single SSE error event then [DONE]."""
    async def _gen():
        yield "data: " + error_json + "\n\n"
        yield "data: [DONE]\n\n"
    return _gen()


@router.post("/enhance/stream")
async def enhance_stream(
    request: EnhanceRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
):
    """Streaming prompt enhancement (SSE) — primary consumer enhance path.

    Delegates to the canonical ``_generate`` pipeline and re-frames its SSE
    events into the extension protocol (content/complete/[DONE]).

    For enterprise requests (enterprise_id present) the moderation pipeline
    runs in-process (D-029) before enhancement. Fail-closed per D-030.
    """
    await _rate_guard(request, http_request)

    try:
        effective_prompt, extra_meta = await _apply_enterprise_moderation(request)
    except _ModerationBlock as exc:
        return StreamingResponse(
            _error_sse_stream(exc.args[0]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Substitute the (possibly redacted) prompt for _generate.
    if effective_prompt != request.prompt:
        request = request.model_copy(update={"prompt": effective_prompt})

    # Fetch session essence + stable persona in parallel (both best-effort, degrade open).
    context_hint, persona_hint = await asyncio.gather(
        _fetch_context_hint(request.user_id, effective_prompt),
        _fetch_user_persona(request.user_id),
    )

    # Fetch per-tenant system prompt suffix (enterprise only; degrades open).
    tenant_suffix = await _fetch_tenant_prompt_suffix(request.enterprise_id) if request.enterprise_id else ""
    if tenant_suffix:
        context_hint = (
            f"{context_hint}\n\n[TENANT_CONSTRAINTS]\n{tenant_suffix}"
            if context_hint
            else f"[TENANT_CONSTRAINTS]\n{tenant_suffix}"
        )

    trace_id = str(uuid.uuid4())
    trace_ctx = {
        "user_id": request.user_id,
        "mode": request.context.get("mode", "") if isinstance(request.context, dict) else "",
        "target_ai": request.target_ai,
        "context_hint": context_hint,
        "persona_hint": persona_hint,
        "raw_prompt": request.prompt,
        "suggested_ai": _resolve_suggested_ai(persona_hint, request.domain or ""),
    }

    inner: StreamingResponse = await _generate(
        _to_local(request, context_hint=context_hint, persona_hint=persona_hint), background_tasks
    )
    if request.user_id and request.user_id != "anonymous":
        from shared.supermemory_client import add_memory as _sm_add
        background_tasks.add_task(
            _sm_add,
            user_id=request.user_id,
            content=request.prompt,
            metadata={"domain": request.domain or "", "intent": request.intent or "", "source": "enhance"},
        )
    return StreamingResponse(
        _adapt_stream(inner, extra_meta=extra_meta, trace_id=trace_id, trace_ctx=trace_ctx),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _resolve_suggested_ai(persona_json: str, domain: str) -> str:
    """Return the best-fit AI platform for the enhanced prompt.

    Priority: declared llm_platform → declared primary_model → domain default.
    Falls back to "chatgpt" when nothing is known.
    """
    _PLATFORM_NORMALIZE: dict[str, str | None] = {
        "chatgpt": "chatgpt",
        "claude": "claude",
        "gemini": "gemini",
        "perplexity": "chatgpt",
        "grok": "chatgpt",
        "copilot": "chatgpt",
        "cursor": "claude",
        "other": None,
    }
    _PRIMARY_MODEL_MAP: dict[str, str] = {
        "chatgpt": "chatgpt",
        "claude": "claude",
        "gemini": "gemini",
    }
    _DOMAIN_MAP: dict[str, str] = {
        "software_development": "claude",
        "software_engineering": "claude",
        "data_science": "claude",
        "devops_infrastructure": "claude",
        "cybersecurity": "claude",
        "design_ux": "chatgpt",
        "creative_arts": "chatgpt",
        "content_creation": "chatgpt",
        "marketing_growth": "chatgpt",
        "business_operations": "chatgpt",
        "education": "chatgpt",
        "product_management": "chatgpt",
        "general": "chatgpt",
    }
    try:
        persona = json.loads(persona_json) if persona_json else {}
    except Exception:
        persona = {}
    lp = (persona.get("llm_platform") or "").lower().strip()
    if lp:
        normalized = _PLATFORM_NORMALIZE.get(lp)
        if normalized:
            return normalized
    pm = (persona.get("primary_model") or "").lower().strip()
    if pm:
        normalized = _PRIMARY_MODEL_MAP.get(pm)
        if normalized:
            return normalized
    return _DOMAIN_MAP.get(domain, "chatgpt")


@router.post("/enhance/chat")
async def enhance_chat(
    request: EnhanceRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
    force_media: bool = False,
):
    """Chat-mode (non-streaming) enhancement.

    No separate canonical handler exists for the non-streaming variant, so we
    drain the canonical streaming pipeline and return the final ``complete``
    payload. See RECONCILE.md (verify the exact non-stream response envelope
    the consumer/enterprise clients expect).

    For enterprise requests (enterprise_id present) the moderation pipeline
    runs in-process (D-029) before enhancement. Fail-closed per D-030.
    """
    await _rate_guard(request, http_request)

    try:
        effective_prompt, extra_meta = await _apply_enterprise_moderation(request)
    except _ModerationBlock as exc:
        raise HTTPException(status_code=403, detail=json.loads(exc.args[0]))

    if effective_prompt != request.prompt:
        request = request.model_copy(update={"prompt": effective_prompt})
    context_hint, persona_hint = await asyncio.gather(
        _fetch_context_hint(request.user_id, effective_prompt),
        _fetch_user_persona(request.user_id),
    )

    # Fetch per-tenant system prompt suffix (enterprise only; degrades open).
    tenant_suffix = await _fetch_tenant_prompt_suffix(request.enterprise_id) if request.enterprise_id else ""
    if tenant_suffix:
        context_hint = (
            f"{context_hint}\n\n[TENANT_CONSTRAINTS]\n{tenant_suffix}"
            if context_hint
            else f"[TENANT_CONSTRAINTS]\n{tenant_suffix}"
        )

    trace_id = str(uuid.uuid4())
    inner: StreamingResponse = await _generate(
        _to_local(request, force_media=force_media, context_hint=context_hint, persona_hint=persona_hint), background_tasks
    )
    if request.user_id and request.user_id != "anonymous":
        from shared.supermemory_client import add_memory as _sm_add
        background_tasks.add_task(
            _sm_add,
            user_id=request.user_id,
            content=request.prompt,
            metadata={"domain": request.domain or "", "intent": request.intent or "", "source": "enhance"},
        )
    enhanced_prompt = ""
    metadata: dict[str, Any] = {}
    annotated: list = []
    error: str | None = None
    async for raw_chunk in inner.body_iterator:
        if isinstance(raw_chunk, bytes):
            raw_chunk = raw_chunk.decode("utf-8")
        for line in raw_chunk.split("\n"):
            line = line.strip()
            if not line.startswith("data:"):
                continue
            raw_json = line[5:].strip()
            if not raw_json:
                continue
            try:
                event = json.loads(raw_json)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "done":
                result = event.get("result", {})
                enhanced_prompt = result.get("enhanced_prompt", "")
                annotated = result.get("annotated_segments", [])
                metadata = {
                    "domain": result.get("domain", ""),
                    "intent": result.get("intent", ""),
                    "intent_description": result.get("summary", ""),
                    "complexity": result.get("complexity", "medium"),
                }
                if extra_meta:
                    metadata.update(extra_meta)
            elif event.get("type") == "error":
                error = event.get("message", "enhancement failed")
    if error:
        raise HTTPException(status_code=502, detail=error)

    suggested_ai = _resolve_suggested_ai(persona_hint, metadata.get("domain", ""))

    if os.getenv("PROMPT_TRACE_ENABLED", "").lower() in ("1", "true", "yes"):
        try:
            from shared.prompt_trace_store import get_default_store as _get_trace_store
            _store = _get_trace_store()

            _raw = request.prompt or ""
            _enh = enhanced_prompt or ""
            _expansion_ratio = round(len(_enh) / len(_raw), 3) if _raw else 0.0
            _constraint_words = {"must", "only", "never", "always", "do not", "avoid", "require", "ensure"}
            _enh_lower = _enh.lower()
            _constraint_count = sum(_enh_lower.count(w) for w in _constraint_words)
            _placeholder_count = len(re.findall(r'\[[A-Z_]{3,}\]', _enh))
            _technique_count = len(annotated)

            trace_record = {
                "trace_id": trace_id,
                "flow": "enhance_chat",
                "user_id": request.user_id or "anonymous",
                "prompt_mode": request.context.get("mode", "") if isinstance(request.context, dict) else "",
                "target_ai": request.target_ai,
                "domain": metadata.get("domain", ""),
                "intent": metadata.get("intent", ""),
                "model": "llama-3.3-70b-versatile",
                "input": {"raw_prompt": _raw if os.getenv("PROMPT_TRACE_CAPTURE_FULL_TEXT", "").lower() in ("1", "true", "yes") else ""},
                "output": {"final_text": _enh, "quality_score": None},
                "before_after": {"before": _raw, "after": _enh},
                "metrics": {
                    "expansion_ratio": _expansion_ratio,
                    "constraint_count": _constraint_count,
                    "placeholder_count": _placeholder_count,
                    "technique_count": _technique_count,
                },
                "status": "completed",
                "suggested_ai": suggested_ai,
            }
            background_tasks.add_task(_store.record, trace_record)
            asyncio.create_task(write_trace(trace_record))
        except Exception:
            pass

    return {
        "enhanced_prompt": enhanced_prompt,
        "annotated_segments": annotated,
        "metadata": metadata,
        "tokens": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "_trace_id": trace_id,
        "suggested_ai": suggested_ai,
    }


class FeedbackRequest(BaseModel):
    trace_id: str
    outcome: str
    # Accepted for forward-compatible attribution; not yet used — record_outcome
    # keys solely on trace_id, which already carries the owning user_id.
    user_id: str = "anonymous"


@router.post("/enhance/feedback")
async def enhance_feedback(req: FeedbackRequest) -> dict[str, Any]:
    """Attach a downstream outcome to a prior enhancement. Degrades open.

    outcome ∈ {copied, reenhanced, thumbs_up, thumbs_down, ignored}.
    Always 200 — an unknown outcome returns status="ignored" rather than
    erroring, so the extension never has to handle a failure here.
    """
    from shared.trace_db import record_outcome

    ok = await record_outcome(req.trace_id, req.outcome)
    return {"status": "recorded" if ok else "ignored", "trace_id": req.trace_id}


async def _deduct_tokens(session: AsyncSession, user_id: str, cost: int) -> None:
    """Deduct enhancement tokens from the user's balance in PostgreSQL.

    Retained for reuse by refine.py. The canonical pipeline currently tracks
    usage via the local store; the production token ledger (table/column, or
    whether deduction happens in the Node backend) MUST be verified against the
    deployed source — see RECONCILE.md. Guarded so a schema mismatch never 500s.
    """
    if user_id in ("", "anonymous"):
        return
    try:
        result = await session.execute(
            text(
                "UPDATE user_tokens SET balance = balance - :cost "
                "WHERE user_id = :uid AND balance >= :cost "
                "RETURNING balance"
            ),
            {"cost": cost, "uid": user_id},
        )
        row = result.first()
        await session.commit()
    except Exception:  # noqa: BLE001 - DB schema may differ; never 500 enhance
        await session.rollback()
        return
    if row is None:
        raise HTTPException(status_code=402, detail="Insufficient token balance")
