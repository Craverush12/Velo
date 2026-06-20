"""
shared/groq_client.py — Shared Groq client with API-key pool rotation.

Source service: python-backend / prompt-enhance (Server 2/3), which maintain a
key-rotation pool across CHATGROQ_API_KEY_1/2/3 (falling back to GROQ_API_KEY),
rotating after GROQ_REQUESTS_PER_KEY requests per key.

Standardized on the groq SDK 1.x client API (Groq / AsyncGroq with
``.chat.completions.create``), mirroring the working pattern in core/llm.py.

Per the project rule: when a JSON object is expected, callers pass
``response_format={"type": "json_object"}`` (or use the json=True convenience).
"""

from __future__ import annotations

import threading
from typing import Any, AsyncGenerator, Iterable, Optional

from groq import AsyncGroq, Groq

from .settings import settings


class GroqClientPool:
    """
    Thread-safe round-robin pool over the configured Groq API keys.

    A single key is used for ``GROQ_REQUESTS_PER_KEY`` requests before the pool
    advances to the next key. Sync (:class:`groq.Groq`) and async
    (:class:`groq.AsyncGroq`) clients are lazily created and cached per key.
    """

    def __init__(self) -> None:
        self._keys: list[str] = settings.groq_keys
        self._requests_per_key: int = max(1, int(settings.GROQ_REQUESTS_PER_KEY))
        self._default_model: str = settings.GROQ_MODEL
        self._timeout: int = int(settings.GROQ_TIMEOUT)

        self._lock = threading.Lock()
        self._index: int = 0
        self._used_on_current: int = 0

        self._sync_clients: dict[str, Groq] = {}
        self._async_clients: dict[str, AsyncGroq] = {}

    # ── Key selection ─────────────────────────────────────────────────────────
    def _next_key(self) -> str:
        """Return the next API key, advancing the round-robin counter.

        Raises:
            RuntimeError: if no Groq API keys are configured.
        """
        if not self._keys:
            raise RuntimeError(
                "No Groq API keys configured (set CHATGROQ_API_KEY_1/2/3 or GROQ_API_KEY)."
            )
        with self._lock:
            key = self._keys[self._index]
            self._used_on_current += 1
            if self._used_on_current >= self._requests_per_key:
                self._used_on_current = 0
                self._index = (self._index + 1) % len(self._keys)
            return key

    def _sync_client(self, key: str) -> Groq:
        with self._lock:
            client = self._sync_clients.get(key)
            if client is None:
                client = Groq(api_key=key, timeout=self._timeout)
                self._sync_clients[key] = client
            return client

    def _async_client(self, key: str) -> AsyncGroq:
        with self._lock:
            client = self._async_clients.get(key)
            if client is None:
                client = AsyncGroq(api_key=key, timeout=self._timeout)
                self._async_clients[key] = client
            return client

    # ── Public API ────────────────────────────────────────────────────────────
    def chat(
        self,
        messages: Iterable[dict[str, Any]],
        model: Optional[str] = None,
        response_format: Optional[dict[str, Any]] = None,
        temperature: float = 0.7,
        stream: bool = False,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Any:
        """Synchronous chat completion.

        Returns the raw groq response object (or a streaming iterator when
        ``stream=True``). ``response_format`` is forwarded only when provided.
        """
        key = self._next_key()
        client = self._sync_client(key)
        params: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            **kwargs,
        }
        if response_format is not None:
            params["response_format"] = response_format
        return client.chat.completions.create(**params)

    async def async_chat(
        self,
        messages: Iterable[dict[str, Any]],
        model: Optional[str] = None,
        response_format: Optional[dict[str, Any]] = None,
        temperature: float = 0.7,
        stream: bool = False,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> Any:
        """Asynchronous chat completion using :class:`groq.AsyncGroq`.

        Returns the raw response object (or an async streaming iterator when
        ``stream=True``).
        """
        key = self._next_key()
        client = self._async_client(key)
        params: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            **kwargs,
        }
        if response_format is not None:
            params["response_format"] = response_format
        return await client.chat.completions.create(**params)

    async def stream_chat(
        self,
        messages: Iterable[dict[str, Any]],
        model: Optional[str] = None,
        response_format: Optional[dict[str, Any]] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """Async generator yielding text content chunks, suitable for SSE.

        Each yielded value is the incremental ``delta.content`` string of a
        streamed completion.
        """
        key = self._next_key()
        client = self._async_client(key)
        params: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }
        if response_format is not None:
            params["response_format"] = response_format

        stream = await client.chat.completions.create(**params)
        async for chunk in stream:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                yield content


# Module-level singleton.
groq_pool = GroqClientPool()
