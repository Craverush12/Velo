# tests/eval/structural_scorer.py
"""Deterministic structural scorer for enhanced prompts.

Mirrors the depth requirements in core/prompts/enhance_system.md ("Engineering
Rules"): explicit role, >=5 distinct techniques, explicit output format, a
failure-mode constraint, and substantive difference from the raw prompt. No LLM
call — safe for CI.
"""
from __future__ import annotations

import re
from typing import Any

_ROLE_RE = re.compile(r"\byou are\b|\bact as\b|\bas an? (senior|expert|professional)\b", re.I)
_FORMAT_RE = re.compile(
    r"\boutput\b|\bformat\b|\breturn\b|\bsections?\b|\btable\b|\bjson\b|\bbullet|\bmarkdown\b", re.I
)
_NEGATIVE_RE = re.compile(r"\bdo not\b|\bavoid\b|\bnever\b|\bdon't\b|\bwithout\b", re.I)
_PLACEHOLDER_RE = re.compile(r"\[[A-Z_]{3,}\]")


def score_enhancement(item: dict[str, Any]) -> dict[str, Any]:
    enhanced = (item.get("enhanced_prompt") or "").strip()
    raw = (item.get("raw_prompt") or "").strip()
    segments = item.get("annotated_segments") or []

    if not enhanced:
        return {"score": 0.0, "checks": {
            "has_role": False, "five_techniques": False, "has_output_format": False,
            "has_failure_constraint": False, "length_delta": False,
        }}

    distinct_techniques = {
        s.get("technique") for s in segments if isinstance(s, dict) and s.get("technique")
    }

    checks = {
        "has_role": bool(_ROLE_RE.search(enhanced)),
        "five_techniques": len(distinct_techniques) >= 5,
        "has_output_format": bool(_FORMAT_RE.search(enhanced)),
        "has_failure_constraint": bool(_NEGATIVE_RE.search(enhanced)),
        "length_delta": len(enhanced) >= int(len(raw) * 1.2) + 20,
    }
    score = round(sum(1 for v in checks.values() if v) / len(checks), 3)
    return {"score": score, "checks": checks, "distinct_techniques": sorted(t for t in distinct_techniques if t)}
