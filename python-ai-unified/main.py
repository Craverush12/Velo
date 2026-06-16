"""
main.py — ThinkVelocity AI Unified service entrypoint.

Merges three previously separate Python services into ONE FastAPI app
(see docs/python-ai-merge-plan.md §4):

  - /ai/*       — canonical prompt-enhance build (Server 3)
  - /context/*  — context-engine (Server 2)

The app is intentionally tolerant at startup: shared infrastructure
(DB, Redis) and the sub-routers are wired defensively so the process still
boots for local development and partial deploys. Anything that fails to
initialize is logged as a warning and the corresponding feature degrades
rather than crashing the whole service.

Run locally:
    uvicorn main:app --reload --port 8005
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from shared.settings import settings

# ---------------------------------------------------------------------------
# Logging — initialized as early as possible. shared.logging_config owns the
# real configuration; if it is not present yet (parallel development) we fall
# back to a basic config so we still get useful output.
# ---------------------------------------------------------------------------
try:
    from shared.logging_config import configure_logging  # type: ignore

    configure_logging(settings.LOG_LEVEL)
except Exception:  # noqa: BLE001 - logging must never block boot
    logging.basicConfig(
        level=getattr(logging, str(settings.LOG_LEVEL).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

logger = logging.getLogger("thinkvelocity.unified")


# ---------------------------------------------------------------------------
# Shared resource handles. Populated in lifespan; referenced by /health.
# Each is optional — a None value means "not available / not initialized".
# ---------------------------------------------------------------------------
_resources: dict[str, Any] = {
    "groq": False,
    "db": False,
    "redis": False,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown: warm the Groq pool, open DB + Redis. Tolerate failures."""
    logger.info("Starting ThinkVelocity AI Unified (port %s)…", settings.APP_PORT)

    # ── Groq client pool ──────────────────────────────────────────────────
    try:
        from shared.groq_client import groq_pool

        # Warm the pool: instantiate the first client so a missing/invalid key
        # surfaces here as a warning rather than on the first request.
        warmup = getattr(groq_pool, "warmup", None)
        if callable(warmup):
            maybe_coro = warmup()
            if hasattr(maybe_coro, "__await__"):
                await maybe_coro
        else:
            # Fallback warmup: touch the configured keys without making a call.
            _ = getattr(settings, "groq_keys", [])
        app.state.groq_pool = groq_pool
        _resources["groq"] = True
        logger.info("Groq pool ready (%d key(s) configured).", len(settings.groq_keys))
    except Exception as exc:  # noqa: BLE001
        app.state.groq_pool = None
        _resources["groq"] = False
        logger.warning("Groq pool unavailable at startup: %s", exc)

    # ── PostgreSQL (SQLAlchemy async engine) ──────────────────────────────
    try:
        from shared.db import engine  # type: ignore

        app.state.db_engine = engine
        _resources["db"] = engine is not None
        logger.info("Database engine initialized.")
    except Exception as exc:  # noqa: BLE001
        app.state.db_engine = None
        _resources["db"] = False
        logger.warning("Database engine unavailable at startup: %s", exc)

    # ── Redis cache ───────────────────────────────────────────────────────
    try:
        from shared.redis_cache import get_redis  # type: ignore

        redis_client = get_redis()
        # Best-effort connectivity probe; ignore if the client can't ping.
        ping = getattr(redis_client, "ping", None)
        if callable(ping):
            result = ping()
            if hasattr(result, "__await__"):
                await result
        app.state.redis = redis_client
        _resources["redis"] = redis_client is not None
        logger.info("Redis cache connected.")
    except Exception as exc:  # noqa: BLE001
        app.state.redis = None
        _resources["redis"] = False
        logger.warning("Redis cache unavailable at startup: %s", exc)

    logger.info(
        "Startup complete. groq=%s db=%s redis=%s",
        _resources["groq"],
        _resources["db"],
        _resources["redis"],
    )

    try:
        yield
    finally:
        # ── Shutdown — close everything we opened, best-effort. ───────────
        logger.info("Shutting down ThinkVelocity AI Unified…")

        engine = getattr(app.state, "db_engine", None)
        if engine is not None:
            try:
                dispose = getattr(engine, "dispose", None)
                if callable(dispose):
                    result = dispose()
                    if hasattr(result, "__await__"):
                        await result
                logger.info("Database engine disposed.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error disposing database engine: %s", exc)

        redis_client = getattr(app.state, "redis", None)
        if redis_client is not None:
            try:
                close = getattr(redis_client, "aclose", None) or getattr(
                    redis_client, "close", None
                )
                if callable(close):
                    result = close()
                    if hasattr(result, "__await__"):
                        await result
                logger.info("Redis connection closed.")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error closing Redis connection: %s", exc)

        logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="ThinkVelocity AI Unified",
    version="1.0.0",
    description="Unified FastAPI service merging prompt-enhance (/ai/*) and "
    "context-engine (/context/*).",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Safe request logging (SOC2 CC6.7): logs method/path/status/timing only —
# never body, Authorization header, or query values. Degrades gracefully if
# the scrubber module isn't importable.
try:
    from shared.log_scrubber import LogScrubberMiddleware  # type: ignore

    app.add_middleware(LogScrubberMiddleware)
    logger.info("Request log-scrubber middleware enabled.")
except Exception as exc:  # noqa: BLE001
    logger.warning("LogScrubberMiddleware unavailable: %s", exc)


# ---------------------------------------------------------------------------
# Router wiring — guarded so a missing router (parallel development / partial
# deploy) logs a clear warning and the app still boots.
# ---------------------------------------------------------------------------
_routers_mounted: dict[str, bool] = {"ai": False, "context": False, "quality_compat": False}

try:
    from routers.ai import ai_router  # type: ignore

    app.include_router(ai_router, prefix="/ai")
    _routers_mounted["ai"] = True
    logger.info("Mounted /ai router.")
except ImportError as exc:
    logger.warning("Skipped /ai router (not importable yet): %s", exc)

try:
    from routers.quality_compat import router as quality_compat_router  # type: ignore

    app.include_router(quality_compat_router)
    _routers_mounted["quality_compat"] = True
    logger.info("Mounted /api/v1/quality compatibility router.")
except ImportError as exc:
    logger.warning("Skipped /api/v1/quality compatibility router: %s", exc)

try:
    from routers.context import context_router  # type: ignore

    app.include_router(context_router, prefix="/context")
    _routers_mounted["context"] = True
    logger.info("Mounted /context router.")
except ImportError as exc:
    logger.warning("Skipped /context router (not importable yet): %s", exc)


# ---------------------------------------------------------------------------
# Root health — reports app status plus sub-router and resource health.
# ---------------------------------------------------------------------------
@app.get("/health", tags=["health"])
async def root_health() -> dict[str, Any]:
    """Root service health, including sub-router and shared-resource status."""
    all_routers_up = all(_routers_mounted.values())
    return {
        "status": "ok" if all_routers_up else "degraded",
        "service": "python-ai-unified",
        "version": "1.0.0",
        "routers": {
            "ai": "up" if _routers_mounted["ai"] else "down",
            "context": "up" if _routers_mounted["context"] else "down",
            "quality_compat": "up" if _routers_mounted["quality_compat"] else "down",
        },
        "resources": {
            "groq": "up" if _resources["groq"] else "down",
            "database": "up" if _resources["db"] else "down",
            "redis": "up" if _resources["redis"] else "down",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.APP_PORT,
        reload=settings.DEV_MODE,
        log_level=str(settings.LOG_LEVEL).lower(),
    )
