"""
Pipeline contracts — Pydantic schemas ONLY. No logic, no imports from pipeline modules.

Stage flow:
  EnhancementRequest → [pre_enhancement] → EnhancementContext
  EnhancementContext → [enhancement]     → EnhancementOutput
  (ctx, out, signal) → [post_enhancement] → stored
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContextFragment(BaseModel):
    content: str
    relevance_score: float
    source: str


class EnhancementRequest(BaseModel):
    prompt: str
    user_id: str
    session_id: str | None = None
    target_ai: str | None = None
    mode_hint: str | None = None
    prior_ai_response: str | None = None


class EnhancementContext(BaseModel):
    """Stage 1 output. Frozen — never mutated after build_context() returns."""
    model_config = ConfigDict(frozen=True)

    request_id: str
    original_prompt: str
    intent_state: Literal["certain", "exploring"]
    user_certainty: Literal["exploring", "executing", "mixed"]
    mode_resolved: str
    mode_was_overridden: bool
    target_ai: str | None
    context_fragments: list[ContextFragment]
    conversation_signal: Literal["new", "continuation", "correction", "retry"]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    pre_enhancement_latency_ms: float


class EnhancementOutput(BaseModel):
    """Stage 2 output. Includes all fields needed for observability and G-03 audit."""
    request_id: str
    enhanced_prompt: str
    template_used: str
    context_fragments_used: list[ContextFragment]
    context_fragments_dropped: list[ContextFragment]
    model_used: str
    token_count_in: int
    token_count_out: int
    enhancement_latency_ms: float
    target_ai_optimized: bool = False
    user_certainty: Literal["exploring", "executing", "mixed"] | None = None


class FeedbackSignal(BaseModel):
    request_id: str
    user_action: Literal["accepted", "edited", "discarded", "timeout"]
    edit_distance: float | None = None
