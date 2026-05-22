from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.llm import agentic_stream

router = APIRouter(prefix="/agentic", tags=["agentic"])


class AgenticRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10_000)
    system_prompt: str = "You are a helpful AI assistant with web search, code execution, and browsing capabilities. Use your tools when needed to provide accurate, up-to-date information."
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=256, le=8192)


@router.post("/chat")
async def agentic_chat(request: AgenticRequest):
    import json
    async def event_stream():
        async for chunk in agentic_stream(
            request.system_prompt,
            request.prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        ):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
