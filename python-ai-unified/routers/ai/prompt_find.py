"""/ai/prompt/find — enterprise context discovery (policy + documents).

Wired per A0-4 / SPRINT_TASKS to the Node.js backend public (no-auth) endpoints:

  GET  {NODE_BACKEND_URL}/api/v1/processed-context/public/user/{user_id}
  POST {NODE_BACKEND_URL}/api/v1/processed-context/public/search
       body: { userId, embedding?: [...], query?, limit: 5 }

Accepts: { user_id, enterprise_id?, query? }
Returns: { policy: [...], documents: [...], errors: [] }

Degrades per leg (one failure returns partial + error entry, never 5xx the whole call).
No auth token required (public endpoints per processedContextRoutes.js).
Uses shared/node_client (node_get + node_post) and shared/embedding_client when query present.

Leg 3 (D-110): Supermemory fallback search. Only runs when Leg 2 (Node semantic
search) returns zero documents AND a query was provided — same "local wins,
Supermemory fills the gap" contract as the enhance pipeline's
_fetch_context_hint. Marked with source="supermemory" on each result so
callers/UI can distinguish provenance.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from shared.embedding_client import generate_embedding
from shared.node_client import node_get, node_post
from shared.settings import settings

router = APIRouter(tags=["prompt-find"])


class PromptFindRequest(BaseModel):
    """Request for /ai/prompt/find (enterprise policy + context docs lookup)."""
    user_id: str
    enterprise_id: str | None = None
    query: str | None = None


@router.post("/prompt/find")
async def prompt_find(request: PromptFindRequest) -> dict[str, Any]:
    """POST /ai/prompt/find

    Two-legged call against Node public processed-context routes (degrade per leg).
    - Leg 1 (GET user): result placed in "policy"
    - Leg 2 (POST search): if query present, generate embedding and include it.
      Result placed in "documents".
    """
    policy: list[Any] = []
    documents: list[Any] = []
    errors: list[str] = []

    user_id = str(request.user_id or "").strip()
    if not user_id:
        return {"policy": [], "documents": [], "errors": ["user_id is required"]}

    # Leg 1: fetch user's processed contexts (treated as policy / memory for grounding)
    try:
        user_data = await node_get(
            f"/api/v1/processed-context/public/user/{user_id}",
            params={"limit": "20"},
        )
        if isinstance(user_data, dict):
            policy = (
                user_data.get("items")
                or user_data.get("data")
                or user_data.get("contexts")
                or user_data.get("results")
                or []
            )
        elif isinstance(user_data, list):
            policy = user_data
        elif user_data:
            policy = [user_data]
    except Exception as exc:  # noqa: BLE001 - degrade per leg
        errors.append(f"user_fetch: {exc}")

    # Leg 2: semantic search for relevant documents
    try:
        search_body: dict[str, Any] = {"userId": user_id, "limit": 5}
        if request.query and request.query.strip():
            q = request.query.strip()
            search_body["query"] = q
            try:
                emb = await generate_embedding(q)
                if emb:
                    search_body["embedding"] = emb
            except Exception as emb_exc:  # noqa: BLE001
                errors.append(f"embedding_generation: {emb_exc}")
        if request.enterprise_id:
            search_body["enterpriseId"] = request.enterprise_id

        search_data = await node_post(
            "/api/v1/processed-context/public/search", search_body
        )
        if isinstance(search_data, dict):
            documents = (
                search_data.get("documents")
                or search_data.get("results")
                or search_data.get("contexts")
                or search_data.get("items")
                or []
            )
        elif isinstance(search_data, list):
            documents = search_data
        elif search_data:
            documents = [search_data]
    except Exception as exc:  # noqa: BLE001 - degrade per leg
        errors.append(f"search: {exc}")

    # Leg 3 (D-110): Supermemory fallback — only when Leg 2 found nothing and
    # a query was actually provided. Never overrides real Node search results.
    if not documents and request.query and request.query.strip() and settings.SUPERMEMORY_API_KEY:
        try:
            from shared.supermemory_client import search_memories as _sm_search
            sm_snippets = await _sm_search(user_id, request.query.strip(), limit=5)
            if sm_snippets:
                documents = [
                    {"content": snippet, "source": "supermemory"} for snippet in sm_snippets
                ]
        except Exception as exc:  # noqa: BLE001 - degrade per leg
            errors.append(f"supermemory_search: {exc}")

    return {
        "policy": policy,
        "documents": documents,
        "errors": errors,
    }
