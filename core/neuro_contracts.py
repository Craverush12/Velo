from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.contracts import PromptMode, TargetAI, normalize_prompt_mode, normalize_target_ai


NEURO_SCHEMA_VERSION = "2026-05-21.neuro-score.v1"
NEURO_DISCLAIMER = (
    "This is a prompt-quality heuristic inspired by brain-response modeling. "
    "It is not fMRI prediction."
)


class NeuroDimensions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    clarity: int = Field(ge=0, le=100)
    sensory_specificity: int = Field(ge=0, le=100)
    temporal_structure: int = Field(ge=0, le=100)
    attention_salience: int = Field(ge=0, le=100)
    cognitive_load: int = Field(ge=0, le=100)
    output_grounding: int = Field(ge=0, le=100)
    multimodal_readiness: int = Field(ge=0, le=100)
    personal_fit: int = Field(default=0, ge=0, le=100)


class NeuroScoreRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    raw_prompt: str
    enhanced_prompt: str | None = None
    target_ai: TargetAI | None = None
    prompt_mode: PromptMode = "normal"
    personalization_context: dict | None = None

    @field_validator("raw_prompt")
    @classmethod
    def raw_prompt_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("raw_prompt must not be empty")
        return value

    @field_validator("enhanced_prompt", mode="before")
    @classmethod
    def clean_optional_prompt(cls, value) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("target_ai", mode="before")
    @classmethod
    def valid_target_ai(cls, value: str | None) -> str | None:
        return normalize_target_ai(value)

    @field_validator("prompt_mode", mode="before")
    @classmethod
    def valid_prompt_mode(cls, value: str | None) -> str:
        return normalize_prompt_mode(value)


class NeuroScoreResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = NEURO_SCHEMA_VERSION
    overall_score: int = Field(ge=0, le=100)
    score_delta: int = Field(ge=-100, le=100)
    label: Literal["Low", "Moderate", "Strong", "High Signal"]
    dimensions: NeuroDimensions
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    suggested_improvements: list[str] = Field(default_factory=list)
    disclaimer: str = NEURO_DISCLAIMER

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, value) -> str:
        label = str(value or "").strip()
        normalized = label.lower().replace("_", " ").replace("-", " ")
        normalized = " ".join(normalized.split())
        aliases = {
            "low": "Low",
            "low signal": "Low",
            "moderate": "Moderate",
            "moderate signal": "Moderate",
            "medium": "Moderate",
            "medium signal": "Moderate",
            "strong": "Strong",
            "strong signal": "Strong",
            "high": "High Signal",
            "high signal": "High Signal",
        }
        return aliases.get(normalized, label)

    @field_validator("strengths", "risks", "suggested_improvements", mode="before")
    @classmethod
    def clean_string_list(cls, value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned[:8]
