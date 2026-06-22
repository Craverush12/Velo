"""ICP (Ideal Customer Profile) signal classifier.

Takes a raw content signal (reddit post, search result, blog snippet) and
returns a structured classification: who the person is, what pain they have,
and how relevant they are to Velocity's prompt-enhancement product.

Degrades open: Groq failure returns a low-confidence unknown result so
callers never need to handle exceptions from this module.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_VALID_CATEGORIES = frozenset(
    {"developer", "content_creator", "marketer", "student", "researcher", "business_operator"}
)
_BRIEF_THRESHOLD = 0.6

_SYSTEM_PROMPT = (
    "You are an ICP (Ideal Customer Profile) classifier for a content intelligence pipeline. "
    "Velocity is a prompt enhancement tool that helps people get better results from AI models "
    "(ChatGPT, Claude, Gemini). Target users are people who use AI tools daily and want to write "
    "better prompts.\n\n"
    "Given a content signal (title + text from Reddit, search results, or blog), output ONLY JSON "
    "with these exact keys:\n"
    "- icp_category: one of developer | content_creator | marketer | student | researcher | business_operator\n"
    "- problem_tags: list of up to 5 specific pain points as short strings\n"
    "- stage: one of awareness | consideration | activation | retention\n"
    "- emotion: one of frustrated | curious | excited | skeptical\n"
    "- product_relevance: float 0.0-1.0 — how relevant this signal is to someone building/marketing "
    "a prompt enhancement tool (1.0 = directly about AI prompting struggles)\n"
    "- content_brief: if product_relevance >= 0.6, a one-paragraph content brief; otherwise null\n"
    "- confidence: float 0.0-1.0 — your classification confidence\n\n"
    "Be concise. Max 300 output tokens."
)


def _low_confidence_result(signal: dict[str, Any]) -> dict[str, Any]:
    return {
        "icp_category": "unknown",
        "problem_tags": [],
        "stage": "awareness",
        "emotion": "curious",
        "product_relevance": 0.0,
        "content_brief": None,
        "confidence": 0.0,
        **( {"signal_id": signal["signal_id"]} if "signal_id" in signal else {} ),
    }


def _enforce_brief_threshold(result: dict[str, Any]) -> dict[str, Any]:
    """Null out content_brief when product_relevance is below threshold."""
    if result.get("product_relevance", 0.0) < _BRIEF_THRESHOLD:
        result["content_brief"] = None
    return result


def _normalise(raw: dict[str, Any], signal: dict[str, Any]) -> dict[str, Any]:
    category = raw.get("icp_category", "")
    if category not in _VALID_CATEGORIES:
        category = "unknown"

    tags = raw.get("problem_tags") or []
    if not isinstance(tags, list):
        tags = []

    relevance = float(raw.get("product_relevance") or 0.0)
    relevance = max(0.0, min(1.0, relevance))

    brief = raw.get("content_brief")
    if relevance < _BRIEF_THRESHOLD:
        brief = None
    elif brief is not None and not str(brief).strip():
        brief = None

    out: dict[str, Any] = {
        "icp_category": category,
        "problem_tags": tags[:5],
        "stage": raw.get("stage") or "awareness",
        "emotion": raw.get("emotion") or "curious",
        "product_relevance": relevance,
        "content_brief": brief,
        "confidence": max(0.0, min(1.0, float(raw.get("confidence") or 0.0))),
    }
    if "signal_id" in signal:
        out["signal_id"] = signal["signal_id"]
    return out


async def classify_signal(signal: dict[str, Any]) -> dict[str, Any]:
    """Classify a single content signal into an ICP profile.

    Returns a fully-populated dict. Never raises — Groq failures produce a
    zero-confidence unknown result so the pipeline can continue.
    """
    from shared.groq_client import groq_pool

    user_content = json.dumps({
        "title": signal.get("title", ""),
        "text": (signal.get("text") or "")[:2000],
        "source": signal.get("source", ""),
    })

    try:
        response = await groq_pool.async_chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=300,
        )
        content = response if isinstance(response, str) else response.choices[0].message.content
        raw = json.loads(content)
        return _normalise(raw, signal)
    except Exception as exc:  # noqa: BLE001 — classifier must never propagate
        logger.warning("icp_classifier failed for signal '%s': %s", signal.get("title", "")[:60], exc)
        return _low_confidence_result(signal)
