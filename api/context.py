import os

from fastapi import APIRouter
from pydantic import BaseModel

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
