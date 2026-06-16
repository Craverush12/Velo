from __future__ import annotations

from typing import Any

from core.blog_quality import validate_blog_post
from core.blog_trends import SerperClient, collect_trend_sources, queries_from_env, select_topic_clusters
from core.blog_writer import generate_blog_article
from storage.blog_store import BlogStore


class BlogGenerationService:
    def __init__(
        self,
        *,
        store: BlogStore,
        serper_client: SerperClient | None = None,
    ):
        self.store = store
        self.serper_client = serper_client or SerperClient()

    async def run_once(self, *, trigger: str = "manual", max_posts: int = 1) -> dict[str, Any]:
        queries = queries_from_env()
        run = self.store.create_run(trigger=trigger, queries=queries)
        posts: list[dict[str, Any]] = []
        try:
            sources = collect_trend_sources(self.serper_client, queries=queries)
            topics = select_topic_clusters(
                sources,
                existing_slugs=self.store.existing_slugs(),
                max_topics=max_posts,
                min_sources=1,
            )
            for topic in topics:
                article = await generate_blog_article(topic)
                quality = validate_blog_post(article, existing_slugs=self.store.existing_slugs())
                article["status"] = quality["status"]
                article["quality_score"] = quality["quality_score"]
                article["validation_errors"] = quality["validation_errors"]
                article["seo_score"] = quality["seo_score"]
                article["geo_score"] = quality["geo_score"]
                article["eeat_score"] = quality["eeat_score"]
                article["schema_jsonld"] = quality["schema_jsonld"]
                article["seo_audit"] = quality["seo_audit"]
                post = self.store.create_post(article, run_id=run["id"])
                posts.append(post)
            finished = self.store.finish_run(
                run["id"],
                status="completed",
                stats={
                    "sources_seen": len(sources),
                    "topics_selected": len(topics),
                    "created": len(posts),
                },
            )
            return {
                "status": finished["status"],
                "run_id": run["id"],
                "created_post_count": len(posts),
                "posts": posts,
                "stats": finished["stats"],
            }
        except Exception as exc:
            self.store.finish_run(run["id"], status="failed", stats={"created": len(posts)}, error=str(exc))
            raise
