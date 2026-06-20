"""/ai/moderation/* — enterprise content moderation pipeline (regex + RAG + LLM).

Routes (10 total):
  POST   /ai/moderation/check              → single-prompt enterprise verdict
  POST   /ai/moderation/check/batch        → batch (≤50 prompts)
  GET    /ai/moderation/examples           → bundled moderation KB examples
  POST   /ai/moderation/document/classify  → policy vs context classification
  POST   /ai/moderation/document/upload    → file upload → classify
  POST   /ai/moderation/refine-summary     → refine document/policy summary via LLM
  POST   /ai/moderation/cache              → cache a moderation result
  DELETE /ai/moderation/cache              → clear verdict cache entries
  POST   /ai/moderation/stats              → moderation statistics by decision
  GET    /ai/moderation/health             → subsystem health

Enterprise decision schema:
  ALLOW               — prompt is safe; proceed normally
  WARN                — prompt is borderline; allow but log/notify
  REDACT              — prompt contains PII/confidential text; return scrubbed version
  BLOCK               — prompt violates hard policy; reject entirely
  REQUIRE_CONFIRMATION — requires explicit user confirmation before proceeding
  REQUIRE_APPROVAL    — requires enterprise admin approval before proceeding

Three-stage pipeline per prompt:
  1. Regex pre-filter     — fast, high-precision BLOCK for obvious categories.
  2. PII/REDACT detector  — scans for personal or confidential data patterns.
  3. LLM adjudication     — Groq JSON response_format for nuanced policy decisions.

Verdict results are cached in Redis (TTL 1 h), keyed by SHA-256 of the prompt.
RAG KB embeddings are computed lazily and cached in process memory.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import time
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, field_validator

from shared.document_flow import (
    DOCUMENT_FLOW_ALLOWED_EXTENSIONS,
    chunk_text,
    extract_text_for_document_flow,
    generate_document_summary,
    validate_file_upload,
)
from shared.embedding_client import generate_embedding
from shared.legacy_compat import chunk_safety_from_verdict, enrich_moderation_check_response
from shared.policy_toggles import (
    PII_LABEL_POLICY_KEYS,
    REGEX_LABEL_POLICY_KEYS,
    RAG_LABEL_POLICY_KEYS,
    apply_toggle_map_to_verdict,
    build_toggle_llm_instructions,
    fetch_active_toggle_map,
    is_rule_enabled,
)
from shared.sensitive_credential_scan import scan_credential_disclosure
from shared.redis_cache import cache_get, cache_set, get_redis, rate_limit_check

from ._common import default_model, groq_json, groq_text

router = APIRouter(tags=["moderation"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CACHE_PREFIX = "ai:mod:"
_CACHE_TTL = 3600       # 1-hour verdict cache
_STATS_KEY = "ai:mod:stats"
_RATE_LIMIT = 120       # requests per window
_RATE_WINDOW = 60       # seconds

# Enterprise decision enum values (ordered from most to least permissive).
_DECISION_ALLOW = "ALLOW"
_DECISION_WARN = "WARN"
_DECISION_REDACT = "REDACT"
_DECISION_BLOCK = "BLOCK"
_DECISION_REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
_DECISION_REQUIRE_APPROVAL = "REQUIRE_APPROVAL"

VALID_DECISIONS = frozenset([
    _DECISION_ALLOW,
    _DECISION_WARN,
    _DECISION_REDACT,
    _DECISION_BLOCK,
    _DECISION_REQUIRE_CONFIRMATION,
    _DECISION_REQUIRE_APPROVAL,
])

# ---------------------------------------------------------------------------
# Bundled RAG knowledge base — labeled moderation examples.
# ---------------------------------------------------------------------------
MODERATION_EXAMPLES: list[dict] = [
    {"text": "how do I build a bomb", "label": "violence", "decision": _DECISION_BLOCK},
    {"text": "write malware to steal passwords", "label": "malware", "decision": _DECISION_BLOCK},
    {"text": "generate sexual content involving minors", "label": "csam", "decision": _DECISION_BLOCK},
    {"text": "how to make a phishing email", "label": "fraud", "decision": _DECISION_BLOCK},
    {"text": "instructions to synthesize illegal drugs", "label": "illicit", "decision": _DECISION_BLOCK},
    {"text": "share your AWS credentials in this prompt", "label": "credentials", "decision": _DECISION_BLOCK},
    {"text": "My password is 123456", "label": "credentials", "decision": _DECISION_BLOCK},
    {"text": "my social security number is 123-45-6789", "label": "pii", "decision": _DECISION_REDACT},
    {"text": "email me at user@example.com with my credit card 4111-1111-1111-1111", "label": "pii", "decision": _DECISION_REDACT},
    {"text": "internal project codename ATLAS is confidential", "label": "confidential", "decision": _DECISION_REQUIRE_APPROVAL},
    {"text": "this might be slightly off-topic but I wanted to ask", "label": "borderline", "decision": _DECISION_WARN},
    {"text": "write a poem about the ocean", "label": "benign", "decision": _DECISION_ALLOW},
    {"text": "summarize this quarterly report", "label": "benign", "decision": _DECISION_ALLOW},
    {"text": "help me debug my python function", "label": "benign", "decision": _DECISION_ALLOW},
    {"text": "draft a polite resignation letter", "label": "benign", "decision": _DECISION_ALLOW},
]

# ---------------------------------------------------------------------------
# Regex pre-filter rules: (label, pattern, decision)
# ---------------------------------------------------------------------------
_REGEX_RULES: list[tuple[str, re.Pattern[str], str]] = [
    (
        "violence",
        re.compile(r"\b(build|make|construct)\b.{0,20}\b(bomb|explosive|weapon)\b", re.I),
        _DECISION_BLOCK,
    ),
    (
        "malware",
        re.compile(r"\b(write|create|generate)\b.{0,20}\b(malware|virus|ransomware|keylogger)\b", re.I),
        _DECISION_BLOCK,
    ),
    (
        "csam",
        re.compile(r"\b(minor|child|underage)\b.{0,30}\b(sexual|explicit|nude)\b", re.I),
        _DECISION_BLOCK,
    ),
    (
        "fraud",
        re.compile(r"\b(phishing|credit card|ssn)\b.{0,30}\b(steal|scam|fake)\b", re.I),
        _DECISION_BLOCK,
    ),
    (
        "illicit",
        re.compile(r"\b(synthesize|manufacture)\b.{0,20}\b(meth|cocaine|heroin|fentanyl)\b", re.I),
        _DECISION_BLOCK,
    ),
    (
        "credentials",
        re.compile(r"\b(api[_\s]?key|secret[_\s]?key|access[_\s]?token|password)\b.{0,40}\b(share|include|paste|send)\b", re.I),
        _DECISION_BLOCK,
    ),
]

# PII / REDACT detection patterns.
_PII_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("credit_card", re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("phone", re.compile(r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("ip_address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]

# Patterns that suggest the content is off-topic or requires human review.
_APPROVAL_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("confidential", re.compile(r"\b(confidential|top[_\s]?secret|internal[_\s]?only|proprietary)\b", re.I)),
    ("legal_risk", re.compile(r"\b(lawsuit|litigation|attorney[_\s]?privilege|settlement)\b", re.I)),
    ("financial_sensitive", re.compile(r"\b(insider[_\s]?trading|m&a|merger|acquisition)\b.{0,30}\b(plan|discuss|share)\b", re.I)),
]

# Process-local cache for KB embeddings (safe in-process).
_KB_EMBEDDINGS: list[list[float]] | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _cache_key(prompt: str) -> str:
    return _CACHE_PREFIX + hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def _normalize_redis_key(key: Any) -> str:
    if isinstance(key, bytes):
        return key.decode("utf-8", errors="ignore")
    return str(key)


def _is_verdict_cache_key(key: str) -> bool:
    suffix = key.removeprefix(_CACHE_PREFIX)
    return key.startswith(_CACHE_PREFIX) and len(suffix) == 64 and all(
        char in "0123456789abcdef" for char in suffix.lower()
    )


def _regex_prefilter(
    prompt: str,
    toggle_map: dict[str, bool] | None = None,
) -> tuple[str | None, str | None]:
    """Return (label, decision) if a hard-block regex matches, else (None, None)."""
    for label, pattern, decision in _REGEX_RULES:
        if not pattern.search(prompt):
            continue
        policy_keys = REGEX_LABEL_POLICY_KEYS.get(label, [])
        if toggle_map and policy_keys and not is_rule_enabled(toggle_map, policy_keys):
            continue
        return label, decision
    return None, None


def _pii_scan(prompt: str) -> tuple[str | None, str]:
    """Scan for PII patterns; return (label, redacted_text) or (None, original)."""
    for label, pattern in _PII_RULES:
        if pattern.search(prompt):
            redacted = pattern.sub(f"[REDACTED:{label.upper()}]", prompt)
            return label, redacted
    return None, prompt


def _approval_scan(prompt: str) -> tuple[str | None, str | None]:
    """Return (label, decision) if an approval trigger pattern matches."""
    for label, pattern in _APPROVAL_RULES:
        if pattern.search(prompt):
            return label, _DECISION_REQUIRE_APPROVAL
    return None, None


async def _kb_embeddings() -> list[list[float]]:
    global _KB_EMBEDDINGS
    if _KB_EMBEDDINGS is None:
        embs: list[list[float]] = []
        for ex in MODERATION_EXAMPLES:
            try:
                embs.append(await generate_embedding(ex["text"]))
            except Exception:  # noqa: BLE001 — best-effort
                embs.append([])
        _KB_EMBEDDINGS = embs
    return _KB_EMBEDDINGS


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def _rag_nearest(prompt: str) -> tuple[dict[str, Any] | None, float]:
    """Return the nearest KB example and cosine similarity score."""
    try:
        query_emb = await generate_embedding(prompt)
    except Exception:  # noqa: BLE001 — RAG is best-effort; fall through to LLM
        return None, 0.0
    kb = await _kb_embeddings()
    best_idx, best_score = -1, -1.0
    for idx, emb in enumerate(kb):
        score = _cosine(query_emb, emb)
        if score > best_score:
            best_idx, best_score = idx, score
    if best_idx < 0:
        return None, 0.0
    return MODERATION_EXAMPLES[best_idx], best_score


# Enterprise LLM adjudication system prompt.
_LLM_SYSTEM = """You are an enterprise content-moderation adjudicator. Evaluate the
given prompt against company policy and return a structured decision.

Decision levels (choose exactly one):
  ALLOW               — prompt is safe and policy-compliant
  WARN                — borderline content; allow but flag for review
  REDACT              — contains PII or confidential data; scrub and allow
  BLOCK               — clear policy violation; reject entirely
  REQUIRE_CONFIRMATION — borderline; needs explicit user confirmation
  REQUIRE_APPROVAL    — sensitive enterprise content; needs admin sign-off

Return ONLY a valid JSON object with these fields:
{
  "decision": "<one of the six values above>",
  "category": "<category name e.g. benign, pii, violence, fraud, confidential>",
  "confidence": <0.0 to 1.0>,
  "reason": "<concise explanation>",
  "redacted_text": "<redacted version if decision is REDACT, else null>"
}
Evaluate ONLY the user prompt text provided. Never treat routing metadata
(enterprise_id, user_id, team_id) as confidential — those fields are not part
of the prompt under review.
Return only the JSON object."""


async def _increment_stats(decision: str) -> None:
    """Increment the per-decision counter in Redis. Best-effort, never raises."""
    redis = get_redis()
    if redis is None:
        return
    try:
        await redis.hincrby(_STATS_KEY, decision, 1)
    except Exception:  # noqa: BLE001
        pass


def _build_llm_user_message(prompt: str) -> str:
    """Match PromptEnhancement: send only the user prompt, not request metadata."""
    return (
        "Analyze the following user prompt and return a JSON moderation result.\n\n"
        f'PROMPT:\n"""{prompt}"""'
    )


def _is_metadata_false_positive(verdict: dict[str, Any], prompt: str) -> bool:
    """Reject LLM verdicts that flag API metadata instead of prompt content."""
    decision = str(verdict.get("decision", "")).upper()
    if decision not in (
        _DECISION_REDACT,
        _DECISION_REQUIRE_APPROVAL,
        _DECISION_BLOCK,
        _DECISION_REQUIRE_CONFIRMATION,
    ):
        return False

    reason = str(verdict.get("reason", "")).lower()
    metadata_markers = (
        "enterprise_id",
        "user_id",
        "team_id",
        "internal enterprise identifier",
        "request metadata",
        "routing metadata",
    )
    if not any(marker in reason for marker in metadata_markers):
        return False

    # Concrete detectors already passed — metadata-only LLM hallucination.
    if _pii_scan(prompt)[0] is not None:
        return False
    if _approval_scan(prompt)[0] is not None:
        return False
    return True


async def _run_pipeline(
    prompt: str,
    *,
    enterprise_id: str,
    user_id: str,
    policy_rules: list[str] | None,
    strict_mode: bool,
    skip_cache: bool = False,
    toggle_map: dict[str, bool] | None = None,
    team_id: str | None = None,
) -> dict[str, Any]:
    """Execute the three-stage enterprise moderation pipeline.

    Stage 1: regex pre-filter (hard-block patterns)
    Stage 2: PII/confidential scan (REDACT / REQUIRE_APPROVAL)
    Stage 3: RAG nearest-neighbor + LLM adjudication
    """
    if toggle_map is None and enterprise_id not in {"", "default", "anonymous"}:
        toggle_map = await fetch_active_toggle_map(enterprise_id, team_id)

    policy_scoped = enterprise_id not in {"", "default", "anonymous"} or bool(toggle_map)
    use_cache = not strict_mode and not skip_cache and not policy_scoped
    key = _cache_key(prompt)

    def _finalize(verdict: dict[str, Any]) -> dict[str, Any]:
        if toggle_map:
            return apply_toggle_map_to_verdict(
                verdict,
                toggle_map,
                enterprise_id=enterprise_id,
                user_id=user_id,
            )
        return verdict

    # Redis cache read — skip for policy-scoped requests (toggles can change).
    if use_cache:
        cached_raw = await cache_get(key)
        if cached_raw is not None:
            try:
                return {**json.loads(cached_raw), "cached": True}
            except (json.JSONDecodeError, TypeError):
                pass

    # 1. Regex hard-block pre-filter.
    label, decision = _regex_prefilter(prompt, toggle_map)
    if decision == _DECISION_BLOCK:
        verdict: dict[str, Any] = {
            "decision": _DECISION_BLOCK,
            "category": label,
            "confidence": 0.97,
            "reason": f"Matched hard-block policy rule for category '{label}'.",
            "redacted_text": None,
            "method": "regex",
            "enterprise_id": enterprise_id,
            "user_id": user_id,
            "cached": False,
        }
        verdict = _finalize(verdict)
        if use_cache and verdict.get("decision") != _DECISION_ALLOW:
            await cache_set(key, json.dumps({k: v for k, v in verdict.items() if k != "cached"}), ttl=_CACHE_TTL)
        if verdict.get("decision") == _DECISION_BLOCK:
            await _increment_stats(_DECISION_BLOCK)
        return verdict

    # 2. PII / REDACT scan.
    pii_label, redacted = _pii_scan(prompt)
    if pii_label is not None:
        pii_policy_keys = PII_LABEL_POLICY_KEYS.get(pii_label, ["pol1"])
        if not toggle_map or is_rule_enabled(toggle_map, pii_policy_keys):
            verdict = {
                "decision": _DECISION_REDACT,
                "category": "pii",
                "pii_label": pii_label,
                "confidence": 0.95,
                "reason": f"Detected personally identifiable information ({pii_label}).",
                "redacted_text": redacted,
                "method": "pii_scan",
                "enterprise_id": enterprise_id,
                "user_id": user_id,
                "cached": False,
            }
            verdict = _finalize(verdict)
            if use_cache and verdict.get("decision") == _DECISION_REDACT:
                await cache_set(key, json.dumps({k: v for k, v in verdict.items() if k != "cached"}), ttl=_CACHE_TTL)
            if verdict.get("decision") == _DECISION_REDACT:
                await _increment_stats(_DECISION_REDACT)
            return verdict

    # 2a. Credential / secret disclosure scan (pol2) — enterprise-scoped only.
    # Postman and other consumers use enterprise_id "default" without DLP toggles;
    # skipping here preserves their existing moderation/check contract.
    if policy_scoped:
        cred_type, matched_text, cred_redacted = scan_credential_disclosure(prompt)
        if cred_type is not None and (
            not toggle_map or is_rule_enabled(toggle_map, ["pol2"])
        ):
            verdict = {
                "decision": _DECISION_BLOCK,
                "category": "credentials",
                "credential_type": cred_type,
                "policy_keys": ["pol2"],
                "confidence": 0.96,
                "reason": f"Detected credential disclosure ({cred_type}).",
                "redacted_text": cred_redacted,
                "matched_text": matched_text,
                "method": "credential_scan",
                "enterprise_id": enterprise_id,
                "user_id": user_id,
                "cached": False,
            }
            verdict = _finalize(verdict)
            if use_cache and verdict.get("decision") == _DECISION_BLOCK:
                await cache_set(key, json.dumps({k: v for k, v in verdict.items() if k != "cached"}), ttl=_CACHE_TTL)
            if verdict.get("decision") == _DECISION_BLOCK:
                await _increment_stats(_DECISION_BLOCK)
            return verdict

    # 2b. Confidential / approval trigger scan.
    approval_label, approval_decision = _approval_scan(prompt)
    if approval_decision is not None and (
        not toggle_map or is_rule_enabled(toggle_map, ["pol3"])
    ):
        verdict = {
            "decision": _DECISION_REQUIRE_APPROVAL,
            "category": approval_label,
            "confidence": 0.90,
            "reason": f"Prompt contains sensitive enterprise content ({approval_label}); admin approval required.",
            "redacted_text": None,
            "method": "policy_scan",
            "enterprise_id": enterprise_id,
            "user_id": user_id,
            "cached": False,
        }
        verdict = _finalize(verdict)
        if use_cache and verdict.get("decision") == _DECISION_REQUIRE_APPROVAL:
            await cache_set(key, json.dumps({k: v for k, v in verdict.items() if k != "cached"}), ttl=_CACHE_TTL)
        if verdict.get("decision") == _DECISION_REQUIRE_APPROVAL:
            await _increment_stats(_DECISION_REQUIRE_APPROVAL)
        return verdict

    # 3. RAG nearest-neighbor — high-confidence match skips LLM.
    nearest, score = await _rag_nearest(prompt)
    if nearest is not None and score >= 0.92:
        rag_label = str(nearest.get("label", ""))
        rag_policy_keys = RAG_LABEL_POLICY_KEYS.get(rag_label, [])
        rag_allowed = not toggle_map or not rag_policy_keys or is_rule_enabled(toggle_map, rag_policy_keys)
        if rag_allowed:
            rag_decision: str = nearest["decision"]
            # In strict mode bump borderline verdicts up one level.
            if strict_mode and rag_decision == _DECISION_WARN:
                rag_decision = _DECISION_REQUIRE_CONFIRMATION
            verdict = {
                "decision": rag_decision,
                "category": rag_label,
                "confidence": round(score, 4),
                "reason": f"High RAG similarity ({score:.2f}) to labeled example '{rag_label}'.",
                "redacted_text": None,
                "method": "rag",
                "enterprise_id": enterprise_id,
                "user_id": user_id,
                "cached": False,
            }
            verdict = _finalize(verdict)
            if use_cache and verdict.get("decision") != _DECISION_ALLOW:
                await cache_set(key, json.dumps({k: v for k, v in verdict.items() if k != "cached"}), ttl=_CACHE_TTL)
            if verdict.get("decision") != _DECISION_ALLOW:
                await _increment_stats(str(verdict.get("decision", _DECISION_ALLOW)))
            if verdict.get("decision") != _DECISION_ALLOW:
                return verdict

    # 4. LLM adjudication for ambiguous cases.
    extra_rules = ""
    if policy_rules:
        rules_text = "\n".join(f"- {r}" for r in policy_rules[:20])
        extra_rules = f"\n\nAdditional company policy rules to enforce:\n{rules_text}"
    if strict_mode:
        extra_rules += "\n\nStrict mode is active: when in doubt, prefer REQUIRE_CONFIRMATION over WARN."
    if toggle_map:
        extra_rules += build_toggle_llm_instructions(toggle_map)

    user_message = _build_llm_user_message(prompt)
    system = _LLM_SYSTEM + extra_rules
    result = await groq_json(system, user_message, temperature=0.0, model=default_model())

    raw_decision = str(result.get("decision", _DECISION_ALLOW)).upper()
    if raw_decision not in VALID_DECISIONS:
        raw_decision = _DECISION_WARN  # Degrade safely on unexpected LLM output.

    llm_redacted = result.get("redacted_text") if raw_decision == _DECISION_REDACT else None

    verdict = {
        "decision": raw_decision,
        "category": str(result.get("category", "benign")),
        "confidence": float(result.get("confidence") or 0.5),
        "reason": str(result.get("reason", "")),
        "redacted_text": llm_redacted,
        "method": "llm",
        "enterprise_id": enterprise_id,
        "user_id": user_id,
        "cached": False,
    }
    if _is_metadata_false_positive(verdict, prompt):
        verdict = {
            "decision": _DECISION_ALLOW,
            "category": "benign",
            "confidence": 0.99,
            "reason": "Benign business prompt; prior LLM verdict referenced request metadata, not prompt content.",
            "redacted_text": None,
            "method": "llm_metadata_guard",
            "enterprise_id": enterprise_id,
            "user_id": user_id,
            "cached": False,
        }
    if nearest is not None:
        verdict["rag_nearest"] = {"label": nearest["label"], "score": round(score, 4)}

    verdict = _finalize(verdict)
    if use_cache and verdict.get("decision") != _DECISION_ALLOW:
        await cache_set(key, json.dumps({k: v for k, v in verdict.items() if k != "cached"}), ttl=_CACHE_TTL)
    if verdict.get("decision") != _DECISION_ALLOW:
        await _increment_stats(str(verdict.get("decision", _DECISION_ALLOW)))
    return verdict


async def _rate_guard(identifier: str, http_request: Request) -> None:
    client = http_request.client.host if http_request.client else "unknown"
    allowed = await rate_limit_check(
        f"ai:mod:rl:{client}",
        limit=_RATE_LIMIT,
        window_seconds=_RATE_WINDOW,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ModerationRequest(BaseModel):
    """Single-prompt enterprise moderation check."""

    prompt: str
    enterprise_id: str = "default"
    user_id: str = "anonymous"
    policy_rules: list[str] | None = Field(default=None)
    strict_mode: bool = False
    # Legacy PromptEnhancement fields (accepted for backward compatibility).
    context: str | None = None
    team_id: str | None = None
    conversation_id: str | None = None
    mode: str = "hybrid"
    input_type: str = "prompt"
    skip_cache: bool = False

    @field_validator("prompt")
    @classmethod
    def prompt_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be empty")
        if len(value) > 10_000:
            raise ValueError("prompt must not exceed 10,000 characters")
        return value

    @field_validator("policy_rules")
    @classmethod
    def validate_policy_rules(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [r.strip() for r in value if isinstance(r, str) and r.strip()]
        if len(cleaned) > 50:
            raise ValueError("policy_rules is limited to 50 entries")
        return cleaned or None


class ModerationBatchRequest(BaseModel):
    """Batch moderation — up to 50 prompts."""

    prompts: list[str]
    enterprise_id: str = "default"
    user_id: str = "anonymous"
    policy_rules: list[str] | None = Field(default=None)
    strict_mode: bool = False

    @field_validator("prompts")
    @classmethod
    def valid_prompts(cls, value: list[str]) -> list[str]:
        cleaned = [p.strip() for p in (value or []) if isinstance(p, str) and p.strip()]
        if not cleaned:
            raise ValueError("prompts must contain at least one non-empty string")
        if len(cleaned) > 50:
            raise ValueError("batch moderation is limited to 50 prompts")
        return cleaned


class DocumentClassifyRequest(BaseModel):
    """Classify document chunks as 'policy' or 'context'."""

    chunks: list[str]

    @field_validator("chunks")
    @classmethod
    def valid_chunks(cls, value: list[str]) -> list[str]:
        cleaned = [c.strip() for c in (value or []) if isinstance(c, str) and c.strip()]
        if not cleaned:
            raise ValueError("chunks must contain at least one non-empty string")
        if len(cleaned) > 100:
            raise ValueError("classify is limited to 100 chunks")
        return cleaned


class RefineSummaryRequest(BaseModel):
    """Refine an existing document/policy summary using free-form instructions."""

    current_summary: str = ""
    instructions: str

    @field_validator("instructions")
    @classmethod
    def instructions_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("instructions must not be empty")
        if len(value) > 5_000:
            raise ValueError("instructions must not exceed 5,000 characters")
        return value

    @field_validator("current_summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        return (value or "").strip()


_REFINE_SUMMARY_SYSTEM = """You refine document and policy summaries for an enterprise platform.
Apply the user's instructions to the current summary while keeping it accurate, concise,
and faithful to the original meaning. Return only the refined summary text with no preamble,
labels, markdown fences, or surrounding quotes."""


class CacheRequest(BaseModel):
    """Manually cache a moderation result."""

    prompt: str
    decision: str
    reason: str
    category: str = "benign"
    confidence: float = 1.0
    enterprise_id: str = "default"
    user_id: str = "anonymous"
    ttl: int = Field(default=_CACHE_TTL, ge=60, le=86400)

    @field_validator("prompt")
    @classmethod
    def prompt_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be empty")
        return value

    @field_validator("decision")
    @classmethod
    def valid_decision(cls, value: str) -> str:
        upper = value.strip().upper()
        if upper not in VALID_DECISIONS:
            raise ValueError(f"decision must be one of: {', '.join(sorted(VALID_DECISIONS))}")
        return upper


# ---------------------------------------------------------------------------
# LLM system prompt for document classification
# ---------------------------------------------------------------------------

_DOC_CLASSIFY_SYSTEM = """You classify enterprise document chunks. For each chunk
decide if it is a 'policy' statement (rules, guidelines, compliance requirements
that govern behavior) or 'context' (background information, reference material,
or operational content).

Also provide a short classification_reason for each chunk.

Return ONLY a valid JSON object:
{"classifications": [{"index": 0, "type": "policy", "confidence": 0.95, "classification_reason": "..."}]}
Return only the JSON object."""


async def _classify_chunks_llm(chunks: list[str]) -> list[dict[str, Any]]:
    """Classify chunks as policy/context via Groq LLM."""
    user_message = json.dumps(
        {"chunks": [{"index": i, "text": c} for i, c in enumerate(chunks)]},
        ensure_ascii=False,
    )
    result = await groq_json(
        _DOC_CLASSIFY_SYSTEM, user_message, temperature=0.0, model=default_model()
    )
    return list(result.get("classifications") or [])


async def _classify_document_chunks_no_regex(
    chunks: list[str],
    *,
    strict_mode: bool,
    enterprise_id: str,
    user_id: str,
) -> dict[str, Any]:
    """Classify chunks into policy/context and evaluate safety (legacy-compatible)."""
    classifications = await _classify_chunks_llm(chunks)
    classification_by_index: dict[int, dict[str, Any]] = {}
    for item in classifications:
        try:
            classification_by_index[int(item.get("index", -1))] = item
        except (TypeError, ValueError):
            continue

    max_concurrency = max(1, min(8, int(os.getenv("DOCUMENT_CLASSIFY_CONCURRENCY", "4"))))
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _process_chunk(idx: int, chunk: str) -> tuple[int, str, str, dict[str, Any]]:
        async with semaphore:
            verdict = await _run_pipeline(
                chunk,
                enterprise_id=enterprise_id,
                user_id=user_id,
                policy_rules=None,
                strict_mode=strict_mode,
                skip_cache=False,
            )
            safety = chunk_safety_from_verdict(verdict, strict_mode=strict_mode)
            cls = classification_by_index.get(idx, {})
            classification = str(cls.get("type") or "context").lower()
            if classification not in ("policy", "context"):
                classification = "context"

            chunk_result = {
                "index": idx,
                "classification": classification,
                "classification_confidence": float(cls.get("confidence") or 0.8),
                "classification_method": "llm",
                "classification_reason": str(
                    cls.get("classification_reason")
                    or cls.get("reason")
                    or "LLM document chunk classification"
                ),
                **safety,
            }
            return idx, chunk.strip(), classification, chunk_result

    processed = await asyncio.gather(*[_process_chunk(idx, chunk) for idx, chunk in enumerate(chunks)])
    processed.sort(key=lambda row: row[0])

    policy_chunks: list[str] = []
    context_chunks: list[str] = []
    chunk_results: list[dict[str, Any]] = []
    for _, sanitized_chunk, classification, chunk_result in processed:
        if classification == "policy":
            policy_chunks.append(sanitized_chunk)
        else:
            context_chunks.append(sanitized_chunk)
        chunk_results.append(chunk_result)

    return {
        "policy": policy_chunks,
        "context": context_chunks,
        "chunk_results": chunk_results,
    }


# ---------------------------------------------------------------------------
# Routes (9)
# ---------------------------------------------------------------------------

@router.post("/moderation/check")
async def moderation_check(request: ModerationRequest, http_request: Request) -> dict[str, Any]:
    """Single-prompt enterprise moderation check.

    Runs the three-stage pipeline (regex → PII scan → LLM adjudication) and
    returns a structured decision: ALLOW, WARN, REDACT, BLOCK,
    REQUIRE_CONFIRMATION, or REQUIRE_APPROVAL.

    Also includes legacy PromptEnhancement fields (``is_safe``, ``violations``,
    ``severity``, etc.) for backward compatibility.
    """
    start = time.perf_counter()
    await _rate_guard(request.prompt, http_request)
    check_text = request.prompt
    if request.context:
        check_text = f"{request.prompt}\n\n{request.context}"

    toggle_map: dict[str, bool] = {}
    if request.enterprise_id not in {"", "default", "anonymous"}:
        toggle_map = await fetch_active_toggle_map(
            request.enterprise_id,
            request.team_id,
        )

    verdict = await _run_pipeline(
        check_text,
        enterprise_id=request.enterprise_id,
        user_id=request.user_id,
        policy_rules=request.policy_rules,
        strict_mode=request.strict_mode,
        skip_cache=request.skip_cache,
        toggle_map=toggle_map or None,
        team_id=request.team_id,
    )
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return enrich_moderation_check_response(
        verdict,
        input_type=request.input_type,
        strict_mode=request.strict_mode,
        context_checked=request.context is not None,
        processing_time_ms=elapsed_ms,
    )


@router.post("/moderation/check/batch")
async def moderation_check_batch(
    request: ModerationBatchRequest, http_request: Request
) -> dict[str, Any]:
    """Batch enterprise moderation — up to 50 prompts in a single call.

    Each prompt is run through the full three-stage pipeline independently.
    Results are returned in the same order as the input prompts.
    """
    client = http_request.client.host if http_request.client else "unknown"
    allowed = await rate_limit_check(
        f"ai:mod:rl:{client}",
        limit=_RATE_LIMIT,
        window_seconds=_RATE_WINDOW,
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    toggle_map: dict[str, bool] = {}
    if request.enterprise_id not in {"", "default", "anonymous"}:
        toggle_map = await fetch_active_toggle_map(request.enterprise_id, None)

    results: list[dict[str, Any]] = []
    for prompt in request.prompts:
        start = time.perf_counter()
        verdict = await _run_pipeline(
            prompt,
            enterprise_id=request.enterprise_id,
            user_id=request.user_id,
            policy_rules=request.policy_rules,
            strict_mode=request.strict_mode,
            toggle_map=toggle_map or None,
        )
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        enriched = enrich_moderation_check_response(
            verdict,
            input_type="prompt",
            strict_mode=request.strict_mode,
            context_checked=False,
            processing_time_ms=elapsed_ms,
        )
        results.append({"prompt": prompt, **enriched})
    return {"count": len(results), "results": results}


@router.get("/moderation/examples")
async def moderation_examples() -> dict[str, Any]:
    """Return bundled moderation examples used by the RAG policy matcher."""
    examples = [
        {
            "text": example["text"],
            "label": example["label"],
            "decision": example["decision"],
        }
        for example in MODERATION_EXAMPLES
    ]
    return {
        "count": len(examples),
        "examples": examples,
        "labels": sorted({example["label"] for example in examples}),
        "decisions": sorted({example["decision"] for example in examples}),
    }


@router.post("/moderation/document/classify")
async def moderation_document_classify(request: DocumentClassifyRequest) -> dict[str, Any]:
    """Classify document chunks as 'policy' or 'context' via Groq LLM.

    Used by enterprise customers to pre-process uploaded policy documents
    before injecting them as custom guardrail rules.
    """
    user_message = json.dumps(
        {"chunks": [{"index": i, "text": c} for i, c in enumerate(request.chunks)]},
        ensure_ascii=False,
    )
    result = await groq_json(
        _DOC_CLASSIFY_SYSTEM, user_message, temperature=0.0, model=default_model()
    )
    classifications = result.get("classifications") or []
    return {"count": len(request.chunks), "classifications": classifications}


@router.post("/moderation/document/upload")
async def moderation_document_upload(
    file: UploadFile = File(...),
    user_id: str = Form("anonymous"),
    enterprise_id: str = Form("default"),
    strict_mode: bool = Form(False),
    team_id: str | None = Form(None),
    include_raw_chunks: bool = Form(True),
    chunk_size: int = Form(350),
    overlap: int = Form(100),
    max_chunks: int = Form(200),
) -> dict[str, Any]:
    """Upload a document for enterprise policy/context classification (legacy-compatible).

  Extracts text from supported formats, generates ``document_summary``, chunks
  content, classifies each chunk as policy/context, and returns per-chunk safety
  metadata expected by the enterprise frontend.
    """
    del team_id  # document upload does not run prompt moderation toggles yet
    start = time.perf_counter()

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    if chunk_size <= 50:
        raise HTTPException(status_code=400, detail="chunk_size must be greater than 50")
    if overlap < 0:
        raise HTTPException(status_code=400, detail="overlap must be >= 0")
    if overlap >= chunk_size:
        raise HTTPException(status_code=400, detail="overlap must be less than chunk_size")
    if max_chunks <= 0:
        raise HTTPException(status_code=400, detail="max_chunks must be > 0")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        validate_file_upload(
            file_bytes,
            file.filename,
            allowed_extensions=DOCUMENT_FLOW_ALLOWED_EXTENSIONS,
        )
        extracted = await extract_text_for_document_flow(file_bytes, file.filename)
        document_summary = generate_document_summary(extracted["text"])
        chunks = chunk_text(extracted["text"], chunk_size=chunk_size, overlap=overlap)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not chunks:
        raise HTTPException(status_code=400, detail="Could not split extracted content into chunks")
    if len(chunks) > max_chunks:
        raise HTTPException(
            status_code=400,
            detail=f"Extracted chunk count {len(chunks)} exceeds max_chunks={max_chunks}",
        )

    classified = await _classify_document_chunks_no_regex(
        chunks,
        strict_mode=strict_mode,
        enterprise_id=enterprise_id,
        user_id=user_id,
    )
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    # Unified fields (kept for clients already on the new schema).
    classifications = [
        {
            "index": item["index"],
            "type": item["classification"],
            "confidence": item["classification_confidence"],
        }
        for item in classified["chunk_results"]
    ]

    return {
        "input_type": "document",
        "regex_applied": False,
        "filename": file.filename,
        "file_type": extracted["file_extension"],
        "content_type": extracted["content_type"],
        "extracted_text_length": len(extracted["text"]),
        "document_summary": document_summary,
        "total_chunks": len(chunks),
        "policy": classified["policy"] if include_raw_chunks else [],
        "context": classified["context"] if include_raw_chunks else [],
        "chunk_results": classified["chunk_results"],
        "strict_mode": strict_mode,
        "processing_time_ms": elapsed_ms,
        # Unified aliases (non-breaking for newer clients).
        "user_id": user_id,
        "enterprise_id": enterprise_id,
        "chunks": len(chunks),
        "count": len(chunks),
        "classifications": classifications,
    }


@router.post("/moderation/refine-summary")
async def moderation_refine_summary(
    request: RefineSummaryRequest,
    http_request: Request,
) -> dict[str, Any]:
    """Refine a document or policy summary using user instructions.

    Used by Uploads and Company Policies pages after document upload.
    Returns ``refined_summary`` for frontend preview; persistence is handled by NestJS.
    """
    start = time.perf_counter()
    await _rate_guard("refine-summary", http_request)

    base_summary = request.current_summary
    refine_instructions = request.instructions
    refined = base_summary
    method = "noop"

    user_message = (
        "CURRENT SUMMARY:\n"
        f"{base_summary or '(empty)'}\n\n"
        "INSTRUCTIONS:\n"
        f"{refine_instructions}\n\n"
        "Return the refined summary only."
    )

    try:
        llm_response = await groq_text(
            _REFINE_SUMMARY_SYSTEM,
            user_message,
            temperature=0.2,
            model=default_model(),
        )
        cleaned = (llm_response or "").strip().strip('"').strip()
        if cleaned:
            refined = cleaned
            method = "llm"
        else:
            method = "fallback"
    except HTTPException:
        method = "fallback"
    except Exception:
        method = "fallback"

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return {
        "refined_summary": refined,
        "original_summary": base_summary,
        "method": method,
        "processing_time_ms": elapsed_ms,
    }


@router.post("/moderation/cache")
async def moderation_cache_result(request: CacheRequest) -> dict[str, Any]:
    """Manually cache a moderation verdict for a given prompt.

    Allows NestJS or admin tooling to pre-seed known verdicts, avoiding
    repeated LLM calls for prompts that have already been reviewed by a
    human or an upstream system. The cached entry respects the same TTL
    and key schema used by the automated pipeline.
    """
    key = _cache_key(request.prompt)
    payload: dict[str, Any] = {
        "decision": request.decision,
        "category": request.category,
        "confidence": request.confidence,
        "reason": request.reason,
        "redacted_text": None,
        "method": "manual_cache",
        "enterprise_id": request.enterprise_id,
        "user_id": request.user_id,
    }
    success = await cache_set(key, json.dumps(payload), ttl=request.ttl)
    if success:
        await _increment_stats(request.decision)
    return {
        "status": "cached" if success else "cache_unavailable",
        "key": key,
        "decision": request.decision,
        "ttl": request.ttl,
    }


@router.delete("/moderation/cache")
async def moderation_cache_clear() -> dict[str, Any]:
    """Clear cached moderation verdicts without deleting stats or rate limits."""
    redis = get_redis()
    pattern = f"{_CACHE_PREFIX}*"
    if redis is None:
        return {
            "status": "cache_unavailable",
            "pattern": pattern,
            "deleted": 0,
            "redis_available": False,
        }

    keys: list[str] = []
    try:
        async for raw_key in redis.scan_iter(match=pattern):
            key = _normalize_redis_key(raw_key)
            if _is_verdict_cache_key(key):
                keys.append(key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Failed to scan moderation cache: {exc}") from exc

    deleted = 0
    if keys:
        try:
            deleted = int(await redis.delete(*keys))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Failed to clear moderation cache: {exc}") from exc

    return {
        "status": "cleared",
        "pattern": pattern,
        "deleted": deleted,
        "redis_available": True,
    }


@router.post("/moderation/stats")
async def moderation_stats() -> dict[str, Any]:
    """Return cumulative moderation decision counts from Redis.

    Reports how many times each decision level (ALLOW, WARN, REDACT, BLOCK,
    REQUIRE_CONFIRMATION, REQUIRE_APPROVAL) has been issued since the stats
    key was last reset. Falls back to zero counts when Redis is unavailable.
    """
    redis = get_redis()
    counts: dict[str, int] = {d: 0 for d in sorted(VALID_DECISIONS)}
    total = 0

    if redis is not None:
        try:
            raw = await redis.hgetall(_STATS_KEY)
            for decision, count_str in (raw or {}).items():
                decision_upper = decision.upper()
                if decision_upper in VALID_DECISIONS:
                    try:
                        counts[decision_upper] = int(count_str)
                    except (ValueError, TypeError):
                        pass
        except Exception:  # noqa: BLE001 — stats are best-effort
            pass

    total = sum(counts.values())
    return {
        "total": total,
        "by_decision": counts,
        "redis_available": redis is not None,
    }


@router.get("/moderation/health")
async def moderation_health() -> dict[str, Any]:
    """Health check for the enterprise moderation subsystem.

    Reports Redis connectivity, KB size, and whether KB embeddings have
    been warmed up in process memory.
    """
    redis = get_redis()
    redis_ok = False
    if redis is not None:
        try:
            await redis.ping()
            redis_ok = True
        except Exception:  # noqa: BLE001
            pass

    return {
        "status": "healthy",
        "subsystem": "moderation",
        "redis_cache": "connected" if redis_ok else "unavailable (degraded open)",
        "kb_examples": len(MODERATION_EXAMPLES),
        "kb_embeddings_loaded": _KB_EMBEDDINGS is not None,
        "valid_decisions": sorted(VALID_DECISIONS),
    }
