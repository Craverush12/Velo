"""
shared/db.py — Async SQLAlchemy engine for the unified python-ai service.

Source services: python-backend / prompt-enhance (Server 2/3), which connect to
PostgreSQL via PG_CONNECTION using psycopg + SQLAlchemy. Used by the /ai/* routes
that need direct DB access (token deduction, pgvector RAG, analytics).

If PG_CONNECTION is unset (e.g. local dev, or routes that never touch the DB),
``engine`` is None and ``get_session`` raises a clear RuntimeError so DB-backed
routes fail loudly while DB-free routes keep working.

The connection string is normalized to the async ``postgresql+psycopg://`` driver
(SQLAlchemy 2.x + psycopg 3 async).
"""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .settings import settings


def _normalize_async_dsn(dsn: str) -> str:
    """Ensure the DSN uses an async-capable psycopg driver."""
    if dsn.startswith("postgresql+psycopg://") or dsn.startswith(
        "postgresql+asyncpg://"
    ):
        return dsn
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    if dsn.startswith("postgres://"):
        return dsn.replace("postgres://", "postgresql+psycopg://", 1)
    return dsn


def _build_engine() -> Optional[AsyncEngine]:
    dsn = (settings.PG_CONNECTION or "").strip()
    if not dsn:
        return None
    return create_async_engine(
        _normalize_async_dsn(dsn),
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=False,
    )


# Module-level engine (None when PG_CONNECTION is unset).
engine: Optional[AsyncEngine] = _build_engine()

# Session factory (None when there is no engine).
async_session_maker: Optional[async_sessionmaker[AsyncSession]] = (
    async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    if engine is not None
    else None
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding an async SQLAlchemy session.

    Raises:
        RuntimeError: if PG_CONNECTION is not configured (no engine available).
    """
    if async_session_maker is None:
        raise RuntimeError(
            "Database is not configured: set PG_CONNECTION to enable DB-backed routes."
        )
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
