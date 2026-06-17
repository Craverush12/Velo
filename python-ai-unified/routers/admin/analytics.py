"""Prompt trace analytics endpoints for the admin dashboard.

Auth: Bearer token via PROMPT_ANALYTICS_API_TOKEN env var (server-to-server only).
No dependency on the legacy core.admin_auth or storage.admin_store modules.
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.prompt_trace_store import PromptTraceStore, get_default_store

logger = logging.getLogger("thinkvelocity.admin.analytics")

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


# ---------------------------------------------------------------------------
# DB-backed endpoints (Items 1 & 2 from 2026-06-17 reviewer analysis)
# ---------------------------------------------------------------------------

async def _get_db_session():
    """Yield an async SQLAlchemy session; 503 if DB is unavailable."""
    try:
        from shared.db import async_session_maker
        if async_session_maker is None:
            raise HTTPException(status_code=503, detail="Database not configured")
        async with async_session_maker() as session:
            yield session
    except ImportError:
        raise HTTPException(status_code=503, detail="Database module unavailable")


@router.get("/enhance-health")
async def enhance_health(
    weeks: int = 8,
    db: AsyncSession = Depends(_get_db_session),
    _auth: dict = Depends(_require_bearer),
):
    """Weekly behavioral metrics from save_enhance_prompt.

    Returns per-week: total_enhances, thumbs_up, thumbs_down, re_enhance_rate_pct,
    first_attempt_acceptance_pct.

    re_enhance_rate = conversations with more than one enhance / total conversations.
    first_attempt_acceptance = conversations with exactly one enhance / total conversations.
    """
    from sqlalchemy import text as _text

    sql = _text("""
        WITH weekly AS (
            SELECT
                date_trunc('week', created_at) AS week_start,
                conversation_id,
                COUNT(*) AS enhances_in_convo,
                SUM(CASE WHEN feedback = 1 THEN 1 ELSE 0 END) AS thumbs_up_in_convo,
                SUM(CASE WHEN feedback = -1 THEN 1 ELSE 0 END) AS thumbs_down_in_convo
            FROM save_enhance_prompt
            WHERE created_at >= now() - (:weeks * INTERVAL '1 week')
            GROUP BY date_trunc('week', created_at), conversation_id
        )
        SELECT
            week_start,
            COUNT(*) AS total_conversations,
            SUM(enhances_in_convo) AS total_enhances,
            SUM(thumbs_up_in_convo) AS thumbs_up,
            SUM(thumbs_down_in_convo) AS thumbs_down,
            ROUND(
                100.0 * SUM(CASE WHEN enhances_in_convo > 1 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                2
            ) AS re_enhance_rate_pct,
            ROUND(
                100.0 * SUM(CASE WHEN enhances_in_convo = 1 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0),
                2
            ) AS first_attempt_acceptance_pct
        FROM weekly
        GROUP BY week_start
        ORDER BY week_start DESC
    """)

    try:
        result = await db.execute(sql, {"weeks": weeks})
        rows = result.mappings().all()
        return {
            "weeks_requested": weeks,
            "rows": [dict(r) for r in rows],
        }
    except Exception as exc:
        logger.error("enhance-health query failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


@router.get("/enhance-pairs")
async def enhance_pairs(
    user_id: str = "",
    days: int = 30,
    min_raw_length: int = 0,
    page: int = 1,
    page_size: int = 25,
    db: AsyncSession = Depends(_get_db_session),
    _auth: dict = Depends(_require_bearer),
):
    """Raw + enhanced prompt pairs joined from user_prompts + save_enhance_prompt.

    Joins on conversation_id. Filters by user_id (optional), days back, and
    minimum raw prompt length. Returns paginated pairs.
    """
    from sqlalchemy import text as _text

    if page < 1:
        page = 1
    if page_size < 1 or page_size > 200:
        page_size = 25
    offset = (page - 1) * page_size

    filters = ["sep.created_at >= now() - (:days * INTERVAL '1 day')"]
    params: dict[str, Any] = {
        "days": days,
        "min_raw_length": min_raw_length,
        "limit": page_size,
        "offset": offset,
    }

    if user_id:
        filters.append("sep.user_id = :user_id")
        params["user_id"] = user_id

    if min_raw_length > 0:
        filters.append("length(up.user_prompt) >= :min_raw_length")

    where_clause = " AND ".join(filters)

    count_sql = _text(f"""
        SELECT COUNT(*)
        FROM save_enhance_prompt sep
        JOIN user_prompts up ON up.conversation_id = sep.conversation_id
        WHERE {where_clause}
    """)

    data_sql = _text(f"""
        SELECT
            sep.id,
            sep.user_id,
            sep.conversation_id,
            up.user_prompt AS raw_prompt,
            sep.enhanced_prompt,
            sep.domain,
            sep.mode,
            sep.feedback,
            sep.created_at
        FROM save_enhance_prompt sep
        JOIN user_prompts up ON up.conversation_id = sep.conversation_id
        WHERE {where_clause}
        ORDER BY sep.created_at DESC
        LIMIT :limit OFFSET :offset
    """)

    try:
        total_result = await db.execute(count_sql, params)
        total = total_result.scalar() or 0

        data_result = await db.execute(data_sql, params)
        rows = data_result.mappings().all()

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": (total + page_size - 1) // page_size if total else 0,
            "pairs": [dict(r) for r in rows],
        }
    except Exception as exc:
        logger.error("enhance-pairs query failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")
