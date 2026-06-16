"""/ai/quality/* — prompt quality metrics and analysis.

Source routes (Server 2 core, present on Server 3):
  - GET  /api/v1/quality/metrics            -> /ai/quality/metrics
  - GET  /api/v1/quality/accuracy           -> /ai/quality/accuracy
  - GET  /api/v1/quality/performance        -> /ai/quality/performance (?operation=)
  - GET  /api/v1/quality/mode-distribution  -> /ai/quality/mode-distribution
  - GET  /api/v1/quality/health             -> /ai/quality/health
  - POST /api/v1/quality/analyze-prompt     -> /ai/quality/analyze-prompt

Note: the parent mounts ai_router under /ai, so this sub-router uses prefix
"/quality" to yield the documented /ai/quality/* paths.

Pure in-memory metrics + a Groq-backed analyze-prompt scorer (merge plan §5:
no external deps besides the LLM call for analyze-prompt). The metric stores
here are process-local accumulators; the canonical Server 3 build sources these
from its telemetry pipeline — see RECONCILE.md.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

router = APIRouter(prefix="/quality", tags=["quality"])

# ---------------------------------------------------------------------------
# In-memory metric accumulators (process-local).
# ---------------------------------------------------------------------------
_LATENCIES: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=1000))
_MODE_COUNTS: dict[str, int] = defaultdict(int)
_MODE_CONFIDENCE: dict[str, list[float]] = defaultdict(list)
_ACCURACY: dict[str, dict[str, int]] = {
    "domain": {"correct": 0, "total": 0},
    "intent": {"correct": 0, "total": 0},
}
_STARTED_AT = time.time()


def record_latency(operation: str, seconds: float) -> None:
    """Public hook for other routers to feed latency samples."""
    _LATENCIES[operation].append(seconds)


def record_mode(mode: str, confidence: float | None = None) -> None:
    _MODE_COUNTS[mode] += 1
    if confidence is not None:
        _MODE_CONFIDENCE[mode].append(confidence)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    f = int(k)
    c = min(f + 1, len(ordered) - 1)
    if f == c:
        return ordered[f]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


@router.get("/metrics")
async def quality_metrics():
    """Quality metrics overview. Source: GET /api/v1/quality/metrics."""
    total_modes = sum(_MODE_COUNTS.values())
    total_latency_samples = sum(len(v) for v in _LATENCIES.values())
    return {
        "uptime_seconds": round(time.time() - _STARTED_AT, 2),
        "total_operations": total_latency_samples,
        "total_mode_selections": total_modes,
        "operations_tracked": sorted(_LATENCIES.keys()),
        "accuracy": {
            k: (v["correct"] / v["total"] if v["total"] else None)
            for k, v in _ACCURACY.items()
        },
    }


@router.get("/accuracy")
async def quality_accuracy():
    """Domain/intent classification accuracy. Source: GET /api/v1/quality/accuracy."""
    out: dict[str, Any] = {}
    for key, counts in _ACCURACY.items():
        total = counts["total"]
        out[key] = {
            "correct": counts["correct"],
            "total": total,
            "accuracy": (counts["correct"] / total) if total else None,
        }
    return out


@router.get("/performance")
async def quality_performance(operation: str | None = None):
    """P50/P95/P99 latency stats. Source: GET /api/v1/quality/performance?operation=."""
    operations = [operation] if operation else list(_LATENCIES.keys())
    stats: dict[str, Any] = {}
    for op in operations:
        samples = list(_LATENCIES.get(op, []))
        stats[op] = {
            "count": len(samples),
            "p50": round(_percentile(samples, 0.50), 4),
            "p95": round(_percentile(samples, 0.95), 4),
            "p99": round(_percentile(samples, 0.99), 4),
            "max": round(max(samples), 4) if samples else 0.0,
        }
    return {"operation": operation, "performance": stats}


@router.get("/mode-distribution")
async def quality_mode_distribution():
    """Mode selection frequency and confidence. Source: GET /api/v1/quality/mode-distribution."""
    total = sum(_MODE_COUNTS.values()) or 0
    distribution: dict[str, Any] = {}
    for mode, count in _MODE_COUNTS.items():
        confidences = _MODE_CONFIDENCE.get(mode, [])
        distribution[mode] = {
            "count": count,
            "frequency": (count / total) if total else 0.0,
            "avg_confidence": (sum(confidences) / len(confidences)) if confidences else None,
        }
    return {"total_selections": total, "distribution": distribution}


@router.get("/health")
async def quality_health():
    """Quality subsystem health. Source: GET /api/v1/quality/health."""
    sample_count = sum(len(v) for v in _LATENCIES.values())
    if sample_count == 0:
        status = "healthy"  # no traffic yet is not unhealthy
    else:
        status = "healthy"
    return {
        "status": status,
        "uptime_seconds": round(time.time() - _STARTED_AT, 2),
        "samples": sample_count,
    }


class AnalyzePromptRequest(BaseModel):
    prompt: str

    @field_validator("prompt")
    @classmethod
    def prompt_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be empty")
        if len(value) > 10_000:
            raise ValueError("prompt must not exceed 10,000 characters")
        return value


@router.post("/analyze-prompt")
async def analyze_prompt(request: AnalyzePromptRequest):
    """Classify a prompt's domain/intent for the consumer extension.

    Source: POST /api/v1/quality/analyze-prompt on prompt-enhance (Server 3).

    PER D-019: this mirrors the canonical, extension-proven classifier in
    ``api/extension_bridge.ext_quality_analyze`` (the same handler the extension
    hits via /dev/test/api/v1/quality/analyze-prompt) — a fast, deterministic
    keyword classifier returning ``{status, metadata}``. It deliberately does
    NOT make an LLM call: the extension's analyze-prompt is a synchronous,
    pre-enhance hint used for UI routing, so a Groq round-trip would change the
    proven latency/contract. See RECONCILE.md if the deployed Server 3 build is
    found to also surface clarity/specificity scores on this route.
    """
    text = request.prompt.lower()
    if any(w in text for w in ("code", "function", "class", "build", "implement", "develop", "debug")):
        domain, intent = "software_development", "implementation"
    elif any(w in text for w in ("write", "essay", "blog", "article", "copy", "draft")):
        domain, intent = "content_creation", "writing"
    elif any(w in text for w in ("data", "analyze", "research", "study", "insight", "report")):
        domain, intent = "research_analysis", "analysis"
    elif any(w in text for w in ("design", "ui", "ux", "image", "visual", "logo", "create")):
        domain, intent = "design", "creation"
    else:
        domain, intent = "general", "task_completion"

    return {
        "status": "success",
        "metadata": {
            "domain": domain,
            "intent": intent,
            "intent_description": f"User wants to accomplish a {domain.replace('_', ' ')} task.",
        },
    }
