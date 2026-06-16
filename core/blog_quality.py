from __future__ import annotations

import re
from typing import Any

from core.blog_seo_audit import audit_blog_post


def validate_blog_post(
    post: dict[str, Any],
    *,
    existing_slugs: set[str] | None = None,
    min_word_count: int = 700,
    min_seo_score: int = 65,
    min_geo_score: int = 65,
    min_eeat_score: int = 60,
) -> dict[str, Any]:
    errors: list[str] = []
    score = 100
    existing_slugs = existing_slugs or set()

    slug = str(post.get("slug") or "").strip()
    if not slug:
        errors.append("slug is required")
    elif slug in existing_slugs:
        errors.append("slug already exists")

    sources = post.get("sources") if isinstance(post.get("sources"), list) else []
    if len(sources) < 3:
        errors.append("post needs at least 3 sources")

    content = str(post.get("content_markdown") or post.get("content_html") or "")
    word_count = len(re.findall(r"\b[\w'-]+\b", content))
    if word_count < min_word_count:
        errors.append(f"post needs at least {min_word_count} words")

    meta_title = str(post.get("meta_title") or "")
    if not 30 <= len(meta_title) <= 70:
        errors.append("meta_title must be 30-70 characters")

    meta_description = str(post.get("meta_description") or "")
    if not 80 <= len(meta_description) <= 170:
        errors.append("meta_description must be 80-170 characters")

    if "/blog" not in content or "/extension-download" not in content:
        errors.append("post must include internal links to /blog and /extension-download")

    if not post.get("faq"):
        errors.append("post must include at least one FAQ item")

    copied = _copied_source_snippets(content, sources)
    if copied:
        errors.append("post appears to copy source snippet text")

    seo_audit = audit_blog_post(post)
    if seo_audit["seo_score"] < min_seo_score:
        errors.append(f"seo_score must be at least {min_seo_score}")
    if seo_audit["geo_score"] < min_geo_score:
        errors.append(f"geo_score must be at least {min_geo_score}")
    if seo_audit["eeat_score"] < min_eeat_score:
        errors.append(f"eeat_score must be at least {min_eeat_score}")
    for item in seo_audit["missing_items"]:
        if item not in errors:
            errors.append(item)

    score -= min(90, len(errors) * 12)
    score = int(round((score * 0.7) + (((seo_audit["seo_score"] + seo_audit["geo_score"] + seo_audit["eeat_score"]) / 3) * 0.3)))
    if len(sources) >= 3:
        score += min(6, len(sources) - 3)
    if word_count >= max(min_word_count, 900):
        score += 4
    score = max(0, min(100, score))

    return {
        "status": "ready" if not errors else "draft",
        "quality_score": score,
        "validation_errors": errors,
        "word_count": word_count,
        "seo_score": seo_audit["seo_score"],
        "geo_score": seo_audit["geo_score"],
        "eeat_score": seo_audit["eeat_score"],
        "schema_jsonld": seo_audit["schema_jsonld"],
        "seo_audit": seo_audit,
    }


def _copied_source_snippets(content: str, sources: list[dict[str, Any]]) -> bool:
    compact_content = _compact(content)
    for source in sources:
        snippet = str(source.get("snippet") or "")
        words = re.findall(r"\b[\w'-]+\b", snippet)
        if len(words) < 12:
            continue
        phrase = _compact(" ".join(words[:16]))
        if phrase and phrase in compact_content:
            return True
    return False


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value.lower())).strip()
