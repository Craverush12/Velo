from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Any, Callable

from core.blog_outbound import build_substack_variant
from storage.blog_store import BlogStore, get_default_blog_store


SUPPORTED_BROWSER_PLATFORMS = {"medium", "substack"}
DEFAULT_PROFILE_DIR = Path(os.getenv("BLOG_BROWSER_PROFILE_DIR", "storage/browser-profiles/outbound")).resolve()
DEFAULT_SCREENSHOT_DIR = Path(os.getenv("BLOG_BROWSER_SCREENSHOT_DIR", "storage/browser-screenshots")).resolve()


class BrowserLoginRequired(RuntimeError):
    pass


class BrowserPublishFailed(RuntimeError):
    pass


def build_browser_variant(
    post: dict[str, Any],
    *,
    platform: str,
    canonical_base_url: str = "https://thinkvelocity.ai/blog",
    substack_publication_url: str = "https://thinkvelocity.substack.com",
) -> dict[str, Any]:
    clean_platform = _clean_platform(platform)
    if clean_platform not in SUPPORTED_BROWSER_PLATFORMS:
        raise ValueError(f"unsupported browser platform: {platform}")
    if clean_platform == "substack":
        variant = build_substack_variant(
            post,
            publication_url=substack_publication_url,
            canonical_base_url=canonical_base_url,
        )
        return {
            **variant,
            "status": "draft",
            "target_url": f"{substack_publication_url.rstrip('/')}/publish/post",
            "method": "browser",
        }

    slug = str(post.get("slug") or "").strip("/")
    canonical_url = f"{canonical_base_url.rstrip('/')}/{slug}" if slug else canonical_base_url.rstrip("/")
    title = str(post.get("title") or "ThinkVelocity AI Update").strip()
    excerpt = str(post.get("excerpt") or "").strip()
    body = str(post.get("content_markdown") or "").strip()
    keywords = [str(item) for item in post.get("keywords", []) if str(item).strip()]
    intro = (
        "This ThinkVelocity field note connects current AI and developer-tool news "
        "to practical prompt workflows for teams using AI every day."
    )
    cta = (
        "\n\n---\n\n"
        "ThinkVelocity helps teams turn rough intent into clearer, context-rich prompts: "
        "https://thinkvelocity.ai?utm_source=medium&utm_medium=outbound_blog&utm_campaign=auto_blog\n\n"
        f"Canonical version: {canonical_url}"
    )
    return {
        "platform": "medium",
        "method": "browser",
        "status": "draft",
        "target_url": "https://medium.com/new-story",
        "title": title,
        "subtitle": excerpt[:140],
        "body_markdown": f"{intro}\n\n{body}{cta}",
        "canonical_url": canonical_url,
        "tags": _medium_tags(keywords),
    }


class BrowserOutboundRunner:
    def __init__(
        self,
        *,
        store: BlogStore | None = None,
        profile_dir: Path | str | None = None,
        screenshot_dir: Path | str | None = None,
        headless: bool = False,
        timeout_ms: int = 60000,
        publisher_factory: Callable[[], Any] | None = None,
    ):
        self.store = store or get_default_blog_store()
        self.profile_dir = Path(profile_dir or DEFAULT_PROFILE_DIR).resolve()
        self.screenshot_dir = Path(screenshot_dir or DEFAULT_SCREENSHOT_DIR).resolve()
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.publisher_factory = publisher_factory

    def run_next(self, *, platforms: list[str] | None = None) -> dict[str, Any]:
        job = self.store.claim_next_outbound_job(platforms=platforms, method="browser")
        if job is None:
            return {"status": "idle", "reason": "no queued browser outbound jobs"}
        return self.run_job(job)

    def run_job(self, job: dict[str, Any]) -> dict[str, Any]:
        post = self.store.get_post(job["post_id"])
        if post is None:
            return self._finish_failed(job, "Blog post not found")
        if post.get("status") != "ready":
            return self._finish_failed(job, "Blog post must be ready before browser outbound publishing")
        try:
            variant = build_browser_variant(
                post,
                platform=job["platform"],
                canonical_base_url=os.getenv("BLOG_CANONICAL_BASE_URL", "https://thinkvelocity.ai/blog"),
                substack_publication_url=os.getenv("SUBSTACK_PUBLICATION_URL", "https://thinkvelocity.substack.com"),
            )
            publisher = self.publisher_factory() if self.publisher_factory else BrowserDraftPublisher(
                profile_dir=self.profile_dir,
                screenshot_dir=self.screenshot_dir,
                headless=self.headless,
                timeout_ms=self.timeout_ms,
            )
            result = publisher.create_draft(variant)
        except Exception as exc:
            return self._finish_failed(job, str(exc))

        publication = {
            "platform": job["platform"],
            "status": "draft_created",
            "remote": {
                "url": result.get("url", ""),
                "screenshot_path": result.get("screenshot_path", ""),
                "method": "browser",
            },
            "canonical_url": variant["canonical_url"],
            "created_at": _nowish(),
        }
        publications = list(post.get("outbound_publications") or [])
        publications.append(publication)
        self.store.update_post(post["id"], {"outbound_publications": publications})
        finished = self.store.finish_outbound_job(job["id"], status="completed", result=result)
        return {"status": "completed", "job": finished, "publication": publication}

    def _finish_failed(self, job: dict[str, Any], error: str) -> dict[str, Any]:
        finished = self.store.finish_outbound_job(job["id"], status="failed", error=error)
        return {"status": "failed", "job": finished, "error": error}


class BrowserDraftPublisher:
    def __init__(
        self,
        *,
        profile_dir: Path,
        screenshot_dir: Path,
        headless: bool,
        timeout_ms: int = 60000,
    ):
        self.profile_dir = profile_dir
        self.screenshot_dir = screenshot_dir
        self.headless = headless
        self.timeout_ms = timeout_ms

    def create_draft(self, variant: dict[str, Any]) -> dict[str, Any]:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserPublishFailed("Install Playwright with `pip install playwright` and `python -m playwright install chromium`.") from exc

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(self.profile_dir),
                headless=self.headless,
                viewport={"width": 1440, "height": 1000},
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(self.timeout_ms)
            try:
                if variant["platform"] == "medium":
                    result = MediumBrowserAdapter().create_draft(page, variant)
                elif variant["platform"] == "substack":
                    result = SubstackBrowserAdapter().create_draft(page, variant)
                else:
                    raise ValueError(f"unsupported browser platform: {variant['platform']}")
            except PlaywrightTimeoutError as exc:
                raise BrowserPublishFailed(f"Timed out while creating {variant['platform']} draft") from exc
            finally:
                screenshot_path = self.screenshot_dir / f"{variant['platform']}-{int(time.time())}.png"
                try:
                    page.screenshot(path=str(screenshot_path), full_page=True)
                except Exception:
                    screenshot_path = Path("")
                context.close()
            result.setdefault("screenshot_path", str(screenshot_path) if screenshot_path else "")
            return result

    def open_login_session(self, platform: str) -> dict[str, Any]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BrowserPublishFailed("Install Playwright with `pip install playwright` and `python -m playwright install chromium`.") from exc

        clean_platform = _clean_platform(platform)
        if clean_platform not in SUPPORTED_BROWSER_PLATFORMS:
            raise ValueError(f"unsupported browser platform: {platform}")
        target_url = "https://medium.com/new-story"
        if clean_platform == "substack":
            target_url = f"{os.getenv('SUBSTACK_PUBLICATION_URL', 'https://thinkvelocity.substack.com').rstrip('/')}/publish/home"
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(self.profile_dir),
                headless=False,
                viewport={"width": 1440, "height": 1000},
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(target_url, wait_until="domcontentloaded")
            print(f"Opened {clean_platform} in the persistent outbound profile.")
            print("Complete login in the browser window, then press Enter here to close it.")
            try:
                input()
            finally:
                context.close()
        return {"status": "login_session_closed", "platform": clean_platform, "profile_dir": str(self.profile_dir)}


class MediumBrowserAdapter:
    def create_draft(self, page: Any, variant: dict[str, Any]) -> dict[str, Any]:
        page.goto(variant["target_url"], wait_until="domcontentloaded")
        _raise_if_login_required(page, "Medium")
        _fill_medium_title(page, variant["title"])
        _fill_medium_body(page, variant["body_markdown"])
        _maybe_set_medium_tags(page, variant["tags"])
        page.wait_for_timeout(1500)
        return {"status": "draft_created", "platform": "medium", "url": page.url}


class SubstackBrowserAdapter:
    def create_draft(self, page: Any, variant: dict[str, Any]) -> dict[str, Any]:
        page.goto(variant["target_url"], wait_until="domcontentloaded")
        _raise_if_login_required(page, "Substack")
        _fill_first_working(page, ["textarea[placeholder*='Title']", "[contenteditable='true']"], variant["title"])
        _fill_first_working(page, ["textarea[placeholder*='Subtitle']", "input[placeholder*='Subtitle']"], variant.get("subtitle", ""), required=False)
        _fill_editor_body(page, variant["body_markdown"])
        page.wait_for_timeout(1500)
        return {"status": "draft_created", "platform": "substack", "url": page.url}


def _fill_medium_title(page: Any, title: str) -> None:
    selectors = [
        "textarea[placeholder='Title']",
        "textarea[aria-label='Title']",
        "[data-testid='storyTitle']",
        "h1[contenteditable='true']",
    ]
    _fill_first_working(page, selectors, title)


def _fill_medium_body(page: Any, body: str) -> None:
    selectors = [
        "[data-testid='story-editor'] [contenteditable='true']",
        "article [contenteditable='true']",
        "div[contenteditable='true']",
    ]
    _fill_first_working(page, selectors, body)


def _fill_editor_body(page: Any, body: str) -> None:
    selectors = [
        ".ProseMirror",
        "[data-testid='editor'] [contenteditable='true']",
        "article [contenteditable='true']",
        "div[contenteditable='true']",
    ]
    _fill_first_working(page, selectors, body)


def _fill_first_working(page: Any, selectors: list[str], text: str, *, required: bool = True) -> bool:
    if not text and not required:
        return False
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=5000)
            locator.click()
            try:
                locator.fill(text)
            except Exception:
                page.keyboard.insert_text(text)
            return True
        except Exception:
            continue
    if required:
        raise BrowserPublishFailed(f"Could not find an editable field for selectors: {', '.join(selectors)}")
    return False


def _maybe_set_medium_tags(page: Any, tags: list[str]) -> None:
    if not tags:
        return
    try:
        page.keyboard.press("Control+Alt+T")
    except Exception:
        return


def _raise_if_login_required(page: Any, platform: str) -> None:
    url = page.url.lower()
    if "signin" in url or "login" in url or "account" in url and "login" in url:
        raise BrowserLoginRequired(f"{platform} login required in the local browser profile")


def _medium_tags(keywords: list[str]) -> list[str]:
    tags = ["AI", "Productivity", "Prompt Engineering"]
    for keyword in keywords:
        clean = " ".join(str(keyword).split())[:25]
        if clean and clean.lower() not in {tag.lower() for tag in tags}:
            tags.append(clean)
        if len(tags) >= 5:
            break
    return tags[:5]


def _clean_platform(value: str) -> str:
    return str(value or "").strip().lower()


def _nowish() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local browser outbound blog jobs.")
    parser.add_argument("--once", action="store_true", help="Run one queued job and exit.")
    parser.add_argument("--platform", action="append", choices=sorted(SUPPORTED_BROWSER_PLATFORMS), help="Limit to one or more platforms.")
    parser.add_argument("--login-platform", choices=sorted(SUPPORTED_BROWSER_PLATFORMS), help="Open a persistent browser profile for manual login.")
    parser.add_argument("--profile-dir", default=str(DEFAULT_PROFILE_DIR), help="Persistent browser profile directory.")
    parser.add_argument("--screenshots", default=str(DEFAULT_SCREENSHOT_DIR), help="Screenshot output directory.")
    parser.add_argument("--headless", action="store_true", help="Run without showing the browser. Use only after login is stable.")
    args = parser.parse_args(argv)

    if args.login_platform:
        result = BrowserDraftPublisher(
            profile_dir=Path(args.profile_dir).resolve(),
            screenshot_dir=Path(args.screenshots).resolve(),
            headless=False,
        ).open_login_session(args.login_platform)
        print(result)
        return 0

    runner = BrowserOutboundRunner(profile_dir=args.profile_dir, screenshot_dir=args.screenshots, headless=args.headless)
    result = runner.run_next(platforms=args.platform)
    print(result)
    return 0 if result.get("status") in {"completed", "idle"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
