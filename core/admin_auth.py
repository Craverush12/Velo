from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Final


PASSWORD_ALGORITHM: Final = "pbkdf2_sha256"
PASSWORD_ITERATIONS: Final = 260_000
SESSION_COOKIE_NAME: Final = "tv_admin_session"
SESSION_TTL_HOURS: Final = 12

ROLES: Final = ("super_admin", "admin", "support_ops", "read_only")

ROLE_PERMISSIONS: Final[dict[str, set[str]]] = {
    "read_only": {
        "dashboard:view",
        "audit:view",
        "users:view",
        "admin_users:view",
        "content:view",
        "config:view",
        "operations:view",
    },
    "support_ops": {
        "dashboard:view",
        "audit:view",
        "users:view",
        "users:edit",
        "users:reset",
        "admin_users:view",
        "content:view",
        "config:view",
        "operations:view",
    },
    "admin": {
        "dashboard:view",
        "audit:view",
        "users:view",
        "users:edit",
        "users:reset",
        "admin_users:view",
        "content:view",
        "content:manage",
        "config:view",
        "config:manage",
        "pricing:manage",
        "operations:view",
        "operations:run",
    },
    "super_admin": {"*"},
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def session_expires_at() -> datetime:
    return now_utc() + timedelta(hours=SESSION_TTL_HOURS)


def generate_token(byte_count: int = 32) -> str:
    return secrets.token_urlsafe(byte_count)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    clean = _validate_password_input(password)
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        clean.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "$".join(
        [
            PASSWORD_ALGORITHM,
            str(PASSWORD_ITERATIONS),
            _b64(salt),
            _b64(digest),
        ]
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = password_hash.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = _unb64(salt_raw)
        expected = _unb64(digest_raw)
    except (ValueError, TypeError):
        return False

    candidate = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(candidate, expected)


def normalize_role(role: str) -> str:
    clean = (role or "").strip().lower().replace("-", "_")
    if clean == "support":
        clean = "support_ops"
    if clean not in ROLES:
        raise ValueError(f"unsupported admin role: {role}")
    return clean


def role_has_permission(role: str, permission: str) -> bool:
    try:
        clean_role = normalize_role(role)
    except ValueError:
        return False
    permissions = ROLE_PERMISSIONS.get(clean_role, set())
    return "*" in permissions or permission in permissions


def can_manage_target_role(actor_role: str, target_role: str) -> bool:
    actor = normalize_role(actor_role)
    target = normalize_role(target_role)
    if actor == "super_admin":
        return True
    return actor == "admin" and target != "super_admin"


def _validate_password_input(password: str) -> str:
    clean = str(password or "")
    if len(clean) < 10:
        raise ValueError("admin password must be at least 10 characters")
    return clean


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
