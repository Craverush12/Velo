"""Backward-compatible response shaping for legacy PromptEnhancement clients."""

from __future__ import annotations

from typing import Any

_DECISION_ALLOW = "ALLOW"
_DECISION_WARN = "WARN"
_DECISION_REDACT = "REDACT"
_DECISION_BLOCK = "BLOCK"
_DECISION_REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
_DECISION_REQUIRE_APPROVAL = "REQUIRE_APPROVAL"

_SEVERITY_BY_DECISION = {
    _DECISION_ALLOW: "low",
    _DECISION_WARN: "medium",
    _DECISION_REDACT: "high",
    _DECISION_BLOCK: "critical",
    _DECISION_REQUIRE_CONFIRMATION: "medium",
    _DECISION_REQUIRE_APPROVAL: "high",
}

# Mirrors PromptEnhancement SENSITIVE_TYPE_POLICY_KEYS for DLP breach labeling.
_CATEGORY_POLICY_KEYS: dict[str, list[str]] = {
    "pii": ["pol1"],
    "ssn": ["pol1"],
    "email": ["pol1"],
    "phone": ["pol1"],
    "personal_id": ["pol1"],
    "credit_card": ["pol4"],
    "credentials": ["pol2"],
    "password": ["pol2"],
    "api_key": ["pol2"],
    "malware": ["pol6"],
    "fraud": ["pol6"],
    "violence": ["pol7"],
    "csam": ["pol7"],
    "illicit": ["pol7"],
}


_PII_LABEL_POLICY_KEYS: dict[str, list[str]] = {
    "ssn": ["pol1"],
    "email": ["pol1"],
    "phone": ["pol1"],
    "ip_address": ["pol1"],
    "credit_card": ["pol4"],
}


def policy_keys_for_verdict(verdict: dict[str, Any]) -> list[str]:
    explicit = verdict.get("policy_keys")
    if isinstance(explicit, list):
        keys = [
            str(key).strip().lower()
            for key in explicit
            if isinstance(key, str) and str(key).strip()
        ]
        if keys:
            return keys

    category = str(verdict.get("category", "")).strip().lower()
    method = str(verdict.get("method", "")).strip().lower()
    keys: list[str] = []

    if category in _CATEGORY_POLICY_KEYS:
        keys.extend(_CATEGORY_POLICY_KEYS[category])

    pii_label = str(verdict.get("pii_label", "")).strip().lower()
    if pii_label:
        keys.extend(_PII_LABEL_POLICY_KEYS.get(pii_label, ["pol1"]))

    # PII scan uses category "pii" with method pii_scan; map sub-labels when present.
    if method == "pii_scan" and category == "pii":
        reason = str(verdict.get("reason", "")).lower()
        if "ssn" in reason:
            keys.extend(_CATEGORY_POLICY_KEYS.get("ssn", []))
        elif "credit" in reason:
            keys.extend(_CATEGORY_POLICY_KEYS.get("credit_card", []))
        elif "email" in reason:
            keys.extend(_CATEGORY_POLICY_KEYS.get("email", []))
        elif "phone" in reason:
            keys.extend(_CATEGORY_POLICY_KEYS.get("phone", []))

    deduped: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key not in seen:
            seen.add(key)
            deduped.append(key)
    return deduped


def _build_violations(verdict: dict[str, Any]) -> list[dict[str, Any]]:
    decision = str(verdict.get("decision", _DECISION_ALLOW)).upper()
    if decision == _DECISION_ALLOW:
        return []

    category = str(verdict.get("category", "policy"))
    severity = _SEVERITY_BY_DECISION.get(decision, "medium")
    reason = str(verdict.get("reason", ""))
    method = str(verdict.get("method", "llm"))
    policy_keys = policy_keys_for_verdict(verdict)

    violation: dict[str, Any] = {
        "category": category,
        "severity": severity,
        "method": method,
    }
    if policy_keys:
        violation["policy_keys"] = policy_keys
    if decision == _DECISION_REDACT:
        violation["explanation"] = reason or "Sensitive data detected"
    else:
        violation["explanation"] = reason
        violation["llm_reasoning"] = reason

    return [violation]


def _legacy_is_safe(verdict: dict[str, Any], *, strict_mode: bool) -> bool:
    decision = str(verdict.get("decision", _DECISION_ALLOW)).upper()
    severity = _SEVERITY_BY_DECISION.get(decision, "low")
    is_safe = decision in (_DECISION_ALLOW, _DECISION_WARN, _DECISION_REDACT)
    if strict_mode and severity in ("medium", "high", "critical"):
        is_safe = False
    if decision in (_DECISION_BLOCK, _DECISION_REQUIRE_CONFIRMATION, _DECISION_REQUIRE_APPROVAL):
        is_safe = False
    return is_safe


def enrich_moderation_check_response(
    verdict: dict[str, Any],
    *,
    input_type: str = "prompt",
    strict_mode: bool = False,
    context_checked: bool = False,
    processing_time_ms: float | None = None,
) -> dict[str, Any]:
    """Merge unified decision schema with legacy PromptEnhancement fields."""
    violations = _build_violations(verdict)
    method = str(verdict.get("method", "llm"))
    detection_method = method
    if method == "regex":
        detection_method = "hybrid (regex-only)"
    elif method == "llm":
        detection_method = "rag (llm)"
    elif method == "rag":
        detection_method = "hybrid (rag-detected)"

    detected_sensitive_data = None
    if str(verdict.get("decision", "")).upper() == _DECISION_REDACT:
        detected_sensitive_data = [
            {
                "type": str(verdict.get("category", "pii")),
                "detection_method": method,
            }
        ]
        if verdict.get("redacted_text"):
            detected_sensitive_data[0]["masked_value"] = verdict["redacted_text"]

    legacy = {
        "is_safe": _legacy_is_safe(verdict, strict_mode=strict_mode),
        "has_violations": len(violations) > 0,
        "violation_count": len(violations),
        "violations": violations,
        "severity": _SEVERITY_BY_DECISION.get(str(verdict.get("decision", _DECISION_ALLOW)).upper(), "low"),
        "confidence": float(verdict.get("confidence") or 0.5),
        "detection_method": detection_method,
        "input_type": input_type,
        "regex_applied": method == "regex",
        "context_checked": context_checked,
        "strict_mode": strict_mode,
        "processing_time_ms": processing_time_ms,
        "detected_sensitive_data": detected_sensitive_data,
    }
    policy_keys = policy_keys_for_verdict(verdict)
    if policy_keys:
        legacy["policy_keys"] = policy_keys
        legacy["matchedRuleKeys"] = policy_keys
    if "cached" in verdict:
        legacy["cached"] = verdict["cached"]
    return {**verdict, **legacy}


def chunk_safety_from_verdict(
    verdict: dict[str, Any],
    *,
    strict_mode: bool,
) -> dict[str, Any]:
    """Map a unified moderation verdict to legacy per-chunk safety fields."""
    violations = _build_violations(verdict)
    decision = str(verdict.get("decision", _DECISION_ALLOW)).upper()
    severity = _SEVERITY_BY_DECISION.get(decision, "low")
    is_safe = _legacy_is_safe(verdict, strict_mode=strict_mode)

    detected_sensitive_data = None
    if decision == _DECISION_REDACT:
        detected_sensitive_data = [
            {
                "type": str(verdict.get("category", "pii")),
                "detection_method": str(verdict.get("method", "pii_scan")),
            }
        ]

    return {
        "is_safe": is_safe,
        "severity": severity,
        "violations": violations,
        "detection_method": f"{verdict.get('method', 'llm')} (llm-only)",
        "regex_applied": False,
        "detected_sensitive_data": detected_sensitive_data,
    }


def mcq_to_legacy_questions(mcq_questions: list[dict[str, Any]]) -> tuple[list[str], list[list[str]]]:
    """Convert unified mcq_questions to legacy parallel questions/options arrays."""
    questions: list[str] = []
    options: list[list[str]] = []
    default_options = ["More specific / detailed", "Broader overview", "Different emphasis", "Option 4"]

    for item in mcq_questions:
        question = str(item.get("question_text") or item.get("question") or "").strip()
        if not question:
            continue
        questions.append(question)
        answer_options = item.get("answer_options") or item.get("options") or []
        normalized_options = [str(opt).strip() for opt in answer_options if str(opt).strip()]
        if len(normalized_options) >= 4:
            options.append(normalized_options[:4])
        elif len(normalized_options) == 3:
            options.append(normalized_options + ["Option 4"])
        elif normalized_options:
            while len(normalized_options) < 3:
                normalized_options.append(f"Option {len(normalized_options) + 1}")
            options.append(normalized_options + ["Option 4"])
        else:
            options.append(list(default_options))

    # Legacy extension clients expect up to 4 slots; only pad when the model returned nothing.
    if not questions:
        while len(questions) < 4:
            idx = len(questions) + 1
            questions.append(f"Clarifying question {idx}?")
            options.append(["Option 1", "Option 2", "Option 3", "Option 4"])

    return questions[:4], options[:4]


def refine_result_to_legacy(result: dict[str, Any]) -> dict[str, Any]:
    """Add legacy enhanced_prompt alias to canonical refine result."""
    if not isinstance(result, dict):
        return result
    refined = result.get("refined_prompt", "")
    return {
        **result,
        "enhanced_prompt": refined,
        "original_prompt": result.get("original_prompt") or result.get("prompt"),
        "qa_pairs_used": result.get("qa_pairs_used") or result.get("clarification_qa") or [],
    }


def _enum_value(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def build_enhance_complete_payload(
    result: dict[str, Any],
    *,
    original_prompt: str = "",
    mode: str = "standard",
    target_ai: str | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build SSE/JSON complete payload: new unified fields + legacy extras.

    New fields are set first; legacy PromptEnhancement top-level fields are
    added only when the key is not already present (never overwrites).
    """
    usage = result.get("_usage") if isinstance(result.get("_usage"), dict) else {}
    timings = result.get("_stage_timings") if isinstance(result.get("_stage_timings"), dict) else {}
    domain = _enum_value(result.get("domain"))
    intent = _enum_value(result.get("intent"))
    summary = str(result.get("summary") or "")
    quality = float(result.get("prompt_quality_score") or 0.0)
    media_intent = result.get("_media_intent")
    total_ms = round(sum(float(v) for v in timings.values()) if timings else 0.0, 2)

    metadata: dict[str, Any] = {
        "domain": domain,
        "intent": intent,
        "intent_description": summary,
        "complexity": str(result.get("complexity") or result.get("prompt_mode") or "medium"),
    }
    if extra_meta:
        sanitized_meta = {
            key: value
            for key, value in extra_meta.items()
            if not str(key).startswith("_")
        }
        metadata.update(sanitized_meta)

    performance: dict[str, Any] = {
        "processing_time_ms": int(timings.get("llm_stream_ms") or total_ms or 0),
        "total_ms": total_ms,
        "validation_ms": 0.0,
        "analysis_ms": float(timings.get("intent_classify_ms") or 0),
        "context_ms": float(timings.get("context_prepare_ms") or 0),
        "enhancement_ms": float(timings.get("llm_stream_ms") or 0),
    }

    payload: dict[str, Any] = {
        "type": "complete",
        "status": "completed",
        "enhanced_prompt": str(result.get("enhanced_prompt") or ""),
        "annotated_segments": result.get("annotated_segments") or [],
        "performance": performance,
        "metadata": metadata,
    }

    recommendations = result.get("target_ai_recommendations") or []
    suggested_ai = None
    if recommendations and isinstance(recommendations[0], dict):
        suggested_ai = recommendations[0].get("ai") or recommendations[0].get("name")

    personalization = result.get("_personalization_used")
    personalization_fields: list[str] = []
    if isinstance(personalization, dict):
        personalization_fields = sorted(
            key for key, value in personalization.items() if value not in (None, "")
        )

    legacy_fields: dict[str, Any] = {
        "message": "Enhancement completed successfully",
        "request": {
            "original_prompt": original_prompt,
            "mode": mode,
            "target_ai": target_ai,
            "provider": "auto",
        },
        "domain_analysis": {
            "domain": domain,
            "confidence": quality,
            "all_scores": {},
            "top_3_domains": [],
            "sub_domains": [],
            "analysis_method": "unified",
        },
        "intent_analysis": {
            "intent": intent,
            "confidence": quality,
            "all_scores": {},
            "sub_intents": [],
            "intent_category": "unknown",
        },
        "complexity_analysis": {},
        "target_ai_routing": {
            "suggested_target_ai": suggested_ai,
            "final_target_ai": target_ai or suggested_ai,
            "user_override": target_ai is not None,
            "confidence": quality,
        }
        if (suggested_ai or target_ai)
        else None,
        "context_injection": {
            "enterprise_context_used": False,
            "enterprise_context_length": 0,
            "enterprise_context_status": "not_fetched",
            "document_context_used": False,
            "document_context_length": 0,
            "document_context_status": "not_fetched",
            "personalization_context_used": bool(personalization_fields),
            "personalization_fields": personalization_fields,
        },
        "tokens": {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "estimated_cost": float(usage.get("estimated_cost") or 0.0),
        },
        "citations": [],
        "context_used": [],
        "retrieved_chunks": [],
        "used_documents": [],
        "company_policy_names": [],
        "project_policy_names": [],
        "matched_content_sources": {},
        "citation_events": [],
        "citation_maps": [],
        "is_media": bool(media_intent),
        "media_type": media_intent,
        "media_subtype": None,
        "media_json": None,
        "placeholder_fields": result.get("placeholder_fields") or [],
        "framework_used": result.get("framework_used"),
        "schema_version": result.get("schema_version"),
    }

    for key, value in legacy_fields.items():
        if key not in payload:
            payload[key] = value

    return payload
