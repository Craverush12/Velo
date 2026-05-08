import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from core import context_loader, safety
from core.llm import stream_completion
from core.normalize import quality_ceiling as _quality_ceiling, normalize_result as _normalize_result
from storage import store

router = APIRouter()

_SYSTEM_PROMPT = (Path(__file__).parent.parent / "core" / "prompts" / "enhance_system.md").read_text()


class EnhanceRequest(BaseModel):
    prompt: str
    user_id: str = "anonymous"
    target_ai: str | None = None
    session_id: str | None = None

    @field_validator("prompt")
    @classmethod
    def prompt_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt must not be empty")
        if len(v) > 10_000:
            raise ValueError("prompt must not exceed 10,000 characters")
        return v


async def _generate(request: EnhanceRequest, background_tasks: BackgroundTasks):
    clean_prompt, redactions = safety.redact(request.prompt)

    user_ctx = store.get_user_context(request.user_id)
    ctx_block = context_loader.format_context_for_prompt(user_ctx)

    user_message_parts = [
        f"Raw prompt: {clean_prompt}",
        f"Target AI: {request.target_ai or 'not specified'}",
    ]
    if ctx_block:
        user_message_parts.append(ctx_block)
    user_message = "\n".join(user_message_parts)

    accumulated = ""
    usage_sink: dict = {}

    async def event_stream():
        nonlocal accumulated
        try:
            async for chunk in stream_completion(_SYSTEM_PROMPT, user_message, usage_sink=usage_sink):
                accumulated += chunk
                payload = json.dumps({"type": "chunk", "content": chunk})
                yield f"data: {payload}\n\n"

            try:
                result = _normalize_result(json.loads(accumulated), clean_prompt)
                if redactions:
                    result["_redactions"] = redactions
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
                    clean_prompt,                       # original_prompt
                    result.get("enhanced_prompt", ""),  # enhanced_prompt
                )
                payload = json.dumps({"type": "done", "result": result})
                yield f"data: {payload}\n\n"
            except json.JSONDecodeError:
                payload = json.dumps({
                    "type": "error",
                    "message": "Failed to parse enhancement output",
                    "raw": accumulated[:500],
                })
                yield f"data: {payload}\n\n"
        except HTTPException as e:
            payload = json.dumps({"type": "error", "message": e.detail})
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/enhance")
async def enhance(request: EnhanceRequest, background_tasks: BackgroundTasks):
    return await _generate(request, background_tasks)
