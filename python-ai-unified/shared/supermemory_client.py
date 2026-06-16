"""
shared/supermemory_client.py — Supermemory.ai API client.

Provides async helpers for adding, searching, listing, and deleting memories.
All calls are fire-and-forget safe: callers should wrap in asyncio.create_task()
and never await them on the critical path.

API base: https://api.supermemory.ai/v3
  POST   /documents          — add a memory
  POST   /search             — semantic search (field: "q")
  DELETE /documents/{id}     — delete a memory by ID

Enabled only when SUPERMEMORY_API_KEY is set. All functions degrade silently
(log warning, return empty) when the key is missing or the API is unreachable.

SECURITY (fixed 2026-06-16): isolation between users is done via Supermemory's
`containerTags` field, NOT a top-level `userId` field. The original
implementation sent `userId` in both /documents and /search payloads —
Supermemory's API accepts that field but does not use it to scope search
results, meaning every user's query searched and could return EVERY other
user's stored memories (verified live: a query with a never-used random
user_id returned real production users' memories). containerTags is the
correct, verified-isolating mechanism — confirmed by a live two-user test
where each user's search only ever returned their own tagged content.

Memories written before this fix have no containerTags and are therefore
unreachable by any containerTags-scoped search going forward (effectively
quarantined, not deleted) — this stops the leak immediately without needing
a backfill, though it also means pre-fix memories are now orphaned data.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger("thinkvelocity.supermemory")

_BASE = "https://api.supermemory.ai/v3"
_TIMEOUT = 10.0


def _get_key() -> str:
    from .settings import get_settings
    return get_settings().SUPERMEMORY_API_KEY


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_key()}",
        "Content-Type": "application/json",
    }


async def add_memory(
    user_id: str,
    content: str,
    metadata: Optional[dict] = None,
) -> Optional[str]:
    """
    Push a memory to Supermemory for the given user.

    Returns the Supermemory document ID on success, None on any failure.
    Designed to be called via asyncio.create_task() — never blocks the caller.
    """
    key = _get_key()
    if not key:
        return None
    if not content or not user_id:
        return None

    # containerTags is what actually isolates this memory to this user on
    # search — see module docstring. userId is kept in metadata for
    # observability/debugging only; it is NOT a search filter.
    payload = {"content": content, "containerTags": [user_id]}
    meta = dict(metadata or {})
    meta.setdefault("user_id", user_id)
    payload["metadata"] = meta

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(f"{_BASE}/documents", json=payload, headers=_headers())
            resp.raise_for_status()
            data = resp.json()
            doc_id = data.get("id")
            logger.info("supermemory: stored memory user=%s doc_id=%s", user_id, doc_id)
            return doc_id
    except Exception as exc:
        logger.warning("supermemory: add_memory failed user=%s — %s", user_id, exc)
        return None


async def search_memories(
    user_id: str,
    query: str,
    limit: int = 3,
) -> list[str]:
    """
    Search Supermemory for memories relevant to the query for this user.

    Returns a flat list of content strings (chunks), ordered by relevance.
    Returns [] on any failure — never raises.
    """
    key = _get_key()
    if not key or not query or not user_id:
        return []

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE}/search",
                # containerTags scopes results to this user only — see module
                # docstring for why userId alone does not isolate searches.
                json={"q": query, "containerTags": [user_id], "limit": limit},
                headers=_headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results") or []
        snippets: list[str] = []
        for r in results:
            for chunk in r.get("chunks") or []:
                text = (chunk.get("content") or "").strip()
                if text:
                    snippets.append(text)

        logger.debug(
            "supermemory: search user=%s query='%s' hits=%d",
            user_id, query[:60], len(snippets),
        )
        return snippets[:limit]
    except Exception as exc:
        logger.warning("supermemory: search_memories failed user=%s — %s", user_id, exc)
        return []


async def delete_memory(document_id: str) -> bool:
    """
    Delete a memory by Supermemory document ID.

    Returns True on success, False on any failure.
    """
    key = _get_key()
    if not key or not document_id:
        return False

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.delete(
                f"{_BASE}/documents/{document_id}",
                headers=_headers(),
            )
            resp.raise_for_status()
            logger.info("supermemory: deleted doc_id=%s", document_id)
            return True
    except Exception as exc:
        logger.warning("supermemory: delete_memory failed doc_id=%s — %s", document_id, exc)
        return False
