"""
shared/embedding_client.py — Text embedding generation.

Source services: context-engine (Server 2) and prompt-enhance (Server 3), both
of which use the NVIDIA embedding API as primary with a local
sentence-transformers (all-MiniLM-L6-v2) fallback.

Primary path: NVIDIA NIM embeddings API (OpenAI-compatible /v1/embeddings),
authenticated with NVIDIA_EMBEDDING_API_KEY (falling back to NVIDIA_API_KEY),
using EMBEDDING_MODEL and producing EMBEDDING_DIMENSION-length vectors.

Fallback path: a lazily loaded sentence-transformers model. Any error talking
to NVIDIA (missing key, network, HTTP, schema) is caught and the fallback is
used instead, so embeddings never hard-fail when a local model is available.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from .settings import settings

logger = logging.getLogger("thinkvelocity.embeddings")

_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1/embeddings"

# Lazily loaded sentence-transformers model (loaded once, reused).
_local_model = None
_local_model_lock = asyncio.Lock()
_LOCAL_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _pad_or_truncate(vector: list[float], dim: int) -> list[float]:
    """Coerce a vector to the configured EMBEDDING_DIMENSION length."""
    if len(vector) == dim:
        return vector
    if len(vector) > dim:
        return vector[:dim]
    return vector + [0.0] * (dim - len(vector))


async def _nvidia_embed(texts: list[str], *, input_type: str = "query") -> list[list[float]]:
    """Call the NVIDIA embeddings API for a batch of texts."""
    api_key = settings.nvidia_embedding_key
    if not api_key:
        raise RuntimeError("No NVIDIA embedding API key configured.")

    payload = {
        "input": texts,
        "model": settings.EMBEDDING_MODEL,
        "input_type": input_type,
        "encoding_format": "float",
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(_NVIDIA_BASE_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    # OpenAI-compatible schema: {"data": [{"embedding": [...], "index": i}, ...]}
    items = sorted(data["data"], key=lambda d: d.get("index", 0))
    return [list(item["embedding"]) for item in items]


async def _get_local_model():
    """Lazily load and cache the local sentence-transformers model."""
    global _local_model
    if _local_model is not None:
        return _local_model
    async with _local_model_lock:
        if _local_model is None:
            from sentence_transformers import SentenceTransformer

            # Blocking load — run off the event loop.
            _local_model = await asyncio.to_thread(
                SentenceTransformer, _LOCAL_MODEL_NAME
            )
            logger.info("embedding_client: loaded local model '%s'", _LOCAL_MODEL_NAME)
    return _local_model


async def _local_embed(texts: list[str]) -> list[list[float]]:
    """Generate embeddings locally with sentence-transformers."""
    model = await _get_local_model()
    vectors = await asyncio.to_thread(
        lambda: model.encode(texts, convert_to_numpy=True).tolist()
    )
    return [list(v) for v in vectors]


async def generate_embeddings_batch(
    texts: list[str],
    *,
    input_type: str = "query",
) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts.

    Tries the NVIDIA API first; on any failure, returns zero vectors so that
    callers (context search, similarity ranking) degrade gracefully without
    blocking on a remote model download that can time out and kill the worker.
    All returned vectors are coerced to EMBEDDING_DIMENSION length.
    """
    if not texts:
        return []

    dim = settings.EMBEDDING_DIMENSION
    try:
        vectors = await _nvidia_embed(texts, input_type=input_type)
        return [_pad_or_truncate(v, dim) for v in vectors]
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "embedding_client: NVIDIA embedding failed (%s); using local fallback",
            exc,
        )
        try:
            vectors = await _local_embed(texts)
            return [_pad_or_truncate(v, dim) for v in vectors]
        except Exception as local_exc:  # noqa: BLE001
            logger.warning(
                "embedding_client: local embedding failed (%s); returning zero vectors",
                local_exc,
            )
            return [[0.0] * dim for _ in texts]


async def generate_embedding(text: str) -> list[float]:
    """Generate a single embedding vector for ``text``."""
    result = await generate_embeddings_batch([text])
    return result[0] if result else []
