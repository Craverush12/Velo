"""/ai/media/* and /ai/transcribe — media enhancement and audio transcription.

Source routes (canonical prompt-enhance / Server 3):
  - POST /media/enhance -> /ai/media/enhance (forces media mode; test endpoint)
  - POST /transcribe    -> /ai/transcribe    (multipart audio; Groq whisper)

PER D-019, both reuse this monorepo's canonical logic:
  * /media/enhance → the enhance pipeline with media mode forced (via enhance_chat)
  * /transcribe    → the real ``api.cothinker.cothinker_transcribe`` (the same
    handler the extension's /dev/test/transcribe delegates to)
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Request, UploadFile

from local_app import cothinker_transcribe

from .enhance import EnhanceRequest, enhance_chat

router = APIRouter(tags=["media"])


@router.post("/media/enhance")
async def media_enhance(
    request: EnhanceRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
):
    """Media enhancement — runs the enhance pipeline with media mode forced.

    Source: POST /media/enhance on prompt-enhance (Server 3). Test endpoint.
    """
    return await enhance_chat(
        request, http_request, background_tasks, force_media=True
    )


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """Transcribe an uploaded audio file (voice mode).

    Source: POST /transcribe on prompt-enhance (Server 3 only). Delegates to the
    canonical ``cothinker_transcribe`` — the same path the extension uses.
    """
    return await cothinker_transcribe(audio)
