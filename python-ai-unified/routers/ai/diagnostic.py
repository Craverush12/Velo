"""/ai/diagnostic/* — isolated diagnostic micro-tests (dev/debug only).

Source routes (Server 2 core, present on Server 3):
  - POST /diagnostic/domain         -> /ai/diagnostic/domain
  - POST /diagnostic/intent         -> /ai/diagnostic/intent
  - POST /diagnostic/web-search     -> /ai/diagnostic/web-search
  - POST /diagnostic/rag-strategies -> /ai/diagnostic/rag-strategies
  - POST /diagnostic/target-ai      -> /ai/diagnostic/target-ai
  - POST /diagnostic/complexity     -> /ai/diagnostic/complexity
  - POST /diagnostic/all            -> /ai/diagnostic/all
  - GET  /diagnostic/health         -> /ai/diagnostic/health

Each endpoint exercises a single analysis service in isolation. The LLM-backed
ones (domain, intent, target-ai) call Groq; complexity is a deterministic local
calculation; web-search and rag-strategies return structured stubs faithful to
the documented behavior (no web/RAG deps wired in dev mode) — see RECONCILE.md.
"""

from __future__ import annotations

import json
import re

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from ._common import default_model, groq_json

router = APIRouter(prefix="/diagnostic", tags=["diagnostic"])


class DiagnosticRequest(BaseModel):
    prompt: str
    target_ai: str | None = None

    @field_validator("prompt")
    @classmethod
    def prompt_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be empty")
        return value


_DOMAIN_SYSTEM = """Classify the domain of the given prompt. Valid domains:
software_engineering, data_science, devops_infrastructure, mobile_development,
marketing_growth, design_ux, legal, finance, education, health_science,
business_operations, creative_arts, product_management, cybersecurity,
ecommerce, general. Return ONLY JSON:
{"domain": "<domain>", "confidence": 0.0, "reason": "<why>"}"""

_INTENT_SYSTEM = """Classify the intent of the given prompt. Examples:
code_generation, debugging, code_review, architecture_design, data_analysis,
research, creative_writing, copywriting, marketing, business_strategy,
legal_analysis, financial_analysis, design_brief, learning_explanation,
system_design, product_strategy, testing_qa, data_extraction, code_conversion,
task_automation, general_qa. Return ONLY JSON:
{"intent": "<intent>", "confidence": 0.0, "reason": "<why>"}"""

_TARGET_AI_SYSTEM = """Given a prompt, generate a target-AI optimization strategy:
which AI platform fits best and how the prompt should be adapted. Return ONLY JSON:
{"target_ai": "<platform>", "strategy": "<how to optimize>", "rationale": "<why>"}"""


def _payload(request: DiagnosticRequest) -> str:
    return json.dumps(
        {"prompt": request.prompt, "target_ai": request.target_ai}, ensure_ascii=False
    )


@router.post("/domain")
async def diagnostic_domain(request: DiagnosticRequest):
    """Test domain analysis in isolation. Source: POST /diagnostic/domain."""
    return await groq_json(_DOMAIN_SYSTEM, _payload(request), temperature=0.0, model=default_model())


@router.post("/intent")
async def diagnostic_intent(request: DiagnosticRequest):
    """Test intent analysis in isolation. Source: POST /diagnostic/intent."""
    return await groq_json(_INTENT_SYSTEM, _payload(request), temperature=0.0, model=default_model())


@router.post("/target-ai")
async def diagnostic_target_ai(request: DiagnosticRequest):
    """Test LLM-generated target AI strategy. Source: POST /diagnostic/target-ai."""
    return await groq_json(_TARGET_AI_SYSTEM, _payload(request), temperature=0.2, model=default_model())


@router.post("/web-search")
async def diagnostic_web_search(request: DiagnosticRequest):
    """Test the web search service in isolation. Source: POST /diagnostic/web-search.

    Web search (Tavily/SerpAPI/Google CSE) is not provisioned in dev mode; this
    returns the structured shape the canonical service produces with an explicit
    'disabled' marker so callers can branch deterministically. See RECONCILE.md.
    """
    return {
        "query": request.prompt,
        "results": [],
        "provider": None,
        "enabled": False,
        "note": "Web search providers not configured in this environment.",
    }


@router.post("/rag-strategies")
async def diagnostic_rag_strategies(request: DiagnosticRequest):
    """Test RAG strategy retrieval in isolation. Source: POST /diagnostic/rag-strategies.

    Derives candidate prompt-engineering strategies heuristically from the
    prompt text. The canonical build retrieves these from a vector knowledge
    base — see RECONCILE.md.
    """
    text = request.prompt.lower()
    strategies: list[str] = ["task_clarification", "output_format_spec"]
    if any(k in text for k in ("code", "function", "api", "debug", "implement")):
        strategies.append("domain_specific_depth")
    if any(k in text for k in ("step", "reason", "why", "analyze", "compare")):
        strategies.append("chain_of_thought")
    if any(k in text for k in ("persona", "act as", "you are", "expert")):
        strategies.append("persona_injection")
    return {"prompt": request.prompt, "strategies": strategies, "source": "heuristic"}


@router.post("/complexity")
async def diagnostic_complexity(request: DiagnosticRequest):
    """Test complexity calculation in isolation. Source: POST /diagnostic/complexity.

    Deterministic local calculation based on length, sentence count, and
    vocabulary richness — no external deps.
    """
    text = request.prompt
    words = re.findall(r"\w+", text)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    word_count = len(words)
    unique_ratio = (len(set(w.lower() for w in words)) / word_count) if word_count else 0.0
    avg_sentence_len = (word_count / len(sentences)) if sentences else float(word_count)
    # Normalize into a 0-1 complexity score.
    length_factor = min(word_count / 200.0, 1.0)
    sentence_factor = min(avg_sentence_len / 30.0, 1.0)
    score = round(0.4 * length_factor + 0.3 * sentence_factor + 0.3 * unique_ratio, 4)
    return {
        "prompt_length": len(text),
        "word_count": word_count,
        "sentence_count": len(sentences),
        "avg_sentence_length": round(avg_sentence_len, 2),
        "unique_word_ratio": round(unique_ratio, 4),
        "complexity_score": score,
    }


@router.post("/all")
async def diagnostic_all(request: DiagnosticRequest):
    """Run all diagnostic microservices together. Source: POST /diagnostic/all."""
    domain = await diagnostic_domain(request)
    intent = await diagnostic_intent(request)
    target_ai = await diagnostic_target_ai(request)
    web_search = await diagnostic_web_search(request)
    rag = await diagnostic_rag_strategies(request)
    complexity = await diagnostic_complexity(request)
    return {
        "domain": domain,
        "intent": intent,
        "target_ai": target_ai,
        "web_search": web_search,
        "rag_strategies": rag,
        "complexity": complexity,
    }


@router.get("/health")
async def diagnostic_health():
    """Health check for the diagnostic subsystem. Source: GET /diagnostic/health."""
    return {
        "status": "healthy",
        "subsystem": "diagnostic",
        "services": [
            "domain",
            "intent",
            "target-ai",
            "web-search",
            "rag-strategies",
            "complexity",
        ],
    }
