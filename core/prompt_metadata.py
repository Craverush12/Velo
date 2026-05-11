from __future__ import annotations

import hashlib
from pathlib import Path

from core.contracts import SCHEMA_VERSION

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prompt_hash(prompt_name: str) -> str:
    return file_sha256(_PROMPTS_DIR / prompt_name)


def prompt_metadata() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "enhance_prompt_hash": prompt_hash("enhance_system.md"),
        "refine_prompt_hash": prompt_hash("refine_system.md"),
    }
