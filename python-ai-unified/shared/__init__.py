"""
shared — Infrastructure layer for the unified ThinkVelocity python-ai service.

This package merges the cross-cutting dependencies of three services:
  - python-backend / prompt-enhance (Server 2/3) — Groq pool, DB, Redis, auth.
  - context-engine (Server 2) — embeddings, Node.js backend client.

Public symbols re-exported here are the stable contract that the /ai/* and
/context/* routers integrate against.
"""

from __future__ import annotations

# Configure logging + scrubber as early as possible.
from .logging_config import configure_logging
from .settings import Settings, get_settings, settings
from .groq_client import GroqClientPool, groq_pool
from .embedding_client import generate_embedding, generate_embeddings_batch
from .db import async_session_maker, engine, get_session
from .redis_cache import cache_get, cache_set, rate_limit_check
from .node_client import node_get, node_post
from .auth import verify_token

__all__ = [
    # logging
    "configure_logging",
    # settings
    "Settings",
    "settings",
    "get_settings",
    # groq
    "GroqClientPool",
    "groq_pool",
    # embeddings
    "generate_embedding",
    "generate_embeddings_batch",
    # db
    "engine",
    "async_session_maker",
    "get_session",
    # redis
    "cache_get",
    "cache_set",
    "rate_limit_check",
    # node backend
    "node_post",
    "node_get",
    # auth
    "verify_token",
]
