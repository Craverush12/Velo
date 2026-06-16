import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from core.blog_quality import validate_blog_post
from core.blog_browser_runner import BrowserOutboundRunner, build_browser_variant
from core.blog_outbound import DevToPublisher, SubstackPublisher, build_devto_variant, build_substack_variant
from core.blog_scheduler import BlogSchedulerConfig, run_blog_generation_once
from core.blog_seo_audit import audit_blog_post
from core.blog_trends import normalize_serper_news, select_topic_clusters
from core.blog_writer import generate_blog_article
from storage.blog_store import BlogStore


SOURCE_FIXTURES = [
    {
        "title": "DiffusionGemma: 4x faster text generation",
        "link": "https://blog.google/innovation-and-ai/technology/developers-tools/diffusion-gemma-faster-text-generation/",
        "source": "blog.google",
        "date": "4 days ago",
        "snippet": "An overview of DiffusionGemma, an exceptionally fast text generation model with up to 4x faster speeds.",
    },
    {
        "title": "Microsoft Build Live",
        "link": "https://news.microsoft.com/build-2026-live/microsoft-build-2026-live/",
        "source": "Microsoft Source",
        "date": "2 weeks ago",
        "snippet": "Microsoft shared developer tool updates and AI workflow announcements at Build.",
    },
    {
        "title": "Apple gives developers new keys to its AI future",
        "link": "https://www.theverge.com/apple-ai-developer-tools",
        "source": "The Verge",
        "date": "5 days ago",
        "snippet": "Apple announced new AI frameworks, Xcode updates, and developer-facing integrations.",
    },
]


class BlogGenerationTests(unittest.TestCase):
    def test_serper_news_results_are_normalized_and_ranked(self):
        sources = normalize_serper_news({"news": SOURCE_FIXTURES}, query="developer tools news")

        self.assertEqual(len(sources), 3)
        self.assertEqual(sources[0]["domain"], "blog.google")
        self.assertEqual(sources[0]["rank"], 1)
        self.assertEqual(sources[0]["query"], "developer tools news")
        self.assertGreater(sources[0]["source_score"], sources[2]["source_score"])

    def test_topic_selection_dedupes_existing_slugs(self):
        sources = normalize_serper_news({"news": SOURCE_FIXTURES}, query="developer tools news")

        topics = select_topic_clusters(
            sources,
            existing_slugs={"diffusiongemma-4x-faster-text-generation"},
            max_topics=2,
        )

        self.assertEqual(len(topics), 1)
        self.assertIn("Microsoft Build", topics[0]["title"])
        self.assertEqual(topics[0]["sources"][0]["domain"], "news.microsoft.com")

    def test_quality_gate_marks_good_post_ready_and_weak_post_draft(self):
        good_post = {
            "slug": "ai-developer-tools-update",
            "title": "AI Developer Tools Update: What Teams Should Change This Week",
            "excerpt": "A concise update for teams tracking AI developer tool changes.",
            "meta_title": "AI Developer Tools Update for Productive Teams",
            "meta_description": "Track the latest AI developer tool updates, what changed, and how teams can apply them in practical workflows with ThinkVelocity.",
            "keywords": ["AI developer tools", "prompt engineering", "automation"],
            "content_markdown": " ".join(["Original analysis for AI teams using /blog and /extension-download."] * 30),
            "content_html": "<p>" + " ".join(["Original analysis for AI teams using /blog and /extension-download."] * 30) + "</p>",
            "faq": [{"question": "Why does this matter?", "answer": "It changes how teams structure AI work."}],
            "sources": normalize_serper_news({"news": SOURCE_FIXTURES}, query="developer tools news"),
        }
        weak_post = {**good_post, "sources": good_post["sources"][:1], "content_markdown": "Thin copy"}

        good_result = validate_blog_post(good_post, existing_slugs=set(), min_word_count=20)
        weak_result = validate_blog_post(weak_post, existing_slugs=set(), min_word_count=20)

        self.assertEqual(good_result["status"], "ready")
        self.assertGreaterEqual(good_result["quality_score"], 80)
        self.assertEqual(weak_result["status"], "draft")
        self.assertIn("at least 3 sources", " ".join(weak_result["validation_errors"]))
        self.assertIn("seo_score", good_result)
        self.assertIn("schema_jsonld", good_result)

    def test_seo_geo_audit_scores_ready_post_and_generates_schema(self):
        post = {
            "slug": "ai-developer-tools-update",
            "title": "AI Developer Tools Update: What Teams Should Change This Week",
            "excerpt": "A concise update for teams tracking AI developer tool changes.",
            "meta_title": "AI Developer Tools Update for Productive Teams",
            "meta_description": "Track the latest AI developer tool updates, what changed, and how teams can apply them in practical workflows with ThinkVelocity.",
            "keywords": ["AI developer tools", "prompt engineering", "automation"],
            "content_markdown": "\n\n".join(
                [
                    "# AI Developer Tools Update",
                    "## Quick Answer",
                    "AI teams should track release notes, compare source-backed claims, and update prompt workflows in ThinkVelocity.",
                    "## What Changed",
                    "Original analysis for AI teams using /blog and /extension-download. ThinkVelocity helps teams convert source-backed updates into better prompts.",
                    "## Why It Matters",
                    "The practical effect is faster prompt iteration, clearer reviews, and better AI workflow governance for teams.",
                ]
            ),
            "faq": [{"question": "Why does this matter?", "answer": "It changes how teams structure AI work."}],
            "sources": normalize_serper_news({"news": SOURCE_FIXTURES}, query="developer tools news"),
        }

        audit = audit_blog_post(post, canonical_base_url="https://thinkvelocity.ai/blog")

        self.assertGreaterEqual(audit["seo_score"], 80)
        self.assertGreaterEqual(audit["geo_score"], 75)
        self.assertGreaterEqual(audit["eeat_score"], 70)
        self.assertEqual(audit["schema_jsonld"]["@graph"][0]["@type"], "BlogPosting")
        self.assertIn("FAQPage", [node["@type"] for node in audit["schema_jsonld"]["@graph"]])
        self.assertFalse(audit["missing_items"])

    def test_seo_geo_audit_flags_thin_unsourced_post(self):
        post = {
            "slug": "thin-post",
            "title": "Thin Post",
            "excerpt": "",
            "meta_title": "Thin",
            "meta_description": "Short",
            "keywords": [],
            "content_markdown": "Thin copy with no answer, no sources, and no internal links.",
            "faq": [],
            "sources": [],
        }

        audit = audit_blog_post(post)

        self.assertLess(audit["seo_score"], 70)
        self.assertLess(audit["geo_score"], 70)
        self.assertLess(audit["eeat_score"], 70)
        self.assertIn("at least 3 cited sources", " ".join(audit["missing_items"]))

    def test_blog_store_persists_posts_runs_and_export_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = BlogStore.local(Path(tmp))
            run = store.create_run(trigger="manual", queries=["developer tools news"])
            post = store.create_post(
                {
                    "slug": "developer-tools-news",
                    "title": "Developer Tools News",
                    "status": "ready",
                    "content_markdown": "Body",
                    "sources": [],
                },
                run_id=run["id"],
            )
            job = store.create_outbound_job(post_id=post["id"], platform="medium", method="browser")
            claimed = store.claim_next_outbound_job(platforms=["medium"])
            store.finish_outbound_job(claimed["id"], status="completed", result={"remote_url": "https://medium.com/p/draft"})
            store.finish_run(run["id"], status="completed", stats={"created": 1})

            reopened = BlogStore.local(Path(tmp))
            posts = reopened.list_posts()
            jobs = reopened.list_outbound_jobs()
            export = reopened.export_posts(status="ready")
            persisted_run = reopened.get_run(run["id"])

        self.assertEqual(posts["items"][0]["id"], post["id"])
        self.assertEqual(jobs["items"][0]["id"], job["id"])
        self.assertEqual(jobs["items"][0]["status"], "completed")
        self.assertEqual(export["posts"][0]["slug"], "developer-tools-news")
        self.assertEqual(persisted_run["status"], "completed")

    def test_writer_generates_normalized_article_from_json_completion(self):
        async def fake_complete(system_prompt, user_message, temperature=0.4, max_tokens=4096, model=None):
            self.assertIn("source-grounded", system_prompt)
            self.assertIn("DiffusionGemma", user_message)
            return json.dumps(
                {
                    "title": "AI Text Generation Speed Updates for Product Teams",
                    "slug": "ai-text-generation-speed-updates-product-teams",
                    "excerpt": "What faster text generation means for product teams.",
                    "meta_title": "AI Text Generation Speed Updates for Product Teams",
                    "meta_description": "Understand the latest AI text generation speed updates and how product teams should adjust prompt workflows.",
                    "keywords": ["AI text generation", "developer tools", "prompt workflows"],
                    "content_markdown": "Original source-backed article with /blog and /extension-download links.",
                    "content_html": "<p>Original source-backed article with /blog and /extension-download links.</p>",
                    "faq": [{"question": "What changed?", "answer": "Generation speed improved."}],
                }
            )

        topic = {"title": "DiffusionGemma: 4x faster text generation", "sources": normalize_serper_news({"news": SOURCE_FIXTURES}, query="developer tools news")}

        article = asyncio.run(generate_blog_article(topic, complete_fn=fake_complete, model="test-model"))

        self.assertEqual(article["slug"], "ai-text-generation-speed-updates-product-teams")
        self.assertEqual(article["model"], "test-model")
        self.assertEqual(len(article["sources"]), 3)

    def test_scheduler_respects_disabled_config_and_max_posts(self):
        class FakeService:
            def __init__(self):
                self.calls = 0

            async def run_once(self, *, trigger, max_posts):
                self.calls += 1
                return {"status": "completed", "created_post_count": max_posts}

        disabled_service = FakeService()
        enabled_service = FakeService()

        disabled = asyncio.run(
            run_blog_generation_once(
                disabled_service,
                config=BlogSchedulerConfig(enabled=False, max_posts_per_run=2),
            )
        )
        enabled = asyncio.run(
            run_blog_generation_once(
                enabled_service,
                config=BlogSchedulerConfig(enabled=True, max_posts_per_run=1),
            )
        )

        self.assertEqual(disabled["status"], "disabled")
        self.assertEqual(disabled_service.calls, 0)
        self.assertEqual(enabled["created_post_count"], 1)
        self.assertEqual(enabled_service.calls, 1)

    def test_substack_variant_adds_velocity_angle_and_canonical_url(self):
        post = {
            "slug": "ai-developer-tools-update",
            "title": "AI Developer Tools Update",
            "excerpt": "What changed in AI developer tools this week.",
            "content_markdown": "Source-backed body for teams building better AI workflows.",
            "keywords": ["AI", "developer tools", "prompt engineering"],
        }

        variant = build_substack_variant(
            post,
            publication_url="https://thinkvelocity.substack.com",
            canonical_base_url="https://thinkvelocity.ai/blog",
        )

        self.assertEqual(variant["title"], "AI Developer Tools Update")
        self.assertEqual(variant["canonical_url"], "https://thinkvelocity.ai/blog/ai-developer-tools-update")
        self.assertIn("ThinkVelocity", variant["body_markdown"])
        self.assertIn("prompt", variant["body_markdown"].lower())

    def test_substack_publisher_requires_publish_endpoint_before_posting(self):
        publisher = SubstackPublisher(
            api_key="test-key",
            publication_url="https://thinkvelocity.substack.com",
            publish_endpoint="",
        )

        result = publisher.publish({"title": "Title", "slug": "title", "content_markdown": "Body"})

        self.assertEqual(result["status"], "not_configured")
        self.assertIn("SUBSTACK_PUBLISH_ENDPOINT", result["reason"])

    def test_substack_status_checks_publication_reachability(self):
        class FakeResponse:
            status_code = 200

            def json(self):
                return {}

        def fake_get(url, *, headers, timeout):
            self.assertEqual(url, "https://thinkvelocity.substack.com/api/v1/posts?limit=1")
            return FakeResponse()

        publisher = SubstackPublisher(
            api_key="",
            publication_url="https://thinkvelocity.substack.com",
            http_get=fake_get,
        )

        status = publisher.status()

        self.assertEqual(status["status"], "not_configured")
        self.assertTrue(status["publication_reachable"])

    def test_substack_publisher_posts_draft_payload_when_endpoint_is_configured(self):
        calls = []

        class FakeResponse:
            status_code = 201

            def json(self):
                return {"id": "draft-1", "url": "https://thinkvelocity.substack.com/p/draft-1"}

            def raise_for_status(self):
                return None

        def fake_post(url, *, headers, json, timeout):
            calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
            return FakeResponse()

        publisher = SubstackPublisher(
            api_key="test-key",
            publication_url="https://thinkvelocity.substack.com",
            publish_endpoint="https://example.test/posts",
            http_post=fake_post,
        )

        result = publisher.publish(
            {
                "title": "AI Developer Tools Update",
                "slug": "ai-developer-tools-update",
                "excerpt": "Excerpt",
                "content_markdown": "Body",
                "keywords": ["AI", "prompt engineering"],
            }
        )

        self.assertEqual(result["status"], "draft_created")
        self.assertEqual(calls[0]["headers"]["X-API-Key"], "test-key")
        self.assertFalse(calls[0]["json"]["published"])
        self.assertEqual(calls[0]["json"]["canonical_url"], "https://thinkvelocity.ai/blog/ai-developer-tools-update")

    def test_devto_variant_adds_velocity_angle_and_canonical_url(self):
        post = {
            "slug": "ai-developer-tools-update",
            "title": "AI Developer Tools Update",
            "excerpt": "What changed in AI developer tools this week.",
            "content_markdown": "Source-backed body for teams building better AI workflows.",
            "keywords": ["AI", "developer tools", "prompt engineering", "automation", "extra"],
        }

        variant = build_devto_variant(post, canonical_base_url="https://thinkvelocity.ai/blog")

        self.assertEqual(variant["title"], "AI Developer Tools Update")
        self.assertEqual(variant["canonical_url"], "https://thinkvelocity.ai/blog/ai-developer-tools-update")
        self.assertFalse(variant["published"])
        self.assertIn("ThinkVelocity", variant["body_markdown"])
        self.assertLessEqual(len(variant["tags"]), 4)
        self.assertTrue(all(tag == tag.lower() for tag in variant["tags"]))

    def test_devto_publisher_posts_unpublished_article(self):
        calls = []

        class FakeResponse:
            status_code = 201

            def json(self):
                return {"id": 123, "url": "https://dev.to/velocity/draft"}

            def raise_for_status(self):
                return None

        def fake_post(url, *, headers, json, timeout):
            calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
            return FakeResponse()

        publisher = DevToPublisher(api_key="dev-key", http_post=fake_post)
        result = publisher.publish(
            {
                "title": "AI Developer Tools Update",
                "slug": "ai-developer-tools-update",
                "excerpt": "Excerpt",
                "content_markdown": "Body",
                "keywords": ["AI", "prompt engineering"],
            }
        )

        self.assertEqual(result["status"], "draft_created")
        self.assertEqual(calls[0]["url"], "https://dev.to/api/articles")
        self.assertEqual(calls[0]["headers"]["api-key"], "dev-key")
        article = calls[0]["json"]["article"]
        self.assertFalse(article["published"])
        self.assertEqual(article["canonical_url"], "https://thinkvelocity.ai/blog/ai-developer-tools-update")

    def test_browser_variants_are_platform_specific_and_draft_first(self):
        post = {
            "slug": "ai-developer-tools-update",
            "title": "AI Developer Tools Update",
            "excerpt": "What changed in AI developer tools this week.",
            "content_markdown": "Source-backed body for teams building better AI workflows.",
            "keywords": ["AI", "developer tools", "prompt engineering", "automation", "extra"],
        }

        medium = build_browser_variant(post, platform="medium", canonical_base_url="https://thinkvelocity.ai/blog")
        substack = build_browser_variant(post, platform="substack", canonical_base_url="https://thinkvelocity.ai/blog")

        self.assertEqual(medium["status"], "draft")
        self.assertEqual(medium["platform"], "medium")
        self.assertEqual(medium["target_url"], "https://medium.com/new-story")
        self.assertLessEqual(len(medium["tags"]), 5)
        self.assertIn("Canonical version: https://thinkvelocity.ai/blog/ai-developer-tools-update", medium["body_markdown"])
        self.assertIn("ThinkVelocity", substack["body_markdown"])
        self.assertIn("/publish", substack["target_url"])

    def test_browser_runner_completes_queued_job_with_publisher_result(self):
        class FakePublisher:
            def __init__(self):
                self.variants = []

            def create_draft(self, variant):
                self.variants.append(variant)
                return {
                    "status": "draft_created",
                    "platform": variant["platform"],
                    "url": "https://medium.com/p/draft",
                    "screenshot_path": "storage/browser-screenshots/medium.png",
                }

        fake_publisher = FakePublisher()
        with tempfile.TemporaryDirectory() as tmp:
            store = BlogStore.local(Path(tmp))
            post = store.create_post(
                {
                    "slug": "developer-tools-news",
                    "title": "Developer Tools News",
                    "status": "ready",
                    "content_markdown": "Body with ThinkVelocity angle.",
                    "keywords": ["AI"],
                }
            )
            store.create_outbound_job(post_id=post["id"], platform="medium", method="browser")

            runner = BrowserOutboundRunner(store=store, publisher_factory=lambda: fake_publisher)
            result = runner.run_next(platforms=["medium"])
            stored = store.get_post(post["id"])
            jobs = store.list_outbound_jobs()

        self.assertEqual(result["status"], "completed")
        self.assertEqual(jobs["items"][0]["status"], "completed")
        self.assertEqual(stored["outbound_publications"][0]["platform"], "medium")
        self.assertEqual(stored["outbound_publications"][0]["remote"]["url"], "https://medium.com/p/draft")
        self.assertEqual(fake_publisher.variants[0]["platform"], "medium")


if __name__ == "__main__":
    unittest.main()
