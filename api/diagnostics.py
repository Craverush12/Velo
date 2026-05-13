from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.prompt_metadata import prompt_metadata
from core.contracts import PROMPT_MODE_VALUES, TARGET_AI_VALUES, TECHNIQUE_COLORS
from core.mcp_tools import list_tools
from core.source_catalog import load_source_catalog
from storage import store


router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])
ROOT = Path(__file__).resolve().parent.parent


class TestRunRequest(BaseModel):
    suite: str = "all"


@router.get("/systems")
async def systems():
    tools = await list_tools()
    return {
        "status": "ok",
        "python": sys.version.split()[0],
        "model": os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
        "storage_path": os.getenv("STORAGE_PATH", "storage/data"),
        "target_ai_values": list(TARGET_AI_VALUES),
        "prompt_modes": list(PROMPT_MODE_VALUES),
        "technique_count": len(TECHNIQUE_COLORS),
        "source_catalog_count": len(load_source_catalog()),
        "mcp_tools": [tool.name for tool in tools],
        **prompt_metadata(),
    }


@router.get("/mcp-tools")
async def mcp_tools():
    tools = await list_tools()
    return {
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema,
            }
            for tool in tools
        ]
    }


@router.get("/sources")
def get_sources():
    return load_source_catalog()


@router.get("/context-smoke/{user_id}")
async def context_smoke(user_id: str):
    context = store.get_user_context(user_id)
    return {
        "ok": True,
        "user_id": context.get("user_id", user_id),
        "enhancement_count": context.get("enhancement_count", 0),
        "has_preferences": bool(context.get("preferences")),
        "recent_context_count": len(context.get("recent_context", [])),
    }


@router.post("/tests")
async def run_tests(request: TestRunRequest):
    suites = {
        "all": [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        "prompt_contracts": [sys.executable, "-m", "unittest", "tests.test_prompt_contracts"],
        "output_validator": [sys.executable, "-m", "unittest", "tests.test_output_validator"],
        "refine_backend": [sys.executable, "-m", "unittest", "tests.test_refine_backend"],
        "intent_backend": [sys.executable, "-m", "unittest", "tests.test_intent_backend"],
        "health_metadata": [sys.executable, "-m", "unittest", "tests.test_health_metadata"],
        "store": [sys.executable, "-m", "unittest", "tests.test_store"],
    }
    command = suites.get(request.suite)
    if command is None:
        raise HTTPException(status_code=400, detail=f"Unknown test suite: {request.suite}")

    proc = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.communicate()
        raise HTTPException(status_code=504, detail="Test run timed out") from exc

    return {
        "suite": request.suite,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
    }
