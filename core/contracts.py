from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SCHEMA_VERSION = "2026-05-14.prompt-contracts.v3"
PROMPT_MODE_VALUES = ("normal", "caveman")

TARGET_AI_VALUES = (
    "claude",
    "chatgpt",
    "gpt-5",
    "gemini",
    "groq",
    "cursor",
    "bolt",
    "replit",
    "gamma",
    "midjourney",
)

TargetAI = Literal[
    "claude",
    "chatgpt",
    "gpt-5",
    "gemini",
    "groq",
    "cursor",
    "bolt",
    "replit",
    "gamma",
    "midjourney",
]

PromptMode = Literal["normal", "caveman"]


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
        "gpt4o": "chatgpt",
        "gpt-4o": "chatgpt",
        "gpt-4": "chatgpt",
        "openai": "chatgpt",
        "llama": "groq",
        "groq/llama": "groq",
        "claude-code": "cursor",
        "claude code": "cursor",
        "v0": "bolt",
        "lovable": "bolt",
        "image-gen": "midjourney",
        "image_gen": "midjourney",
        "presentations": "gamma",
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
    missing_context: list[str] = Field(default_factory=list)
    confirmation_question: str
    questions: list[IntentQuestion] = Field(default_factory=list)
    questions_answered: int = 0
    questions_total: int = 0
    is_finalized: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
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

    @field_validator("confirmation_question", mode="before")
    @classmethod
    def optional_confirmation_question(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()

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
