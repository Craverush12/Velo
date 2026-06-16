from __future__ import annotations

import os
import re
from typing import Any, Callable

import requests


HttpPost = Callable[..., Any]
HttpGet = Callable[..., Any]


def build_substack_variant(
    post: dict[str, Any],
    *,
    publication_url: str,
    canonical_base_url: str = "https://thinkvelocity.ai/blog",
) -> dict[str, Any]:
    slug = str(post.get("slug") or "").strip("/")
    canonical_url = f"{canonical_base_url.rstrip('/')}/{slug}" if slug else canonical_base_url.rstrip("/")
    title = str(post.get("title") or "ThinkVelocity AI Update").strip()
    excerpt = str(post.get("excerpt") or "").strip()
    keywords = [str(item) for item in post.get("keywords", []) if str(item).strip()]
    body = str(post.get("content_markdown") or "").strip()
    tags = _substack_tags(keywords)
    intro = (
        "This ThinkVelocity briefing tracks what changed in AI, developer tools, "
        "and prompt workflows, then turns it into practical actions for people "
        "using AI at work."
    )
    cta = (
        "\n\n---\n\n"
        "Try ThinkVelocity to turn rough ideas into clearer, context-rich prompts: "
        "https://thinkvelocity.ai\n\n"
        f"Canonical version: {canonical_url}"
    )
    return {
        "platform": "substack",
        "publication_url": publication_url.rstrip("/"),
        "title": title,
        "subtitle": excerpt[:160],
        "body_markdown": f"{intro}\n\n{body}{cta}",
        "canonical_url": canonical_url,
        "tags": tags,
    }


def build_devto_variant(
    post: dict[str, Any],
    *,
    canonical_base_url: str = "https://thinkvelocity.ai/blog",
) -> dict[str, Any]:
    slug = str(post.get("slug") or "").strip("/")
    canonical_url = f"{canonical_base_url.rstrip('/')}/{slug}" if slug else canonical_base_url.rstrip("/")
    title = str(post.get("title") or "ThinkVelocity AI Update").strip()
    excerpt = str(post.get("excerpt") or "").strip()
    body = str(post.get("content_markdown") or "").strip()
    keywords = [str(item) for item in post.get("keywords", []) if str(item).strip()]
    intro = (
        "This ThinkVelocity field note connects the latest AI and developer-tool "
        "updates to practical prompt workflows teams can use immediately."
    )
    cta = (
        "\n\n---\n\n"
        "ThinkVelocity helps teams turn rough intent into clearer, context-rich AI prompts: "
        "https://thinkvelocity.ai\n\n"
        f"Canonical version: {canonical_url}"
    )
    return {
        "platform": "devto",
        "title": title,
        "description": _short_description(excerpt or title),
        "body_markdown": f"{intro}\n\n{body}{cta}",
        "canonical_url": canonical_url,
        "tags": _devto_tags(keywords),
        "published": False,
    }


class SubstackPublisher:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        publication_url: str | None = None,
        publish_endpoint: str | None = None,
        auth_header: str | None = None,
        canonical_base_url: str | None = None,
        timeout_seconds: int = 30,
        http_post: HttpPost | None = None,
        http_get: HttpGet | None = None,
    ):
        self.api_key = api_key if api_key is not None else os.getenv("SUBSTACK_API_KEY", "")
        self.publication_url = (publication_url or os.getenv("SUBSTACK_PUBLICATION_URL", "")).rstrip("/")
        self.publish_endpoint = (publish_endpoint if publish_endpoint is not None else os.getenv("SUBSTACK_PUBLISH_ENDPOINT", "")).strip()
        self.auth_header = (auth_header or os.getenv("SUBSTACK_AUTH_HEADER", "X-API-Key")).strip() or "X-API-Key"
        self.canonical_base_url = (canonical_base_url or os.getenv("BLOG_CANONICAL_BASE_URL", "https://thinkvelocity.ai/blog")).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._post = http_post or requests.post
        self._get = http_get or requests.get

    @classmethod
    def from_env(cls) -> "SubstackPublisher":
        return cls()

    def status(self) -> dict[str, Any]:
        if not self.publication_url:
            return {"status": "not_configured", "reason": "SUBSTACK_PUBLICATION_URL is required"}
        reachable = self._publication_reachable()
        if not self.api_key:
            return {
                "status": "not_configured",
                "publication_url": self.publication_url,
                "publication_reachable": reachable,
                "reason": "SUBSTACK_API_KEY is required",
            }
        if not self.publish_endpoint:
            return {
                "status": "configured_without_publish_endpoint",
                "publication_url": self.publication_url,
                "publication_reachable": reachable,
                "reason": "SUBSTACK_PUBLISH_ENDPOINT is required before API posting can be attempted",
            }
        return {
            "status": "configured",
            "publication_url": self.publication_url,
            "publication_reachable": reachable,
            "publish_endpoint_configured": True,
        }

    def publish(self, post: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            return {"status": "not_configured", "reason": "SUBSTACK_API_KEY is required"}
        if not self.publication_url:
            return {"status": "not_configured", "reason": "SUBSTACK_PUBLICATION_URL is required"}
        if not self.publish_endpoint:
            return {
                "status": "not_configured",
                "reason": "SUBSTACK_PUBLISH_ENDPOINT is required before API posting can be attempted",
                "variant": build_substack_variant(
                    post,
                    publication_url=self.publication_url,
                    canonical_base_url=self.canonical_base_url,
                ),
            }
        variant = build_substack_variant(
            post,
            publication_url=self.publication_url,
            canonical_base_url=self.canonical_base_url,
        )
        payload = {
            "title": variant["title"],
            "subtitle": variant["subtitle"],
            "body_markdown": variant["body_markdown"],
            "canonical_url": variant["canonical_url"],
            "tags": variant["tags"],
            "published": False,
        }
        try:
            response = self._post(
                self.publish_endpoint,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            return {"status": "failed", "status_code": status_code, "reason": str(exc), "variant": variant}
        except requests.RequestException as exc:
            return {"status": "failed", "reason": str(exc), "variant": variant}
        data = _safe_json(response)
        return {
            "status": "draft_created",
            "platform": "substack",
            "publication_url": self.publication_url,
            "remote": data,
            "variant": variant,
        }

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ThinkVelocityBlogPublisher/1.0",
        }
        if self.auth_header.lower() == "authorization":
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            headers[self.auth_header] = self.api_key
        return headers

    def _publication_reachable(self) -> bool:
        if not self.publication_url:
            return False
        try:
            response = self._get(
                f"{self.publication_url}/api/v1/posts?limit=1",
                headers={"User-Agent": "ThinkVelocityBlogPublisher/1.0"},
                timeout=min(self.timeout_seconds, 10),
            )
            return 200 <= int(getattr(response, "status_code", 0)) < 400
        except requests.RequestException:
            return False


class DevToPublisher:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_url: str | None = None,
        me_url: str | None = None,
        canonical_base_url: str | None = None,
        timeout_seconds: int = 30,
        http_post: HttpPost | None = None,
        http_get: HttpGet | None = None,
    ):
        self.api_key = api_key if api_key is not None else os.getenv("DEVTO_API_KEY", "")
        self.api_url = (api_url or os.getenv("DEVTO_API_URL", "https://dev.to/api/articles")).strip()
        self.me_url = (me_url or os.getenv("DEVTO_ME_URL", "https://dev.to/api/users/me")).strip()
        self.canonical_base_url = (canonical_base_url or os.getenv("BLOG_CANONICAL_BASE_URL", "https://thinkvelocity.ai/blog")).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._post = http_post or requests.post
        self._get = http_get or requests.get

    @classmethod
    def from_env(cls) -> "DevToPublisher":
        return cls()

    def status(self) -> dict[str, Any]:
        if not self.api_key:
            return {"status": "not_configured", "reason": "DEVTO_API_KEY is required"}
        try:
            response = self._get(
                self.me_url,
                headers=self._headers(),
                timeout=min(self.timeout_seconds, 10),
            )
        except requests.RequestException as exc:
            return {"status": "failed", "reason": str(exc)}
        if int(getattr(response, "status_code", 0)) == 401:
            return {"status": "auth_failed", "reason": "DEVTO_API_KEY was rejected"}
        if not 200 <= int(getattr(response, "status_code", 0)) < 300:
            return {
                "status": "failed",
                "status_code": getattr(response, "status_code", None),
                "reason": getattr(response, "text", "")[:200],
            }
        user = _safe_json(response)
        safe_user = {key: user[key] for key in ("id", "username", "name") if key in user}
        return {"status": "configured", "platform": "devto", "user": safe_user}

    def publish(self, post: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            return {"status": "not_configured", "reason": "DEVTO_API_KEY is required"}
        variant = build_devto_variant(post, canonical_base_url=self.canonical_base_url)
        payload = {
            "article": {
                "title": variant["title"],
                "body_markdown": variant["body_markdown"],
                "published": False,
                "tags": variant["tags"],
                "canonical_url": variant["canonical_url"],
                "description": variant["description"],
            }
        }
        try:
            response = self._post(
                self.api_url,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            return {"status": "failed", "status_code": status_code, "reason": str(exc), "variant": variant}
        except requests.RequestException as exc:
            return {"status": "failed", "reason": str(exc), "variant": variant}
        return {
            "status": "draft_created",
            "platform": "devto",
            "remote": _safe_json(response),
            "variant": variant,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "ThinkVelocityBlogPublisher/1.0",
            "api-key": self.api_key,
        }


def _safe_json(response: Any) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {"data": data}


def _substack_tags(keywords: list[str]) -> list[str]:
    base = ["AI", "Prompt Engineering", "Productivity"]
    for keyword in keywords:
        if keyword and keyword not in base:
            base.append(keyword[:32])
        if len(base) >= 5:
            break
    return base[:5]


def _devto_tags(keywords: list[str]) -> list[str]:
    tags = ["ai", "productivity", "promptengineering"]
    for keyword in keywords:
        clean = re.sub(r"[^a-z0-9]", "", keyword.lower())[:30]
        if clean and clean not in tags:
            tags.append(clean)
        if len(tags) >= 4:
            break
    return tags[:4]


def _short_description(value: str, max_length: int = 155) -> str:
    clean = " ".join(str(value or "").split())
    if len(clean) <= max_length:
        return clean
    return clean[: max_length - 1].rstrip() + "..."
