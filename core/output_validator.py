from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from core.contracts import (
    SCHEMA_VERSION,
    TECHNIQUE_COLORS,
    ClarificationQuestion,
    EnhanceResult,
    RefineResult,
)


class OutputValidationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        error_code: str = "output_validation_failed",
        validation_errors: list[dict] | None = None,
        raw_excerpt: str = "",
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.validation_errors = validation_errors or []
        self.raw_excerpt = raw_excerpt[:500]

    def to_detail(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": str(self),
            "validation_errors": self.validation_errors,
            "raw_excerpt": self.raw_excerpt,
        }


RepairCallback = Callable[[str, str, str], Awaitable[str]]


def quality_ceiling(raw_prompt: str) -> float:
    words = [w for w in raw_prompt.replace("\n", " ").split(" ") if w.strip()]
    word_count = len(words)
    char_count = len(raw_prompt.strip())
    markers = 0
    marker_terms = [
        "output", "format", "audience", "target", "tone", "constraint",
        "example", "context", "because", "using", "avoid", "include",
        "json", "table", "steps", "role", "goal", "metric",
    ]
    lowered = raw_prompt.lower()
    markers += sum(1 for term in marker_terms if term in lowered)
    markers += 1 if "[" in raw_prompt and "]" in raw_prompt else 0
    markers += 1 if "\n" in raw_prompt else 0

    if char_count <= 2 or word_count <= 1:
        return 0.08
    if word_count <= 3:
        return 0.18
    if word_count <= 7 and markers == 0:
        return 0.28
    if word_count <= 12 and markers <= 1:
        return 0.42
    if word_count <= 25 and markers <= 2:
        return 0.62
    if markers >= 4 and word_count >= 20:
        return 0.88
    return 0.74


def parse_json_object(raw: str) -> dict:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = _local_json_cleanup(raw)
    if not isinstance(parsed, dict):
        raise OutputValidationError(
            "Model output must be a JSON object",
            error_code="invalid_json_shape",
            raw_excerpt=raw,
        )
    return parsed


def _local_json_cleanup(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start:end + 1]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise OutputValidationError(
            "Failed to parse model JSON output",
            error_code="json_parse_failed",
            validation_errors=[{"msg": exc.msg, "line": exc.lineno, "column": exc.colno}],
            raw_excerpt=raw,
        ) from exc


def validate_enhance_result(
    result: dict,
    *,
    raw_prompt: str = "",
    prompt_hash: str | None = None,
) -> dict:
    normalized = _normalize_common(result, prompt_field="enhanced_prompt")
    raw_score = normalized.get("prompt_quality_score", 0.0)
    try:
        model_score = float(raw_score or 0.0)
    except (TypeError, ValueError):
        model_score = 0.0
    normalized["prompt_quality_score"] = round(
        max(0.0, min(model_score, quality_ceiling(raw_prompt))), 2
    )
    normalized["schema_version"] = SCHEMA_VERSION
    normalized["prompt_version"] = prompt_hash
    try:
        validated = EnhanceResult.model_validate(normalized)
    except ValidationError as exc:
        raise OutputValidationError(
            "Enhancement output failed schema validation",
            validation_errors=_validation_errors(exc),
            raw_excerpt=json.dumps(result, default=str)[:500],
        ) from exc
    _validate_segments(validated.enhanced_prompt, validated.annotated_segments)
    _validate_placeholders(validated.enhanced_prompt, validated.placeholder_fields)
    return validated.model_dump(mode="json")


def validate_refine_result(
    result: dict,
    *,
    prompt_hash: str | None = None,
) -> dict:
    normalized = _normalize_common(result, prompt_field="refined_prompt")
    normalized["schema_version"] = SCHEMA_VERSION
    normalized["prompt_version"] = prompt_hash
    try:
        validated = RefineResult.model_validate(normalized)
    except ValidationError as exc:
        raise OutputValidationError(
            "Refinement output failed schema validation",
            validation_errors=_validation_errors(exc),
            raw_excerpt=json.dumps(result, default=str)[:500],
        ) from exc
    _validate_segments(validated.refined_prompt, validated.annotated_segments)
    _validate_placeholders(validated.refined_prompt, validated.placeholder_fields)
    return validated.model_dump(mode="json")


async def parse_validate_with_repair(
    kind: str,
    raw: str,
    *,
    raw_prompt: str = "",
    prompt_hash: str | None = None,
    repair_callback: RepairCallback | None = None,
) -> dict:
    try:
        return _validate_kind(kind, parse_json_object(raw), raw_prompt=raw_prompt, prompt_hash=prompt_hash)
    except OutputValidationError as first_error:
        if repair_callback is None:
            raise first_error
        repair_prompt = _repair_prompt(kind, raw, first_error)
        repaired_raw = await repair_callback(kind, raw, repair_prompt)
        try:
            repaired = _validate_kind(
                kind,
                parse_json_object(repaired_raw),
                raw_prompt=raw_prompt,
                prompt_hash=prompt_hash,
            )
        except OutputValidationError as repair_error:
            raise OutputValidationError(
                "Model output could not be repaired into the required schema",
                error_code="json_repair_failed",
                validation_errors=repair_error.validation_errors or first_error.validation_errors,
                raw_excerpt=raw,
            ) from repair_error
        repaired["_repair_status"] = "llm_repaired"
        return repaired


def _validate_kind(kind: str, result: dict, *, raw_prompt: str, prompt_hash: str | None) -> dict:
    if kind == "enhance":
        return validate_enhance_result(result, raw_prompt=raw_prompt, prompt_hash=prompt_hash)
    if kind == "refine":
        return validate_refine_result(result, prompt_hash=prompt_hash)
    raise ValueError(f"Unknown output kind: {kind}")


def _normalize_common(result: dict, *, prompt_field: str) -> dict:
    normalized = dict(result)
    _normalize_clarification_questions(normalized)
    _repair_segment_texts(normalized, prompt_field)
    _normalize_segment_colors(normalized)
    _normalize_placeholder_fields(normalized, prompt_field)
    _normalize_techniques(normalized)
    return normalized


def _normalize_clarification_questions(result: dict) -> None:
    questions = result.get("clarification_questions")
    if questions is None:
        return
    normalized = []
    for item in questions:
        if isinstance(item, str):
            normalized.append({"question": item, "options": []})
        elif isinstance(item, dict):
            normalized.append(item)
    result["clarification_questions"] = [
        ClarificationQuestion.model_validate(item).model_dump(mode="json")
        for item in normalized
        if item.get("question")
    ]


def _repair_segment_texts(result: dict, prompt_field: str) -> None:
    prompt = result.get(prompt_field) or ""
    segments = result.get("annotated_segments") or []
    if not prompt or not segments:
        return
    if "".join(str(seg.get("text", "")) for seg in segments) == prompt:
        return

    cursor = 0
    repaired = []
    for seg in segments:
        text = str(seg.get("text", ""))
        stripped = text.strip()
        found = prompt.find(stripped, cursor) if stripped else -1
        if found < 0:
            return
        new_seg = dict(seg)
        new_seg["text"] = prompt[cursor:found] + stripped
        repaired.append(new_seg)
        cursor = found + len(stripped)
    if repaired and cursor <= len(prompt):
        repaired[-1]["text"] += prompt[cursor:]
        result["annotated_segments"] = repaired


def _normalize_segment_colors(result: dict) -> None:
    for seg in result.get("annotated_segments") or []:
        technique = seg.get("technique")
        expected = TECHNIQUE_COLORS.get(technique)
        if expected:
            seg["color_key"] = expected


def _normalize_techniques(result: dict) -> None:
    techniques = []
    for seg in result.get("annotated_segments") or []:
        technique = seg.get("technique")
        if technique and technique not in techniques:
            techniques.append(technique)
    if result.get("placeholder_fields") and "placeholder_facilitation" not in techniques:
        techniques.append("placeholder_facilitation")
    if techniques:
        result["pe_techniques_applied"] = techniques


def _normalize_placeholder_fields(result: dict, prompt_field: str) -> None:
    fields = result.get("placeholder_fields") or []
    normalized = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        key = str(field.get("key") or "").strip().upper()
        placeholder = str(field.get("placeholder") or f"[{key}]").strip()
        if key and not placeholder.startswith("["):
            placeholder = f"[{placeholder}]"
        field = dict(field)
        field["key"] = key
        field["placeholder"] = placeholder
        normalized.append(field)
    result["placeholder_fields"] = normalized


def _validate_segments(prompt: str, segments: list[Any]) -> None:
    segment_text = "".join(seg.text for seg in segments)
    if segment_text != prompt:
        raise OutputValidationError(
            "Annotated segment text must concatenate exactly to the final prompt",
            error_code="segment_concatenation_mismatch",
            validation_errors=[{"field": "annotated_segments", "msg": "concatenation mismatch"}],
        )


def _validate_placeholders(prompt: str, fields: list[Any]) -> None:
    prompt_placeholders = set(re.findall(r"\[[A-Z][A-Z0-9_]{2,}\]", prompt))
    field_placeholders = {field.placeholder for field in fields}
    if prompt_placeholders != field_placeholders:
        raise OutputValidationError(
            "Placeholder fields must match placeholders in the final prompt",
            error_code="placeholder_mismatch",
            validation_errors=[
                {
                    "field": "placeholder_fields",
                    "missing_fields": sorted(prompt_placeholders - field_placeholders),
                    "extra_fields": sorted(field_placeholders - prompt_placeholders),
                }
            ],
        )


def _validation_errors(exc: ValidationError) -> list[dict]:
    return [
        {
            "loc": list(error.get("loc", [])),
            "msg": error.get("msg", ""),
            "type": error.get("type", ""),
        }
        for error in exc.errors()
    ]


def _repair_prompt(kind: str, raw: str, error: OutputValidationError) -> str:
    target_prompt_field = "enhanced_prompt" if kind == "enhance" else "refined_prompt"
    return "\n".join([
        "Repair the following JSON so it exactly matches the ThinkVelocity output schema.",
        "Return ONLY a valid JSON object. Do not add markdown fences.",
        f"The required final prompt field is `{target_prompt_field}`.",
        "The `annotated_segments` text values must concatenate exactly to that final prompt field.",
        "Use only valid technique keys and their matching color keys.",
        "Every uppercase bracket placeholder like [TARGET_AUDIENCE] must have one placeholder_fields item, and no extras.",
        f"Schema version: {SCHEMA_VERSION}",
        "",
        "Validation failure:",
        json.dumps(error.to_detail(), ensure_ascii=False),
        "",
        "Raw JSON to repair:",
        raw[:12000],
    ])
