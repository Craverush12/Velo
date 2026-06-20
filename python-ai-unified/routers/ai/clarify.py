"""/ai/clarify/* — generate clarifying questions for a prompt.

Source routes (canonical prompt-enhance / Server 3):
  - POST /clarify          -> /ai/clarify
  - POST /clarify/chat/mcq -> /ai/clarify/chat/mcq (multiple-choice format)

PER D-019: reuses the canonical ``api.refine.refine_prepare`` logic (the same
function the extension's /dev/test/clarify delegates to), rather than a
reconstructed clarification prompt. A light Redis rate-limit is layered on.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from shared.redis_cache import rate_limit_check

from local_app import RefinePrepareRequest, refine_prepare_fn

router = APIRouter(tags=["clarify"])

CLARIFY_RATE_LIMIT = 90
CLARIFY_RATE_WINDOW = 60


class ClarifyRequest(BaseModel):
    prompt: str
    user_id: str = "anonymous"
    auth_token: str = ""


async def _rate_limit(request: ClarifyRequest, http_request: Request) -> None:
    client = http_request.client.host if http_request.client else "unknown"
    allowed = await rate_limit_check(
        f"ai:clarify:rl:{request.user_id}:{client}",
        limit=CLARIFY_RATE_LIMIT,
        window_seconds=CLARIFY_RATE_WINDOW,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


async def _prepare_questions(request: ClarifyRequest) -> list[dict]:
    """Run the canonical refine-prepare pipeline and return its questions."""
    prepare_req = RefinePrepareRequest(
        original_prompt=request.prompt,
        user_id=request.user_id,
        prompt_mode="research",
    )
    result = await refine_prepare_fn(prepare_req)
    if isinstance(result, dict):
        return result.get("questions", []) or []
    # RefinePrepareResult model → questions attribute
    return getattr(result, "questions", []) or []


@router.post("/clarify")
async def clarify(request: ClarifyRequest, http_request: Request):
    """Generate clarifying questions for a prompt (canonical refine-prepare)."""
    await _rate_limit(request, http_request)
    questions = await _prepare_questions(request)
    return {"questions": questions[:3], "questions_total": min(len(questions), 3)}


@router.post("/clarify/chat/mcq")
async def clarify_chat_mcq(request: ClarifyRequest, http_request: Request):
    """MCQ-format clarifying questions (chat mode).

    Maps the canonical refine-prepare questions into the extension's MCQ shape
    (mirrors ``extension_bridge.ext_clarify``).
    """
    await _rate_limit(request, http_request)
    questions = await _prepare_questions(request)
    mcq_questions = [
        {
            "question_id": (q.get("id") if isinstance(q, dict) else getattr(q, "id", str(i)))
            or str(i),
            "question_text": (
                q.get("question") if isinstance(q, dict) else getattr(q, "question", "")
            )
            or "",
            "answer_options": (
                q.get("options") if isinstance(q, dict) else getattr(q, "options", [])
            )
            or [],
        }
        for i, q in enumerate(questions[:3])
    ]
    return {
        "mcq_questions": mcq_questions,
        "tokens": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }
