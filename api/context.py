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

    ctx = store.get_user_context(user_id)
    if body.personalization_notes is not None:
        store.update_personalization_notes(user_id, body.personalization_notes)
    if body.preferences is not None:
        store.update_preferences(user_id, body.preferences)
    return store.get_user_context(user_id)
