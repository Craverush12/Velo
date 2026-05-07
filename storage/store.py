import json
import os
from datetime import datetime, timezone
from pathlib import Path

_STORAGE_PATH = Path(os.getenv("STORAGE_PATH", "storage/data"))

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
    _STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    return _STORAGE_PATH / f"user_{user_id}.json"


def get_user_context(user_id: str) -> dict:
    p = _path(user_id)
    if not p.exists():
        ctx = dict(_DEFAULT_CONTEXT)
        ctx["user_id"] = user_id
        now = datetime.now(timezone.utc).isoformat()
        ctx["created_at"] = now
        ctx["updated_at"] = now
        return ctx
    with open(p) as f:
        return json.load(f)


def save_user_context(user_id: str, context: dict) -> None:
    with open(_path(user_id), "w") as f:
        json.dump(context, f, indent=2)


def reset_user_context(user_id: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    ctx = json.loads(json.dumps(_DEFAULT_CONTEXT))
    ctx["user_id"] = user_id
    ctx["created_at"] = now
    ctx["updated_at"] = now
    save_user_context(user_id, ctx)
    return ctx


def update_after_enhancement(
    user_id: str,
    intent: str,
    domain: str,
    summary: str,
    framework: str | None = None,
    placeholder_count: int = 0,
    tokens_used: int = 0,
    tokens_saved: int = 0,
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
                "at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        + ctx["recent_context"]
    )[:7]

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
