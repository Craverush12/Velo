import asyncio
import json
import os

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/connectors", tags=["connectors"])

_RESPONSES_URL = "https://api.groq.com/openai/v1/responses"
_CONNECTOR_MODEL = os.getenv("LLM_CONNECTOR_MODEL", "openai/gpt-oss-120b")

_LABELS = {
    "connector_gmail": "Gmail",
    "connector_googlecalendar": "Google Calendar",
    "connector_googledrive": "Google Drive",
}


class ConnectorRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=5000)
    access_token: str = Field(..., min_length=10)
    connector: str = Field(
        ..., pattern=r"^connector_(gmail|googlecalendar|googledrive)$"
    )


def _api_key() -> str:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured")
    return key


@router.post("/query")
async def connector_query(request: ConnectorRequest):
    """Run a query through a Google Workspace MCP connector via Groq Responses API."""
    label = _LABELS[request.connector]
    payload = {
        "model": _CONNECTOR_MODEL,
        "tools": [
            {
                "type": "mcp",
                "server_label": label,
                "connector_id": request.connector,
                "authorization": request.access_token,
                "require_approval": "never",
            }
        ],
        "input": request.prompt,
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            _RESPONSES_URL,
            headers={
                "Authorization": f"Bearer {_api_key()}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Groq Responses API error: {resp.text}",
        )

    data = resp.json()
    return {
        "output_text": data.get("output_text", ""),
        "model": data.get("model", _CONNECTOR_MODEL),
        "usage": data.get("usage", {}),
    }


_CONNECTOR_SHORT_NAMES = {
    "gmail": "connector_gmail",
    "calendar": "connector_googlecalendar",
    "drive": "connector_googledrive",
    "connector_gmail": "connector_gmail",
    "connector_googlecalendar": "connector_googlecalendar",
    "connector_googledrive": "connector_googledrive",
}


class ContextGatherRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=5000)
    access_token: str = Field(..., min_length=10)
    connectors: list[str] = Field(default_factory=lambda: ["gmail", "calendar", "drive"])


async def _gather_snippet(connector_id: str, label: str, prompt: str, access_token: str) -> dict | None:
    retrieval_prompt = (
        f"Find 2-3 short snippets most relevant to this task: {prompt}. "
        "Return as a JSON object with key 'snippets' containing an array of objects, "
        "each with keys 'source' (the connector name) and 'summary' (a one-sentence summary). "
        "Keep each summary under 120 characters. Be concise."
    )
    payload = {
        "model": _CONNECTOR_MODEL,
        "tools": [
            {
                "type": "mcp",
                "server_label": label,
                "connector_id": connector_id,
                "authorization": access_token,
                "require_approval": "never",
            }
        ],
        "input": retrieval_prompt,
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _RESPONSES_URL,
                headers={
                    "Authorization": f"Bearer {_api_key()}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
        output_text = data.get("output_text", "")
        try:
            parsed = json.loads(output_text)
            snippets = parsed.get("snippets", [])
            return {"source": label, "snippets": snippets[:3]}
        except (json.JSONDecodeError, AttributeError):
            if output_text.strip():
                return {"source": label, "snippets": [{"source": label, "summary": output_text.strip()[:120]}]}
            return None
    except Exception:
        return None


@router.post("/context-gather")
async def context_gather(request: ContextGatherRequest):
    """Gather relevant context snippets from Google Workspace connectors for a given prompt."""
    tasks = []
    for name in request.connectors:
        connector_id = _CONNECTOR_SHORT_NAMES.get(name)
        if not connector_id:
            continue
        label = _LABELS.get(connector_id, name)
        tasks.append(_gather_snippet(connector_id, label, request.prompt, request.access_token))

    results = await asyncio.gather(*tasks)
    all_snippets = []
    for result in results:
        if result:
            all_snippets.extend(result.get("snippets", []))

    return {"snippets": all_snippets[:9]}


@router.post("/drive/test")
async def drive_test(access_token: str, prompt: str = "Find spreadsheet files I worked on last month"):
    """Quick smoke-test for the Google Drive connector workflow from the docs."""
    req = ConnectorRequest(
        prompt=prompt,
        access_token=access_token,
        connector="connector_googledrive",
    )
    return await connector_query(req)
