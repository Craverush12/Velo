from __future__ import annotations

import logging
import math
import os
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


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

# ---------------------------------------------------------------------------
# Reddit intelligence scraper
# ---------------------------------------------------------------------------

_REDDIT_SUBREDDITS: list[str] = [
    "MachineLearning",
    "programming",
    "SideProject",
    "AIAssistants",
    "artificial",
    "productivity",
    "learnprogramming",
]

_REDDIT_UA = "ThinkVelocity-Intel/1.0"
_REDDIT_ENDPOINT = "https://www.reddit.com/r/{subreddit}/hot.json?limit=25"
_REDDIT_SOURCE_SCORE = 45
_REDDIT_TIMEOUT = 15

# Normalisation caps used by _score_reddit_post to keep output in [0, 1].
# log1p(10_000) ≈ 9.21  — practically all real posts fall under this ceiling.
_SCORE_CAP = math.log1p(10_000)
_COMMENTS_CAP = math.log1p(1_000)


def _score_reddit_post(post: dict[str, Any]) -> float:
    """Return a relevance score in [0.0, 1.0] for a Reddit post data dict.

    Returns 0.0 for posts that fail quality thresholds:
      - reddit score < 5
      - num_comments < 2
      - empty selftext AND title shorter than 20 characters
    """
    score = post.get("score", 0)
    num_comments = post.get("num_comments", 0)
    title = str(post.get("title") or "")
    selftext = str(post.get("selftext") or "").strip()

    if score < 5:
        return 0.0
    if num_comments < 2:
        return 0.0
    if not selftext and len(title) < 20:
        return 0.0

    # Logarithmic normalisation so viral posts don't dominate.
    score_norm = min(math.log1p(score) / _SCORE_CAP, 1.0)
    comments_norm = min(math.log1p(num_comments) / _COMMENTS_CAP, 1.0)
    return round((score_norm * 0.6 + comments_norm * 0.4), 4)


def collect_reddit_sources(
    subreddits: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch hot posts from each subreddit and normalise them into the same
    dict shape as :func:`collect_trend_sources`.

    Degrade-open: any subreddit that fails (network error, bad JSON, non-200
    status) returns [] for that source; the rest continue.  Never raises.

    Rate-limited: 1-second sleep between consecutive subreddit requests.
    """
    targets = subreddits if subreddits is not None else _REDDIT_SUBREDDITS
    if not targets:
        return []

    all_items: list[dict[str, Any]] = []
    checked_at = datetime.now(timezone.utc).isoformat()

    for idx, subreddit in enumerate(targets):
        if idx > 0:
            time.sleep(1)

        url = _REDDIT_ENDPOINT.format(subreddit=subreddit)
        try:
            response = requests.get(
                url,
                headers={"User-Agent": _REDDIT_UA},
                timeout=_REDDIT_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.warning("Reddit fetch failed for r/%s: %s", subreddit, exc)
            continue

        try:
            children = data.get("data", {}).get("children", [])
        except Exception as exc:
            logger.warning("Reddit data extraction failed for r/%s: %s", subreddit, exc)
            continue

        for rank, child in enumerate(children, start=1):
            post = child.get("data", {})
            relevance = _score_reddit_post(post)
            if relevance == 0.0:
                continue

            title = str(post.get("title") or "").strip()
            selftext = str(post.get("selftext") or "").strip()[:400]
            link = str(post.get("url") or "").strip()

            if not title or not link:
                continue

            domain = _domain(link)
            all_items.append(
                {
                    "title": title,
                    "url": link,
                    "domain": domain,
                    "snippet": selftext,
                    "published_label": "",
                    "source": f"reddit.com/r/{subreddit}",
                    "query": f"r/{subreddit}",
                    "rank": rank,
                    "checked_at": checked_at,
                    "source_score": _REDDIT_SOURCE_SCORE,
                    # Extra Reddit metadata preserved for downstream use.
                    "reddit_score": post.get("score", 0),
                    "reddit_comments": post.get("num_comments", 0),
                    "reddit_created_utc": post.get("created_utc"),
                    "reddit_subreddit": str(post.get("subreddit") or subreddit),
                    "relevance_score": relevance,
                }
            )

    return all_items


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
    include_reddit: bool = True,
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for query in queries or queries_from_env():
        payload = client.news(query, num=results_per_query)
        sources.extend(normalize_serper_news(payload, query=query))
    if include_reddit:
        sources.extend(collect_reddit_sources())
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
