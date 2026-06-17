"""Prompt trace analytics endpoints for the admin dashboard.

Auth: Bearer token via PROMPT_ANALYTICS_API_TOKEN env var (server-to-server only).
No dependency on the legacy core.admin_auth or storage.admin_store modules.
"""

from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from shared.prompt_trace_store import PromptTraceStore, get_default_store

router = APIRouter(prefix="/admin/api", tags=["admin-analytics"])


def _get_trace_store() -> PromptTraceStore:
    return get_default_store()


def _require_bearer(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    configured = os.getenv("PROMPT_ANALYTICS_API_TOKEN", "").strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Analytics token not configured")
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token.strip(), configured):
        raise HTTPException(status_code=401, detail="Invalid analytics token")
    return {"auth_type": "bearer"}


@router.get("/prompt-traces")
def list_traces(
    flow: str = "",
    status: str = "",
    user_id: str = "",
    prompt_mode: str = "",
    search: str = "",
    page: int = 1,
    page_size: int = 25,
    include_payload: bool = False,
    trace_store: PromptTraceStore = Depends(_get_trace_store),
    _auth: dict = Depends(_require_bearer),
):
    return trace_store.list_traces(
        flow=flow,
        status=status,
        user_id=user_id,
        prompt_mode=prompt_mode,
        search=search,
        page=page,
        page_size=page_size,
        include_payload=include_payload,
    )


@router.get("/prompt-traces/{trace_id}/diff")
def trace_diff(
    trace_id: str,
    trace_store: PromptTraceStore = Depends(_get_trace_store),
    _auth: dict = Depends(_require_bearer),
):
    diff = trace_store.diff(trace_id)
    if diff is None:
        raise HTTPException(status_code=404, detail="Prompt trace not found")
    return diff


@router.get("/prompt-traces/{trace_id}")
def trace_detail(
    trace_id: str,
    trace_store: PromptTraceStore = Depends(_get_trace_store),
    _auth: dict = Depends(_require_bearer),
):
    trace = trace_store.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Prompt trace not found")
    return {"trace": trace}


@router.get("/prompt-metrics")
def prompt_metrics(
    days: int | None = None,
    trace_store: PromptTraceStore = Depends(_get_trace_store),
    _auth: dict = Depends(_require_bearer),
):
    return {"metrics": trace_store.metrics(days=days)}
