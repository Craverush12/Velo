"""Intel router — ICP classification and content brief management.

Auth: X-Admin-Token header matching PROMPT_ANALYTICS_API_TOKEN env var.
Mirrors the token-check pattern in routers/admin/analytics.py but uses a
dedicated header so automation scripts don't need to construct a Bearer line.
"""
from __future__ import annotations

import hmac
import logging
import os
from typing import Annotated, Any  # Annotated used for Header injection

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from routers.intel.icp_classifier import classify_signal
from shared.brief_queue import brief_queue

logger = logging.getLogger(__name__)

router = APIRouter(tags=["intel"])


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def _require_token(
    x_admin_token: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    configured = os.getenv("PROMPT_ANALYTICS_API_TOKEN", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Admin token not configured")
    if not x_admin_token:
        raise HTTPException(status_code=401, detail="X-Admin-Token header required")
    if not hmac.compare_digest(x_admin_token.strip(), configured):
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return {"auth_type": "token"}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SignalItem(BaseModel):
    title: str = ""
    text: str = ""
    url: str = ""
    source: str = ""
    source_score: int = 0
    signal_id: str | None = None


class ClassifyRequest(BaseModel):
    signals: list[SignalItem] = Field(default_factory=list, max_length=20)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/classify")
async def classify_signals(
    body: ClassifyRequest,
    _auth: dict = Depends(_require_token),
) -> dict[str, Any]:
    """Classify up to 20 content signals. High-relevance results auto-queue."""
    results = []
    for item in body.signals:
        classified = await classify_signal(item.model_dump(exclude_none=True))
        brief_queue.push(classified)
        results.append(classified)
    return {"results": results}


@router.get("/briefs")
def get_briefs(_auth: dict = Depends(_require_token)) -> dict[str, Any]:
    """Return current queue contents without draining."""
    return {"briefs": brief_queue.peek(limit=50), "total": brief_queue.size()}


@router.delete("/briefs")
def drain_briefs(_auth: dict = Depends(_require_token)) -> dict[str, Any]:
    """Drain and return all queued briefs."""
    items = brief_queue.pop_all()
    return {"drained": items, "count": len(items)}
