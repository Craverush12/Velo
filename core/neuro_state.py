from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.contracts import PromptMode, TargetAI, normalize_prompt_mode, normalize_target_ai


NEURO_STATE_SCHEMA_VERSION = "2026-05-22.neuro-orchestrator.v1"

WorkflowMode = Literal["research", "build", "media"]
ActionKind = Literal[
    "enhance_now",
    "refine_prepare",
    "ask_clarifying_question",
    "request_upload",
    "suggest_connector",
    "run_compare",
    "create_skill",
    "handoff_agentic_work",
    "wait_for_user",
]
QuestionAnswerType = Literal["short_text", "long_text", "single_select", "multi_select"]
MemoryCandidateType = Literal[
    "output_style",
    "domain_interest",
    "tool_preference",
    "format_preference",
    "constraint_preference",
    "workflow_pattern",
]


def normalize_workflow_mode(value: str | None) -> WorkflowMode:
    if value is None:
        return "research"
    normalized = value.strip().lower().replace("-", "_")
    aliases = {
        "normal": "research",
        "default": "research",
        "caveman": "build",
        "fast": "build",
        "fast_build": "build",
        "builder": "build",
        "creative": "media",
        "image": "media",
        "design": "media",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"research", "build", "media"}:
        raise ValueError("selected_mode must be one of: research, build, media")
    return normalized  # type: ignore[return-value]


def workflow_mode_to_prompt_mode(mode: str | None) -> PromptMode:
    normalized = normalize_workflow_mode(mode)
    if normalized == "build":
        return "fast_build"
    return normalized


class NeuroAttachmentContext(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    name: str
    media_type: str = ""
    extracted_text: str = ""
    summary: str = ""

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: Any) -> str:
        value = str(value or "").strip()
        return value[:160] or "attachment"

    @field_validator("media_type", "extracted_text", "summary", mode="before")
    @classmethod
    def clean_optional_text(cls, value: Any) -> str:
        return str(value or "").strip()[:5000]


class NeuroTriggerPolicy(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ask_user: bool = False
    enhance_now: bool = True
    retrieve_context: bool = False
    use_uploads: bool = False
    suggest_connector: bool = False
    run_comparison: bool = False
    write_memory: bool = False
    reason: str = "Act with the available context unless a missing detail materially changes the output."

    @field_validator("reason", mode="before")
    @classmethod
    def clean_reason(cls, value: Any) -> str:
        text = str(value or "").strip()
        return text[:300] or "Use the smallest action that helps the user reach the goal faster."


class NeuroMemoryCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: MemoryCandidateType
    key: str
    value: str
    evidence: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    persistence: Literal["candidate", "suggest", "auto"] = "candidate"

    @field_validator("key", "value", "evidence", mode="before")
    @classmethod
    def clean_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("memory candidate text must not be empty")
        return text[:500]


class NeuroActionCard(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    description: str
    action: ActionKind
    priority: int = Field(default=2, ge=1, le=5)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "title", "description", mode="before")
    @classmethod
    def clean_required_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("action card text must not be empty")
        return text[:300]


class RefineQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    question: str
    why_it_matters: str
    answer_type: QuestionAnswerType = "short_text"
    options: list[str] = Field(default_factory=list)
    priority: int = Field(default=1, ge=1, le=3)
    intent_gap: str = "missing_context"

    @field_validator("id", "question", "why_it_matters", "intent_gap", mode="before")
    @classmethod
    def clean_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("question fields must not be empty")
        return text[:500]

    @field_validator("options", mode="before")
    @classmethod
    def clean_options(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [str(item).strip()[:120] for item in value if str(item).strip()][:6]


class NeuroGoalState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = NEURO_STATE_SCHEMA_VERSION
    user_final_goal: str
    immediate_task: str
    success_definition: str
    selected_mode: WorkflowMode = "research"
    prompt_mode: PromptMode = "research"
    target_ai: TargetAI | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    can_act_now: bool = True
    blocking_gaps: list[str] = Field(default_factory=list)
    fastest_next_action: str
    context_needs: list[str] = Field(default_factory=list)
    mode_execution_hints: list[str] = Field(default_factory=list)
    trigger_policy: NeuroTriggerPolicy = Field(default_factory=NeuroTriggerPolicy)
    product_signals: list[str] = Field(default_factory=list)
    memory_candidates: list[NeuroMemoryCandidate] = Field(default_factory=list)
    profile_update_candidates: list[NeuroMemoryCandidate] = Field(default_factory=list)

    @field_validator("selected_mode", mode="before")
    @classmethod
    def valid_selected_mode(cls, value: str | None) -> WorkflowMode:
        return normalize_workflow_mode(value)

    @field_validator("prompt_mode", mode="before")
    @classmethod
    def valid_prompt_mode(cls, value: str | None) -> str:
        return normalize_prompt_mode(value)

    @field_validator("target_ai", mode="before")
    @classmethod
    def valid_target_ai(cls, value: str | None) -> str | None:
        return normalize_target_ai(value)

    @field_validator("user_final_goal", "immediate_task", "success_definition", "fastest_next_action", mode="before")
    @classmethod
    def clean_required_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("required Neuro goal state text must not be empty")
        return text[:1000]

    @field_validator("blocking_gaps", "context_needs", "mode_execution_hints", "product_signals", mode="before")
    @classmethod
    def clean_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [str(item).strip()[:300] for item in value if str(item).strip()][:8]

    @model_validator(mode="after")
    def align_prompt_mode(self) -> "NeuroGoalState":
        expected = workflow_mode_to_prompt_mode(self.selected_mode)
        if self.prompt_mode in ("normal", "caveman"):
            self.prompt_mode = expected
        return self


class NeuroDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = NEURO_STATE_SCHEMA_VERSION
    action_decision: ActionKind
    rationale: str
    can_act_now: bool = True
    context_needs: list[str] = Field(default_factory=list)
    next_step_label: str
    execution_hints: list[str] = Field(default_factory=list)
    action_cards: list[NeuroActionCard] = Field(default_factory=list)
    memory_candidates: list[NeuroMemoryCandidate] = Field(default_factory=list)
    profile_update_candidates: list[NeuroMemoryCandidate] = Field(default_factory=list)

    @field_validator("rationale", "next_step_label", mode="before")
    @classmethod
    def clean_required_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("decision text must not be empty")
        return text[:500]

    @field_validator("context_needs", "execution_hints", mode="before")
    @classmethod
    def clean_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [str(item).strip()[:300] for item in value if str(item).strip()][:8]


class RefinePrepareResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: str = NEURO_STATE_SCHEMA_VERSION
    questions: list[RefineQuestion] = Field(default_factory=list, max_length=3)
    context_patterns: list[str] = Field(default_factory=list)
    first_pass_enhancement: str | None = None
    neuro_state: NeuroGoalState
    decision: NeuroDecision
    memory_candidates: list[NeuroMemoryCandidate] = Field(default_factory=list)
    profile_update_candidates: list[NeuroMemoryCandidate] = Field(default_factory=list)

    @field_validator("context_patterns", mode="before")
    @classmethod
    def clean_context_patterns(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [str(item).strip()[:300] for item in value if str(item).strip()][:6]

    @field_validator("first_pass_enhancement", mode="before")
    @classmethod
    def clean_optional_prompt(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text[:8000] or None
