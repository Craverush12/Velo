from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SCHEMA_VERSION = "2026-05-11.prompt-contracts.v1"


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
    general = "general"


Technique = Literal[
    "persona_injection",
    "task_clarification",
    "chain_of_thought",
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
]


TECHNIQUE_COLORS: dict[str, str] = {
    "persona_injection": "indigo",
    "task_clarification": "sky",
    "chain_of_thought": "amber",
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
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    summary: str
    schema_version: str = SCHEMA_VERSION
    prompt_version: str | None = None

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
    pe_techniques_applied: list[Technique] = Field(default_factory=list)
    key_additions: list[str] = Field(default_factory=list)
    summary: str
    schema_version: str = SCHEMA_VERSION
    prompt_version: str | None = None

    @field_validator("refined_prompt", "framework_used", "summary")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value
