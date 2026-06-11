"""
Adapter layer exposing extension-compatible endpoints at /dev/test/...
Translates the Chrome extension's protocol to the internal FastAPI pipeline.

Extension protocol:
  POST /dev/test/enhance/stream          → SSE: type "content"/"complete"/"[DONE]"
  POST /dev/test/clarify                 → { mcq_questions: [...] }
  POST /dev/test/refine                  → { enhanced_prompt, tokens }
  POST /dev/test/transcribe              → { transcript }
  POST /dev/test/api/v1/quality/analyze-prompt → { status, metadata }

Internal pipeline:
  POST /enhance                          → SSE: type "chunk"/"done"
  POST /refine/prepare                   → { questions: [...] }
  POST /refine                           → { refined_prompt, ... }
  POST /cothinker/transcribe             → { transcript }
"""
from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.cothinker import cothinker_transcribe as _cothinker_transcribe
from api.enhance import EnhanceRequest, _generate
from api.refine import (
    RefineRequest,
    RefinePrepareRequest,
    refine as _refine,
    refine_prepare as _refine_prepare,
)
from core.contracts import ClarificationQA, normalize_prompt_mode

router = APIRouter(prefix="/dev/test")

_EXT_MODE_TO_INTERNAL: dict[str, str] = {
    "flash": "normal",
    "standard": "normal",
    "best": "research",
    "build": "fast_build",
    "media": "media",
}


def _map_mode(ext_mode: str | None) -> str:
    raw = (ext_mode or "flash").lower()
    return normalize_prompt_mode(_EXT_MODE_TO_INTERNAL.get(raw, "normal"))


# ── Enhance stream ────────────────────────────────────────────────────────────

class ExtEnhanceRequest(BaseModel):
    prompt: str
    user_id: str = "anonymous"
    auth_token: str = ""
    context: dict = {}
    chat_history: list = []
    target_ai: str | None = None
    domain: str = ""
    intent: str = ""
    intent_description: str = ""
    user_context: dict = {}


@router.post("/enhance/stream")
async def ext_enhance_stream(ext_req: ExtEnhanceRequest, background_tasks: BackgroundTasks):
    mode = _map_mode(ext_req.context.get("mode"))
    inner_req = EnhanceRequest(
        prompt=ext_req.prompt,
        user_id=ext_req.user_id,
        target_ai=ext_req.target_ai or None,
        prompt_mode=mode,
    )
    inner_resp: StreamingResponse = await _generate(inner_req, background_tasks)

    async def adapted_stream():
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
                    payload = json.dumps({"type": "content", "chunk": event.get("content", "")})
                    yield f"data: {payload}\n\n"
                elif ev_type == "done":
                    result = event.get("result", {})
                    payload = json.dumps({
                        "type": "complete",
                        "enhanced_prompt": result.get("enhanced_prompt", ""),
                        "annotated_segments": result.get("annotated_segments", []),
                        "performance": {"processing_time_ms": 0},
                        "metadata": {
                            "domain": result.get("domain", ""),
                            "intent": result.get("intent", ""),
                            "intent_description": result.get("summary", ""),
                            "complexity": result.get("complexity", "medium"),
                        },
                    })
                    yield f"data: {payload}\n\n"
                    yield "data: [DONE]\n\n"
                elif ev_type == "error":
                    payload = json.dumps({"type": "error", "message": event.get("message", "")})
                    yield f"data: {payload}\n\n"

    return StreamingResponse(
        adapted_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Clarify ───────────────────────────────────────────────────────────────────

class ExtClarifyRequest(BaseModel):
    prompt: str
    user_id: str = "anonymous"
    auth_token: str = ""


@router.post("/clarify")
async def ext_clarify(req: ExtClarifyRequest):
    prepare_req = RefinePrepareRequest(
        original_prompt=req.prompt,
        user_id=req.user_id,
        prompt_mode="research",
    )
    result = await _refine_prepare(prepare_req)
    questions: list[dict] = result.get("questions", [])
    mcq_questions = [
        {
            "question_id": q.get("id", str(i)),
            "question_text": q.get("question", ""),
            "answer_options": q.get("options", []),
        }
        for i, q in enumerate(questions)
    ]
    return {
        "mcq_questions": mcq_questions,
        "tokens": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }


# ── Refine ────────────────────────────────────────────────────────────────────

class ExtRefineRequest(BaseModel):
    prompt: str
    qa_pairs: list[dict] = []
    user_id: str = "anonymous"
    auth_token: str = ""


@router.post("/refine")
async def ext_refine(req: ExtRefineRequest):
    clarification_qa = [
        ClarificationQA(
            question=pair.get("question", ""),
            answer=pair.get("answer", ""),
        )
        for pair in req.qa_pairs
        if pair.get("answer", "").strip()
    ]
    refine_req = RefineRequest(
        original_prompt=req.prompt,
        clarification_qa=clarification_qa,
        user_id=req.user_id,
        prompt_mode="research",
    )
    result = await _refine(refine_req)
    return {
        "enhanced_prompt": result.get("refined_prompt", ""),
        "tokens": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }


# ── Transcribe (voice-to-text) ────────────────────────────────────────────────

@router.post("/transcribe")
async def ext_transcribe(audio: UploadFile = File(...)):
    """Proxy for cothinker_transcribe — used by the Chrome extension voice mode."""
    return await _cothinker_transcribe(audio)


# ── Quality analyze stub ──────────────────────────────────────────────────────

class ExtQualityRequest(BaseModel):
    prompt: str


@router.post("/api/v1/quality/analyze-prompt")
async def ext_quality_analyze(req: ExtQualityRequest):
    text = req.prompt.lower()
    if any(w in text for w in ("code", "function", "class", "build", "implement", "develop", "debug")):
        domain, intent = "software_development", "implementation"
    elif any(w in text for w in ("write", "essay", "blog", "article", "copy", "draft")):
        domain, intent = "content_creation", "writing"
    elif any(w in text for w in ("data", "analyze", "research", "study", "insight", "report")):
        domain, intent = "research_analysis", "analysis"
    elif any(w in text for w in ("design", "ui", "ux", "image", "visual", "logo", "create")):
        domain, intent = "design", "creation"
    else:
        domain, intent = "general", "task_completion"

    return {
        "status": "success",
        "metadata": {
            "domain": domain,
            "intent": intent,
            "intent_description": f"User wants to accomplish a {domain.replace('_', ' ')} task.",
        },
    }
