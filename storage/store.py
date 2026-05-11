import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

# ── Storage backend feature flag ──────────────────────────────────────────────
# STORAGE_BACKEND controls where user data lives.
# "local"     — JSON files on disk (default, no extra deps)
# "s3"        — AWS S3 (requires S3_BUCKET, AWS_* env vars + boto3)
# "lightsail" — LightSail object storage (requires LIGHTSAIL_* env vars + boto3)
_BACKEND = os.getenv("STORAGE_BACKEND", "local")

if _BACKEND not in ("local",):
    raise RuntimeError(
        f"STORAGE_BACKEND={_BACKEND!r} is not yet implemented.\n"
        "Supported now: 'local'.\n"
        "To migrate: implement the backend in storage/store.py, then set the env var."
    )

# ── Path resolution (always absolute — safe regardless of CWD) ───────────────
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
    },
    "recent_context": [],
    "personalization_notes": "",
    "enhancement_count": 0,
    "total_tokens_used": 0,
    "total_tokens_saved": 0,
    "created_at": "",
    "updated_at": "",
}


def _path(user_id: str) -> Path:
    if not _USER_ID_RE.fullmatch(user_id):
        raise ValueError("user_id must match ^[A-Za-z0-9_-]{1,64}$")
    _STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    path = (_STORAGE_PATH / f"user_{user_id}.json").resolve()
    if not path.is_relative_to(_STORAGE_PATH):
        raise ValueError("resolved storage path escaped STORAGE_PATH")
    return path


def _lock_for(user_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        if user_id not in _LOCKS:
            _LOCKS[user_id] = threading.Lock()
        return _LOCKS[user_id]


def get_user_context(user_id: str) -> dict:
    p = _path(user_id)
    if not p.exists():
        ctx = json.loads(json.dumps(_DEFAULT_CONTEXT))
        ctx["user_id"] = user_id
        now = datetime.now(timezone.utc).isoformat()
        ctx["created_at"] = now
        ctx["updated_at"] = now
        return ctx
    with open(p) as f:
        return json.load(f)


def save_user_context(user_id: str, context: dict) -> None:
    path = _path(user_id)
    tmp = path.with_suffix(".json.tmp")
    with _lock_for(user_id):
        with open(tmp, "w") as f:
            json.dump(context, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)


def reset_user_context(user_id: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    ctx = json.loads(json.dumps(_DEFAULT_CONTEXT))
    ctx["user_id"] = user_id
    ctx["created_at"] = now
    ctx["updated_at"] = now
    save_user_context(user_id, ctx)
    return ctx


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
                "at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        + ctx["recent_context"]
    )[:20]  # bumped from 7 → 20 so history sidebar has real depth

    ctx["enhancement_count"] = ctx.get("enhancement_count", 0) + 1
    ctx["placeholder_count"] = ctx.get("placeholder_count", 0) + max(0, int(placeholder_count or 0))
    ctx["total_tokens_used"] = ctx.get("total_tokens_used", 0) + max(0, int(tokens_used or 0))
    ctx["total_tokens_saved"] = ctx.get("total_tokens_saved", 0) + max(0, int(tokens_saved or 0))
    ctx["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_user_context(user_id, ctx)


def update_preferences(user_id: str, preferences: dict) -> None:
    ctx = get_user_context(user_id)
    ctx["preferences"].update(preferences)
    ctx["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_user_context(user_id, ctx)


def update_personalization_notes(user_id: str, notes: str) -> None:
    ctx = get_user_context(user_id)
    ctx["personalization_notes"] = notes
    ctx["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_user_context(user_id, ctx)
