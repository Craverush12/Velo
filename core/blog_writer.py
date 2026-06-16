from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Awaitable, Callable

from core.blog_trends import slugify
from core.llm import complete


CompleteFn = Callable[..., Awaitable[str]]


async def generate_blog_article(
    topic: dict[str, Any],
    *,
    complete_fn: CompleteFn = complete,
    model: str | None = None,
) -> dict[str, Any]:
    selected_model = model or os.getenv("BLOG_GENERATION_MODEL") or os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    raw = await complete_fn(
        _system_prompt(),
        _user_message(topic),
        temperature=0.45,
        max_tokens=4096,
        model=selected_model,
    )
    article = _parse_json_object(raw)
    sources = topic.get("sources") if isinstance(topic.get("sources"), list) else []
    article["sources"] = sources
    article["model"] = selected_model
    article["trend_score"] = topic.get("trend_score", 0)
    if not article.get("slug"):
        article["slug"] = slugify(article.get("title") or topic.get("title") or "blog-post")
    return _normalize_article(article)


def _system_prompt() -> str:
    path = Path(__file__).parent / "prompts" / "blog_writer_system.md"
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _user_message(topic: dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "Write one original source-grounded ThinkVelocity blog post.",
            "topic": topic.get("title", ""),
            "trend_score": topic.get("trend_score", 0),
            "sources": topic.get("sources", []),
            "required_internal_links": ["/blog", "/extension-download", "/prompt-library"],
        },
        ensure_ascii=True,
    )


def _parse_json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end < start:
            raise ValueError("blog writer returned invalid JSON")
        parsed = json.loads(raw[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("blog writer must return a JSON object")
    return parsed


def _normalize_article(article: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(article.get("title") or "").strip(),
        "slug": slugify(str(article.get("slug") or article.get("title") or "blog-post")),
        "excerpt": str(article.get("excerpt") or "").strip(),
        "meta_title": str(article.get("meta_title") or "").strip(),
        "meta_description": str(article.get("meta_description") or "").strip(),
        "keywords": article.get("keywords") if isinstance(article.get("keywords"), list) else [],
        "content_markdown": str(article.get("content_markdown") or "").strip(),
        "content_html": str(article.get("content_html") or "").strip(),
        "faq": article.get("faq") if isinstance(article.get("faq"), list) else [],
        "sources": article.get("sources") if isinstance(article.get("sources"), list) else [],
        "model": str(article.get("model") or ""),
        "trend_score": article.get("trend_score", 0),
    }
