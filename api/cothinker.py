from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import requests as _requests
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from core.connectors_catalog import connector_catalog_summary
from core.contracts import PromptMode, TargetAI, normalize_prompt_mode, normalize_target_ai
from core.llm import complete, complete_multi_turn
from core.output_validator import parse_json_object, parse_validate_with_repair

router = APIRouter(prefix="/cothinker", tags=["cothinker"])

_DIALOGUE_BASE = (
    Path(__file__).parent.parent / "core" / "prompts" / "cothinker_system.md"
).read_text(encoding="utf-8")

_FINALIZE_SYSTEM = (
    Path(__file__).parent.parent / "core" / "prompts" / "cothinker_finalize_system.md"
).read_text(encoding="utf-8")

_GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_SERPER_URL = "https://google.serper.dev/search"
_TTS_VOICE = "en-US-GuyNeural"

# ── 10 confirmation fields ────────────────────────────────────────

CT_FIELDS: list[str] = [
    "target_llm",
    "core_goal",
    "task_type",
    "domain",
    "audience",
    "output_format",
    "constraints",
    "background_context",
    "tone",
    "success_criteria",
]

CT_FIELD_LABELS: dict[str, str] = {
    "target_llm": "Target AI",
    "core_goal": "Core Goal",
    "task_type": "Task Type",
    "domain": "Domain",
    "audience": "Audience",
    "output_format": "Output Format",
    "constraints": "Constraints",
    "background_context": "Context",
    "tone": "Tone",
    "success_criteria": "Success Criteria",
}

# ── Session store ─────────────────────────────────────────────────

SESSION_TTL = 3600  # 1 hour


@dataclass
class CTSession:
    session_id: str
    messages: list[dict] = field(default_factory=list)
    confirmed: dict[str, str | None] = field(
        default_factory=lambda: {f: None for f in CT_FIELDS}
    )
    last_activity: float = field(default_factory=time.time)


_sessions: dict[str, CTSession] = {}


def _get_session(session_id: str | None) -> CTSession:
    now = time.time()
    stale = [k for k, v in _sessions.items() if now - v.last_activity > SESSION_TTL]
    for k in stale:
        del _sessions[k]

    if session_id and session_id in _sessions:
        s = _sessions[session_id]
        s.last_activity = now
        return s

    s = CTSession(session_id=uuid.uuid4().hex)
    _sessions[s.session_id] = s
    return s


def _confirmation_count(confirmed: dict) -> int:
    return sum(1 for v in confirmed.values() if v)


def _build_system_prompt(confirmed: dict) -> str:
    count = _confirmation_count(confirmed)
    conf_lines = "\n".join(
        f"  {CT_FIELD_LABELS.get(k, k)}: {v}" for k, v in confirmed.items() if v
    ) or "  (none yet)"
    remaining = [
        CT_FIELD_LABELS.get(k, k) for k, v in confirmed.items() if not v
    ]
    next_targets = ", ".join(remaining[:4]) if remaining else "all confirmed"

    state_block = f"""

---
## Current Session State ({count}/10 confirmed)

Confirmed:
{conf_lines}

Still needed (prioritize in this order): {next_targets}
"""
    return _DIALOGUE_BASE + state_block


# ── Web search: Serper.dev ────────────────────────────────────────

def _search_sync(query: str, api_key: str) -> str:
    resp = _requests.post(
        _SERPER_URL,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": query, "num": 5},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    lines: list[str] = []
    answer_box = data.get("answerBox", {})
    if answer_box.get("answer"):
        lines.append(f"[Direct answer] {answer_box['answer']}")
    elif answer_box.get("snippet"):
        lines.append(f"[Direct answer] {answer_box['snippet']}")
    for item in data.get("organic", [])[:4]:
        snippet = item.get("snippet", "").strip()
        title = item.get("title", "").strip()
        if snippet:
            lines.append(f"- {title}: {snippet}")
    return "\n".join(lines) if lines else "No results found."


# ── STT: Groq Whisper via REST ────────────────────────────────────

def _transcribe_sync(audio_bytes: bytes, filename: str, api_key: str) -> str:
    resp = _requests.post(
        _GROQ_STT_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        files={"file": (filename, audio_bytes, "audio/webm")},
        data={"model": "whisper-large-v3", "response_format": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("text", "").strip()


# ── TTS: edge-tts in isolated thread (fixes Windows WinError 64) ──

def _sync_speak(text: str, voice: str) -> bytes:
    """Run edge-tts in a fresh event loop to avoid Windows ProactorEventLoop SSL issues."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        import edge_tts

        async def _generate() -> bytes:
            communicate = edge_tts.Communicate(text, voice)
            chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        return loop.run_until_complete(_generate())
    finally:
        loop.close()
        asyncio.set_event_loop(None)


# ── Request / Response models ─────────────────────────────────────

class TurnRequest(BaseModel):
    session_id: str | None = None
    user_message: str | None = None


class SpeakRequest(BaseModel):
    text: str


class FinalizeRequest(BaseModel):
    session_id: str | None = None
    messages: list[dict] = Field(default_factory=list)  # fallback if no session_id
    user_id: str = "anonymous"
    target_ai: TargetAI | None = None
    prompt_mode: PromptMode = "normal"
    incognito: bool = False

    @field_validator("target_ai", mode="before")
    @classmethod
    def valid_target_ai(cls, v: str | None) -> str | None:
        return normalize_target_ai(v)

    @field_validator("prompt_mode", mode="before")
    @classmethod
    def valid_prompt_mode(cls, v: str | None) -> str:
        return normalize_prompt_mode(v)


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/transcribe")
async def cothinker_transcribe(audio: UploadFile = File(...)):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured")
    audio_bytes = await audio.read()
    try:
        transcript = await asyncio.to_thread(
            _transcribe_sync, audio_bytes, audio.filename or "audio.webm", api_key
        )
    except _requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Transcription failed: {e}") from e
    return {"transcript": transcript}


@router.post("/speak")
async def cothinker_speak(request: SpeakRequest):
    if not request.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    try:
        audio_bytes = await asyncio.to_thread(_sync_speak, request.text.strip(), _TTS_VOICE)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TTS failed: {e}") from e
    return Response(content=audio_bytes, media_type="audio/mpeg")


@router.post("/turn")
async def cothinker_turn(request: TurnRequest):
    session = _get_session(request.session_id)

    # Build messages for LLM (don't persist __init__ in session history)
    if request.user_message is not None:
        session.messages.append({"role": "user", "content": request.user_message})
        messages_for_llm = session.messages
    else:
        messages_for_llm = [{"role": "user", "content": "__init__"}]

    system = _build_system_prompt(session.confirmed)
    raw = await complete_multi_turn(system, messages_for_llm, temperature=0.8, max_tokens=600)

    try:
        parsed = parse_json_object(raw)
        reply = str(parsed.get("reply") or "Tell me more about what you need.").strip()
        is_done = bool(parsed.get("is_done", False))
        updates = parsed.get("confirmed_updates") or {}

        # ── Web search: if LLM requested a search, do it and re-call ──
        search_query = str(parsed.get("search_query") or "").strip()
        if search_query:
            serper_key = os.getenv("SERPER_API_KEY")
            if serper_key:
                try:
                    search_results = await asyncio.to_thread(_search_sync, search_query, serper_key)
                    search_block = (
                        f"\n\n[REAL-TIME SEARCH RESULTS for '{search_query}']\n"
                        f"{search_results}\n"
                        f"[END SEARCH]\n\n"
                        f"Use the above facts naturally in your reply if they add value. "
                        f"Do not mention that you searched — just speak from knowledge."
                    )
                    raw2 = await complete_multi_turn(
                        system + search_block, messages_for_llm, temperature=0.8, max_tokens=600
                    )
                    parsed2 = parse_json_object(raw2)
                    reply = str(parsed2.get("reply") or reply).strip()
                    is_done = bool(parsed2.get("is_done", is_done))
                    updates = parsed2.get("confirmed_updates") or updates
                except Exception:
                    pass  # fall through with original reply

        if isinstance(updates, dict):
            for k, v in updates.items():
                if k in session.confirmed and v:
                    session.confirmed[k] = str(v).strip()
    except Exception:
        reply = "Tell me more about what you need."
        is_done = False

    session.messages.append({"role": "assistant", "content": reply})
    count = _confirmation_count(session.confirmed)

    return {
        "session_id": session.session_id,
        "reply": reply,
        "is_done": is_done,
        "confirmed": session.confirmed,
        "confirmation_count": count,
    }


@router.post("/finalize")
async def cothinker_finalize(request: FinalizeRequest):
    # Prefer server-side session; fall back to client-provided messages
    if request.session_id and request.session_id in _sessions:
        session = _sessions[request.session_id]
        messages = session.messages
        confirmed = session.confirmed
    else:
        messages = [{"role": m["role"], "content": m["content"]} for m in request.messages]  # type: ignore[index]
        confirmed = {}

    user_message = json.dumps(
        {
            "conversation": messages,
            "confirmed_fields": confirmed,
            "target_ai": request.target_ai,
            "prompt_mode": request.prompt_mode,
            "connector_catalog": connector_catalog_summary(),
        },
        ensure_ascii=False,
    )

    raw_prompt = next(
        (m["content"] for m in messages if m.get("role") == "user"),
        "prompt from cothinker conversation",
    )

    async def _repair(kind: str, raw: str, repair_prompt: str) -> str:
        return await complete(
            "You repair ThinkVelocity JSON outputs. Return only valid JSON.",
            repair_prompt,
            temperature=0,
            max_tokens=4096,
        )

    raw = await complete(_FINALIZE_SYSTEM, user_message, temperature=0.7, max_tokens=4096)
    return await parse_validate_with_repair(
        "enhance",
        raw,
        raw_prompt=raw_prompt,
        prompt_hash="cothinker-v1",
        prompt_mode=request.prompt_mode,
        repair_callback=_repair,
    )
