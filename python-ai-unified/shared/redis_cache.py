"""
shared/redis_cache.py — Async Redis cache + rate limiting helpers.

Source services: python-backend / prompt-enhance (Server 2/3), which use Redis
for response caching and per-key rate limiting on the /ai/* routes. The
context-engine (Server 2) has no Redis dependency.

All helpers degrade gracefully when Redis is unavailable: reads return None,
writes are no-ops, and rate-limit checks fail open (allow the request) so a
Redis outage never takes the whole service down.

Client is created from REDIS_URL (default redis://localhost:6379/0).
"""

from __future__ import annotations

import logging
from typing import Optional

from redis import asyncio as aioredis

from .settings import settings

logger = logging.getLogger("thinkvelocity.cache")

_client: Optional["aioredis.Redis"] = None


def _get_client() -> Optional["aioredis.Redis"]:
    """Lazily create the shared async Redis client."""
    global _client
    if _client is None:
        try:
            _client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis_cache: failed to create client: %s", exc)
            return None
    return _client


def get_redis() -> Optional["aioredis.Redis"]:
    """Public accessor for the shared async Redis client.

    Returns the lazily-created client (or None if it could not be created).
    Used by the app lifespan to attach the client to ``app.state`` and run a
    startup connectivity probe (``await client.ping()``).
    """
    return _get_client()


async def cache_get(key: str) -> Optional[str]:
    """Return the cached string value for ``key``, or None if absent/unavailable."""
    client = _get_client()
    if client is None:
        return None
    try:
        return await client.get(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis_cache: cache_get(%s) failed: %s", key, exc)
        return None


async def cache_set(key: str, value: str, ttl: int = 300) -> bool:
    """Set ``key`` to ``value`` with a TTL (seconds). Returns success as bool."""
    client = _get_client()
    if client is None:
        return False
    try:
        await client.set(key, value, ex=ttl)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis_cache: cache_set(%s) failed: %s", key, exc)
        return False


async def rate_limit_check(key: str, limit: int, window_seconds: int) -> bool:
    """
    Fixed-window rate limiter.

    Increments a counter for ``key`` and applies an expiry of ``window_seconds``
    on first hit. Returns True if the request is allowed (count <= limit),
    False if the limit is exceeded. Fails open (returns True) when Redis is
    unavailable.
    """
    client = _get_client()
    if client is None:
        return True
    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, window_seconds)
        return count <= limit
    except Exception as exc:  # noqa: BLE001
        logger.warning("redis_cache: rate_limit_check(%s) failed: %s", key, exc)
        return True
