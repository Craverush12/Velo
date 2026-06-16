import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.admin import get_admin_store
from api.blog_admin import get_blog_service, get_blog_store, get_devto_publisher, get_substack_publisher
from main import app
from storage.admin_store import AdminStore
from storage.blog_store import BlogStore


class FakeBlogService:
    def __init__(self, store: BlogStore):
        self.store = store

    async def run_once(self, *, trigger: str = "manual", max_posts: int = 1):
        run = self.store.create_run(trigger=trigger, queries=["developer tools news"])
        post = self.store.create_post(
            {
                "slug": "developer-tools-news",
                "title": "Developer Tools News",
                "status": "ready",
                "excerpt": "A practical update for AI teams.",
                "meta_title": "Developer Tools News for AI Teams",
                "meta_description": "A source-backed developer tools update for AI teams using ThinkVelocity.",
                "keywords": ["developer tools"],
                "content_markdown": "Body with /blog and /extension-download links.",
                "content_html": "<p>Body with /blog and /extension-download links.</p>",
                "faq": [],
                "sources": [],
                "quality_score": 91,
                "seo_score": 88,
                "geo_score": 82,
                "eeat_score": 76,
                "schema_jsonld": {"@context": "https://schema.org", "@graph": [{"@type": "BlogPosting"}]},
                "seo_audit": {"missing_items": [], "recommendations": []},
                "validation_errors": [],
            },
            run_id=run["id"],
        )
        self.store.finish_run(run["id"], status="completed", stats={"created": 1})
        return {"status": "completed", "run_id": run["id"], "created_post_count": 1, "posts": [post]}


class FakeSubstackPublisher:
    def status(self):
        return {"status": "configured_without_publish_endpoint", "publication_reachable": True}

    def publish(self, post):
        return {
            "status": "not_configured",
            "reason": "SUBSTACK_PUBLISH_ENDPOINT is required before API posting can be attempted",
            "variant": {
                "title": post["title"],
                "body_markdown": "ThinkVelocity variant body",
                "canonical_url": f"https://thinkvelocity.ai/blog/{post['slug']}",
            },
        }


class FakeDevToPublisher:
    calls = 0

    def status(self):
        return {"status": "configured", "platform": "devto", "user": {"username": "velocity"}}

    def publish(self, post):
        type(self).calls += 1
        return {
            "status": "draft_created",
            "platform": "devto",
            "remote": {"id": 123, "url": "https://dev.to/velocity/draft"},
            "variant": {
                "title": post["title"],
                "body_markdown": "ThinkVelocity DEV.to variant body",
                "canonical_url": f"https://thinkvelocity.ai/blog/{post['slug']}",
            },
        }


class BlogAdminApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.admin_store = AdminStore.local(Path(self.tmp.name) / "admin")
        self.admin_store.ensure_bootstrap_admin("owner@example.com", "change-me-now")
        self.blog_store = BlogStore.local(Path(self.tmp.name) / "blog")
        self.blog_service = FakeBlogService(self.blog_store)
        FakeDevToPublisher.calls = 0
        app.dependency_overrides[get_admin_store] = lambda: self.admin_store
        app.dependency_overrides[get_blog_store] = lambda: self.blog_store
        app.dependency_overrides[get_blog_service] = lambda: self.blog_service
        app.dependency_overrides[get_substack_publisher] = lambda: FakeSubstackPublisher()
        app.dependency_overrides[get_devto_publisher] = lambda: FakeDevToPublisher()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.tmp.cleanup()

    def _login(self):
        response = self.client.post(
            "/admin/api/login",
            json={"email": "owner@example.com", "password": "change-me-now"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["csrf_token"]

    def test_blog_admin_routes_require_authentication(self):
        response = self.client.get("/admin/api/blog-posts")

        self.assertEqual(response.status_code, 401)

    def test_run_generator_requires_csrf_and_creates_post(self):
        csrf = self._login()

        missing_csrf = self.client.post("/admin/api/blog-generator/run", json={"max_posts": 1})
        created = self.client.post(
            "/admin/api/blog-generator/run",
            headers={"X-CSRF-Token": csrf},
            json={"max_posts": 1},
        )
        listed = self.client.get("/admin/api/blog-posts")

        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["created_post_count"], 1)
        self.assertEqual(listed.json()["items"][0]["slug"], "developer-tools-news")
        self.assertEqual(listed.json()["items"][0]["seo_score"], 88)

    def test_blog_post_seo_audit_route_returns_stored_scores(self):
        csrf = self._login()
        run = self.client.post(
            "/admin/api/blog-generator/run",
            headers={"X-CSRF-Token": csrf},
            json={"max_posts": 1},
        )
        post_id = run.json()["posts"][0]["id"]

        audit = self.client.get(f"/admin/api/blog-posts/{post_id}/seo-audit")

        self.assertEqual(audit.status_code, 200, audit.text)
        self.assertEqual(audit.json()["seo_score"], 88)
        self.assertEqual(audit.json()["geo_score"], 82)
        self.assertEqual(audit.json()["eeat_score"], 76)
        self.assertEqual(audit.json()["schema_jsonld"]["@graph"][0]["@type"], "BlogPosting")

    def test_approve_reject_and_export_posts(self):
        csrf = self._login()
        run = self.client.post(
            "/admin/api/blog-generator/run",
            headers={"X-CSRF-Token": csrf},
            json={"max_posts": 1},
        )
        post_id = run.json()["posts"][0]["id"]

        reject = self.client.post(
            f"/admin/api/blog-posts/{post_id}/reject",
            headers={"X-CSRF-Token": csrf},
            json={"reason": "Needs a better source angle"},
        )
        approve = self.client.post(
            f"/admin/api/blog-posts/{post_id}/approve",
            headers={"X-CSRF-Token": csrf},
        )
        exported = self.client.get("/admin/api/blog-posts/export?status=ready")
        audit = self.client.get("/admin/api/audit-logs")

        self.assertEqual(reject.status_code, 200, reject.text)
        self.assertEqual(reject.json()["status"], "rejected")
        self.assertEqual(approve.status_code, 200, approve.text)
        self.assertEqual(approve.json()["status"], "ready")
        self.assertEqual(exported.json()["posts"][0]["id"], post_id)
        self.assertGreaterEqual(audit.json()["total"], 3)

    def test_substack_outbound_status_and_publish_are_admin_protected(self):
        csrf = self._login()
        run = self.client.post(
            "/admin/api/blog-generator/run",
            headers={"X-CSRF-Token": csrf},
            json={"max_posts": 1},
        )
        post_id = run.json()["posts"][0]["id"]

        status = self.client.get("/admin/api/blog-outbound/substack/status")
        missing_csrf = self.client.post(f"/admin/api/blog-posts/{post_id}/outbound/substack")
        publish = self.client.post(
            f"/admin/api/blog-posts/{post_id}/outbound/substack",
            headers={"X-CSRF-Token": csrf},
        )

        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "configured_without_publish_endpoint")
        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(publish.status_code, 200)
        self.assertEqual(publish.json()["status"], "not_configured")
        self.assertIn("ThinkVelocity", publish.json()["variant"]["body_markdown"])

    def test_devto_outbound_status_and_publish_are_admin_protected(self):
        csrf = self._login()
        run = self.client.post(
            "/admin/api/blog-generator/run",
            headers={"X-CSRF-Token": csrf},
            json={"max_posts": 1},
        )
        post_id = run.json()["posts"][0]["id"]

        status = self.client.get("/admin/api/blog-outbound/devto/status")
        missing_csrf = self.client.post(f"/admin/api/blog-posts/{post_id}/outbound/devto")
        publish = self.client.post(
            f"/admin/api/blog-posts/{post_id}/outbound/devto",
            headers={"X-CSRF-Token": csrf},
        )
        stored = self.client.get(f"/admin/api/blog-posts/{post_id}")

        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "configured")
        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(publish.status_code, 200)
        self.assertEqual(publish.json()["status"], "draft_created")
        self.assertEqual(stored.json()["outbound_publications"][0]["platform"], "devto")

    def test_devto_outbound_refuses_posts_that_are_not_ready(self):
        csrf = self._login()
        post = self.blog_store.create_post(
            {
                "slug": "weak-draft",
                "title": "Weak Draft",
                "status": "draft",
                "quality_score": 91,
                "content_markdown": "Body",
            }
        )

        publish = self.client.post(
            f"/admin/api/blog-posts/{post['id']}/outbound/devto",
            headers={"X-CSRF-Token": csrf},
        )

        self.assertEqual(publish.status_code, 409)
        self.assertIn("ready", publish.json()["detail"])
        self.assertEqual(FakeDevToPublisher.calls, 0)

    def test_devto_outbound_prevents_duplicate_drafts(self):
        csrf = self._login()
        run = self.client.post(
            "/admin/api/blog-generator/run",
            headers={"X-CSRF-Token": csrf},
            json={"max_posts": 1},
        )
        post_id = run.json()["posts"][0]["id"]

        first = self.client.post(
            f"/admin/api/blog-posts/{post_id}/outbound/devto",
            headers={"X-CSRF-Token": csrf},
        )
        second = self.client.post(
            f"/admin/api/blog-posts/{post_id}/outbound/devto",
            headers={"X-CSRF-Token": csrf},
        )
        stored = self.client.get(f"/admin/api/blog-posts/{post_id}")

        self.assertEqual(first.json()["status"], "draft_created")
        self.assertEqual(second.json()["status"], "duplicate_skipped")
        self.assertEqual(FakeDevToPublisher.calls, 1)
        self.assertEqual(len(stored.json()["outbound_publications"]), 1)

    def test_browser_outbound_job_requires_ready_post_and_csrf(self):
        csrf = self._login()
        draft = self.blog_store.create_post(
            {
                "slug": "weak-draft",
                "title": "Weak Draft",
                "status": "draft",
                "content_markdown": "Body",
            }
        )

        missing_csrf = self.client.post(f"/admin/api/blog-posts/{draft['id']}/outbound/browser/medium")
        queued = self.client.post(
            f"/admin/api/blog-posts/{draft['id']}/outbound/browser/medium",
            headers={"X-CSRF-Token": csrf},
        )

        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(queued.status_code, 409)
        self.assertIn("ready", queued.json()["detail"])

    def test_browser_outbound_job_queues_once_and_lists_jobs(self):
        csrf = self._login()
        run = self.client.post(
            "/admin/api/blog-generator/run",
            headers={"X-CSRF-Token": csrf},
            json={"max_posts": 1},
        )
        post_id = run.json()["posts"][0]["id"]

        first = self.client.post(
            f"/admin/api/blog-posts/{post_id}/outbound/browser/substack",
            headers={"X-CSRF-Token": csrf},
        )
        second = self.client.post(
            f"/admin/api/blog-posts/{post_id}/outbound/browser/substack",
            headers={"X-CSRF-Token": csrf},
        )
        jobs = self.client.get("/admin/api/blog-outbound/browser/jobs")

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["status"], "queued")
        self.assertEqual(first.json()["platform"], "substack")
        self.assertEqual(second.json()["status"], "duplicate_skipped")
        self.assertEqual(jobs.json()["items"][0]["platform"], "substack")


if __name__ == "__main__":
    unittest.main()
