from __future__ import annotations

import hashlib
from pathlib import Path

from core.contracts import SCHEMA_VERSION
from core.contracts import PROMPT_MODE_VALUES
from core.prompt_modes import prompt_versions

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prompt_hash(prompt_name: str) -> str:
    return file_sha256(_PROMPTS_DIR / prompt_name)


def prompt_metadata() -> dict:
    versions = prompt_versions()
    return {
        "schema_version": SCHEMA_VERSION,
        "enhance_prompt_hash": prompt_hash("enhance_system.md"),
        "refine_prompt_hash": prompt_hash("refine_system.md"),
        "intent_prompt_hash": prompt_hash("intent_system.md"),
        "prompt_modes": list(PROMPT_MODE_VALUES),
        "prompt_versions": versions,
        "enhance_prompt_versions": versions["enhance"],
        "refine_prompt_versions": versions["refine"],
    }
