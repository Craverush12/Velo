from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SCHEMA_VERSION = "2026-05-14.prompt-contracts.v3"
PROMPT_MODE_VALUES = ("normal", "caveman", "research", "fast_build", "media")

TARGET_AI_VALUES = (
    # Chat & LLM Assistants
    "claude",
    "chatgpt",
    "gpt-5",
    "o3",
    "gemini",
    "grok",
    "mistral",
    "deepseek",
    "copilot",
    "kimi",
    "meta-ai",
    "qwen",
    "poe",
    "pi",
    "zai",
    "genspark",
    "felo",
    # Inference / Speed
    "groq",
    "compound_mini",
    # Research
    "perplexity",
    # Coding & Dev Tools
    "cursor",
    "windsurf",
    "codeium",
    "github-copilot",
    "devin",
    "emergent",
    "bolt",
    "v0",
    "replit",
    "lovable",
    # Image & Design
    "midjourney",
    "leonardo",
    "ideogram",
    "krea",
    "recraft",
    "canva",
    # Video
    "runway",
    "pika",
    "heygen",
    "hera",
    "google-flow",
    # Audio / Music
    "suno",
    "udio",
    # Productivity & Presentations
    "gamma",
    "copyai",
    "manus",
    "tome",
)

TargetAI = Literal[
    "claude", "chatgpt", "gpt-5", "o3", "gemini", "grok",
    "mistral", "deepseek", "copilot", "kimi", "meta-ai", "qwen",
    "poe", "pi", "zai", "genspark", "felo",
    "groq", "compound_mini", "perplexity",
    "cursor", "windsurf", "codeium", "github-copilot", "devin", "emergent",
    "bolt", "v0", "replit", "lovable",
    "midjourney", "leonardo", "ideogram", "krea", "recraft", "canva",
    "runway", "pika", "heygen", "hera", "google-flow",
    "suno", "udio",
    "gamma", "copyai", "manus", "tome",
]

PromptMode = Literal["normal", "caveman", "research", "fast_build", "media"]


def normalize_prompt_mode(value: str | None) -> str:
    if value is None:
        return "normal"
    normalized = value.strip().lower().replace("-", "_")
    if not normalized:
        return "normal"
    aliases = {
        "default": "normal",
        "standard": "normal",
        "base": "normal",
        "cave": "caveman",
        "caveman_mode": "caveman",
        "cavemanmode": "caveman",
        "fast": "fast_build",
        "build": "fast_build",
        "fastbuild": "fast_build",
        "research_mode": "research",
        "media_mode": "media",
        "creative": "media",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in PROMPT_MODE_VALUES:
        raise ValueError(f"prompt_mode must be one of: {', '.join(PROMPT_MODE_VALUES)}")
    return normalized


def normalize_target_ai(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    aliases = {
        # OpenAI
        "gpt4o": "chatgpt",
        "gpt-4o": "chatgpt",
        "gpt-4": "chatgpt",
        "openai": "chatgpt",
        "chatgpt-4o": "chatgpt",
        "o1": "o3",
        "o1-pro": "o3",
        "o3-mini": "o3",
        # Groq (inference provider)
        "llama": "groq",
        "mixtral": "groq",
        "groq/llama": "groq",
        # Grok (xAI)
        "xai": "grok",
        "grok-3": "grok",
        "x.ai": "grok",
        "grok.com": "grok",
        # Compound
        "compound-mini": "compound_mini",
        "groq/compound-mini": "compound_mini",
        "groq/compound": "compound_mini",
        "compound": "compound_mini",
        # Perplexity
        "perplexity.ai": "perplexity",
        "pplx": "perplexity",
        # Claude Code → Cursor (IDE context)
        "claude-code": "cursor",
        "claude code": "cursor",
        "cursor.com": "cursor",
        # Windsurf / Codeium — now distinct
        "windsurf.ai": "windsurf",
        "codeium.com": "codeium",
        # GitHub Copilot
        "github copilot": "github-copilot",
        "gh copilot": "github-copilot",
        "copilot chat": "github-copilot",
        # Devin
        "devin.ai": "devin",
        "cognition": "devin",
        # Emergent
        "emergent.sh": "emergent",
        # Builders
        "bolt.new": "bolt",
        "lovable.dev": "lovable",
        "v0.dev": "v0",
        "vercel v0": "v0",
        # Microsoft Copilot (distinct from GitHub Copilot)
        "microsoft copilot": "copilot",
        "ms copilot": "copilot",
        "bing chat": "copilot",
        "copilot.microsoft.com": "copilot",
        # Mistral
        "mistral.ai": "mistral",
        "chat.mistral.ai": "mistral",
        "le chat": "mistral",
        # DeepSeek
        "deepseek.com": "deepseek",
        "chat.deepseek.com": "deepseek",
        # Kimi (Moonshot AI)
        "kimi.com": "kimi",
        "moonshot": "kimi",
        "moonshot ai": "kimi",
        # Meta AI
        "meta.ai": "meta-ai",
        "metaai": "meta-ai",
        "meta ai": "meta-ai",
        "llama chat": "meta-ai",
        # Qwen (Alibaba)
        "chat.qwen.ai": "qwen",
        "alibaba": "qwen",
        "qwen2": "qwen",
        # Poe
        "poe.com": "poe",
        # Pi (Inflection AI)
        "pi.ai": "pi",
        "inflection": "pi",
        # Z.ai
        "z.ai": "zai",
        "chat.z.ai": "zai",
        # Genspark
        "genspark.ai": "genspark",
        # Felo
        "felo.ai": "felo",
        # Image platforms
        "image-gen": "midjourney",
        "image_gen": "midjourney",
        "midjourney.com": "midjourney",
        "leonardo.ai": "leonardo",
        "app.leonardo.ai": "leonardo",
        "ideogram.ai": "ideogram",
        "krea.ai": "krea",
        "recraft.ai": "recraft",
        "canva.com": "canva",
        # Video platforms
        "app.runwayml.com": "runway",
        "runwayml": "runway",
        "pika.art": "pika",
        "pika labs": "pika",
        "app.heygen.com": "heygen",
        "hera.video": "hera",
        "google flow": "google-flow",
        "labs.google": "google-flow",
        # Audio / Music
        "suno.com": "suno",
        "suno.ai": "suno",
        "udio.com": "udio",
        # Productivity
        "presentations": "gamma",
        "slides": "gamma",
        "gamma.app": "gamma",
        "app.copy.ai": "copyai",
        "copy.ai": "copyai",
        "copy ai": "copyai",
        "manus.im": "manus",
        "tomeapp.ai": "tome",
        "tome.app": "tome",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in TARGET_AI_VALUES:
        raise ValueError(f"target_ai must be one of: {', '.join(TARGET_AI_VALUES)}")
    return normalized


class Intent(str, Enum):
    code_generation = "code_generation"
    debugging = "debugging"
    code_review = "code_review"
    architecture_design = "architecture_design"
    data_analysis = "data_analysis"
    research = "research"
    creative_writing = "creative_writing"
    copywriting = "copywriting"
    marketing = "marketing"
    business_strategy = "business_strategy"
    legal_analysis = "legal_analysis"
    financial_analysis = "financial_analysis"
    design_brief = "design_brief"
    learning_explanation = "learning_explanation"
    system_design = "system_design"
    product_strategy = "product_strategy"
    testing_qa = "testing_qa"
    data_extraction = "data_extraction"
    code_conversion = "code_conversion"
    task_automation = "task_automation"
    general_qa = "general_qa"


class Domain(str, Enum):
    software_engineering = "software_engineering"
    data_science = "data_science"
    devops_infrastructure = "devops_infrastructure"
    mobile_development = "mobile_development"
    marketing_growth = "marketing_growth"
    design_ux = "design_ux"
    legal = "legal"
    finance = "finance"
    education = "education"
    health_science = "health_science"
    business_operations = "business_operations"
    creative_arts = "creative_arts"
    product_management = "product_management"
    cybersecurity = "cybersecurity"
    ecommerce = "ecommerce"
    general = "general"


Technique = Literal[
    "persona_injection",
    "task_clarification",
    "chain_of_thought",
    "tree_of_thought",
    "socratic_prompting",
    "structured_output",
    "output_format_spec",
    "constraint_definition",
    "context_framing",
    "few_shot_example",
    "negative_space",
    "target_ai_optimization",
    "step_back_trigger",
    "contrastive",
    "domain_specific_depth",
    "user_context_integration",
    "placeholder_facilitation",
]


ColorKey = Literal[
    "indigo",
    "sky",
    "amber",
    "emerald",
    "rose",
    "violet",
    "purple",
    "red",
    "orange",
    "teal",
    "pink",
    "cyan",
    "lime",
    "slate",
    "blue",
    "fuchsia",
    "green",
]


TECHNIQUE_COLORS: dict[str, str] = {
    "persona_injection": "indigo",
    "task_clarification": "sky",
    "chain_of_thought": "amber",
    "tree_of_thought": "blue",
    "socratic_prompting": "fuchsia",
    "structured_output": "green",
    "output_format_spec": "emerald",
    "constraint_definition": "rose",
    "context_framing": "violet",
    "few_shot_example": "purple",
    "negative_space": "red",
    "target_ai_optimization": "orange",
    "step_back_trigger": "teal",
    "contrastive": "pink",
    "domain_specific_depth": "cyan",
    "user_context_integration": "lime",
    "placeholder_facilitation": "slate",
}


class AnnotatedSegment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    text: str
    technique: Technique
    technique_label: str
    color_key: ColorKey
    reason: str
    is_original: bool = False
    original_text: str | None = None

    @field_validator("id", "text", "technique_label", "reason")
    @classmethod
    def not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value


class PlaceholderField(BaseModel):
    model_config = ConfigDict(extra="ignore")

    key: str
    label: str
    placeholder: str
    description: str
    required: bool = True
    example: str = ""
    type: Literal["text", "textarea", "number", "url", "date", "list"] = "text"

    @field_validator("key")
    @classmethod
    def valid_key(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized or not normalized.replace("_", "").isalnum():
            raise ValueError("placeholder key must be uppercase snake-case")
        return normalized

    @field_validator("placeholder")
    @classmethod
    def valid_placeholder(cls, value: str) -> str:
        value = value.strip()
        if not (value.startswith("[") and value.endswith("]")):
            raise ValueError("placeholder must use square brackets")
        return value


class ClarificationQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str
    options: list[str] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("question must not be empty")
        return value.strip()


class ClarificationQA(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str
    answer: str

    @field_validator("question", "answer")
    @classmethod
    def qa_not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("question and answer must not be empty")
        return value.strip()


class SourceInspiration(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    url: str
    category: str
    use_case: str

class ConnectorRecommendation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    category: str
    use_case: str
    url: str = ""
    connector_type: str = "ai_platform"

    @field_validator("name", "url", "category", "use_case")
    @classmethod
    def source_text_not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value.strip()


class IntentQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    question: str
    options: list[str] = Field(default_factory=list)
    type: str = "multiple_choice"

    @field_validator("id", "question")
    @classmethod
    def not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value.strip()


class AIRecommendation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ai: str
    rank: int = Field(ge=1, le=3)
    reason: str

    @field_validator("ai", "reason")
    @classmethod
    def not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value.strip()


GAP_FIELDS = [
    "target_audience",
    "output_format",
    "key_constraints",
]


GAP_QUESTIONS: dict[str, dict] = {
    "target_audience": {
        "id": "target_audience",
        "question": "Help me tailor this perfectly — who are you creating this for?",
        "options": [
            "End users / customers",
            "Developers / technical team",
            "Business stakeholders / executives",
            "Designers / creatives",
            "General public / broad audience",
        ],
        "type": "multiple_choice",
        "persuasion": "Knowing your audience lets me match tone, complexity, and framing so it lands the first time.",
    },
    "output_format": {
        "id": "output_format",
        "question": "To nail the exact format — what should the final output look like?",
        "options": [
            "A written document / article",
            "Step-by-step instructions / guide",
            "Code / technical specification",
            "Email or message draft",
            "Presentation / slide deck",
        ],
        "type": "multiple_choice",
        "persuasion": "The right format means the result is ready to use immediately with zero rework.",
    },
    "key_constraints": {
        "id": "key_constraints",
        "question": "Any must-have guardrails I should know about?",
        "options": [
            "Keep it concise (under 500 words)",
            "Tone should be professional / formal",
            "Needs to be beginner-friendly",
            "Include specific technical details",
            "No specific constraints — use your judgment",
        ],
        "type": "multiple_choice",
        "persuasion": "Constraints prevent vague outputs and make sure the result fits your exact use case.",
    },
}


def detect_gaps(classification: dict) -> list[str]:
    """Deterministically detect which required fields are missing/empty."""
    gaps: list[str] = []
    for field in GAP_FIELDS:
        value = classification.get(field)
        if not value:
            gaps.append(field)
        elif isinstance(value, list) and not value:
            gaps.append(field)
        elif isinstance(value, str) and not value.strip():
            gaps.append(field)
    return gaps


def build_gap_questions(gaps: list[str]) -> list[IntentQuestion]:
    """Build persuasive questions for each missing field."""
    questions: list[IntentQuestion] = []
    for field in gaps:
        template = GAP_QUESTIONS.get(field)
        if template:
            questions.append(IntentQuestion(
                id=template["id"],
                question=template["question"],
                options=list(template["options"]),
                type=template["type"],
            ))
    return questions


def compute_confidence(classification: dict) -> float:
    """Compute confidence deterministically as ratio of filled required fields."""
    filled = 0
    for field in GAP_FIELDS:
        value = classification.get(field)
        if value and not (isinstance(value, list) and not value) and not (isinstance(value, str) and not value.strip()):
            filled += 1
    total = len(GAP_FIELDS)
    return filled / total if total > 0 else 1.0


class IntentConfirmationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = SCHEMA_VERSION
    intent: Intent
    domain: Domain
    interpreted_need: str
    deliverable: str
    target_audience: str = ""
    output_format: str = ""
    key_constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    questions: list[IntentQuestion] = Field(default_factory=list)
    questions_total: int = 0
    is_finalized: bool = True
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    suggested_prompt_mode: PromptMode = "normal"
    suggested_techniques: list[Technique] = Field(default_factory=list)
    enhancement_strategy: list[str] = Field(default_factory=list)
    source_inspirations: list[SourceInspiration] = Field(default_factory=list)
    target_ai: TargetAI | None = None
    prompt_mode: PromptMode = "normal"

    @field_validator("interpreted_need", "deliverable")
    @classmethod
    def intent_text_not_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator(
        "target_audience",
        "output_format",
        mode="before",
    )
    @classmethod
    def optional_text_default(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("suggested_prompt_mode", "prompt_mode", mode="before")
    @classmethod
    def valid_confirmation_prompt_mode(cls, value: str | None) -> str:
        return normalize_prompt_mode(value)

    @field_validator("target_ai", mode="before")
    @classmethod
    def valid_confirmation_target_ai(cls, value: str | None) -> str | None:
        return normalize_target_ai(value)


class PersonalizationTrace(BaseModel):
    model_config = ConfigDict(extra="ignore")
    rule: str
    reason: str


class EnhanceResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enhanced_prompt: str
    annotated_segments: list[AnnotatedSegment]
    placeholder_fields: list[PlaceholderField] = Field(default_factory=list)
    framework_used: str
    framework_rationale: str = ""
    pe_techniques_applied: list[Technique] = Field(default_factory=list)
    intent: Intent
    domain: Domain
    prompt_quality_score: float = Field(ge=0.0, le=1.0)
    target_ai_optimized: bool = False
    target_ai_recommendations: list[AIRecommendation] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    recommended_connectors: list[ConnectorRecommendation] = Field(default_factory=list)
    personalization_trace: list[PersonalizationTrace] = Field(default_factory=list)
    injection_detected: bool = False
    summary: str
    schema_version: str = SCHEMA_VERSION
    prompt_version: str | None = None
    prompt_mode: PromptMode = "normal"

    @field_validator("enhanced_prompt", "framework_used", "summary")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("framework_rationale", mode="before")
    @classmethod
    def default_framework_rationale(cls, value: Any) -> str:
        return "" if value is None else str(value)


class RefineResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    refined_prompt: str
    annotated_segments: list[AnnotatedSegment]
    placeholder_fields: list[PlaceholderField] = Field(default_factory=list)
    framework_used: str
    framework_rationale: str = ""
    pe_techniques_applied: list[Technique] = Field(default_factory=list)
    prompt_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    quality_delta: float = 0.0
    key_additions: list[str] = Field(default_factory=list)
    recommended_connectors: list[ConnectorRecommendation] = Field(default_factory=list)
    summary: str
    schema_version: str = SCHEMA_VERSION
    prompt_version: str | None = None
    prompt_mode: PromptMode = "normal"

    @field_validator("refined_prompt", "framework_used", "summary")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("framework_rationale", mode="before")
    @classmethod
    def default_framework_rationale(cls, value: Any) -> str:
        return "" if value is None else str(value)
