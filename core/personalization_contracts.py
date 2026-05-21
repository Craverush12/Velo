from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.contracts import normalize_target_ai


PERSONALIZATION_SCHEMA_VERSION = "2026-05-21.personalization.v1"


class PersonalizationPreferences(BaseModel):
    model_config = ConfigDict(extra="ignore")

    output_style: Literal["concise", "balanced", "detailed"] = "balanced"
    expertise_level: Literal["beginner", "intermediate", "senior", "expert"] = "intermediate"
    preferred_tools: list[str] = Field(default_factory=list)
    industry: str = ""
    tone: str = ""
    default_target_ai: str = ""
    format_preferences: list[str] = Field(default_factory=list)
    must_include: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    examples_preference: Literal["none", "only_when_useful", "always", "balanced"] = "balanced"
    personalization_source: Literal["manual", "ai_extracted"] = "ai_extracted"

    @field_validator(
        "preferred_tools",
        "format_preferences",
        "must_include",
        "avoid",
        mode="before",
    )
    @classmethod
    def clean_string_list(cls, value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned[:12]

    @field_validator("industry", "tone", mode="before")
    @classmethod
    def clean_text(cls, value) -> str:
        return "" if value is None else str(value).strip()[:200]

    @field_validator("default_target_ai", mode="before")
    @classmethod
    def clean_target_ai(cls, value) -> str:
        normalized = normalize_target_ai(value)
        return normalized or ""


class PersonalizationExtractResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = PERSONALIZATION_SCHEMA_VERSION
    preferences: PersonalizationPreferences
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def summary_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("summary must not be empty")
        return value
