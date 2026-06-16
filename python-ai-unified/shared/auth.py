"""
shared/auth.py — API token validation dependency.

Source services: all three (python-backend, prompt-enhance, context-engine),
where AUTH_ENABLED=false and routes are public. API token header validation
(API_AUTH_TOKEN) exists but is inactive; this module makes it switchable.

When AUTH_ENABLED is false (the default), ``verify_token`` is a passthrough that
returns None — all routes are public. When AUTH_ENABLED is true, it validates a
Bearer token in the Authorization header against API_AUTH_TOKEN.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, status

from .settings import settings


async def verify_token(
    authorization: Optional[str] = Header(default=None),
) -> Optional[str]:
    """
    FastAPI dependency for optional bearer-token auth.

    Returns:
        None when auth is disabled (passthrough), otherwise the validated token.

    Raises:
        HTTPException(401): when auth is enabled and the bearer token is missing
            or does not match API_AUTH_TOKEN.
        HTTPException(500): when auth is enabled but no API_AUTH_TOKEN is set.
    """
    if not settings.AUTH_ENABLED:
        return None

    expected = (settings.API_AUTH_TOKEN or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth is enabled but API_AUTH_TOKEN is not configured.",
        )

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format; expected 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token.strip() != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token.strip()
