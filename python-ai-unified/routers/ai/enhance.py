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

import json
import logging
import re
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

_INJECTION_PATTERNS = [
    r'ignore.{0,10}previous',
    r'system prompt',
    r'you are now',
    r'disregard',
    r'forget.{0,10}instructions',
    r'new instructions',
    r'ignore.{0,10}instructions',
]

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from shared.db import get_session
from shared.redis_cache import rate_limit_check

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
        from shared.db import async_engine
        async with AsyncSession(async_engine) as session:
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


async def _fetch_context_hint(user_id: str, query: str) -> str:
    """Fetch the top-3 session essences from Node backend context store via in-process search.

    Returns a pipe-delimited string of essences, or empty string on any failure.
    Degrades open — a missing context hint never blocks enhancement.
    """
    if not user_id or user_id == "anonymous":
        return ""
    try:
        from routers.context import search_contexts, ContextSearchRequest
        response = await search_contexts(
            ContextSearchRequest(user_id=user_id, query=query, limit=3)
        )
        results = response.results or []
        passed = [r for r in results if r.similarity >= CONTEXT_SIMILARITY_THRESHOLD and r.essence and r.essence != "User is working on a task."]
        if len(results) > len(passed):
            logger.debug("context_hint: gated %d low-relevance essences (threshold=%.2f)", len(results) - len(passed), CONTEXT_SIMILARITY_THRESHOLD)
        essences = [r.essence for r in passed]
        return " | ".join(essences) if essences else ""
    except Exception:
        return ""


def _sanitize_attachment_text(name: str, text: str, user_id: str) -> str:
    """Sanitise attachment text before it reaches LLM infrastructure.

    Order of operations:
      1. Truncate to 8000 chars (bridge-layer limit; canonical side truncates at 5000).
      2. PII redaction — emails, phones, SSNs, card numbers, API keys.
      3. Prompt-injection detection — if matched, replace entire text with a
         policy-violation notice and log a WARNING.
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
            return "[CONTENT REDACTED: policy violation detected in attachment]"

    return text


def _to_local(
    req: EnhanceRequest,
    *,
    force_media: bool = False,
    context_hint: str = "",
) -> LocalEnhanceRequest:
    """Translate the extension request into the canonical EnhanceRequest."""
    mode = "media" if force_media else map_mode(req.context.get("mode"))
    attachments = [
        LocalAttachmentItem(
            name=a.get("name", "") if isinstance(a, dict) else "",
            text=_sanitize_attachment_text(
                a.get("name", "") if isinstance(a, dict) else "",
                a.get("text", "") if isinstance(a, dict) else "",
                req.user_id,
            ),
        )
        for a in (req.attachments or [])
        if isinstance(a, dict) and a.get("text")
    ]
    return LocalEnhanceRequest(
        prompt=req.prompt,
        user_id=req.user_id,
        target_ai=req.target_ai or None,
        prompt_mode=mode,
        attachments=attachments,
        context_hint=context_hint,
    )


async def _adapt_stream(inner_resp: StreamingResponse, *, extra_meta: dict[str, Any] | None = None):
    """Adapt the canonical chunk/done SSE → extension content/complete/[DONE].

    ``extra_meta`` is merged into the ``metadata`` field of the ``complete``
    event. Used to propagate moderation annotations (``redacted``, ``warning``)
    to the client without altering consumer paths (extra_meta is None / {} there).
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
                yield "data: " + json.dumps(
                    {
                        "type": "complete",
                        "enhanced_prompt": result.get("enhanced_prompt", ""),
                        "annotated_segments": result.get("annotated_segments", []),
                        "performance": {"processing_time_ms": 0},
                        "metadata": metadata,
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

    # Fetch session essence from Node backend context store (best-effort, degrades open).
    context_hint = await _fetch_context_hint(request.user_id, effective_prompt)

    # Fetch per-tenant system prompt suffix (enterprise only; degrades open).
    tenant_suffix = await _fetch_tenant_prompt_suffix(request.enterprise_id) if request.enterprise_id else ""
    if tenant_suffix:
        context_hint = (
            f"{context_hint}\n\n[TENANT_CONSTRAINTS]\n{tenant_suffix}"
            if context_hint
            else f"[TENANT_CONSTRAINTS]\n{tenant_suffix}"
        )

    inner: StreamingResponse = await _generate(
        _to_local(request, context_hint=context_hint), background_tasks
    )
    return StreamingResponse(
        _adapt_stream(inner, extra_meta=extra_meta),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
    context_hint = await _fetch_context_hint(request.user_id, effective_prompt)

    # Fetch per-tenant system prompt suffix (enterprise only; degrades open).
    tenant_suffix = await _fetch_tenant_prompt_suffix(request.enterprise_id) if request.enterprise_id else ""
    if tenant_suffix:
        context_hint = (
            f"{context_hint}\n\n[TENANT_CONSTRAINTS]\n{tenant_suffix}"
            if context_hint
            else f"[TENANT_CONSTRAINTS]\n{tenant_suffix}"
        )

    inner: StreamingResponse = await _generate(
        _to_local(request, force_media=force_media, context_hint=context_hint), background_tasks
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
    return {
        "enhanced_prompt": enhanced_prompt,
        "annotated_segments": annotated,
        "metadata": metadata,
        "tokens": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }


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
