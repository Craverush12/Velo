import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.llm import complete

router = APIRouter()

_SYSTEM_PROMPT = (Path(__file__).parent.parent / "core" / "prompts" / "refine_system.md").read_text()


def _normalize_result(result: dict) -> dict:
    prompt = result.get("refined_prompt") or ""
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
    return result


class RefineRequest(BaseModel):
    original_prompt: str
    clarification_qa: list[dict]
    user_id: str = "anonymous"
    target_ai: str | None = None


@router.post("/refine")
async def refine(request: RefineRequest):
    qa_lines = []
    for i, qa in enumerate(request.clarification_qa, 1):
        qa_lines.append(f"Q{i}: {qa.get('question', '')}")
        qa_lines.append(f"A{i}: {qa.get('answer', '')}")

    user_message = "\n".join([
        f"Original prompt: {request.original_prompt}",
        f"Target AI: {request.target_ai or 'not specified'}",
        "",
        "Clarification Q&A:",
        *qa_lines,
    ])

    raw = await complete(_SYSTEM_PROMPT, user_message)
    try:
        return _normalize_result(json.loads(raw))
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Failed to parse refinement response")
