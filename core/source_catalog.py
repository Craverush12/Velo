from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES_PATH = ROOT / "Scraping Sources.md"

_ROW_RE = re.compile(
    r"^\|\s*\d+\s*\|\s*(?P<name>.*?)\s*\|\s*(?P<url>.*?)\s*\|\s*(?P<description>.*?)\s*\|$"
)
_LINK_RE = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<url>[^)]+)\)")


def load_source_catalog() -> list[dict[str, str]]:
    if not SOURCES_PATH.exists():
        return []

    sources: list[dict[str, str]] = []
    category = "General"
    for raw_line in SOURCES_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("## CATEGORY"):
            category = _clean_text(line.replace("##", "").strip())
            category = re.sub(r"^CATEGORY\s+\d+\s+", "", category, flags=re.IGNORECASE)
            category = category.lstrip("-— ").strip() or "General"
            continue

        match = _ROW_RE.match(line)
        if not match:
            continue

        name = _clean_text(match.group("name"))
        url_cell = match.group("url")
        link_match = _LINK_RE.search(url_cell)
        url = link_match.group("url") if link_match else _clean_text(url_cell)
        description = _clean_text(match.group("description"))
        if name and url:
            sources.append({
                "name": name,
                "url": url,
                "category": category,
                "description": description,
            })
    return sources


def source_catalog_summary(limit: int = 24) -> list[dict[str, str]]:
    return load_source_catalog()[:limit]


def recommend_sources(prompt: str, limit: int = 5) -> list[dict[str, str]]:
    sources = load_source_catalog()
    if not sources:
        return []

    prompt_l = prompt.lower()
    weighted: list[tuple[int, dict[str, str]]] = []
    for source in sources:
        text = " ".join([
            source.get("name", ""),
            source.get("category", ""),
            source.get("description", ""),
        ]).lower()
        score = 0
        score += _score_category(prompt_l, text)
        score += _score_name(prompt_l, source.get("name", "").lower())
        if score > 0:
            weighted.append((score, source))

    if not weighted:
        defaults = ["ShadCN UI", "21st Dev", "v0 by Vercel", "LandingHero AI Library", "PromptDen"]
        weighted = [
            (1, source)
            for source in sources
            if source.get("name") in defaults
        ]

    weighted.sort(key=lambda item: item[0], reverse=True)
    seen: set[str] = set()
    selected: list[dict[str, str]] = []
    for _, source in weighted:
        name = source.get("name", "")
        if name in seen:
            continue
        seen.add(name)
        selected.append({
            "name": name,
            "url": source.get("url", ""),
            "category": source.get("category", ""),
            "use_case": _use_case_for(source),
        })
        if len(selected) >= limit:
            break
    return selected


def _score_category(prompt: str, source_text: str) -> int:
    score = 0
    if any(term in prompt for term in ("ui", "frontend", "interface", "component", "design", "dashboard", "app")):
        score += 2 if any(term in source_text for term in ("component", "ui", "react", "tailwind", "shadcn")) else 0
    if any(term in prompt for term in ("landing", "hero", "marketing", "saas", "pricing")):
        score += 3 if any(term in source_text for term in ("landing", "hero", "marketing", "block", "template")) else 0
    if any(term in prompt for term in ("motion", "animate", "animation", "microinteraction")):
        score += 4 if any(term in source_text for term in ("motion", "animated", "animation", "framer")) else 0
    if any(term in prompt for term in ("prompt", "claude", "cursor", "v0", "bolt", "lovable", "ai builder")):
        score += 3 if any(term in source_text for term in ("prompt", "ai", "builder", "v0", "lovable", "bolt")) else 0
    if any(term in prompt for term in ("figma", "prototype", "wireframe")):
        score += 2 if any(term in source_text for term in ("figma", "design", "prototype")) else 0
    return score


def _score_name(prompt: str, name: str) -> int:
    aliases = {
        "shadcn": "shadcn",
        "hero ui": "heroui",
        "heroui": "heroui",
        "aceternity": "aceternity",
        "magic ui": "magic ui",
        "21st": "21st",
        "v0": "v0",
        "lovable": "lovable",
        "bolt": "bolt",
        "promptden": "promptden",
    }
    return sum(5 for term, alias in aliases.items() if term in prompt and alias in name)


def _use_case_for(source: dict[str, str]) -> str:
    category = source.get("category", "")
    description = source.get("description", "")
    if "AI UI Builders" in category:
        return "Use as a target surface or benchmark for prompt-to-UI output."
    if "Prompt Libraries" in category:
        return "Use as a prompt-pattern reference for sharper task framing."
    if "Animated" in category:
        return "Use for motion, transitions, and premium interaction ideas."
    if "Block" in category or "Landing" in category:
        return "Use for page structure, sections, and conversion-focused layout."
    if "Component" in category:
        return "Use for accessible components and design-system consistency."
    return description[:160] if description else "Use as a design or prompt reference."


def _clean_text(value: str) -> str:
    value = (
        value.replace("â€”", "-")
        .replace("â", "-")
        .replace("â†’", "->")
        .replace("â€“", "-")
    )
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\[\^\d+\]", "", value)
    value = value.replace("**", "").replace("\\&", "&")
    value = _LINK_RE.sub(lambda m: m.group("label"), value)
    return " ".join(value.strip().split())
