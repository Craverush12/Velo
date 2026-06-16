from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse
from typing import Any


def audit_blog_post(
    post: dict[str, Any],
    *,
    canonical_base_url: str = "https://thinkvelocity.ai/blog",
) -> dict[str, Any]:
    title = _text(post.get("title"))
    slug = _text(post.get("slug")).strip("/")
    excerpt = _text(post.get("excerpt"))
    meta_title = _text(post.get("meta_title"))
    meta_description = _text(post.get("meta_description"))
    content = _text(post.get("content_markdown") or post.get("content_html"))
    keywords = [str(item).strip() for item in post.get("keywords", []) if str(item).strip()]
    faq = post.get("faq") if isinstance(post.get("faq"), list) else []
    sources = post.get("sources") if isinstance(post.get("sources"), list) else []
    canonical_url = f"{canonical_base_url.rstrip('/')}/{slug}" if slug else canonical_base_url.rstrip("/")
    word_count = len(re.findall(r"\b[\w'-]+\b", content))

    missing: list[str] = []
    recommendations: list[str] = []
    seo_score = 100
    geo_score = 100
    eeat_score = 100

    seo_score = _check_range(meta_title, 30, 70, "meta title length should be 30-70 characters", missing, seo_score, 12)
    seo_score = _check_range(meta_description, 80, 170, "meta description length should be 80-170 characters", missing, seo_score, 12)
    seo_score = _check_range(title, 35, 90, "article title should be descriptive and 35-90 characters", recommendations, seo_score, 5)
    if not _has_heading(content, 1):
        seo_score -= 6
        recommendations.append("add one clear H1 heading")
    if not _has_heading(content, 2):
        seo_score -= 8
        recommendations.append("add H2 sections for scannability")
    if "/blog" not in content:
        seo_score -= 10
        missing.append("internal link to /blog is required")
    if "/extension-download" not in content:
        seo_score -= 10
        missing.append("internal link to /extension-download is required")
    if not keywords:
        seo_score -= 8
        missing.append("at least one target keyword is required")

    if len(sources) < 3:
        geo_score -= 24
        eeat_score -= 20
        missing.append("at least 3 cited sources are required for GEO and E-E-A-T")
    elif len(_source_domains(sources)) < 2:
        geo_score -= 10
        recommendations.append("use sources from at least two unique domains")
    if not _has_answer_first(content):
        geo_score -= 12
        recommendations.append("add an answer-first opening section for AEO/GEO")
    if not faq:
        geo_score -= 14
        seo_score -= 6
        missing.append("FAQ section is required for answer-engine coverage")
    if not _has_schema_ready_faq(faq):
        geo_score -= 6
        recommendations.append("make FAQ answers complete enough for FAQPage schema")
    if word_count < 250:
        geo_score -= 8
        eeat_score -= 8
        recommendations.append("expand original analysis for stronger AI citation coverage")

    official_count = sum(1 for source in sources if _looks_official_source(source))
    if sources and official_count == 0:
        eeat_score -= 10
        recommendations.append("include at least one official product blog, docs page, or changelog")
    if "ThinkVelocity" not in content and "thinkvelocity" not in content.lower():
        eeat_score -= 8
        recommendations.append("add a ThinkVelocity-specific product angle")
    if not _has_original_analysis(content):
        eeat_score -= 10
        recommendations.append("add concrete original analysis instead of only summarizing sources")

    seo_score = _clamp(seo_score)
    geo_score = _clamp(geo_score)
    eeat_score = _clamp(eeat_score)
    schema = _schema_jsonld(
        post,
        canonical_url=canonical_url,
        title=title,
        description=meta_description or excerpt,
        keywords=keywords,
        faq=faq,
        sources=sources,
    )
    return {
        "seo_score": seo_score,
        "geo_score": geo_score,
        "eeat_score": eeat_score,
        "canonical_url": canonical_url,
        "schema_jsonld": schema,
        "missing_items": _dedupe(missing),
        "recommendations": _dedupe(recommendations),
        "signals": {
            "word_count": word_count,
            "source_count": len(sources),
            "unique_source_domains": len(_source_domains(sources)),
            "official_source_count": official_count,
            "has_faq": bool(faq),
            "has_answer_first": _has_answer_first(content),
            "has_internal_blog_link": "/blog" in content,
            "has_extension_download_link": "/extension-download" in content,
        },
    }


def _schema_jsonld(
    post: dict[str, Any],
    *,
    canonical_url: str,
    title: str,
    description: str,
    keywords: list[str],
    faq: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    blog_post: dict[str, Any] = {
        "@type": "BlogPosting",
        "headline": title,
        "description": description,
        "url": canonical_url,
        "mainEntityOfPage": canonical_url,
        "datePublished": post.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "dateModified": post.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        "author": {"@type": "Organization", "name": "ThinkVelocity"},
        "publisher": {"@type": "Organization", "name": "ThinkVelocity", "url": "https://thinkvelocity.ai"},
    }
    if keywords:
        blog_post["keywords"] = keywords
    citations = [source.get("url") for source in sources if source.get("url")]
    if citations:
        blog_post["citation"] = citations

    graph: list[dict[str, Any]] = [blog_post]
    if faq:
        graph.append(
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": _text(item.get("question")),
                        "acceptedAnswer": {"@type": "Answer", "text": _text(item.get("answer"))},
                    }
                    for item in faq
                    if _text(item.get("question")) and _text(item.get("answer"))
                ],
            }
        )
    return {"@context": "https://schema.org", "@graph": graph}


def _check_range(value: str, low: int, high: int, message: str, bucket: list[str], score: int, penalty: int) -> int:
    if not low <= len(value) <= high:
        bucket.append(message)
        return score - penalty
    return score


def _has_heading(content: str, level: int) -> bool:
    return bool(re.search(rf"^{'#' * level}\s+\S+", content, flags=re.MULTILINE))


def _has_answer_first(content: str) -> bool:
    first = content[:500].lower()
    return any(marker in first for marker in ("quick answer", "answer:", "in short", "short answer", "what changed"))


def _has_schema_ready_faq(faq: list[dict[str, Any]]) -> bool:
    return any(len(_text(item.get("question"))) >= 10 and len(_text(item.get("answer"))) >= 20 for item in faq)


def _looks_official_source(source: dict[str, Any]) -> bool:
    domain = _domain(source.get("url") or source.get("domain"))
    title = _text(source.get("title")).lower()
    official_markers = ("blog.", "docs.", "developer.", "developers.", "changelog", "release", "news.microsoft.com")
    return any(marker in domain for marker in official_markers) or any(marker in title for marker in ("release notes", "changelog", "docs"))


def _has_original_analysis(content: str) -> bool:
    lowered = content.lower()
    return any(marker in lowered for marker in ("why it matters", "practical", "teams should", "workflow", "thinkvelocity"))


def _source_domains(sources: list[dict[str, Any]]) -> set[str]:
    return {_domain(source.get("url") or source.get("domain")) for source in sources if _domain(source.get("url") or source.get("domain"))}


def _domain(value: Any) -> str:
    clean = _text(value)
    if not clean:
        return ""
    parsed = urlparse(clean if "://" in clean else f"https://{clean}")
    return parsed.netloc.lower().removeprefix("www.")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _clamp(value: int) -> int:
    return max(0, min(100, int(value)))
