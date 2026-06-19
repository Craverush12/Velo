# python-ai-unified/routers/ai/reflexion.py
"""Structurally-gated self-critique pass for enhancements.

Only fires when (a) mode is a deep mode and (b) the structural score is below
floor. Bounds cost: strong enhancements skip the second LLM call entirely.
Degrades open: any failure returns the original result unchanged.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_DEEP_MODES = {"best", "build", "research"}
_FLOOR = 0.80

_ROLE_RE = re.compile(r"\byou are\b|\bact as\b|\bas an? (senior|expert|professional)\b", re.I)
_FORMAT_RE = re.compile(r"\boutput\b|\bformat\b|\breturn\b|\bsections?\b|\btable\b|\bjson\b|\bbullet|\bmarkdown\b", re.I)
_NEGATIVE_RE = re.compile(r"\bdo not\b|\bavoid\b|\bnever\b|\bdon't\b|\bwithout\b", re.I)


def _structural_score(result: dict[str, Any]) -> float:
    enhanced = (result.get("enhanced_prompt") or "").strip()
    if not enhanced:
        return 0.0
    segs = {s.get("technique") for s in (result.get("annotated_segments") or [])
            if isinstance(s, dict) and s.get("technique")}
    # 4 checks here vs 5 in tests/eval/structural_scorer.py: length_delta is
    # intentionally omitted — this gate scores the enhanced prompt in isolation
    # and a length ratio is not a reliable quality signal mid-pipeline. Raw
    # numbers will differ from the eval scorer by design.
    checks = [
        bool(_ROLE_RE.search(enhanced)),
        len(segs) >= 5,
        bool(_FORMAT_RE.search(enhanced)),
        bool(_NEGATIVE_RE.search(enhanced)),
    ]
    return sum(1 for c in checks if c) / len(checks)


async def _groq_critique(result: dict[str, Any], raw_prompt: str) -> dict[str, Any]:
    """Ask Groq to repair the enhancement against the depth rules. Returns a
    dict with at least enhanced_prompt + annotated_segments, or raises."""
    from shared.groq_client import groq_pool

    system = (
        "You are a prompt-quality critic. Improve the ENHANCED prompt so it has: "
        "an explicit role, >=5 distinct techniques, an explicit output format, and "
        "a constraint preventing the most common failure mode. Return ONLY JSON: "
        "{\"enhanced_prompt\": str, \"annotated_segments\": [{\"technique\": str}]}."
    )
    user = json.dumps({"raw_prompt": raw_prompt,
                       "enhanced_prompt": result.get("enhanced_prompt", "")})
    raw = await groq_pool.async_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},  # project hard rule: all Groq calls
        temperature=0.2, max_tokens=1500,
    )
    content = raw if isinstance(raw, str) else raw.choices[0].message.content
    return json.loads(content)


async def maybe_improve(result: dict[str, Any], *, raw_prompt: str, mode: str) -> dict[str, Any]:
    if mode not in _DEEP_MODES:
        return result
    if _structural_score(result) >= _FLOOR:
        return result
    try:
        fixed = await _groq_critique(result, raw_prompt)
        if fixed.get("enhanced_prompt"):
            merged = dict(result)
            merged["enhanced_prompt"] = fixed["enhanced_prompt"]
            if fixed.get("annotated_segments"):
                merged["annotated_segments"] = fixed["annotated_segments"]
            merged["_reflexion_applied"] = True
            return merged
    except Exception as exc:  # noqa: BLE001 - reflexion must never break enhance
        logger.warning("reflexion failed, returning original: %s", exc)
    return result
