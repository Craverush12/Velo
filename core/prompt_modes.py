from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from core.contracts import PROMPT_MODE_VALUES, PromptMode, normalize_prompt_mode

PROMPTS_DIR = Path(__file__).parent / "prompts"

_BASE_FILES = {
    "enhance": "enhance_system.md",
    "refine": "refine_system.md",
}

_OVERLAY_FILES = {
    "enhance": {
        "caveman": "enhance_caveman_overlay.md",
        "research": "enhance_research_overlay.md",
        "fast_build": "enhance_fast_build_overlay.md",
        "media": "enhance_media_overlay.md",
    },
    "refine": {
        "caveman": "refine_caveman_overlay.md",
    },
}

# Internal-only overlay keys not exposed as user-facing PromptMode values.
_INTERNAL_OVERLAY_FILES: dict[str, dict[str, str]] = {
    "enhance": {
        **_OVERLAY_FILES["enhance"],
        "media_imagegen": "enhance_media_imagegen_overlay.md",
    },
}


@dataclass(frozen=True)
class PromptBundle:
    kind: str
    mode: PromptMode
    text: str
    version: str
    files: tuple[str, ...]


def prompt_bundle(kind: str, mode: str | None = None) -> PromptBundle:
    if kind not in _BASE_FILES:
        raise ValueError(f"unknown prompt kind: {kind}")

    normalized_mode = normalize_prompt_mode(mode)
    files = [_BASE_FILES[kind]]
    parts = [_read_prompt(files[0])]

    overlay_name = _OVERLAY_FILES.get(kind, {}).get(normalized_mode)
    if overlay_name:
        files.append(overlay_name)
        parts.append(_read_prompt(overlay_name))

    text = "\n\n---\n\n".join(parts)
    return PromptBundle(
        kind=kind,
        mode=normalized_mode,  # type: ignore[arg-type]
        text=text,
        version=_hash_prompt_variant(kind, normalized_mode, files, text),
        files=tuple(files),
    )


def prompt_bundle_internal(kind: str, internal_mode: str) -> PromptBundle:
    """Build a bundle using an internal mode key that bypasses user-facing mode validation.

    The returned bundle's .mode is set to the nearest user-facing PromptMode so
    downstream storage and telemetry are never confused by internal keys.
    """
    if kind not in _BASE_FILES:
        raise ValueError(f"unknown prompt kind: {kind}")
    internal_map = _INTERNAL_OVERLAY_FILES.get(kind, {})
    if internal_mode not in internal_map and internal_mode not in _OVERLAY_FILES.get(kind, {}):
        raise ValueError(f"unknown internal_mode: {internal_mode!r} for kind {kind!r}")
    files = [_BASE_FILES[kind]]
    parts = [_read_prompt(files[0])]
    overlay_name = internal_map.get(internal_mode)
    if overlay_name:
        files.append(overlay_name)
        parts.append(_read_prompt(overlay_name))
    text = "\n\n---\n\n".join(parts)
    # Map internal mode to the nearest user-facing PromptMode for telemetry
    _internal_to_user_mode: dict[str, str] = {
        "media_imagegen": "media",
    }
    user_mode = _internal_to_user_mode.get(internal_mode, internal_mode)
    return PromptBundle(
        kind=kind,
        mode=user_mode,  # type: ignore[arg-type]
        text=text,
        version=_hash_prompt_variant(kind, internal_mode, files, text),
        files=tuple(files),
    )


def prompt_versions() -> dict[str, dict[str, str]]:
    return {
        kind: {mode: prompt_bundle(kind, mode).version for mode in PROMPT_MODE_VALUES}
        for kind in _BASE_FILES
    }


def _read_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _hash_prompt_variant(kind: str, mode: str, files: list[str], text: str) -> str:
    h = hashlib.sha256()
    h.update(f"kind={kind}\nmode={mode}\nfiles={','.join(files)}\n".encode("utf-8"))
    h.update(text.encode("utf-8"))
    return h.hexdigest()
