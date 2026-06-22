"""In-memory brief queue with optional DB persistence.

Holds classified content briefs that cleared the product_relevance threshold.
Capped at 500 entries (deque auto-evicts oldest). DB writes are best-effort —
if the content_briefs table doesn't exist yet, the queue keeps operating
in-memory without error.
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

_THRESHOLD = 0.6
_MAXLEN = 500


class BriefQueue:
    def __init__(self) -> None:
        self._q: deque[dict[str, Any]] = deque(maxlen=_MAXLEN)

    def push(self, brief: dict[str, Any]) -> None:
        """Enqueue only if product_relevance meets the threshold."""
        if (brief.get("product_relevance") or 0.0) < _THRESHOLD:
            return
        self._q.append(brief)
        self._persist_async(brief)

    def pop_all(self) -> list[dict[str, Any]]:
        items = list(self._q)
        self._q.clear()
        return items

    def peek(self, limit: int = 50) -> list[dict[str, Any]]:
        return list(self._q)[:limit]

    def size(self) -> int:
        return len(self._q)

    def _persist_async(self, brief: dict[str, Any]) -> None:
        """Fire-and-forget DB write. Import asyncio lazily so this module
        stays usable in sync test contexts."""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._db_write(brief))
        except RuntimeError:
            pass

    async def _db_write(self, brief: dict[str, Any]) -> None:
        try:
            from shared.trace_db import _pool

            if _pool is None:
                return
            async with _pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO content_briefs
                        (icp_category, problem_tags, stage, emotion,
                         product_relevance, content_brief, confidence, signal_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    brief.get("icp_category"),
                    brief.get("problem_tags") or [],
                    brief.get("stage"),
                    brief.get("emotion"),
                    brief.get("product_relevance"),
                    brief.get("content_brief"),
                    brief.get("confidence"),
                    brief.get("signal_id"),
                )
        except Exception as exc:  # noqa: BLE001 — table may not exist yet
            logger.debug("brief_queue DB write skipped: %s", exc)


# Module-level singleton shared across the process lifetime.
brief_queue = BriefQueue()
