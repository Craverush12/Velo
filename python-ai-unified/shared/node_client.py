"""
shared/node_client.py — Async HTTP client for the Node.js backend.

Source service: context-engine (Server 2), which proxies data persistence
through a Node.js backend (NODE_BACKEND_URL) instead of touching PostgreSQL
directly. Used by the /context/* routes (process-context, process-essence,
user profile, etc.) in the unified app.

A single shared httpx.AsyncClient is lazily created and reused. ``aclose`` is
provided for the FastAPI lifespan shutdown.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from .settings import settings

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    """Lazily create the shared httpx client bound to NODE_BACKEND_URL.

    Raises:
        RuntimeError: if NODE_BACKEND_URL is not configured.
    """
    global _client
    base_url = (settings.NODE_BACKEND_URL or "").strip()
    if not base_url:
        raise RuntimeError(
            "NODE_BACKEND_URL is not configured: cannot reach the Node.js backend."
        )
    if _client is None:
        _client = httpx.AsyncClient(base_url=base_url, timeout=30.0)
    return _client


async def node_post(path: str, json: Optional[dict[str, Any]] = None) -> Any:
    """POST JSON to the Node.js backend and return the parsed JSON response."""
    client = _get_client()
    resp = await client.post(path, json=json)
    resp.raise_for_status()
    return resp.json()


async def node_get(path: str, params: Optional[dict[str, Any]] = None) -> Any:
    """GET from the Node.js backend and return the parsed JSON response."""
    client = _get_client()
    resp = await client.get(path, params=params)
    resp.raise_for_status()
    return resp.json()


async def aclose() -> None:
    """Close the shared client (call from the FastAPI lifespan shutdown)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
