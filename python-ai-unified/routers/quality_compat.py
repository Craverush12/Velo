"""/api/v1/quality/* compatibility routes.

The canonical unified service exposes quality APIs under /ai/quality/*. These
aliases preserve older clients that still call /api/v1/quality/* directly.
"""

from __future__ import annotations

from fastapi import APIRouter

from routers.ai.quality import (
    analyze_prompt,
    quality_accuracy,
    quality_health,
    quality_metrics,
    quality_mode_distribution,
    quality_performance,
)

router = APIRouter(prefix="/api/v1/quality", tags=["quality-compat"])

router.add_api_route("/metrics", quality_metrics, methods=["GET"])
router.add_api_route("/accuracy", quality_accuracy, methods=["GET"])
router.add_api_route("/performance", quality_performance, methods=["GET"])
router.add_api_route("/mode-distribution", quality_mode_distribution, methods=["GET"])
router.add_api_route("/health", quality_health, methods=["GET"])
router.add_api_route("/analyze-prompt", analyze_prompt, methods=["POST"])
