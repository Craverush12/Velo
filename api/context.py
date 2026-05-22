import json
import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from core.llm import complete
from core.output_validator import parse_json_object
from storage import store

router = APIRouter()


class ContextUpdateRequest(BaseModel):
    clear: bool = False
    personalization_notes: str | None = None
    preferences: dict | None = None


@router.get("/context/{user_id}")
def get_context(user_id: str):
    return store.get_user_context(user_id)


@router.patch("/context/{user_id}")
def update_context(user_id: str, body: ContextUpdateRequest):
    if body.clear:
        return store.reset_user_context(user_id)
    if body.personalization_notes is not None:
        store.update_personalization_notes(user_id, body.personalization_notes)
    if body.preferences is not None:
        store.update_preferences(user_id, body.preferences)
    return store.get_user_context(user_id)


@router.get("/history/{user_id}")
def get_history(user_id: str):
    """Newest-first list of enhancement entries for the given user."""
    return store.get_history(user_id)


@router.get("/config")
def get_config():
    """Returns server-side defaults so the browser UI can align its user identity."""
    return {
        "default_user_id": os.getenv("VELOCITY_USER_ID", "anonymous"),
    }


_INSIGHTS_SYSTEM_PROMPT = (
    Path(__file__).parent.parent / "core" / "prompts" / "memory_insights_system.md"
).read_text(encoding="utf-8")


@router.get("/context/{user_id}/insights")
async def get_memory_insights(user_id: str):
    history = store.get_history(user_id)
    if not history:
        return {"clusters": [], "market_basket": [], "classification": "No data"}
    
    # We only send a simplified slice of history to save tokens
    simplified = [
        {
            "intent": h.get("intent", ""),
            "domain": h.get("domain", ""),
            "framework": h.get("framework", ""),
            "summary": h.get("summary", "")
        }
        for h in history[:15]
    ]

    user_msg = "\n".join([
        "Analyze this recent activity.",
        json.dumps(simplified, ensure_ascii=False, indent=2)
    ])

    try:
        raw = await complete(
            _INSIGHTS_SYSTEM_PROMPT,
            user_msg,
            temperature=0.2,
            max_tokens=800,
        )
        parsed = parse_json_object(raw)
        return parsed
    except Exception as e:
        return {"clusters": [], "market_basket": [], "classification": f"Error: {str(e)}"}
