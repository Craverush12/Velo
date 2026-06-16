from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests


SERPER_NEWS_URL = "https://google.serper.dev/news"
SERPER_SEARCH_URL = "https://google.serper.dev/search"

DEFAULT_BLOG_QUERIES = [
    "latest AI model updates",
    "developer tools news",
    "software updates today",
    "AI productivity tools news",
    "startup technology news",
    "cybersecurity updates",
    "automation tools AI",
]

_OFFICIAL_HINTS = (
    "blog.",
    "developer.",
    "developers.",
    "docs.",
    "news.",
    "changelog",
    "release",
)
_OFFICIAL_DOMAINS = {
    "openai.com",
    "anthropic.com",
    "google.com",
    "blog.google",
    "developers.googleblog.com",
    "microsoft.com",
    "news.microsoft.com",
    "apple.com",
    "developer.apple.com",
    "github.blog",
    "cloudflare.com",
    "aws.amazon.com",
    "nvidia.com",
    "huggingface.co",
}
_PRESS_DOMAINS = {
    "techcrunch.com",
    "theverge.com",
    "wired.com",
    "arstechnica.com",
    "venturebeat.com",
    "zdnet.com",
    "thenextweb.com",
    "hindustantimes.com",
}
_REJECT_DOMAINS = {
    "pinterest.com",
    "youtube.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
}


class SerperClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        region: str | None = None,
        language: str | None = None,
        timeout_seconds: int = 20,
    ):
        self.api_key = api_key or os.getenv("SERPER_API_KEY", "")
        self.region = region or os.getenv("BLOG_AUTOGEN_REGION", "in")
        self.language = language or os.getenv("BLOG_AUTOGEN_LANGUAGE", "en")
        self.timeout_seconds = timeout_seconds

    def news(self, query: str, *, num: int = 10) -> dict[str, Any]:
        return self._post(SERPER_NEWS_URL, query=query, num=num)

    def search(self, query: str, *, num: int = 10) -> dict[str, Any]:
        return self._post(SERPER_SEARCH_URL, query=query, num=num)

    def _post(self, url: str, *, query: str, num: int) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("SERPER_API_KEY is not configured")
        response = requests.post(
            url,
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
            json={"q": query, "gl": self.region, "hl": self.language, "num": num},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()


def queries_from_env() -> list[str]:
    raw = os.getenv("BLOG_AUTOGEN_QUERIES", "").strip()
    if not raw:
        return list(DEFAULT_BLOG_QUERIES)
    return [item.strip() for item in raw.split(",") if item.strip()]


def collect_trend_sources(
    client: SerperClient,
    *,
    queries: list[str] | None = None,
    results_per_query: int = 10,
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for query in queries or queries_from_env():
        payload = client.news(query, num=results_per_query)
        sources.extend(normalize_serper_news(payload, query=query))
    return dedupe_sources(sources)


def normalize_serper_news(payload: dict[str, Any], *, query: str) -> list[dict[str, Any]]:
    items = payload.get("news") or payload.get("organic") or []
    checked_at = datetime.now(timezone.utc).isoformat()
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        link = str(item.get("link") or "").strip()
        title = str(item.get("title") or "").strip()
        if not link or not title:
            continue
        domain = _domain(link)
        if not domain or _root_domain(domain) in _REJECT_DOMAINS:
            continue
        normalized.append(
            {
                "title": title,
                "url": link,
                "domain": domain,
                "snippet": str(item.get("snippet") or "").strip(),
                "published_label": str(item.get("date") or "").strip(),
                "source": str(item.get("source") or domain).strip(),
                "query": query,
                "rank": index,
                "checked_at": checked_at,
                "source_score": source_score(domain, link),
            }
        )
    normalized.sort(key=lambda row: (-row["source_score"], row["rank"]))
    return normalized


def dedupe_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for source in sources:
        key = source.get("url", "").rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def select_topic_clusters(
    sources: list[dict[str, Any]],
    *,
    existing_slugs: set[str] | None = None,
    max_topics: int = 1,
    min_sources: int = 1,
) -> list[dict[str, Any]]:
    existing_slugs = existing_slugs or set()
    ranked = sorted(sources, key=lambda row: (-row.get("source_score", 0), row.get("rank", 99)))
    topics: list[dict[str, Any]] = []
    used_queries: set[str] = set()
    for source in ranked:
        query = source.get("query", "")
        if query in used_queries:
            continue
        slug = slugify(source["title"])
        if slug in existing_slugs:
            continue
        related = [
            row
            for row in ranked
            if row.get("query", "") == query
            and slugify(row.get("title", "")) not in existing_slugs
            and (row["url"] == source["url"] or _token_overlap(source["title"], row["title"]) >= 0.0)
        ]
        if len(related) < min_sources:
            related = [source]
        used_queries.add(query)
        topics.append(
            {
                "title": source["title"],
                "slug": slug,
                "query": query,
                "trend_score": sum(row.get("source_score", 0) for row in related) + max(0, 12 - source.get("rank", 12)),
                "sources": related[:5],
            }
        )
        if len(topics) >= max_topics:
            break
    return topics


def source_score(domain: str, url: str = "") -> int:
    root = _root_domain(domain)
    lowered = f"{domain} {url}".lower()
    if domain in _OFFICIAL_DOMAINS or root in _OFFICIAL_DOMAINS or any(hint in lowered for hint in _OFFICIAL_HINTS):
        return 100
    if root in _PRESS_DOMAINS or domain in _PRESS_DOMAINS:
        return 75
    if root in {"reddit.com", "news.ycombinator.com", "producthunt.com"}:
        return 45
    return 35


def slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")[:160]


def _domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().removeprefix("www.")


def _root_domain(domain: str) -> str:
    parts = domain.split(".")
    if len(parts) <= 2:
        return domain
    return ".".join(parts[-2:])


def _token_overlap(left: str, right: str) -> float:
    left_tokens = {token for token in re.findall(r"[a-z0-9]+", left.lower()) if len(token) > 3}
    right_tokens = {token for token in re.findall(r"[a-z0-9]+", right.lower()) if len(token) > 3}
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))
