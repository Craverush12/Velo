import copy
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from storage.db import DatabaseStorage, load_all_json_contexts

# STORAGE_BACKEND controls where user data lives.
# "local"      - JSON files on disk (default, no extra deps)
# "postgresql" - SQLAlchemy-backed PostgreSQL when DATABASE_URL is configured.
_BACKEND_ENV = os.getenv("STORAGE_BACKEND", "").strip().lower()
_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if _BACKEND_ENV in ("", "auto"):
    _BACKEND = "postgresql" if _DATABASE_URL else "local"
elif _BACKEND_ENV in ("local", "json"):
    _BACKEND = "local"
elif _BACKEND_ENV in ("postgres", "postgresql", "db", "database"):
    _BACKEND = "postgresql"
else:
    raise RuntimeError(
        f"STORAGE_BACKEND={_BACKEND_ENV!r} is not supported.\n"
        "Supported: 'local', 'postgresql'."
    )

if _BACKEND == "postgresql" and not _DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required when STORAGE_BACKEND=postgresql")

_DB_STORAGE = DatabaseStorage(_DATABASE_URL) if _BACKEND == "postgresql" else None


def _resolve_path() -> Path:
    env = os.getenv("STORAGE_PATH", "").strip()
    if env:
        p = Path(env)
        if not p.is_absolute():
            p = Path(__file__).parent.parent / p
        return p.resolve()
    return Path(__file__).parent / "data"


_STORAGE_PATH = _resolve_path()
_USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()

_DEFAULT_CONTEXT = {
    "user_id": "",
    "domains": [],
    "frameworks_used": [],
    "placeholder_count": 0,
    "preferences": {
        "output_style": "balanced",
        "expertise_level": "intermediate",
        "preferred_tools": [],
        "industry": "",
        "tone": "",
        "default_target_ai": "",
        "format_preferences": [],
        "must_include": [],
        "avoid": [],
        "examples_preference": "balanced",
        "personalization_source": "manual",
    },
    "recent_context": [],
    "personalization_notes": "",
    "enhancement_count": 0,
    "total_tokens_used": 0,
    "total_tokens_saved": 0,
    "created_at": "",
    "updated_at": "",
}


def _validate_user_id(user_id: str) -> None:
    if not _USER_ID_RE.fullmatch(user_id):
        raise ValueError("user_id must match ^[A-Za-z0-9_-]{1,64}$")


def _path(user_id: str) -> Path:
    _validate_user_id(user_id)
    _STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    path = (_STORAGE_PATH / f"user_{user_id}.json").resolve()
    if not path.is_relative_to(_STORAGE_PATH):
        raise ValueError("resolved storage path escaped STORAGE_PATH")
    return path


def storage_path() -> str:
    """Return the resolved storage location and create it if needed."""
    if _BACKEND == "postgresql":
        return _DB_STORAGE._safe_database_url()
    _STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    return str(_STORAGE_PATH)


def storage_healthcheck() -> dict:
    """Verify that the configured storage backend is writable."""
    if _BACKEND == "postgresql":
        return _DB_STORAGE.healthcheck()

    _STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    marker = _STORAGE_PATH / ".healthcheck"
    try:
        marker.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        marker.unlink(missing_ok=True)
    except OSError as exc:
        return {
            "ok": False,
            "backend": _BACKEND,
            "path": str(_STORAGE_PATH),
            "error": str(exc),
        }
    return {
        "ok": True,
        "backend": _BACKEND,
        "path": str(_STORAGE_PATH),
    }


def _lock_for(user_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        if user_id not in _LOCKS:
            _LOCKS[user_id] = threading.Lock()
        return _LOCKS[user_id]


def get_user_context(user_id: str) -> dict:
    _validate_user_id(user_id)
    if _BACKEND == "postgresql":
        return _DB_STORAGE.get_user_context(user_id, _DEFAULT_CONTEXT)

    p = _path(user_id)
    if not p.exists():
        ctx = copy.deepcopy(_DEFAULT_CONTEXT)
        ctx["user_id"] = user_id
        now = datetime.now(timezone.utc).isoformat()
        ctx["created_at"] = now
        ctx["updated_at"] = now
        return ctx
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_user_context(user_id: str, context: dict) -> None:
    _validate_user_id(user_id)
    if _BACKEND == "postgresql":
        _DB_STORAGE.save_user_context(user_id, context)
        return

    path = _path(user_id)
    tmp = path.with_suffix(".json.tmp")
    with _lock_for(user_id):
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(context, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)


def reset_user_context(user_id: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    ctx = copy.deepcopy(_DEFAULT_CONTEXT)
    ctx["user_id"] = user_id
    ctx["created_at"] = now
    ctx["updated_at"] = now
    save_user_context(user_id, ctx)
    return ctx


def migrate_local_json_to_database() -> int:
    """Copy existing user_*.json contexts into the configured database backend."""
    if _BACKEND != "postgresql":
        raise RuntimeError("migrate_local_json_to_database requires PostgreSQL storage")
    return _DB_STORAGE.migrate_json_contexts(load_all_json_contexts(_STORAGE_PATH))


def get_history(user_id: str) -> list[dict]:
    """Return recent_context entries newest-first, safe for API exposure."""
    ctx = get_user_context(user_id)
    return ctx.get("recent_context", [])


def update_after_enhancement(
    user_id: str,
    intent: str,
    domain: str,
    summary: str,
    framework: str | None = None,
    placeholder_count: int = 0,
    tokens_used: int = 0,
    tokens_saved: int = 0,
    original_prompt: str = "",
    enhanced_prompt: str = "",
    schema_version: str | None = None,
    prompt_version: str | None = None,
    prompt_mode: str = "normal",
) -> None:
    ctx = get_user_context(user_id)

    if domain and domain not in ctx["domains"]:
        ctx["domains"] = ([domain] + ctx["domains"])[:10]

    if framework and framework not in ctx.get("frameworks_used", []):
        ctx.setdefault("frameworks_used", [])
        ctx["frameworks_used"] = ([framework] + ctx["frameworks_used"])[:10]

    ctx["recent_context"] = (
        [
            {
                "intent": intent,
                "domain": domain,
                "summary": summary,
                "framework": framework,
                "placeholder_count": placeholder_count,
                "tokens_used": tokens_used,
                "tokens_saved": tokens_saved,
                "original_prompt": original_prompt,
                "enhanced_prompt": enhanced_prompt,
                "schema_version": schema_version,
                "prompt_version": prompt_version,
                "prompt_mode": prompt_mode,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        + ctx["recent_context"]
    )[:20]

    ctx["enhancement_count"] = ctx.get("enhancement_count", 0) + 1
    ctx["placeholder_count"] = ctx.get("placeholder_count", 0) + max(0, int(placeholder_count or 0))
    ctx["total_tokens_used"] = ctx.get("total_tokens_used", 0) + max(0, int(tokens_used or 0))
    ctx["total_tokens_saved"] = ctx.get("total_tokens_saved", 0) + max(0, int(tokens_saved or 0))
    ctx["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_user_context(user_id, ctx)


def update_preferences(user_id: str, preferences: dict) -> None:
    ctx = get_user_context(user_id)
    allowed = set(_DEFAULT_CONTEXT["preferences"].keys())
    clean = {k: v for k, v in preferences.items() if k in allowed}
    ctx["preferences"].update(clean)
    ctx["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_user_context(user_id, ctx)


def update_personalization_notes(user_id: str, notes: str) -> None:
    ctx = get_user_context(user_id)
    ctx["personalization_notes"] = notes
    ctx["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_user_context(user_id, ctx)
