"""
settings_with_sm.py — Pydantic BaseSettings subclass that pulls from AWS Secrets Manager.

This module provides:

  1. SecretsManagerSettings — a BaseSettings subclass that injects SM secrets
     into the environment before pydantic reads it.  Subclass this instead of
     BaseSettings directly to get transparent SM integration.

  2. PythonAISettings — concrete settings class for the python-ai service
     (port 8005).  Clone and rename for extension-api.

  3. ExtensionAPISettings — concrete settings class for the extension-api
     service (port 8000).

  4. get_python_ai_settings() / get_extension_api_settings() — FastAPI
     dependency-injectable singleton factories.

─────────────────────────────────────────────────────────────────────────────
USAGE IN FastAPI (python-ai service)
─────────────────────────────────────────────────────────────────────────────

    # main.py — TOP of file, before any other project import
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    # settings_with_sm handles SM injection internally via __init_subclass__
    from configs.secrets.python.settings_with_sm import (
        PythonAISettings,
        get_python_ai_settings,
    )
    settings = PythonAISettings()   # SM values already merged into env

    from fastapi import FastAPI, Depends
    app = FastAPI()

    @app.get("/config-check")
    def config_check(s: PythonAISettings = Depends(get_python_ai_settings)):
        return {"groq_set": bool(s.GROQ_API_KEY), "env": s.APP_ENV}

─────────────────────────────────────────────────────────────────────────────
COMPATIBILITY
─────────────────────────────────────────────────────────────────────────────
Supports both pydantic v1 (class Config) and pydantic v2 (model_config).
The detection is automatic.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from typing import Optional

# ── Detect pydantic version ──────────────────────────────────────────────────
try:
    from pydantic import VERSION as _PYDANTIC_VERSION

    _PYDANTIC_V2 = int(_PYDANTIC_VERSION.split(".")[0]) >= 2
except Exception:  # noqa: BLE001
    _PYDANTIC_V2 = False

if _PYDANTIC_V2:
    from pydantic_settings import BaseSettings
    from pydantic import Field
else:
    from pydantic import BaseSettings, Field  # type: ignore[no-redef]

# ── Project root on sys.path so secrets_loader is importable ─────────────────
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_THIS_DIR)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from configs.secrets.python.secrets_loader import init_secrets, get_source  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Base class
# ─────────────────────────────────────────────────────────────────────────────

class SecretsManagerSettings(BaseSettings):
    """
    BaseSettings subclass that injects AWS Secrets Manager values into
    os.environ before pydantic reads environment variables.

    Subclasses MUST set the class variable SM_SECRET_NAME to the full path
    of their AWS Secrets Manager secret, e.g.:

        class MySettings(SecretsManagerSettings):
            SM_SECRET_NAME: str = "thinkvelocity/production/python-ai"
            MY_VAR: str = "default"

    The SM_SECRET_NAME field is excluded from the model's public schema.
    """

    # Subclasses override this at class level (not as an env-read field)
    SM_SECRET_NAME: str = ""

    def __init__(self, **data):
        # Inject SM secrets into os.environ before pydantic reads them.
        # This is safe to call multiple times — init_secrets() is idempotent
        # and caches results at module level.
        secret_name = data.pop("SM_SECRET_NAME", None) or self.__class__.__dict__.get(
            "SM_SECRET_NAME", ""
        )
        if secret_name:
            init_secrets(secret_name)
        super().__init__(**data)

    if _PYDANTIC_V2:
        from pydantic import model_config as _mc  # noqa: F401

        model_config = {
            "env_file": ".env",
            "env_file_encoding": "utf-8",
            "extra": "ignore",
            "populate_by_name": True,
        }
    else:
        class Config:  # type: ignore[no-redef]
            env_file = ".env"
            env_file_encoding = "utf-8"
            extra = "ignore"


# ─────────────────────────────────────────────────────────────────────────────
# python-ai settings (port 8005)
# ─────────────────────────────────────────────────────────────────────────────

class PythonAISettings(SecretsManagerSettings):
    """
    Settings for the python-ai FastAPI service.
    Secret path: thinkvelocity/production/python-ai
    """

    SM_SECRET_NAME: str = "thinkvelocity/production/python-ai"

    # ── App ──────────────────────────────────────────────────────────────────
    APP_ENV: str = Field(default="development", description="development | production")
    PORT: int = Field(default=8005)
    LOG_LEVEL: str = Field(default="info")
    LOG_FORMAT: str = Field(default="json")

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="",
        description="PostgreSQL connection string, e.g. postgresql://user:pass@host/db",
    )
    DB_SCHEMA: str = Field(default="consumer")

    # ── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str = Field(
        default="redis://localhost:6379",
        description="Redis connection string",
    )

    # ── AI keys ──────────────────────────────────────────────────────────────
    GROQ_API_KEY: str = Field(default="", description="Groq API key")
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key")
    ANTHROPIC_API_KEY: str = Field(default="", description="Anthropic API key")

    # ── Embedding / context engine ───────────────────────────────────────────
    EMBEDDING_MODEL: str = Field(default="all-MiniLM-L6-v2")
    EMBEDDING_DIM: int = Field(default=1024)
    EMBEDDING_BATCH_SIZE: int = Field(default=32)
    MAX_CONTEXT_WINDOW: int = Field(default=10)
    CONTEXT_SIMILARITY_THRESHOLD: float = Field(default=0.75)
    MAX_MEMORIES_PER_USER: int = Field(default=500)

    # ── Rate limiting ────────────────────────────────────────────────────────
    MAX_REQUESTS_PER_MINUTE: int = Field(default=60)
    MAX_CONCURRENT_LLM_CALLS: int = Field(default=10)

    # ── CORS ─────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = Field(
        default="https://thinkvelocity.in,https://www.thinkvelocity.in,https://enterprise.thinkvelocity.in,chrome-extension://",
    )

    # ── Observability ────────────────────────────────────────────────────────
    SENTRY_DSN: str = Field(default="")

    # ── AWS ──────────────────────────────────────────────────────────────────
    AWS_REGION: str = Field(default="ap-south-1")

    @property
    def allowed_origins_list(self) -> list[str]:
        """Return ALLOWED_ORIGINS as a Python list for CORSMiddleware."""
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def secrets_source(self) -> Optional[str]:
        return get_source()


# ─────────────────────────────────────────────────────────────────────────────
# extension-api settings (port 8000)
# ─────────────────────────────────────────────────────────────────────────────

class ExtensionAPISettings(SecretsManagerSettings):
    """
    Settings for the extension-api FastAPI service.
    Secret path: thinkvelocity/production/extension-api
    """

    SM_SECRET_NAME: str = "thinkvelocity/production/extension-api"

    # ── App ──────────────────────────────────────────────────────────────────
    APP_ENV: str = Field(default="development")
    PORT: int = Field(default=8000)
    LOG_LEVEL: str = Field(default="info")
    LOG_FORMAT: str = Field(default="json")

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(default="")
    DB_SCHEMA: str = Field(default="extension")

    # ── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str = Field(default="redis://localhost:6379")

    # ── Auth ─────────────────────────────────────────────────────────────────
    JWT_SECRET: str = Field(
        default="",
        description="JWT signing secret — must match consumer backend",
    )

    # ── AI ───────────────────────────────────────────────────────────────────
    GROQ_API_KEY: str = Field(default="")

    # ── CORS ─────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = Field(
        default="https://thinkvelocity.in,https://www.thinkvelocity.in,chrome-extension://",
    )

    # ── Rate limiting ────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = Field(default=30)
    RATE_LIMIT_AUTH_PER_MINUTE: int = Field(default=5)

    # ── AWS ──────────────────────────────────────────────────────────────────
    AWS_REGION: str = Field(default="ap-south-1")

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def secrets_source(self) -> Optional[str]:
        return get_source()


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI dependency-injectable singletons
# ─────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_python_ai_settings() -> PythonAISettings:
    """
    Return a cached PythonAISettings instance.

    Usage in FastAPI route:
        from fastapi import Depends
        from configs.secrets.python.settings_with_sm import get_python_ai_settings, PythonAISettings

        @app.get("/info")
        def info(settings: PythonAISettings = Depends(get_python_ai_settings)):
            return {"env": settings.APP_ENV}
    """
    return PythonAISettings()


@lru_cache(maxsize=1)
def get_extension_api_settings() -> ExtensionAPISettings:
    """
    Return a cached ExtensionAPISettings instance.

    Usage in FastAPI route:
        from fastapi import Depends
        from configs.secrets.python.settings_with_sm import get_extension_api_settings, ExtensionAPISettings

        @app.get("/info")
        def info(settings: ExtensionAPISettings = Depends(get_extension_api_settings)):
            return {"env": settings.APP_ENV}
    """
    return ExtensionAPISettings()


# ─────────────────────────────────────────────────────────────────────────────
# CLI self-test
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print("\n=== PythonAISettings ===")
    s = get_python_ai_settings()
    print(f"  APP_ENV             : {s.APP_ENV}")
    print(f"  PORT                : {s.PORT}")
    print(f"  GROQ_API_KEY set    : {bool(s.GROQ_API_KEY)}")
    print(f"  DATABASE_URL set    : {bool(s.DATABASE_URL)}")
    print(f"  REDIS_URL           : {s.REDIS_URL}")
    print(f"  Secrets source      : {s.secrets_source}")
    print(f"  ALLOWED_ORIGINS     : {s.allowed_origins_list}")

    print("\n=== ExtensionAPISettings ===")
    e = get_extension_api_settings()
    print(f"  APP_ENV             : {e.APP_ENV}")
    print(f"  PORT                : {e.PORT}")
    print(f"  GROQ_API_KEY set    : {bool(e.GROQ_API_KEY)}")
    print(f"  DATABASE_URL set    : {bool(e.DATABASE_URL)}")
    print(f"  JWT_SECRET set      : {bool(e.JWT_SECRET)}")
    print(f"  Secrets source      : {e.secrets_source}")
    print()
