from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.admin import _audit, get_admin_store, require_admin
from core.blog_browser_runner import SUPPORTED_BROWSER_PLATFORMS, build_browser_variant
from core.blog_outbound import DevToPublisher, SubstackPublisher
from core.blog_service import BlogGenerationService
from storage.admin_store import AdminStore
from storage.blog_store import BlogStore, get_default_blog_store


router = APIRouter(prefix="/admin/api", tags=["blog-admin"])


class BlogRunRequest(BaseModel):
    max_posts: int = Field(default=1, ge=1, le=5)


class BlogPostPatch(BaseModel):
    slug: str | None = None
    title: str | None = None
    excerpt: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    keywords: list[str] | None = None
    content_markdown: str | None = None
    content_html: str | None = None
    faq: list[dict[str, Any]] | None = None
    sources: list[dict[str, Any]] | None = None
    status: str | None = None


class BlogRejectRequest(BaseModel):
    reason: str = ""


def get_blog_store() -> BlogStore:
    return get_default_blog_store()


def get_blog_service(store: BlogStore = Depends(get_blog_store)) -> BlogGenerationService:
    return BlogGenerationService(store=store)


def get_substack_publisher() -> SubstackPublisher:
    return SubstackPublisher.from_env()


def get_devto_publisher() -> DevToPublisher:
    return DevToPublisher.from_env()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_outbound_ready(post: dict[str, Any]) -> None:
    if post.get("status") != "ready":
        raise HTTPException(status_code=409, detail="Blog post must be ready before outbound publishing")


def _existing_outbound_publication(post: dict[str, Any], platform: str) -> dict[str, Any] | None:
    for publication in post.get("outbound_publications") or []:
        if publication.get("platform") == platform and publication.get("status") == "draft_created":
            return publication
    return None


def _record_outbound_publication(
    blog_store: BlogStore,
    post: dict[str, Any],
    *,
    platform: str,
    result: dict[str, Any],
) -> None:
    publications = list(post.get("outbound_publications") or [])
    publications.append(
        {
            "platform": platform,
            "status": result["status"],
            "remote": result.get("remote", {}),
            "canonical_url": result.get("variant", {}).get("canonical_url", ""),
            "created_at": _now_iso(),
        }
    )
    blog_store.update_post(post["id"], {"outbound_publications": publications})


def _duplicate_result(platform: str, publication: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "duplicate_skipped",
        "platform": platform,
        "reason": f"Outbound draft already exists for {platform}",
        "publication": publication,
    }


@router.post("/blog-generator/run")
async def run_blog_generator(
    body: BlogRunRequest,
    request: Request,
    store: AdminStore = Depends(get_admin_store),
    service: BlogGenerationService = Depends(get_blog_service),
    current: dict[str, Any] = Depends(require_admin("content:manage", csrf=True)),
):
    result = await service.run_once(trigger="manual", max_posts=body.max_posts)
    _audit(
        store=store,
        request=request,
        actor=current["admin"],
        action="blog_generator.run",
        entity_type="blog_generator",
        entity_id=result.get("run_id", ""),
        before=None,
        after=result,
    )
    return result


@router.get("/blog-generator/status")
def blog_generator_status(
    store: BlogStore = Depends(get_blog_store),
    current: dict[str, Any] = Depends(require_admin("content:view")),
):
    runs = store.list_runs(page_size=10)
    return {"runs": runs["items"], "total": runs["total"]}


@router.get("/blog-outbound/substack/status")
def substack_outbound_status(
    publisher: SubstackPublisher = Depends(get_substack_publisher),
    current: dict[str, Any] = Depends(require_admin("content:view")),
):
    return publisher.status()


@router.get("/blog-outbound/devto/status")
def devto_outbound_status(
    publisher: DevToPublisher = Depends(get_devto_publisher),
    current: dict[str, Any] = Depends(require_admin("content:view")),
):
    return publisher.status()


@router.get("/blog-outbound/browser/platforms")
def browser_outbound_platforms(
    current: dict[str, Any] = Depends(require_admin("content:view")),
):
    return {
        "method": "browser",
        "draft_first": True,
        "platforms": [
            {
                "platform": platform,
                "status": "queue_supported",
                "requires_local_login": True,
            }
            for platform in sorted(SUPPORTED_BROWSER_PLATFORMS)
        ],
    }


@router.get("/blog-outbound/browser/jobs")
def list_browser_outbound_jobs(
    status: str = "",
    platform: str = "",
    page: int = 1,
    page_size: int = 25,
    store: BlogStore = Depends(get_blog_store),
    current: dict[str, Any] = Depends(require_admin("content:view")),
):
    return store.list_outbound_jobs(
        status=status,
        platform=platform,
        method="browser",
        page=page,
        page_size=page_size,
    )


@router.get("/blog-posts")
def list_blog_posts(
    status: str = "",
    search: str = "",
    page: int = 1,
    page_size: int = 25,
    store: BlogStore = Depends(get_blog_store),
    current: dict[str, Any] = Depends(require_admin("content:view")),
):
    return store.list_posts(status=status, search=search, page=page, page_size=page_size)


@router.get("/blog-posts/export")
def export_blog_posts(
    status: str = "ready",
    store: BlogStore = Depends(get_blog_store),
    current: dict[str, Any] = Depends(require_admin("content:view")),
):
    return store.export_posts(status=status)


@router.get("/blog-posts/{post_id}")
def get_blog_post(
    post_id: str,
    store: BlogStore = Depends(get_blog_store),
    current: dict[str, Any] = Depends(require_admin("content:view")),
):
    post = store.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return post


@router.get("/blog-posts/{post_id}/seo-audit")
def get_blog_post_seo_audit(
    post_id: str,
    store: BlogStore = Depends(get_blog_store),
    current: dict[str, Any] = Depends(require_admin("content:view")),
):
    post = store.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Blog post not found")
    stored_audit = post.get("seo_audit") if isinstance(post.get("seo_audit"), dict) else {}
    return {
        "post_id": post["id"],
        "slug": post["slug"],
        "title": post["title"],
        "seo_score": post.get("seo_score", 0),
        "geo_score": post.get("geo_score", 0),
        "eeat_score": post.get("eeat_score", 0),
        "schema_jsonld": post.get("schema_jsonld", {}),
        "seo_audit": stored_audit,
        "missing_items": stored_audit.get("missing_items", []),
        "recommendations": stored_audit.get("recommendations", []),
    }


@router.patch("/blog-posts/{post_id}")
def update_blog_post(
    post_id: str,
    body: BlogPostPatch,
    request: Request,
    admin_store: AdminStore = Depends(get_admin_store),
    blog_store: BlogStore = Depends(get_blog_store),
    current: dict[str, Any] = Depends(require_admin("content:manage", csrf=True)),
):
    before = blog_store.get_post(post_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Blog post not found")
    try:
        after = blog_store.update_post(post_id, body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(
        store=admin_store,
        request=request,
        actor=current["admin"],
        action="blog_posts.update",
        entity_type="blog_post",
        entity_id=post_id,
        before=before,
        after=after,
    )
    return after


@router.post("/blog-posts/{post_id}/approve")
def approve_blog_post(
    post_id: str,
    request: Request,
    admin_store: AdminStore = Depends(get_admin_store),
    blog_store: BlogStore = Depends(get_blog_store),
    current: dict[str, Any] = Depends(require_admin("content:manage", csrf=True)),
):
    before = blog_store.get_post(post_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Blog post not found")
    after = blog_store.approve_post(post_id)
    _audit(
        store=admin_store,
        request=request,
        actor=current["admin"],
        action="blog_posts.approve",
        entity_type="blog_post",
        entity_id=post_id,
        before=before,
        after=after,
    )
    return after


@router.post("/blog-posts/{post_id}/reject")
def reject_blog_post(
    post_id: str,
    body: BlogRejectRequest,
    request: Request,
    admin_store: AdminStore = Depends(get_admin_store),
    blog_store: BlogStore = Depends(get_blog_store),
    current: dict[str, Any] = Depends(require_admin("content:manage", csrf=True)),
):
    before = blog_store.get_post(post_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Blog post not found")
    after = blog_store.reject_post(post_id, reason=body.reason)
    _audit(
        store=admin_store,
        request=request,
        actor=current["admin"],
        action="blog_posts.reject",
        entity_type="blog_post",
        entity_id=post_id,
        before=before,
        after=after,
    )
    return after


@router.post("/blog-posts/{post_id}/outbound/substack")
def publish_blog_post_to_substack(
    post_id: str,
    request: Request,
    admin_store: AdminStore = Depends(get_admin_store),
    blog_store: BlogStore = Depends(get_blog_store),
    publisher: SubstackPublisher = Depends(get_substack_publisher),
    current: dict[str, Any] = Depends(require_admin("content:manage", csrf=True)),
):
    post = blog_store.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Blog post not found")
    _ensure_outbound_ready(post)
    existing = _existing_outbound_publication(post, "substack")
    if existing is not None:
        return _duplicate_result("substack", existing)
    result = publisher.publish(post)
    if result.get("status") == "draft_created":
        _record_outbound_publication(blog_store, post, platform="substack", result=result)
    _audit(
        store=admin_store,
        request=request,
        actor=current["admin"],
        action="blog_posts.outbound.substack",
        entity_type="blog_post",
        entity_id=post_id,
        before=post,
        after={k: v for k, v in result.items() if k != "variant"},
    )
    return result


@router.post("/blog-posts/{post_id}/outbound/devto")
def publish_blog_post_to_devto(
    post_id: str,
    request: Request,
    admin_store: AdminStore = Depends(get_admin_store),
    blog_store: BlogStore = Depends(get_blog_store),
    publisher: DevToPublisher = Depends(get_devto_publisher),
    current: dict[str, Any] = Depends(require_admin("content:manage", csrf=True)),
):
    post = blog_store.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Blog post not found")
    _ensure_outbound_ready(post)
    existing = _existing_outbound_publication(post, "devto")
    if existing is not None:
        return _duplicate_result("devto", existing)
    result = publisher.publish(post)
    if result.get("status") == "draft_created":
        _record_outbound_publication(blog_store, post, platform="devto", result=result)
    _audit(
        store=admin_store,
        request=request,
        actor=current["admin"],
        action="blog_posts.outbound.devto",
        entity_type="blog_post",
        entity_id=post_id,
        before=post,
        after={k: v for k, v in result.items() if k != "variant"},
    )
    return result


@router.post("/blog-posts/{post_id}/outbound/browser/{platform}")
def queue_blog_post_for_browser_outbound(
    post_id: str,
    platform: str,
    request: Request,
    admin_store: AdminStore = Depends(get_admin_store),
    blog_store: BlogStore = Depends(get_blog_store),
    current: dict[str, Any] = Depends(require_admin("content:manage", csrf=True)),
):
    clean_platform = platform.strip().lower()
    if clean_platform not in SUPPORTED_BROWSER_PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported browser outbound platform")
    post = blog_store.get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Blog post not found")
    _ensure_outbound_ready(post)
    existing_publication = _existing_outbound_publication(post, clean_platform)
    if existing_publication is not None:
        return _duplicate_result(clean_platform, existing_publication)
    if blog_store.has_active_outbound_job(post_id=post_id, platform=clean_platform, method="browser"):
        return {
            "status": "duplicate_skipped",
            "platform": clean_platform,
            "reason": f"Outbound browser job already exists for {clean_platform}",
        }
    payload = build_browser_variant(post, platform=clean_platform)
    job = blog_store.create_outbound_job(
        post_id=post_id,
        platform=clean_platform,
        method="browser",
        payload=payload,
    )
    _audit(
        store=admin_store,
        request=request,
        actor=current["admin"],
        action=f"blog_posts.outbound.browser.{clean_platform}.queue",
        entity_type="blog_post",
        entity_id=post_id,
        before=post,
        after=job,
    )
    return job
