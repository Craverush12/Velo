"""LLM-as-judge scorer for ThinkVelocity enhanced prompts.

Scores each enhanced prompt on three axes (1-5 each):
  specificity        — concrete constraints vs vague generalizations
  constraint_adherence — mode/sub-type rules enforced (product lock, schema-first, etc.)
  actionability      — can an LLM execute this enhanced prompt without clarifications?

Usage:
    from tests.eval.judge import score_enhancement
    result = await score_enhancement(case, enhanced_prompt)
"""

from __future__ import annotations

import json
import os
import sys
import logging

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_JUDGE_SYSTEM = """You are a prompt-engineering quality evaluator for ThinkVelocity, a prompt enhancement SaaS.

You will receive:
1. The original (raw) prompt from the user
2. The enhanced prompt produced by ThinkVelocity
3. The mode and sub-type (e.g., mode=fast_build, sub=web_app)
4. Required signals: strings that MUST appear in a good enhancement for this case
5. Forbidden signals: strings that MUST NOT appear

Evaluate the enhanced prompt on these three axes, each scored 1–5:

SPECIFICITY (1–5)
  5 = every instruction is concrete and measurable (exact parameter names, HTTP status codes, DDL syntax, shot type names)
  3 = mix of concrete and vague
  1 = entirely vague ("make it better", "add error handling", "be professional")

CONSTRAINT_ADHERENCE (1–5)
  5 = all mode/sub-type rules enforced (product photography → material-specific lighting, no artistic additions;
      api_service → contract-first with request/response schema and HTTP codes;
      academic_lit_review → RISEN framework, citation slots, conflict synthesis required)
  3 = some rules followed, some missed
  1 = mode rules completely ignored

ACTIONABILITY (1–5)
  5 = an LLM could execute this immediately, no clarifying questions needed
  3 = one or two ambiguities remain
  1 = so vague the LLM would need to ask multiple questions before proceeding

Return ONLY valid JSON — no markdown, no explanation:
{
  "specificity": 4,
  "constraint_adherence": 5,
  "actionability": 4,
  "mean": 4.33,
  "pass": true,
  "signals_present": ["backlit", "no hot spots"],
  "signals_missing": [],
  "forbidden_present": [],
  "notes": "One sentence on the most important quality issue, if any."
}

"pass" is true when all three scores >= 3 AND no forbidden signals are present AND mean >= 3.5.
"""


async def score_enhancement(case: dict, enhanced_prompt: str) -> dict:
    """Score one enhanced prompt. Returns the judge's JSON dict."""
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    except ImportError:
        raise RuntimeError("groq SDK not installed — run: pip install groq")

    required = case.get("must_contain", [])
    forbidden = case.get("must_not_contain", [])
    ep_lower = enhanced_prompt.lower()

    signals_present = [s for s in required if s.lower() in ep_lower]
    signals_missing = [s for s in required if s.lower() not in ep_lower]
    forbidden_present = [s for s in forbidden if s.lower() in ep_lower]

    payload = {
        "case_id": case["id"],
        "mode": case.get("mode", ""),
        "sub_type": case.get("build_sub") or case.get("research_sub") or case.get("media_sub") or "",
        "original_prompt": case["prompt"],
        "enhanced_prompt": enhanced_prompt,
        "required_signals": required,
        "forbidden_signals": forbidden,
        "signals_present": signals_present,
        "signals_missing": signals_missing,
        "forbidden_present": forbidden_present,
    }

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0,
        max_tokens=300,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content
    result = json.loads(raw)
    result["signals_present"] = signals_present
    result["signals_missing"] = signals_missing
    result["forbidden_present"] = forbidden_present
    result["case_id"] = case["id"]
    result["mode"] = case.get("mode", "")
    result["sub_type"] = payload["sub_type"]

    length_ok = len(enhanced_prompt) >= case.get("min_length", 0)
    if not length_ok:
        result["pass"] = False
        result.setdefault("notes", "")
        result["notes"] += f" [FAIL: enhanced prompt too short — {len(enhanced_prompt)} < {case['min_length']} chars]"

    return result
