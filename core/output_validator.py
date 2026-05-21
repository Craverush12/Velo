from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from core.contracts import (
    SCHEMA_VERSION,
    TECHNIQUE_COLORS,
    AIRecommendation,
    AnnotatedSegment,
    ClarificationQuestion,
    EnhanceResult,
    RefineResult,
    normalize_prompt_mode,
)
from core.connectors_catalog import load_connector_catalog


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
    prompt_mode: str | None = None,
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
    normalized["prompt_mode"] = normalize_prompt_mode(prompt_mode)
    try:
        validated = EnhanceResult.model_validate(normalized)
    except ValidationError as exc:
        raise OutputValidationError(
            "Enhancement output failed schema validation",
            validation_errors=_validation_errors(exc),
            raw_excerpt=json.dumps(result, default=str)[:500],
        ) from exc
    try:
        _validate_segments(validated.enhanced_prompt, validated.annotated_segments)
    except OutputValidationError:
        validated.annotated_segments = [_single_segment(validated.enhanced_prompt, prefix="s")]
    _validate_placeholders(validated.enhanced_prompt, validated.placeholder_fields)
    return validated.model_dump(mode="json")


def validate_refine_result(
    result: dict,
    *,
    prompt_hash: str | None = None,
    prompt_mode: str | None = None,
) -> dict:
    normalized = _normalize_common(result, prompt_field="refined_prompt")
    normalized["schema_version"] = SCHEMA_VERSION
    normalized["prompt_version"] = prompt_hash
    normalized["prompt_mode"] = normalize_prompt_mode(prompt_mode)

    raw_score = normalized.get("prompt_quality_score", 0.0)
    try:
        model_score = float(raw_score or 0.0)
    except (TypeError, ValueError):
        model_score = 0.0
    normalized["prompt_quality_score"] = round(max(0.0, min(model_score, 1.0)), 2)

    raw_delta = normalized.get("quality_delta", 0.0)
    try:
        normalized["quality_delta"] = float(raw_delta or 0.0)
    except (TypeError, ValueError):
        normalized["quality_delta"] = 0.0

    try:
        validated = RefineResult.model_validate(normalized)
    except ValidationError as exc:
        raise OutputValidationError(
            "Refinement output failed schema validation",
            validation_errors=_validation_errors(exc),
            raw_excerpt=json.dumps(result, default=str)[:500],
        ) from exc
    try:
        _validate_segments(validated.refined_prompt, validated.annotated_segments)
    except OutputValidationError:
        validated.annotated_segments = [_single_segment(validated.refined_prompt, prefix="r")]
    _validate_placeholders(validated.refined_prompt, validated.placeholder_fields)
    return validated.model_dump(mode="json")


async def parse_validate_with_repair(
    kind: str,
    raw: str,
    *,
    raw_prompt: str = "",
    prompt_hash: str | None = None,
    prompt_mode: str | None = None,
    repair_callback: RepairCallback | None = None,
) -> dict:
    try:
        return _validate_kind(
            kind,
            parse_json_object(raw),
            raw_prompt=raw_prompt,
            prompt_hash=prompt_hash,
            prompt_mode=prompt_mode,
        )
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
                prompt_mode=prompt_mode,
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


def _validate_kind(
    kind: str,
    result: dict,
    *,
    raw_prompt: str,
    prompt_hash: str | None,
    prompt_mode: str | None,
) -> dict:
    if kind == "enhance":
        return validate_enhance_result(
            result,
            raw_prompt=raw_prompt,
            prompt_hash=prompt_hash,
            prompt_mode=prompt_mode,
        )
    if kind == "refine":
        return validate_refine_result(result, prompt_hash=prompt_hash, prompt_mode=prompt_mode)
    raise ValueError(f"Unknown output kind: {kind}")


def _normalize_common(result: dict, *, prompt_field: str) -> dict:
    normalized = dict(result)
    _normalize_clarification_questions(normalized)
    _normalize_ai_recommendations(normalized)
    _repair_segment_texts(normalized, prompt_field)
    _clamp_segment_techniques(normalized)
    _normalize_segment_colors(normalized)
    _normalize_placeholder_fields(normalized, prompt_field)
    _normalize_techniques(normalized)
    _normalize_connector_recommendations(normalized)
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


_AI_ORDER = ["claude", "chatgpt", "gpt-5", "gemini", "groq", "cursor", "bolt", "replit", "gamma", "midjourney"]


def _normalize_ai_recommendations(result: dict) -> None:
    recs = result.get("target_ai_recommendations")
    if not recs or not isinstance(recs, list):
        return
    normalized = []
    for item in recs:
        if not isinstance(item, dict):
            continue
        ai = str(item.get("ai", "")).strip().lower()
        if ai not in _AI_ORDER:
            continue
        reason = str(item.get("reason", "")).strip()
        if not reason:
            continue
        rank = item.get("rank", 0)
        try:
            rank = max(1, min(3, int(rank)))
        except (TypeError, ValueError):
            rank = len(normalized) + 1
        normalized.append(AIRecommendation(ai=ai, rank=rank, reason=reason).model_dump(mode="json"))
    if not normalized:
        return
    # Sort by rank, then by AI order
    normalized.sort(key=lambda r: (r["rank"], _AI_ORDER.index(r["ai"]) if r["ai"] in _AI_ORDER else 99))
    # Re-assign ranks 1-3
    for i, rec in enumerate(normalized[:3]):
        rec["rank"] = i + 1
    result["target_ai_recommendations"] = normalized[:3]


def _normalize_connector_recommendations(result: dict) -> None:
    recs = result.get("recommended_connectors")
    if recs is None:
        return
    if isinstance(recs, dict):
        recs = [recs]
    if not isinstance(recs, list):
        result["recommended_connectors"] = []
        return

    catalog = load_connector_catalog()
    catalog_by_name = {entry["name"].lower(): entry for entry in catalog}
    normalized = []
    for item in recs:
        if not isinstance(item, dict):
            continue
        name = str(
            item.get("name")
            or item.get("connector_name")
            or item.get("connector")
            or ""
        ).strip()
        if not name:
            continue
        catalog_entry = _match_connector_catalog_entry(name, catalog_by_name)
        category = str(item.get("category") or "").strip()
        use_case = str(item.get("use_case") or item.get("reason") or "").strip()
        url = str(item.get("url") or "").strip()
        connector_type = str(item.get("connector_type") or item.get("type") or "").strip()
        if catalog_entry:
            name = catalog_entry["name"]
            category = category or catalog_entry["category"]
            use_case = use_case or catalog_entry["use_case"]
            url = url or catalog_entry["url"]
            connector_type = connector_type or catalog_entry["connector_type"]
        if not (name and category and use_case and url):
            continue
        normalized.append({
            "name": name,
            "category": category,
            "use_case": use_case,
            "url": url,
            "connector_type": connector_type or "ai_platform",
        })
    result["recommended_connectors"] = normalized[:4]


def _match_connector_catalog_entry(name: str, catalog_by_name: dict[str, dict[str, str]]) -> dict[str, str] | None:
    lowered = name.lower()
    if lowered in catalog_by_name:
        return catalog_by_name[lowered]
    for catalog_name, entry in catalog_by_name.items():
        if lowered in catalog_name or catalog_name in lowered:
            return entry
    aliases = {
        "claude": "claude (anthropic)",
        "anthropic": "claude (anthropic)",
        "chatgpt": "chatgpt (openai)",
        "openai": "chatgpt (openai)",
        "dalle": "dall-e (openai)",
        "dall-e": "dall-e (openai)",
        "bolt": "bolt.new",
    }
    alias = aliases.get(lowered)
    if alias:
        return catalog_by_name.get(alias)
    return None


def _norm_ws(s: str) -> str:
    """Collapse all whitespace runs to a single space and strip edges."""
    return re.sub(r"\s+", " ", s).strip()


def _find_normalized(prompt: str, target_normalized: str, start_pos: int) -> int:
    """Search for target_normalized (whitespace-collapsed) in prompt from start_pos.

    Uses a sliding window over the original prompt; window size is estimated from
    len(target_normalized) ± 20% (minimum 1 character).  Returns the start position
    in the *original* prompt on the first match, or -1 if not found.
    """
    if not target_normalized:
        return -1
    target_len = len(target_normalized)
    # Estimate a window of original characters that could normalize to target_len chars.
    # Whitespace collapsing can only shrink text, so upper bound adds slack.
    min_win = max(1, int(target_len * 0.8))
    max_win = int(target_len * 1.4) + 4  # small constant for edge safety
    prompt_len = len(prompt)
    for pos in range(start_pos, prompt_len):
        for win in range(min_win, min(max_win + 1, prompt_len - pos + 1)):
            candidate = prompt[pos : pos + win]
            if _norm_ws(candidate) == target_normalized:
                return pos
    return -1


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
        if not stripped:
            continue
        found = prompt.find(stripped, cursor)
        if found < 0:
            # Primary search failed — try whitespace-normalized match.
            norm_stripped = _norm_ws(stripped)
            actual_found = _find_normalized(prompt, norm_stripped, cursor)
            if actual_found >= 0:
                # Determine the length of the matched span in the original prompt.
                # _find_normalized already returned the position; we need the window
                # length — re-run the inner scan to get it.
                prompt_len = len(prompt)
                target_len = len(norm_stripped)
                min_win = max(1, int(target_len * 0.8))
                max_win = int(target_len * 1.4) + 4
                matched_len = None
                for win in range(min_win, min(max_win + 1, prompt_len - actual_found + 1)):
                    if _norm_ws(prompt[actual_found : actual_found + win]) == norm_stripped:
                        matched_len = win
                        break
                if matched_len is not None:
                    found = actual_found
                    stripped = prompt[actual_found : actual_found + matched_len]
        if found < 0:
            # Segment text still not found — skip; prefix absorbed by next found segment.
            continue
        new_seg = dict(seg)
        # Include any gap between previous cursor and this match as part of this segment
        new_seg["text"] = prompt[cursor : found + len(stripped)]
        repaired.append(new_seg)
        cursor = found + len(stripped)

    if not repaired:
        return

    # Absorb any trailing text into the last segment
    if cursor < len(prompt):
        repaired[-1]["text"] += prompt[cursor:]

    joined = "".join(seg["text"] for seg in repaired)
    if joined == prompt:
        result["annotated_segments"] = repaired
        return

    # Safety net: join doesn't equal prompt (edge case).
    # Try to absorb unaccounted prefix into the first segment and suffix into the last.
    if repaired:
        # Find where repaired content starts in prompt
        first_text = repaired[0]["text"]
        prefix_pos = prompt.find(first_text)
        if prefix_pos > 0:
            repaired[0]["text"] = prompt[:prefix_pos] + repaired[0]["text"]
        last_text = repaired[-1]["text"]
        end_pos = prompt.rfind(last_text)
        if end_pos >= 0:
            tail_start = end_pos + len(last_text)
            if tail_start < len(prompt):
                repaired[-1]["text"] += prompt[tail_start:]
        if "".join(seg["text"] for seg in repaired) == prompt:
            result["annotated_segments"] = repaired
        # If still not equal, fall through — _validate_segments → _single_segment handles it.


_VALID_TECHNIQUES = set(TECHNIQUE_COLORS)
_FALLBACK_TECHNIQUE = "task_clarification"


def _clamp_segment_techniques(result: dict) -> None:
    for seg in result.get("annotated_segments") or []:
        if seg.get("technique") not in _VALID_TECHNIQUES:
            seg["technique"] = _FALLBACK_TECHNIQUE
            seg["technique_label"] = "Task Clarification"


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
    prompt = str(result.get(prompt_field) or "")
    prompt_placeholders = sorted(set(re.findall(r"\[[A-Z][A-Z0-9_]{2,}\]", prompt)))
    fields = result.get("placeholder_fields") or []
    normalized_by_placeholder = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        key = str(field.get("key") or "").strip().upper()
        if not key:
            continue
        placeholder = str(field.get("placeholder") or f"[{key}]").strip()
        if not placeholder.startswith("["):
            placeholder = f"[{placeholder}]"
        label = str(field.get("label") or "").strip() or key.replace("_", " ").title()
        description = str(field.get("description") or "").strip() or f"Provide a value for {label}."
        field = dict(field)
        field["key"] = key
        field["placeholder"] = placeholder
        field["label"] = label
        field["description"] = description
        normalized_by_placeholder[placeholder] = field

    normalized = []
    for placeholder in prompt_placeholders:
        field = normalized_by_placeholder.get(placeholder)
        if field is None:
            key = placeholder.strip("[]")
            label = key.replace("_", " ").title()
            field = {
                "key": key,
                "label": label,
                "placeholder": placeholder,
                "description": f"Provide a value for {label}.",
                "required": True,
                "example": "",
                "type": "text",
            }
        normalized.append(field)
    result["placeholder_fields"] = normalized


def _single_segment(prompt: str, prefix: str = "s") -> AnnotatedSegment:
    return AnnotatedSegment(
        id=f"{prefix}1",
        text=prompt,
        technique="task_clarification",
        technique_label="Task Clarification",
        color_key="sky",
        reason="Full enhanced prompt rendered as a single segment.",
        is_original=False,
        original_text=None,
    )


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
    technique_keys = sorted(TECHNIQUE_COLORS)
    color_keys = sorted(set(TECHNIQUE_COLORS.values()))
    return "\n".join([
        "Repair the following JSON so it exactly matches the ThinkVelocity output schema.",
        "Repair syntax, missing required fields, enum values, placeholder metadata, and segment boundaries only.",
        "Preserve the final prompt text exactly unless whitespace must be reassigned between annotated_segments to satisfy concatenation.",
        "Return ONLY a valid JSON object. Do not add markdown fences.",
        f"The required final prompt field is `{target_prompt_field}`.",
        "The `annotated_segments` text values must concatenate exactly to that final prompt field.",
        f"Allowed technique keys: {', '.join(technique_keys)}.",
        f"Allowed color keys: {', '.join(color_keys)}.",
        "Use each technique key with its matching color key.",
        "Every uppercase bracket placeholder like [TARGET_AUDIENCE] must have one placeholder_fields item, and no extras.",
        f"Schema version: {SCHEMA_VERSION}",
        "",
        "Validation failure:",
        json.dumps(error.to_detail(), ensure_ascii=False),
        "",
        "Raw JSON to repair:",
        raw[:12000],
    ])
