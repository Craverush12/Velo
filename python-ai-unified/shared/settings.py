"""
shared/settings.py — Unified Pydantic settings for the merged python-ai service.

Source services:
  - python-backend / prompt-enhance (Server 2/3) — the /ai/* router env vars.
  - context-engine (Server 2) — the /context/* router env vars.

This module merges the FULL superset of environment variables documented in
docs/python-ai-merge-plan.md §3. Every field is optional with a sane default so
the package imports cleanly even with zero environment configured (local dev).

AWS Secrets Manager integration mirrors the existing pattern in
configs/secrets/python/: when AWS_REGION is set we call the shared
``init_secrets`` loader at import time, which injects SM values into os.environ
WITHOUT overwriting variables already present. Pydantic then reads the merged
environment. If the loader cannot be imported (deployed in isolation) we degrade
gracefully and read os.environ / a local .env directly.

Supports pydantic v2 (pydantic-settings) and falls back to pydantic v1.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

# ── Detect pydantic version ──────────────────────────────────────────────────
try:
    from pydantic import VERSION as _PYDANTIC_VERSION

    _PYDANTIC_V2 = int(_PYDANTIC_VERSION.split(".")[0]) >= 2
except Exception:  # noqa: BLE001
    _PYDANTIC_V2 = False

if _PYDANTIC_V2:
    from pydantic import Field
    from pydantic_settings import BaseSettings
else:  # pragma: no cover - v1 fallback
    from pydantic import BaseSettings, Field  # type: ignore[no-redef]


# ── Best-effort AWS Secrets Manager injection (runs once at import) ───────────
def _maybe_load_aws_secrets() -> None:
    """
    Inject AWS Secrets Manager values into os.environ before Settings reads them.

    Only attempted when AWS_REGION is set, so local dev (no AWS) is untouched.
    Never overwrites variables already present in the environment. Degrades
    silently if the shared loader cannot be imported.
    """
    if not os.environ.get("AWS_REGION"):
        return
    secret_name = os.environ.get("SM_SECRET_NAME", "thinkvelocity/production/python-ai")
    try:
        from configs.secrets.python.secrets_loader import init_secrets  # type: ignore

        init_secrets(secret_name)
    except Exception:  # noqa: BLE001 - isolated deploys won't have configs/ on path
        pass


_maybe_load_aws_secrets()


class Settings(BaseSettings):
    """Merged settings for the unified python-ai service (port 8005)."""

    # ── LLM — Groq ─────────────────────────────────────────────────────────
    GROQ_API_KEY: str = Field(default="")
    CHATGROQ_API_KEY_1: str = Field(default="")
    CHATGROQ_API_KEY_2: str = Field(default="")
    CHATGROQ_API_KEY_3: str = Field(default="")
    GROQ_REQUESTS_PER_KEY: int = Field(default=5)
    GROQ_MODEL: str = Field(default="openai/gpt-oss-120b")
    GROQ_TIMEOUT: int = Field(default=30)

    # ── Other LLM providers ─────────────────────────────────────────────────
    OPENAI_API_KEY: str = Field(default="")
    GEMINI_API_KEY: str = Field(default="")
    GOOGLE_API_KEY: str = Field(default="")

    # ── Database ──────────────────────────────────────────────────────────────
    PG_CONNECTION: str = Field(default="")

    # ── Embeddings ──────────────────────────────────────────────────────────
    NVIDIA_API_KEY: str = Field(default="")
    NVIDIA_EMBEDDING_API_KEY: str = Field(default="")
    EMBEDDING_MODEL: str = Field(default="nvidia/nv-embedqa-e5-v5")
    EMBEDDING_DIMENSION: int = Field(default=1024)
    RELEVANCE_THRESHOLD: float = Field(default=0.30)

    # ── Web search ──────────────────────────────────────────────────────────
    TAVILY_API_KEY: str = Field(default="")
    TAVILY_TIMEOUT_MS: int = Field(default=10000)
    TAVILY_MAX_RESULTS: int = Field(default=5)
    TAVILY_ENABLE_CACHING: bool = Field(default=True)
    TAVILY_CACHE_TTL_SECONDS: int = Field(default=3600)
    TAVILY_RATE_LIMIT_PER_MINUTE: int = Field(default=60)
    TAVILY_ENABLE_FALLBACK: bool = Field(default=True)
    TAVILY_FALLBACK_TIMEOUT_MS: int = Field(default=8000)
    SERPAPI_API_KEY: str = Field(default="")
    GOOGLE_CSE_ID: str = Field(default="")

    # ── Auth (currently disabled on all services) ─────────────────────────────
    AUTH_ENABLED: bool = Field(default=False)
    API_AUTH_TOKEN: str = Field(default="")

    # ── Infrastructure ────────────────────────────────────────────────────────
    RATE_LIMITING_ENABLED: bool = Field(default=True)
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # ── Node.js backend (used by /context/* routes) ───────────────────────────
    NODE_BACKEND_URL: str = Field(default="")

    # ── Enterprise (prompt-enhance only) ──────────────────────────────────────
    ENTERPRISE_BACKEND_BASE_URL: str = Field(default="")
    ENTERPRISE_POLICY_ENDPOINT: str = Field(default="")
    ENTERPRISE_CONTENTS_ENDPOINT: str = Field(default="")

    # ── Analytics (currently 404-ing; kept non-blocking) ──────────────────────
    ANALYTICS_PIPELINE_ENABLED: bool = Field(default=False)
    ANALYTICS_ENDPOINT: str = Field(default="")
    ANALYTICS_SERVICE_TOKEN: str = Field(default="")

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = Field(default="INFO")

    # ── App ─────────────────────────────────────────────────────────────────
    APP_PORT: int = Field(default=8005)
    DEV_MODE: bool = Field(default=False)
    ALLOWED_ORIGINS: str = Field(default="*")

    # ── Supermemory ──────────────────────────────────────────────────────────
    SUPERMEMORY_API_KEY: str = Field(default="")

    # ── AWS ─────────────────────────────────────────────────────────────────
    AWS_REGION: str = Field(default="")

    @property
    def groq_keys(self) -> list[str]:
        """
        Ordered, de-duplicated list of usable Groq API keys.

        Prefers the CHATGROQ_API_KEY_1/2/3 rotation pool; falls back to the
        single GROQ_API_KEY. Empty strings are filtered out.
        """
        candidates = [
            self.CHATGROQ_API_KEY_1,
            self.CHATGROQ_API_KEY_2,
            self.CHATGROQ_API_KEY_3,
            self.GROQ_API_KEY,
        ]
        seen: set[str] = set()
        keys: list[str] = []
        for key in candidates:
            key = (key or "").strip()
            if key and key not in seen:
                seen.add(key)
                keys.append(key)
        return keys

    @property
    def allowed_origins_list(self) -> list[str]:
        """ALLOWED_ORIGINS as a list for CORSMiddleware ('*' -> ['*'])."""
        raw = (self.ALLOWED_ORIGINS or "*").strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def nvidia_embedding_key(self) -> str:
        """Resolved NVIDIA key for embeddings (dedicated key, then shared)."""
        return (self.NVIDIA_EMBEDDING_API_KEY or self.NVIDIA_API_KEY or "").strip()

    if _PYDANTIC_V2:
        model_config = {
            "env_file": ".env",
            "env_file_encoding": "utf-8",
            "extra": "ignore",
            "case_sensitive": False,
        }
    else:  # pragma: no cover - v1 fallback

        class Config:  # type: ignore[no-redef]
            env_file = ".env"
            env_file_encoding = "utf-8"
            extra = "ignore"
            case_sensitive = False


# Module-level singleton.
settings = Settings()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """FastAPI-dependency-injectable cached Settings instance."""
    return settings
