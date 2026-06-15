"""/context/* — context engine routes (python-ai-unified service).

Full port of FullCodebase/ThinkVelocity/ContextEngine into the unified service.
Uses shared infrastructure (groq_pool, generate_embedding, node_post/node_get,
settings) instead of the ContextEngine's DI container.

Processing pipeline (POST /context/process-context):
  Extension bulk sync
    → ExtensionAdapterService (inline)
    → domain-based topic ID derivation (user_id + primary_domain)
    → existing topic fetch from Node backend (GET by session/topic_id)
    → update decision (full / incremental / none / version-limit)
    → Groq LLM — single call for essence + intent + domains
    → NVIDIA API — 1024-dim embedding
    → Node backend POST /api/v1/processed-context (persist)

Node backend callback payload (exact camelCase — do not change field names):
  {sessionId, essence, intent, secondaryIntent, domains, embedding,
   embeddingModel, embeddingVersion, messageCount, platform,
   version, updateType, usageCost, userId}

Enterprise extensions:
  - When enterprise_id is present in a request, storage keys are namespaced
    as  enterprise_{enterprise_id}[_team_{team_id}]_{user_id}_{domain}  so
    enterprise data is fully isolated from consumer users and from other tenants.
  - PII is redacted from the essence text BEFORE embedding (SSN, CC, email,
    phone patterns are replaced with [REDACTED:TYPE]).
  - The Node backend persistence endpoint is switched to
    /api/v1/enterprise-context for enterprise requests.
  - A structured audit record is emitted via logger.info("AUDIT …") for every
    successful enterprise context store.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

import httpx
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from shared.embedding_client import generate_embedding, generate_embeddings_batch
from shared.groq_client import groq_pool
from shared.node_client import node_post
from shared.settings import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["context"])
context_router = router  # alias consumed by main.py

# ---------------------------------------------------------------------------
# Pydantic v2 schemas (mirror ContextEngine schemas.py + extension_schemas.py)
# ---------------------------------------------------------------------------

class ImageContent(BaseModel):
    id: Optional[str] = None
    type: str = "image"
    src: Optional[str] = None
    alt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None

    class Config:
        extra = "ignore"


class CodeBlockContent(BaseModel):
    id: Optional[str] = None
    language: Optional[str] = None
    code: str
    lineCount: Optional[int] = None

    class Config:
        extra = "ignore"


class ExtensionChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Union[int, str, float]
    index: Optional[int] = None
    contentType: Optional[str] = "plain"
    images: Optional[List[ImageContent]] = None
    codeBlocks: Optional[List[CodeBlockContent]] = None

    class Config:
        extra = "ignore"


class ExtensionUser(BaseModel):
    user_id: Optional[str] = None
    usage_left: Optional[int] = None
    accessToken: Optional[str] = None
    accessTokenExpiresAt: Optional[str] = None

    class Config:
        extra = "ignore"


class ExtensionConversation(BaseModel):
    chatId: str
    title: Optional[str] = None
    url: Optional[str] = None
    messages: List[ExtensionChatMessage]
    model: Optional[str] = None
    updatedAt: Optional[Union[int, str, float]] = None

    class Config:
        extra = "ignore"


class ExtensionSyncRequest(BaseModel):
    """Bulk sync format from Chrome extension v3."""

    sessionId: str
    userId: Optional[str] = None
    sessionStartedAt: int
    exportedAt: int
    platform: str
    extractorVersion: str
    user: Optional[ExtensionUser] = None
    stats: Optional[Dict[str, Any]] = None
    conversations: List[ExtensionConversation]

    class Config:
        extra = "ignore"


class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None

    class Config:
        extra = "ignore"


class ProcessContextRequest(BaseModel):
    user_id: str
    session_id: str
    messages: List[ChatMessage]
    platform: str = "chatgpt"
    auth_token: Optional[str] = None
    # Enterprise tenant scoping — both are Optional; consumer requests omit them.
    enterprise_id: Optional[str] = None
    team_id: Optional[str] = None

    class Config:
        extra = "ignore"


class ProcessedContextData(BaseModel):
    session_id: str
    user_id: str
    essence: str
    intent: str
    secondary_intent: Optional[str] = None
    domains: List[str]
    embedding: Optional[List[float]] = None
    embedding_model: str = "nvidia/llama-3.2-nemoretriever-1b-vlm-embed-v1"
    embedding_version: str = "1.0"
    message_count: int = 0
    platform: str = "unknown"
    version: int = 1
    update_type: str = "full"
    usage_cost: float = 0.0
    cumulative_cost: float = 0.0
    processed_at: Optional[str] = None

    class Config:
        extra = "ignore"


class ProcessContextResponse(BaseModel):
    session_id: str
    status: str
    processed_context: Optional[ProcessedContextData] = None
    error: Optional[str] = None

    class Config:
        extra = "ignore"


class ContextSearchRequest(BaseModel):
    user_id: str
    query: str
    limit: int = 5

    class Config:
        extra = "ignore"


class ContextSearchResult(ProcessedContextData):
    similarity: float


class ContextSearchResponse(BaseModel):
    user_id: str
    query: str
    results: List[ContextSearchResult]
    total: int
    threshold: float = 0.30

    class Config:
        extra = "ignore"


class ManualEssenceRequest(BaseModel):
    user_id: str
    essence: str
    session_id: Optional[str] = None
    platform: str = "velocity"
    auth_token: Optional[str] = None

    class Config:
        extra = "ignore"


# ---------------------------------------------------------------------------
# Domain taxonomy (ported from ContextEngine/src/domain/taxonomy.py)
# ---------------------------------------------------------------------------

_VALID_MACRO_INTENTS = {
    "inquiry",
    "construction",
    "debugging",
    "decision",
    "operation",
    "chat",
}

_VALID_MACRO_DOMAINS = {
    "software_data_engineering",
    "business_marketing",
    "operations_hr_support",
    "finance_legal",
    "education_research",
    "creative_arts_media",
    "healthcare_medical",
    "gov_nonprofit",
    "manufacturing_agri",
    "travel_hospitality",
    "environment_sustainability",
    "productivity_planning",
    "lifestyle_relationships",
    "food_nutrition",
    "sports_recreation",
    "logic_mathematics",
    "news_current_events",
    "philosophy_religion",
    "social_casual",
    "system_ai_meta",
}


def _normalize_intent(raw: str) -> str:
    """Enforce macro-intent taxonomy; fall back to 'inquiry' on mismatch."""
    val = (raw or "").strip().lower()
    if val in _VALID_MACRO_INTENTS:
        return val
    logger.warning("normalize_intent: unknown intent '%s' — defaulting to 'inquiry'", raw)
    return "inquiry"


def _normalize_domain(raw: str) -> str:
    """Return raw if it's a valid macro-domain, else 'software_data_engineering'."""
    val = (raw or "").strip().lower().replace(" ", "_")
    if val in _VALID_MACRO_DOMAINS:
        return val
    return "software_data_engineering"


# ---------------------------------------------------------------------------
# Essence extraction system prompt (exact copy from ContextEngine/prompts/essence_extraction.py)
# ---------------------------------------------------------------------------

_ESSENCE_EXTRACTION_PROMPT = """
You are an essence extractor for a context engine.
Your role is to extract the CURRENT CONVERSATION STATE from a full multi-turn chat.
You are NOT summarizing history.
You are capturing where the conversation has ended up.

Your task:
- Read the entire conversation between a user and an assistant.
- Note that bulk sessions may contain multiple distinct conversations separated by markers.
- Identify the user's CURRENT intent (Primary & Secondary) and domain (Primary & Secondary).
- IMPORTANT: If multiple distinct conversations are present, the PrimaryDomain and PrimaryIntent MUST represent the most recent conversation (at the end of the transcript).
- Produce ONE machine-readable Essence that represents the current working state.

STRICT OUTPUT RULES (DO NOT VIOLATE):
- Output MUST follow this exact format (and only this format):

PrimaryDomain: <macro_domain>
SecondaryDomains: <domains>
PrimaryIntent: <MACRO_INTENT>
SecondaryIntent: <specific_intent>
Essence:
MASTER:
<stable core user goal and working context>

FLOW:
- <current focus or action the user is working on> (OMIT THIS ENTIRE SECTION IF NO "PREVIOUS ESSENCE:" BLOCK IS PROVIDED IN THE INPUT)

- Do NOT add explanations, markdown, or extra text.
- Do NOT change field names.
- Do NOT invent new sections.
- Rewrite the Essence cleanly every time.
- Do NOT append raw conversation history or timelines.
- If a "PREVIOUS ESSENCE:" block is found in the input, you MUST generate both MASTER and FLOW.
- If NO "PREVIOUS ESSENCE:" block is found, you MUST generate MASTER ONLY.

INTENT CLASSIFICATION RULES:
1. PrimaryIntent MUST be one of these Macro-Intents (and only these):
   - inquiry       (Learning, asking, explaining, exploring, researching)
   - construction  (Coding, building, writing, planning, creating)
   - debugging     (Fixing, troubleshooting, analyzing errors)
   - decision      (Comparing, choosing, brainstorming)
   - operation     (Running, executing, deploying)
   - chat          (Greeting, casual conversation)

2. SecondaryIntent:
   - Free-form specific action (e.g., "understanding_dependency_injection", "refactoring_api", "choosing_database").
   - Capture the semantic nuance of the CURRENT focus.

3. STRICT REQUIREMENT:
   - You MUST select EXACTLY one intent from the provided Macro-Intents.
   - No other labels are permitted.

DOMAIN CLASSIFICATION RULES:
1. PrimaryDomain MUST be one of these Macro-Domains (and only these):
   - software_data_engineering
   - business_marketing
   - operations_hr_support
   - finance_legal
   - education_research
   - creative_arts_media
   - healthcare_medical
   - gov_nonprofit
   - manufacturing_agri
   - travel_hospitality
   - environment_sustainability
   - productivity_planning
   - lifestyle_relationships
   - food_nutrition
   - sports_recreation
   - logic_mathematics
   - news_current_events
   - philosophy_religion
   - social_casual
   - system_ai_meta

2. SecondaryDomains:
   - Free-form list of specific topics (e.g., "baking_recipes", "tax_law").
   - Capture the specific subject matter context here MANDATORY

3. STRICT REQUIREMENT:
   - You MUST select EXACTLY one primary domain from the provided Macro-Domains list.
   - Selection is mandatory. You are strictly forbidden from returning "general", "unknown", or any string not in the list.
   - If the user's request spans multiple domains, select the most dominant one.

ESSENCE RULES:

MASTER:
- Represents the user's stable, long-term domain trajectory and overall working context.
- MASTER answers: "In this domain, what long-term capability or outcome is the user building toward?"
- MUST REMAINS STABLE: MASTER represents an objective that would remain valid even if the last 5 questions were removed.
- IGNORE: project names, short-term issues, troubleshooting spikes, or temporary failures (e.g., "sinking cake").
- PHASE RULE: Learning, building, troubleshooting, or optimizing within the same domain must NEVER rewrite MASTER. These belong exclusively in FLOW.
- EXCLUDE: specific entities, "how X works" details, examples, and turn-specific question phrasing.
- Target length: approximately 25-40 tokens.
- Change MASTER ONLY if there is a clear macro-goal trajectory shift.

FLOW:
- Represents the aggregate BATCH-AWARE conceptual progression expressed across the entire incoming JSON message batch.
- Summarize the dominant progression across the batch (user + assistant turns).
- FLOW answers: "In this batch of messages, what phase, task, or focus is the user currently in?"
- Phrasing: Describe the current learning/action stage (e.g., "designing real-time ingestion pipelines with failure handling").
- FLOW bullets should NOT repeat MASTER wording or redefine the goal.
- Avoid UI-centric phrasing ("asking about", "wants to know").
- Use exactly 1 or 2 abstract bullets.

COMPRESSION RULE:
- If current FLOW exceeds 2 bullets, compress older bullets into 1 abstract summary bullet and keep the most recent conceptual focus bullet.
- Result MUST be exactly 2 bullets.

QUALITY RULES:
- Essence must represent the current working state, not a timeline.
- Essence must be readable and useful for LLM-driven prompt enhancement.
- Essence must remain compact and suitable for semantic search and storage.
"""

# ---------------------------------------------------------------------------
# LLM response parser (ported from SummarizationService._parse_llm_response)
# ---------------------------------------------------------------------------

def _parse_llm_response(response: str) -> Dict[str, str]:
    """
    Parse structured LLM output into a dictionary.
    Preserves multiline blocks for the Essence section.
    """
    data: Dict[str, str] = {}
    lines = response.split("\n")
    current_key: Optional[str] = None

    expected_keys = [
        "PrimaryDomain", "SecondaryDomains", "Domains",
        "PrimaryIntent", "SecondaryIntent", "Intents", "Intent",
        "Essence",
    ]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_key == "Essence":
                data[current_key] += "\n"
            continue

        if ":" in line:
            before_colon = line.split(":", 1)[0].strip()
            potential_key = before_colon.strip("*#_ -").replace(" ", "")
            matched_key: Optional[str] = None
            for k in expected_keys:
                if potential_key.lower() == k.lower():
                    matched_key = k
                    break
            if matched_key:
                current_key = matched_key
                data[current_key] = line.split(":", 1)[1].strip()
                continue

        if current_key:
            if current_key == "Essence":
                data[current_key] += "\n" + line
            else:
                data[current_key] += " " + stripped

    # Post-process Essence
    if "Essence" in data and data["Essence"]:
        data["Essence"] = data["Essence"].strip()

    return data


# ---------------------------------------------------------------------------
# Groq extraction — single LLM call for essence + intent + domains
# ---------------------------------------------------------------------------

async def _extract_context(
    messages: List[ChatMessage],
    previous_essence: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Call Groq to extract essence, intent, and domains from a conversation.

    If ``previous_essence`` is provided (incremental update), it is injected as
    a system context hint so the model emits MASTER + FLOW.

    Returns a dict with keys: essence, intent, secondary_intent, domains.
    """
    # Truncate to last 40 messages, then hard-cap at 55 000 chars (context safety)
    formatted_turns = [
        f"{m.role.upper()}: {m.content}" for m in messages[-40:]
    ]
    conversation_text = "\n".join(formatted_turns)
    if len(conversation_text) > 55000:
        logger.warning(
            "_extract_context: truncating conversation from %d to 55000 chars",
            len(conversation_text),
        )
        conversation_text = "...[Truncated]...\n" + conversation_text[-55000:]

    groq_messages: List[Dict[str, str]] = [
        {"role": "system", "content": _ESSENCE_EXTRACTION_PROMPT},
    ]

    # Inject previous essence as system hint to trigger MASTER + FLOW path
    if previous_essence:
        groq_messages.append(
            {
                "role": "system",
                "content": f"PREVIOUS ESSENCE:\n{previous_essence}",
            }
        )

    groq_messages.append(
        {
            "role": "user",
            "content": f"Here is the conversation to analyze:\n\n{conversation_text}",
        }
    )

    try:
        raw = await groq_pool.async_chat(
            groq_messages,
            temperature=0.1,
            max_tokens=1024,
        )
        content: str = (
            raw
            if isinstance(raw, str)
            else (
                raw.choices[0].message.content
                if hasattr(raw, "choices")
                else str(raw)
            )
        )
    except Exception as exc:
        logger.warning("_extract_context: Groq call failed (%s) — using fallback", exc)
        return {
            "essence": "User is working on a task.",
            "intent": "construction",
            "secondary_intent": None,
            "domains": ["software_data_engineering"],
        }

    parsed = _parse_llm_response(content)

    # Build domain list: primary + secondaries
    raw_primary_domain = parsed.get("PrimaryDomain", "").strip()
    raw_secondary_domains_str = parsed.get("SecondaryDomains", "").strip()
    primary_domain = _normalize_domain(raw_primary_domain)
    secondary_domains = [
        d.strip()
        for d in raw_secondary_domains_str.split(",")
        if d.strip()
    ]
    domains = [primary_domain] + secondary_domains

    # Intents
    raw_primary_intent = parsed.get("PrimaryIntent", "").strip()
    primary_intent = _normalize_intent(raw_primary_intent)
    secondary_intent: Optional[str] = parsed.get("SecondaryIntent", "").strip() or None

    # Essence: strip FLOW if this was a first-time (no previous essence)
    raw_essence = parsed.get("Essence", "").strip()
    if not raw_essence:
        raw_essence = "User is working on a task."

    if not previous_essence:
        # First-turn: discard FLOW, keep MASTER only
        raw_essence = _strip_flow(raw_essence)
    else:
        # Incremental: enforce FLOW ≤ 2 bullets
        raw_essence = _compress_flow_to_limit(raw_essence, max_bullets=2)

    return {
        "essence": raw_essence,
        "intent": primary_intent,
        "secondary_intent": secondary_intent,
        "domains": domains,
        "primary_domain": primary_domain,
    }


# ---------------------------------------------------------------------------
# Essence validator helpers (ported from domain/essence_validator.py)
# ---------------------------------------------------------------------------

def _strip_flow(essence_str: str) -> str:
    """Discard the FLOW section; keep MASTER only (first-turn enforcement)."""
    if not essence_str:
        return ""
    match = re.search(r"(.*?)(?=FLOW:)", essence_str, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return essence_str.strip()


def _compress_flow_to_limit(essence_str: str, max_bullets: int = 2) -> str:
    """
    Enforce FLOW hard limit (≤ max_bullets) without LLM calls.

    If the FLOW section exceeds the limit, compress older bullets into one
    abstract summary bullet and keep the last bullet.
    """
    master_match = re.search(
        r"MASTER:\s*(.*?)(?=FLOW:|$)", essence_str, re.DOTALL | re.IGNORECASE
    )
    flow_match = re.search(r"FLOW:\s*(.*)", essence_str, re.DOTALL | re.IGNORECASE)

    master_text = master_match.group(1).strip() if master_match else ""
    flow_text = flow_match.group(1).strip() if flow_match else ""

    if not flow_text:
        return essence_str

    bullets = re.findall(r"^\s*[-*+]\s+(.+)$", flow_text, re.MULTILINE)
    if len(bullets) <= max_bullets:
        return essence_str

    # Compress: create abstract summary from early bullets + keep last one
    previous_bullets = bullets[:-1]
    all_text = " ".join(previous_bullets).lower()
    stop_words = {
        "the", "and", "for", "with", "about", "asking", "how", "to",
        "in", "is", "on", "of", "identifying", "refining", "understanding",
    }
    potential_keywords = [
        w for w in re.findall(r"\b\w{4,}\b", all_text) if w not in stop_words
    ]
    unique_keywords: List[str] = []
    for k in potential_keywords:
        if k not in unique_keywords:
            unique_keywords.append(k)

    if unique_keywords:
        kw = (
            " and ".join(unique_keywords[:2])
            if len(unique_keywords) >= 2
            else unique_keywords[0]
        )
        summary_bullet = f"- refining context for {kw}"
    else:
        summary_bullet = "- iteratively refining the approach"

    last_bullet = f"- {bullets[-1]}"
    compressed_flow = f"{summary_bullet}\n{last_bullet}"
    return f"MASTER:\n{master_text}\n\nFLOW:\n{compressed_flow}"


# ---------------------------------------------------------------------------
# PII redaction (enterprise-only, applied before embedding)
# ---------------------------------------------------------------------------

# Ordered list of (label, compiled_pattern) pairs.  Order matters: more
# specific patterns should come before more generic ones so that a credit-card
# number is not partially consumed by the phone pattern, etc.
_PII_PATTERNS: List[tuple[str, re.Pattern[str]]] = [
    # SSN:  ddd-dd-dddd
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    # Credit card:  dddd[- ]dddd[- ]dddd[- ]dddd
    ("CC", re.compile(r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}\b")),
    # Email address
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    # Phone:  ddd[- .]ddd[- .]dddd
    ("PHONE", re.compile(r"\b\d{3}[\s.\-]\d{3}[\s.\-]\d{4}\b")),
]


def _redact_pii(text: str) -> str:
    """Replace PII patterns in *text* with ``[REDACTED:TYPE]`` tokens.

    Only called for enterprise requests.  Defined locally so it does not need
    to be imported from an external module.
    """
    for label, pattern in _PII_PATTERNS:
        text = pattern.sub(f"[REDACTED:{label}]", text)
    return text


# ---------------------------------------------------------------------------
# Update decision logic (ported from application/update_decision.py)
# ---------------------------------------------------------------------------

def _decide_update_type(
    previous_context: Optional[ProcessedContextData],
    new_domains: List[str],
) -> Literal["incremental", "full", "none"]:
    """
    Determine whether to do a full recompute or an incremental update.

    Domain-based identity:
    - No previous context → full
    - New primary domain not in previous domains → full (domain shift)
    - Same domain → incremental
    """
    if not previous_context:
        return "full"
    if not new_domains:
        return "full"

    new_primary = new_domains[0]
    prev_domains = previous_context.domains or []

    if new_primary not in prev_domains:
        if not any(d in prev_domains for d in new_domains):
            logger.info(
                "_decide_update_type: FULL — domain shift %s -> %s",
                prev_domains,
                new_domains,
            )
            return "full"

    return "incremental"


# ---------------------------------------------------------------------------
# Cost tracker helpers (ported from application/cost_tracker.py)
# ---------------------------------------------------------------------------

_COST_CONFIG: Dict[str, float] = {
    "full": 1.0,
    "incremental": 0.3,
    "none": 0.0,
    "manual": 0.0,
}

_MAX_COST_PER_SESSION = 5.0
_VERSION_LIMIT = 5


def _estimate_cost(update_type: str) -> float:
    return _COST_CONFIG.get(update_type, 0.0)


def _is_cost_allowed(cumulative: float, estimated: float) -> bool:
    return (cumulative + estimated) <= _MAX_COST_PER_SESSION


# ---------------------------------------------------------------------------
# Platform normalisation
# ---------------------------------------------------------------------------

_PLATFORM_MAP = {"openai": "chatgpt", "anthropic": "claude", "google": "gemini"}


def _normalise_platform(raw: str) -> str:
    p = (raw or "chatgpt").lower().strip()
    return _PLATFORM_MAP.get(p, p)


# ---------------------------------------------------------------------------
# Extension → internal adapter (ported from application/extension_adapter.py)
# ---------------------------------------------------------------------------

def _adapt_bulk_request(ext: ExtensionSyncRequest) -> ProcessContextRequest:
    """Convert extension bulk sync format to internal ProcessContextRequest."""
    raw_uid = ext.userId
    if raw_uid is None and ext.user:
        raw_uid = ext.user.user_id
    if raw_uid is None:
        raise ValueError("User ID is required. Please login to the extension.")

    try:
        int(str(raw_uid))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid non-integer userId: '{raw_uid}'") from exc

    auth_token: Optional[str] = (
        ext.user.accessToken if ext.user and ext.user.accessToken else None
    )

    messages: List[ChatMessage] = []
    for conv in ext.conversations:
        if not conv.messages:
            continue
        for msg in conv.messages:
            parts: List[str] = []
            if msg.content:
                parts.append(msg.content)
            if msg.images:
                for img in msg.images:
                    parts.append(f"[Image: {img.alt or ''}]")
            if msg.codeBlocks:
                for cb in msg.codeBlocks:
                    parts.append(f"```{cb.language or ''}\n{cb.code}\n```")
            messages.append(
                ChatMessage(
                    role=msg.role,
                    content="\n".join(parts),
                    timestamp=str(msg.timestamp),
                )
            )

    return ProcessContextRequest(
        user_id=str(raw_uid),
        session_id=ext.sessionId,
        platform=_normalise_platform(ext.platform),
        messages=messages,
        auth_token=auth_token,
    )


# ---------------------------------------------------------------------------
# Node backend helpers — best-effort, never raises to caller
# ---------------------------------------------------------------------------

async def _fetch_previous_context(
    topic_id: str,
    user_id: str,
    auth_token: Optional[str],
) -> Optional[ProcessedContextData]:
    """
    Retrieve the stored context for ``topic_id`` from the Node backend.
    Returns None on any error or 404.
    """
    _settings = get_settings()
    base_url = (_settings.NODE_BACKEND_URL or "").strip()
    if not base_url:
        logger.warning(
            "_fetch_previous_context: NODE_BACKEND_URL not set — skipping fetch"
        )
        return None

    params: Dict[str, str] = {"userId": user_id}
    headers: Dict[str, str] = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
            resp = await client.get(
                f"/api/v1/processed-context/session/{topic_id}",
                params=params,
                headers=headers,
            )
        if resp.status_code == 404:
            return None
        if resp.status_code == 401:
            logger.warning(
                "_fetch_previous_context: 401 for topic %s — treating as no context",
                topic_id,
            )
            return None
        if resp.status_code != 200:
            logger.warning(
                "_fetch_previous_context: unexpected %d for topic %s",
                resp.status_code,
                topic_id,
            )
            return None

        data = resp.json()
        if not data.get("success") or not data.get("data"):
            return None

        ctx = data["data"]
        return ProcessedContextData(
            session_id=ctx["sessionId"],
            user_id=str(ctx["userId"]),
            essence=ctx["essence"],
            intent=ctx["intent"],
            secondary_intent=ctx.get("secondaryIntent"),
            domains=ctx.get("domains", []),
            embedding=ctx.get("embedding"),
            embedding_model=ctx.get("embeddingModel", "BAAI/bge-m3"),
            embedding_version=ctx.get("embeddingVersion", "1.0"),
            message_count=ctx.get("messageCount", 0),
            platform=ctx.get("platform") or "unknown",
            version=ctx.get("version", 1),
            update_type=ctx.get("updateType", "full"),
            usage_cost=ctx.get("usageCost", 0.0),
            cumulative_cost=0.0,
            processed_at=ctx.get("processedAt"),
        )
    except Exception as exc:
        logger.warning("_fetch_previous_context: error fetching topic %s: %s", topic_id, exc)
        return None


async def _save_to_node(
    ctx: ProcessedContextData,
    auth_token: Optional[str],
    enterprise_id: Optional[str] = None,
    team_id: Optional[str] = None,
) -> None:
    """
    POST processed context to Node backend.

    Consumer path (no enterprise_id): /api/v1/processed-context
    Enterprise path (enterprise_id present): /api/v1/enterprise-context

    Exact camelCase payload — never raises (best-effort).
    """
    payload: Dict[str, Any] = {
        "sessionId": ctx.session_id,
        "essence": ctx.essence,
        "intent": ctx.intent,
        "secondaryIntent": ctx.secondary_intent,
        "domains": ctx.domains,
        "embedding": ctx.embedding,
        "embeddingModel": ctx.embedding_model,
        "embeddingVersion": ctx.embedding_version,
        "messageCount": ctx.message_count,
        "platform": ctx.platform,
        "version": ctx.version,
        "updateType": ctx.update_type,
        "usageCost": ctx.usage_cost,
        "userId": ctx.user_id,
    }
    if auth_token:
        payload["accessToken"] = auth_token

    # Enterprise persistence routing — fall back to consumer path on error
    persist_path = "/api/v1/processed-context"
    if enterprise_id:
        try:
            persist_path = "/api/v1/enterprise-context"
            payload["enterpriseId"] = enterprise_id
            if team_id:
                payload["teamId"] = team_id
        except Exception as exc:  # pragma: no cover — defensive only
            logger.warning(
                "_save_to_node: enterprise routing setup failed (%s) — falling back to consumer path",
                exc,
            )
            persist_path = "/api/v1/processed-context"

    try:
        await node_post(persist_path, payload)
        logger.info(
            "_save_to_node: persisted session=%s user=%s version=%d path=%s",
            ctx.session_id,
            ctx.user_id,
            ctx.version,
            persist_path,
        )
    except Exception as exc:
        logger.warning("_save_to_node: Node persist failed (continuing): %s", exc)


# ---------------------------------------------------------------------------
# Core processing pipeline (ported from ContextProcessorService.process)
# ---------------------------------------------------------------------------

async def _run_processing_pipeline(
    request: ProcessContextRequest,
) -> ProcessedContextData:
    """
    Full ContextEngine processing pipeline:

    1. Classify intent + extract domains (Groq, single call with a 'probe' set
       of messages so we can derive the topic_id before fetching previous state)
    2. Derive domain-based topic_id = user_id + "_" + primary_domain
       (Enterprise: topic_id is prefixed with enterprise_{enterprise_id}[_team_{team_id}]_
        to provide complete tenant isolation in pgvector storage.)
    3. Fetch previous context for that topic (Node backend GET)
    4. Version-limit check (≥ 5 → return stored, no save)
    5. Update decision: full | incremental | none
    6. Cost-limit check
    7. Groq LLM — generate/update essence (with PREVIOUS ESSENCE hint for incremental)
    8. [Enterprise only] Redact PII from essence before embedding
    9. NVIDIA API — generate 1024-dim embedding of the (possibly redacted) essence
    10. Package ProcessedContextData
    11. Persist to Node backend (enterprise path when enterprise_id present)
    12. [Enterprise only] Emit structured audit log
    """
    enterprise_id: Optional[str] = request.enterprise_id
    team_id: Optional[str] = request.team_id
    is_enterprise = bool(enterprise_id)

    messages_dict = [{"role": m.role, "content": m.content} for m in request.messages]

    # --- Step 1: Early extraction for topic routing ---
    # We do a first Groq call without previous_essence to get domain/intent.
    # If this were incremental we'd repeat the call with the hint in step 7;
    # however we reuse this result for full updates and as the basis for
    # incremental hints, avoiding a redundant API round-trip.
    initial_extraction = await _extract_context(request.messages)
    primary_domain = initial_extraction.get("primary_domain", "software_data_engineering")
    primary_intent = initial_extraction["intent"]
    secondary_intent = initial_extraction.get("secondary_intent")
    initial_domains = initial_extraction["domains"]
    initial_essence = initial_extraction["essence"]

    # --- Step 2: Domain-based topic identity ---
    # Enterprise topic keys include the tenant namespace so that enterprise
    # context is completely isolated from consumer users and from other tenants.
    if is_enterprise:
        try:
            if team_id:
                tenant_prefix = f"enterprise_{enterprise_id}_team_{team_id}"
            else:
                tenant_prefix = f"enterprise_{enterprise_id}"
            topic_id = f"{tenant_prefix}_{request.user_id}_{primary_domain}"
        except Exception as exc:
            logger.warning(
                "_pipeline: enterprise topic_id build failed (%s) — falling back to consumer key",
                exc,
            )
            topic_id = f"{request.user_id}_{primary_domain}"
    else:
        topic_id = f"{request.user_id}_{primary_domain}"

    logger.info(
        "_pipeline: topic_id=%s session=%s messages=%d enterprise=%s",
        topic_id,
        request.session_id,
        len(request.messages),
        is_enterprise,
    )

    # --- Step 3: Fetch previous state ---
    previous_context = await _fetch_previous_context(
        topic_id, request.user_id, request.auth_token
    )
    if previous_context:
        logger.info(
            "_pipeline: found existing topic %s (v%d)", topic_id, previous_context.version
        )
    else:
        logger.info("_pipeline: no previous context for topic %s — fresh start", topic_id)

    # --- Step 4: Version limit ---
    if previous_context and previous_context.version >= _VERSION_LIMIT:
        logger.info(
            "_pipeline: version limit reached for %s (v%d) — returning stored context",
            topic_id,
            previous_context.version,
        )
        return previous_context

    # --- Step 5: Update decision ---
    update_type = _decide_update_type(previous_context, initial_domains)

    if update_type == "none" and previous_context:
        logger.info("_pipeline: update_type=none — returning previous context unchanged")
        return previous_context

    # --- Step 6: Cost check ---
    cumulative_cost = previous_context.cumulative_cost if previous_context else 0.0
    estimated_cost = _estimate_cost(update_type)
    if not _is_cost_allowed(cumulative_cost, estimated_cost):
        logger.warning(
            "_pipeline: cost limit for topic %s — cumulative=%.1f estimated=%.1f",
            topic_id,
            cumulative_cost,
            estimated_cost,
        )
        if previous_context:
            return previous_context

    # --- Step 7: Groq extraction with incremental hint if needed ---
    if update_type == "incremental" and previous_context:
        # Inject previous essence to trigger MASTER + FLOW path
        extraction = await _extract_context(
            request.messages, previous_essence=previous_context.essence
        )
        primary_intent = extraction["intent"]
        secondary_intent = extraction.get("secondary_intent")
        final_domains = extraction["domains"]
        final_essence = extraction["essence"]
    else:
        # Full recompute — use the initial extraction result (already stripped of FLOW)
        final_domains = initial_domains
        final_essence = initial_essence
        # Re-strip FLOW to be absolutely safe (strip_flow is idempotent)
        final_essence = _strip_flow(final_essence)

    # --- Step 8: Enterprise PII redaction (before embedding) ---
    embed_essence = final_essence  # text actually fed to the embedding model
    if is_enterprise:
        try:
            embed_essence = _redact_pii(final_essence)
            if embed_essence != final_essence:
                logger.info(
                    "_pipeline: PII redacted from essence for enterprise_id=%s session=%s",
                    enterprise_id,
                    request.session_id,
                )
        except Exception as exc:
            logger.warning(
                "_pipeline: PII redaction failed (%s) — using unredacted essence for embedding",
                exc,
            )
            embed_essence = final_essence  # fall back to original

    # --- Step 9: NVIDIA embedding ---
    embedding: Optional[List[float]] = None
    embedding_model = "nvidia/llama-3.2-nemoretriever-1b-vlm-embed-v1"
    try:
        embedding = await generate_embedding(embed_essence)
        _settings = get_settings()
        embedding_model = _settings.EMBEDDING_MODEL or embedding_model
    except Exception as exc:
        logger.warning("_pipeline: embedding failed (%s) — proceeding without", exc)

    # --- Step 10: Package ---
    new_version = (previous_context.version + 1) if previous_context else 1
    new_cumulative = cumulative_cost + estimated_cost

    ctx = ProcessedContextData(
        session_id=topic_id,
        user_id=request.user_id,
        essence=embed_essence,  # store the (possibly redacted) essence
        intent=primary_intent,
        secondary_intent=secondary_intent,
        domains=final_domains,
        embedding=embedding,
        embedding_model=embedding_model,
        embedding_version="1.0",
        message_count=len(request.messages),
        platform=request.platform,
        version=new_version,
        update_type=update_type,
        usage_cost=estimated_cost,
        cumulative_cost=new_cumulative,
        processed_at=datetime.utcnow().isoformat() + "Z",
    )

    # --- Step 11: Persist ---
    await _save_to_node(
        ctx,
        request.auth_token,
        enterprise_id=enterprise_id,
        team_id=team_id,
    )

    # --- Step 11b: Shadow-write to Supermemory (fire-and-forget) ---
    try:
        from shared.supermemory_client import add_memory as _sm_add
        _settings = get_settings()
        if _settings.SUPERMEMORY_API_KEY:
            asyncio.create_task(
                _sm_add(
                    user_id=request.user_id,
                    content=embed_essence,
                    metadata={
                        "session_id": topic_id,
                        "intent": primary_intent,
                        "domains": final_domains,
                        "platform": request.platform or "unknown",
                        "source": "thinkvelocity_context_engine",
                    },
                )
            )
    except Exception:
        pass  # supermemory write must never affect the main pipeline

    # --- Step 12: Enterprise audit log ---
    if is_enterprise:
        try:
            audit_record = {
                "action": "context_stored",
                "enterprise_id": enterprise_id,
                "user_id": request.user_id,
                "session_id": request.session_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
            logger.info("AUDIT %s", json.dumps(audit_record))
        except Exception:
            pass  # audit failure must never affect the main pipeline

    return ctx


# ---------------------------------------------------------------------------
# Manual essence processing (ported from ContextProcessorService.process_manual_essence)
# ---------------------------------------------------------------------------

async def _run_manual_essence_pipeline(
    request: ManualEssenceRequest,
) -> ProcessedContextData:
    """
    Process a manually entered essence:
    1. Generate NVIDIA embedding
    2. Package with intent=manual_memory, domains=["manual_memory"]
    3. Persist to Node backend
    """
    session_id = request.session_id or (
        f"{request.user_id}_manual_memory_{int(datetime.utcnow().timestamp())}"
    )

    embedding: Optional[List[float]] = None
    embedding_model = "nvidia/llama-3.2-nemoretriever-1b-vlm-embed-v1"
    try:
        embedding = await generate_embedding(request.essence)
        _settings = get_settings()
        embedding_model = _settings.EMBEDDING_MODEL or embedding_model
    except Exception as exc:
        logger.warning("_manual_essence: embedding failed (%s)", exc)

    ctx = ProcessedContextData(
        session_id=session_id,
        user_id=request.user_id,
        essence=request.essence.strip(),
        intent="manual_memory",
        secondary_intent="",
        domains=["manual_memory"],
        embedding=embedding,
        embedding_model=embedding_model,
        embedding_version="1.0",
        message_count=1,
        platform=request.platform,
        version=1,
        update_type="manual",
        usage_cost=0.0,
        cumulative_cost=0.0,
        processed_at=datetime.utcnow().isoformat() + "Z",
    )

    await _save_to_node(ctx, request.auth_token)
    return ctx


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/process-context", response_model=ProcessContextResponse)
async def process_context(request_body: dict = Body(...)) -> ProcessContextResponse:
    """
    Process a bulk conversation sync from the Chrome extension.

    Full pipeline: ExtensionAdapterService → Groq extraction → NVIDIA embedding
    → Node backend persist.
    """
    logger.info(
        "process_context: received bulk sync request (%d keys)",
        len(request_body),
    )

    # Parse extension bulk format
    try:
        ext_req = ExtensionSyncRequest(**request_body)
        internal = _adapt_bulk_request(ext_req)
    except ValueError as exc:
        logger.warning("process_context: validation error — %s", exc)
        raise HTTPException(status_code=400, detail=f"Invalid request format: {exc}")
    except Exception as exc:
        logger.exception("process_context: unexpected parse error")
        raise HTTPException(status_code=400, detail=f"Invalid request format: {exc}")

    if not internal.messages:
        logger.warning(
            "process_context: no messages in sync request session=%s", ext_req.sessionId
        )
        return ProcessContextResponse(
            session_id=ext_req.sessionId,
            status="completed",
            error="No messages to process",
        )

    logger.info(
        "process_context: processing session=%s user=%s messages=%d platform=%s",
        internal.session_id,
        internal.user_id,
        len(internal.messages),
        internal.platform,
    )

    try:
        ctx = await _run_processing_pipeline(internal)
    except ValueError as exc:
        logger.warning("process_context: validation failure — %s", exc)
        raise HTTPException(status_code=422, detail=f"Data validation error: {exc}")
    except Exception as exc:
        logger.exception("process_context: pipeline error")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during context processing",
        )

    return ProcessContextResponse(
        session_id=ext_req.sessionId,
        status="completed",
        processed_context=ctx,
    )


@router.post("/process-essence", response_model=ProcessedContextData)
async def process_essence(request: ManualEssenceRequest) -> ProcessedContextData:
    """
    Process a manually entered essence (memory panel entry).

    Generates a 1024-dim NVIDIA embedding and persists to the Node backend
    with intent=manual_memory so it is stored but does not affect the
    automated domain-topic essence pipeline.
    """
    logger.info(
        "process_essence: user=%s platform=%s",
        request.user_id,
        request.platform,
    )
    try:
        return await _run_manual_essence_pipeline(request)
    except Exception as exc:
        logger.exception("process_essence: unexpected error")
        raise HTTPException(
            status_code=500,
            detail=f"Manual essence processing failed: {exc}",
        )


@router.get("/user/{user_id}/profile")
async def get_user_profile(user_id: str) -> Dict[str, Any]:
    """
    Get user profile — proxies to Node /api/v1/user-profile.

    Returns the user's primary_domains, common_intents, recent_essences, and
    aggregate stats. Degrades gracefully to an empty profile on any failure
    (auth, timeout, Node backend unavailable).
    """
    _settings = get_settings()
    base_url = (_settings.NODE_BACKEND_URL or "").strip()
    if not base_url:
        logger.warning("get_user_profile: NODE_BACKEND_URL not set")
        return {
            "user_id": user_id,
            "primary_domains": [],
            "common_intents": [],
            "recent_essences": [],
            "stats": {},
        }

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
            resp = await client.get(
                "/api/v1/user-profile",
                params={"userId": user_id},
            )

        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") and data.get("data"):
                p = data["data"]
                logger.info(
                    "get_user_profile: retrieved profile for user=%s", user_id
                )
                return {
                    "user_id": p.get("userId", user_id),
                    "primary_domains": p.get("primaryDomains", []),
                    "common_intents": p.get("commonIntents", []),
                    "recent_essences": p.get("recentEssences", []),
                    "stats": p.get("stats", {}),
                }
        elif resp.status_code == 401:
            logger.warning(
                "get_user_profile: 401 for user=%s — returning empty profile", user_id
            )
        elif resp.status_code == 404:
            logger.info("get_user_profile: user=%s not found", user_id)
        else:
            logger.warning(
                "get_user_profile: Node returned %d for user=%s",
                resp.status_code,
                user_id,
            )

    except httpx.TimeoutException:
        logger.warning("get_user_profile: timeout fetching profile for user=%s", user_id)
    except Exception as exc:
        logger.warning("get_user_profile: error for user=%s — %s", user_id, exc)

    # Graceful degradation — always return an empty profile rather than 500
    return {
        "user_id": user_id,
        "primary_domains": [],
        "common_intents": [],
        "recent_essences": [],
        "stats": {},
    }


# ---------------------------------------------------------------------------
# Entity extraction helpers (zero-latency, no external API)
# ---------------------------------------------------------------------------

_FRAMEWORK_PATTERNS = [
    "react", "next.js", "nextjs", "vue", "angular", "svelte",
    "fastapi", "django", "flask", "express", "nestjs",
    "pytorch", "tensorflow", "langchain",
    "postgres", "postgresql", "mysql", "mongodb", "redis",
    "kubernetes", "docker", "terraform", "aws", "gcp", "azure",
]

_DOMAIN_PATTERNS = {
    "e-commerce": ["ecommerce", "e-commerce", "shopify", "shop", "product catalog", "checkout"],
    "saas": ["saas", "subscription", "tenant", "multi-tenant", "billing"],
    "fintech": ["fintech", "payment", "stripe", "banking", "transaction"],
    "healthcare": ["healthcare", "medical", "patient", "clinical", "hipaa"],
    "data_engineering": ["pipeline", "etl", "bigquery", "dbt", "airflow", "spark"],
    "legal_tech": ["legal", "contract", "compliance", "regulatory"],
    "ai_ml": ["llm", "model", "training", "inference", "embedding", "fine-tun"],
}


def extract_entities(essence: str) -> dict:
    """Extract structured entities from a raw essence string.

    Returns a dict with keys: frameworks (list), domain (str or None), language (str or None).
    All matching is case-insensitive substring match — no external API needed.
    Empty lists / None values are omitted from the returned dict.
    """
    text = essence.lower()
    frameworks = [f for f in _FRAMEWORK_PATTERNS if f in text]

    domain = None
    for dom, signals in _DOMAIN_PATTERNS.items():
        if any(s in text for s in signals):
            domain = dom
            break

    language = None
    for lang in ["python", "typescript", "javascript", "go", "rust", "java", "ruby"]:
        if lang in text:
            language = lang
            break

    return {k: v for k, v in {"frameworks": frameworks, "domain": domain, "language": language}.items() if v}


@router.post("/search/contexts", response_model=ContextSearchResponse)
async def search_contexts(request: ContextSearchRequest) -> ContextSearchResponse:
    """
    Semantic search for stored contexts.

    Embeds the query with NVIDIA, then proxies the vector to the Node backend
    public search endpoint. Applies RELEVANCE_THRESHOLD filtering. Degrades
    gracefully to empty results on any failure.
    """
    _settings = get_settings()
    threshold = _settings.RELEVANCE_THRESHOLD or 0.30

    logger.info(
        "search_contexts: user=%s query='%s' limit=%d threshold=%.2f",
        request.user_id,
        request.query[:60],
        request.limit,
        threshold,
    )

    try:
        query_embedding = await generate_embedding(request.query)
    except Exception as exc:
        logger.warning("search_contexts: embedding failed — %s", exc)
        return ContextSearchResponse(
            user_id=request.user_id,
            query=request.query,
            results=[],
            total=0,
            threshold=threshold,
        )

    try:
        data = await node_post(
            "/api/v1/processed-context/public/search",
            {
                "embedding": query_embedding,
                "userId": request.user_id,
                "limit": request.limit,
                "threshold": threshold,
                "searchAllUsers": False,
            },
        )
        raw_results = (
            data.get("data", {}).get("contexts", [])
            if data and data.get("success")
            else []
        )
    except Exception as exc:
        logger.warning("search_contexts: Node search failed — %s", exc)
        raw_results = []

    # Filter by threshold and map to schema
    results: List[ContextSearchResult] = []
    for r in raw_results:
        score = float(r.get("similarity") or 0.0)
        if score < threshold:
            logger.debug(
                "search_contexts: below threshold %.3f < %.3f — skipping", score, threshold
            )
            continue
        results.append(
            ContextSearchResult(
                session_id=str(r.get("sessionId") or r.get("session_id") or ""),
                user_id=str(r.get("userId") or r.get("user_id") or ""),
                essence=r.get("essence") or "No essence",
                intent=r.get("intent") or "",
                secondary_intent=r.get("secondaryIntent") or r.get("secondary_intent"),
                domains=r.get("domains") or [],
                embedding=None,  # omit large vectors from search results
                embedding_model=r.get("embeddingModel") or r.get("embedding_model") or "",
                embedding_version=r.get("embeddingVersion") or r.get("embedding_version") or "1.0",
                message_count=int(r.get("messageCount") or r.get("message_count") or 0),
                platform=r.get("platform") or "unknown",
                version=int(r.get("version") or 1),
                update_type=r.get("updateType") or r.get("update_type") or "full",
                usage_cost=float(r.get("usageCost") or r.get("usage_cost") or 0.0),
                similarity=score,
            )
        )

    logger.info(
        "search_contexts: returned %d results for user=%s", len(results), request.user_id
    )
    return ContextSearchResponse(
        user_id=request.user_id,
        query=request.query,
        results=results,
        total=len(results),
        threshold=threshold,
    )


@router.delete("/memories/{document_id}")
async def delete_user_memory(document_id: str, user_id: str) -> Dict[str, Any]:
    """
    Delete a Supermemory document by ID for a given user.

    The extension panel can call this to let users manage their stored memory.
    Returns 200 with {"deleted": true} on success, 503 when Supermemory is not configured.
    """
    from shared.settings import get_settings as _get_settings
    if not _get_settings().SUPERMEMORY_API_KEY:
        return {"deleted": False, "reason": "supermemory_not_configured"}
    from shared.supermemory_client import delete_memory as _sm_delete
    ok = await _sm_delete(document_id)
    logger.info("delete_user_memory: doc_id=%s user=%s ok=%s", document_id, user_id, ok)
    return {"deleted": ok, "document_id": document_id}


@router.post("/test/batch-embedding")
async def test_batch_embedding(texts: List[str]) -> Dict[str, Any]:
    """
    Test NVIDIA batch embedding generation.

    Accepts a list of strings, runs them through the shared embedding client in
    batch, and returns timing metrics. Useful for validating NVIDIA API
    connectivity and measuring throughput.
    """
    if not texts:
        return {
            "success": True,
            "message": "No texts provided",
            "batch_size": 0,
            "latency_ms": 0.0,
            "average_per_text_ms": 0.0,
        }

    try:
        start = time.time()
        embeddings = await generate_embeddings_batch(texts)
        duration_ms = (time.time() - start) * 1000

        logger.info(
            "test_batch_embedding: %d texts in %.2fms", len(embeddings), duration_ms
        )
        return {
            "success": True,
            "message": f"Successfully generated {len(embeddings)} embeddings in batch",
            "batch_size": len(texts),
            "latency_ms": round(duration_ms, 2),
            "average_per_text_ms": round(duration_ms / len(texts), 2),
        }
    except Exception as exc:
        logger.error("test_batch_embedding: failed — %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/health")
async def context_health() -> Dict[str, Any]:
    """Health check for the context router and its external dependencies."""
    _settings = get_settings()
    return {
        "status": "healthy",
        "router": "context",
        "groq": "configured" if _settings.groq_keys else "missing",
        "nvidia_embeddings": (
            "configured" if _settings.nvidia_embedding_key else "mock_fallback"
        ),
        "node_backend": (
            "configured" if _settings.NODE_BACKEND_URL else "missing"
        ),
        "relevance_threshold": _settings.RELEVANCE_THRESHOLD,
    }
