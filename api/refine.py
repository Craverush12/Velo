from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from core.contracts import AnnotatedSegment, ClarificationQA, PlaceholderField
from core.llm import complete
from core.output_validator import OutputValidationError, parse_validate_with_repair
from core.prompt_metadata import prompt_hash
import json

router = APIRouter()

_SYSTEM_PROMPT = (Path(__file__).parent.parent / "core" / "prompts" / "refine_system.md").read_text()
_PROMPT_HASH = prompt_hash("refine_system.md")


class RefineRequest(BaseModel):
    original_prompt: str
    clarification_qa: list[ClarificationQA]
    previous_enhanced_prompt: str | None = None
    previous_annotated_segments: list[AnnotatedSegment] = Field(default_factory=list)
    previous_framework_used: str | None = None
    previous_pe_techniques_applied: list[str] = Field(default_factory=list)
    previous_placeholder_fields: list[PlaceholderField] = Field(default_factory=list)
    user_id: str = "anonymous"
    target_ai: str | None = None

    @field_validator("original_prompt")
    @classmethod
    def original_prompt_not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("original_prompt must not be empty")
        return value.strip()


def build_refine_user_message(request: RefineRequest) -> str:
    qa_lines = []
    for i, qa in enumerate(request.clarification_qa, 1):
        qa_lines.append(f"Q{i}: {qa.question}")
        qa_lines.append(f"A{i}: {qa.answer}")

    lines = [
        f"Original prompt: {request.original_prompt}",
        f"Target AI: {request.target_ai or 'not specified'}",
        "",
    ]

    if request.previous_enhanced_prompt:
        lines.extend([
            "Previously enhanced prompt:",
            request.previous_enhanced_prompt,
            "",
            f"Previous framework used: {request.previous_framework_used or 'not specified'}",
            "Previous PE techniques:",
            json.dumps(request.previous_pe_techniques_applied, ensure_ascii=False),
            "",
            "Previous placeholder fields JSON:",
            json.dumps(
                [field.model_dump(mode="json") for field in request.previous_placeholder_fields],
                ensure_ascii=False,
            ),
            "",
            "Previous annotated segments JSON:",
            json.dumps(
                [segment.model_dump(mode="json") for segment in request.previous_annotated_segments],
                ensure_ascii=False,
            ),
            "",
        ])
    else:
        lines.extend([
            "Previously enhanced prompt: not provided",
            "Refine from the original prompt and clarification answers only.",
            "",
        ])

    lines.extend([
        "Clarification Q&A:",
        *qa_lines,
    ])
    return "\n".join(lines)


async def _repair_output(kind: str, raw: str, repair_prompt: str) -> str:
    return await complete(
        "You repair ThinkVelocity JSON outputs. Return only valid JSON.",
        repair_prompt,
        temperature=0,
        max_tokens=4096,
    )


@router.post("/refine")
async def refine(request: RefineRequest):
    user_message = build_refine_user_message(request)
    raw = await complete(_SYSTEM_PROMPT, user_message, temperature=0.3)
    try:
        return await parse_validate_with_repair(
            "refine",
            raw,
            prompt_hash=_PROMPT_HASH,
            repair_callback=_repair_output,
        )
    except OutputValidationError as e:
        raise HTTPException(status_code=502, detail=e.to_detail())
