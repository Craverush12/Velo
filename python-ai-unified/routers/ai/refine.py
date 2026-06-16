"""/ai/refine/* — refine an already-enhanced prompt.

Source routes (canonical prompt-enhance / Server 3):
  - POST /refine             -> /ai/refine
  - POST /refine/chat        -> /ai/refine/chat        (chat-mode, non-streaming)
  - POST /refine/chat/stream -> /ai/refine/chat/stream (SSE)

PER D-019: this router REUSES this monorepo's canonical refine pipeline —
``api.refine.refine`` (the same handler the extension hits via /dev/test/refine,
see ``api/extension_bridge.ext_refine``) — rather than a reconstructed refine
prompt. The endpoint request model IS the canonical ``RefineRequest`` so there
is no contract drift.

Per merge plan §5 the refine router layers on PostgreSQL token deduction and a
Redis rate-limit (both degrade open) — concerns the canonical handler does not
own. The canonical handler already returns its own deterministic fallback on
validation failure, so these endpoints never 500 on bad LLM output.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from shared.redis_cache import rate_limit_check

# Canonical refine contract + handler (single source of truth per D-019).
from local_app import RefineRequest, refine_fn

from .enhance import _deduct_tokens, _fetch_context_hint, _fetch_user_persona

router = APIRouter(tags=["refine"])

REFINE_TOKEN_COST = 1
REFINE_RATE_LIMIT = 60
REFINE_RATE_WINDOW = 60


async def _attach_context_hint(request: RefineRequest) -> RefineRequest:
    """Populate request.context_hint and request.persona_hint (D-110 / persona feature).

    Mirrors the enhance pipeline's personalization step so refinements stay
    consistent with what the user's prior sessions establish (stack, domain,
    terminology) and who the user is (occupation, AI familiarity). Skipped for
    incognito requests. Degrades open — any failure leaves the hint empty,
    never blocks refinement.
    """
    if request.incognito or not request.user_id or request.user_id == "anonymous":
        return request
    try:
        import asyncio as _asyncio
        hint, persona = await _asyncio.gather(
            _fetch_context_hint(request.user_id, request.original_prompt),
            _fetch_user_persona(request.user_id),
        )
        if hint:
            request.context_hint = hint
        if persona:
            request.persona_hint = persona
    except Exception:
        pass  # refine must never fail because personalization lookup failed
    return request


async def _rate_guard(user_id: str, http_request: Request) -> None:
    client = http_request.client.host if http_request.client else "unknown"
    allowed = await rate_limit_check(
        f"ai:refine:rl:{user_id}:{client}",
        limit=REFINE_RATE_LIMIT,
        window_seconds=REFINE_RATE_WINDOW,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


@router.post("/refine")
async def refine(
    request: RefineRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Refine an already-enhanced prompt (canonical refine pipeline).

    Source: POST /refine on prompt-enhance (Server 3).
    """
    await _rate_guard(request.user_id, http_request)
    request = await _attach_context_hint(request)
    result = await refine_fn(request)
    await _deduct_tokens(session, request.user_id, REFINE_TOKEN_COST)
    return result


@router.post("/refine/chat")
async def refine_chat(
    request: RefineRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Chat-mode refine (non-streaming).

    Source: POST /refine/chat on prompt-enhance (Server 3). Same canonical
    handler as /refine; the chat variant exists for client routing parity.
    """
    await _rate_guard(request.user_id, http_request)
    request = await _attach_context_hint(request)
    result = await refine_fn(request)
    await _deduct_tokens(session, request.user_id, REFINE_TOKEN_COST)
    return result


async def _refine_stream(request: RefineRequest, session: AsyncSession):
    """Frame the canonical (non-streaming) refine result as an SSE stream.

    No canonical streaming refine handler exists, so we run the canonical
    ``refine_fn`` once and emit a single ``done`` event carrying its result —
    keeping the prompt/LLM logic in one place (D-019). See RECONCILE.md: verify
    the exact streaming envelope the consumer/enterprise clients expect for
    refine (the enhance path uses content/complete/[DONE]).
    """
    try:
        request = await _attach_context_hint(request)
        result = await refine_fn(request)
    except HTTPException as exc:
        yield "data: " + json.dumps({"type": "error", "message": exc.detail}) + "\n\n"
        return
    except Exception as exc:  # noqa: BLE001 - never break the stream
        yield "data: " + json.dumps({"type": "error", "message": str(exc)}) + "\n\n"
        return
    await _deduct_tokens(session, request.user_id, REFINE_TOKEN_COST)
    yield "data: " + json.dumps({"type": "done", "result": result}) + "\n\n"


@router.post("/refine/chat/stream")
async def refine_chat_stream(
    request: RefineRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Streaming refine (SSE).

    Source: POST /refine/chat/stream on prompt-enhance (Server 3 only).
    """
    await _rate_guard(request.user_id, http_request)
    return StreamingResponse(
        _refine_stream(request, session),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
