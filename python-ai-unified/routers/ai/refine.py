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
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from shared.legacy_compat import refine_result_to_legacy
from shared.enterprise_citations import enrich_refine_payload_with_citations, resolve_enterprise_context
from shared.redis_cache import rate_limit_check

# Canonical refine contract + handler (single source of truth per D-019).
from local_app import RefineRequest, refine_fn
from core.contracts import ClarificationQA

from .enhance import _deduct_tokens, _fetch_context_hint, _fetch_user_persona

from shared.db import get_session

router = APIRouter(tags=["refine"])

REFINE_TOKEN_COST = 1
REFINE_RATE_LIMIT = 60
REFINE_RATE_WINDOW = 60


class RefineChatRequest(BaseModel):
    """Accepts canonical and legacy PromptEnhancement refine bodies."""

    original_prompt: str | None = None
    clarification_qa: list[ClarificationQA] | None = None
    prompt: str | None = None
    qa_pairs: list[dict[str, Any]] = Field(default_factory=list)
    previous_enhanced_prompt: str | None = None
    previous_response: str | None = None
    user_id: str = "anonymous"
    target_ai: str | None = None
    prompt_mode: str = "normal"
    incognito: bool = False
    enterprise_id: str | None = None
    team_id: str | None = None
    auth_token: str = ""
    previous_citations: list[dict[str, Any]] = Field(default_factory=list)
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)
    context_used: list[dict[str, Any]] = Field(default_factory=list)
    used_documents: list[dict[str, Any]] = Field(default_factory=list)
    company_policy_names: list[str] = Field(default_factory=list)
    project_policy_names: list[str] = Field(default_factory=list)
    matched_content_sources: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_legacy_fields(self) -> "RefineChatRequest":
        if not self.original_prompt and self.prompt:
            self.original_prompt = self.prompt
        if not self.clarification_qa and self.qa_pairs:
            self.clarification_qa = [
                ClarificationQA(
                    question=str(pair.get("question", "")),
                    answer=str(pair.get("answer", "")),
                )
                for pair in self.qa_pairs
                if str(pair.get("answer", "")).strip()
            ]
        if self.clarification_qa is None:
            self.clarification_qa = []
        if not self.previous_enhanced_prompt and self.previous_response:
            self.previous_enhanced_prompt = self.previous_response
        if not self.original_prompt or not str(self.original_prompt).strip():
            raise ValueError("original_prompt (or legacy prompt) must not be empty")
        return self

    def to_refine_request(self) -> RefineRequest:
        return RefineRequest(
            original_prompt=str(self.original_prompt).strip(),
            clarification_qa=self.clarification_qa or [],
            previous_enhanced_prompt=self.previous_enhanced_prompt,
            user_id=self.user_id,
            target_ai=self.target_ai,  # type: ignore[arg-type]
            prompt_mode=self.prompt_mode,  # type: ignore[arg-type]
            incognito=self.incognito,
        )


def _serialize_refine_result(
    result: Any,
    *,
    enterprise_ctx: dict[str, Any] | None = None,
    carry_forward: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        payload = result.model_dump()
    elif isinstance(result, dict):
        payload = dict(result)
    else:
        payload = {"refined_prompt": str(result)}
    payload.setdefault("original_prompt", payload.get("prompt"))
    payload["qa_pairs_used"] = payload.get("clarification_qa") or payload.get("qa_pairs_used") or []
    legacy = refine_result_to_legacy(payload)
    return enrich_refine_payload_with_citations(
        legacy,
        enterprise_ctx=enterprise_ctx,
        carry_forward=carry_forward,
    )


async def _resolve_refine_enterprise_context(request: RefineChatRequest) -> dict[str, Any]:
    if not request.enterprise_id and not request.auth_token:
        return {}
    try:
        return await resolve_enterprise_context(
            str(request.original_prompt or ""),
            enterprise_id=request.enterprise_id,
            team_id=request.team_id,
            auth_token=request.auth_token,
        )
    except Exception:
        return {}


def _refine_carry_forward(request: RefineChatRequest) -> dict[str, Any]:
    return {
        "previous_citations": request.previous_citations,
        "retrieved_chunks": request.retrieved_chunks,
        "context_used": request.context_used,
        "used_documents": request.used_documents,
        "company_policy_names": request.company_policy_names,
        "project_policy_names": request.project_policy_names,
        "matched_content_sources": request.matched_content_sources,
    }


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
    request: RefineChatRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Chat-mode refine (non-streaming).

    Source: POST /refine/chat on prompt-enhance (Server 3). Same canonical
    handler as /refine; accepts legacy ``prompt`` + ``qa_pairs`` request body.
    """
    await _rate_guard(request.user_id, http_request)
    enterprise_ctx = await _resolve_refine_enterprise_context(request)
    refine_request = request.to_refine_request()
    if enterprise_ctx.get("combined_context"):
        existing_hint = refine_request.context_hint or ""
        combined = str(enterprise_ctx["combined_context"])
        refine_request.context_hint = (
            f"{existing_hint}\n\n[ENTERPRISE_CONTEXT]\n{combined}"
            if existing_hint
            else f"[ENTERPRISE_CONTEXT]\n{combined}"
        )
    refine_request = await _attach_context_hint(refine_request)
    result = await refine_fn(refine_request)
    await _deduct_tokens(session, request.user_id, REFINE_TOKEN_COST)
    return _serialize_refine_result(
        result,
        enterprise_ctx=enterprise_ctx,
        carry_forward=_refine_carry_forward(request),
    )


async def _refine_stream(request: RefineChatRequest, session: AsyncSession):
    """Frame the canonical (non-streaming) refine result as an SSE stream.

    No canonical streaming refine handler exists, so we run the canonical
    ``refine_fn`` once and emit a single ``done`` event carrying its result —
    keeping the prompt/LLM logic in one place (D-019). See RECONCILE.md: verify
    the exact streaming envelope the consumer/enterprise clients expect for
    refine (the enhance path uses content/complete/[DONE]).
    """
    try:
        enterprise_ctx = await _resolve_refine_enterprise_context(request)
        refine_request = request.to_refine_request()
        if enterprise_ctx.get("combined_context"):
            existing_hint = refine_request.context_hint or ""
            combined = str(enterprise_ctx["combined_context"])
            refine_request.context_hint = (
                f"{existing_hint}\n\n[ENTERPRISE_CONTEXT]\n{combined}"
                if existing_hint
                else f"[ENTERPRISE_CONTEXT]\n{combined}"
            )
        refine_request = await _attach_context_hint(refine_request)
        result = await refine_fn(refine_request)
    except HTTPException as exc:
        yield "data: " + json.dumps({"type": "error", "message": exc.detail}) + "\n\n"
        return
    except Exception as exc:  # noqa: BLE001 - never break the stream
        yield "data: " + json.dumps({"type": "error", "message": str(exc)}) + "\n\n"
        return
    await _deduct_tokens(session, request.user_id, REFINE_TOKEN_COST)
    yield "data: " + json.dumps(
        {
            "type": "done",
            "result": _serialize_refine_result(
                result,
                enterprise_ctx=enterprise_ctx,
                carry_forward=_refine_carry_forward(request),
            ),
        }
    ) + "\n\n"


@router.post("/refine/chat/stream")
async def refine_chat_stream(
    request: RefineChatRequest,
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
