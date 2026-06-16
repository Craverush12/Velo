"""local_app.py — Bridge to this monorepo's canonical core/api logic (D-019).

The unified service REUSES the repo's existing enhancement pipeline as the
single source of truth rather than re-implementing prompt/Groq logic. This
module puts the repo root on sys.path and re-exports the real handlers/contracts
that the /ai/* routers adapt onto the documented unified paths.

It mirrors the proven adapter pattern in ``api/extension_bridge.py`` (the
extension-facing ``/dev/test/*`` layer) — the same real functions, re-exposed
under ``/ai/*``.

Deploy note: because of this reuse, ``python-ai-unified`` is a façade WITHIN the
monorepo — its Docker build context is the repo root (``core/`` + ``api/`` +
``storage/`` copied in, repo root on PYTHONPATH). See README + Dockerfile.
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Real canonical logic (the same functions the extension hits via /dev/test/*).
from api.enhance import EnhanceRequest, _generate, AttachmentItem  # noqa: E402
from api.refine import (  # noqa: E402
    RefineRequest,
    RefinePrepareRequest,
    refine as refine_fn,
    refine_prepare as refine_prepare_fn,
)
from api.cothinker import cothinker_transcribe  # noqa: E402
from core.contracts import ClarificationQA, normalize_prompt_mode  # noqa: E402

# Extension mode aliases → internal prompt modes (from extension_bridge.py).
# The consumer extension's modeToApi() converts UI labels before sending:
#   standard / flash  → "flash"    → internal "normal"  (Fast mode)
#   research          → "research" → internal "research" (Best mode)
#   media             → "media"    → internal "media"    (Media mode)
#   caveman           → "caveman"  → internal "caveman"  (Saver mode)
EXT_MODE_TO_INTERNAL: dict[str, str] = {
    # Strings the extension actually sends (output of modeToApi)
    "flash": "normal",
    "research": "research",
    "media": "media",
    "caveman": "caveman",
    # Legacy / alternate aliases kept for back-compat
    "fast": "normal",
    "normal": "normal",
    "standard": "normal",
    "best": "research",
    "build": "fast_build",
    "saver": "caveman",
}


def map_mode(ext_mode: str | None) -> str:
    """Map an extension mode label to a normalized internal prompt mode."""
    raw = (ext_mode or "flash").lower()
    return normalize_prompt_mode(EXT_MODE_TO_INTERNAL.get(raw, "normal"))


__all__ = [
    "EnhanceRequest",
    "_generate",
    "AttachmentItem",
    "RefineRequest",
    "RefinePrepareRequest",
    "refine_fn",
    "refine_prepare_fn",
    "cothinker_transcribe",
    "ClarificationQA",
    "normalize_prompt_mode",
    "map_mode",
]
