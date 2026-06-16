from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BlogSchedulerConfig:
    enabled: bool = False
    interval_hours: int = 24
    max_posts_per_run: int = 1
    run_on_start: bool = False


def blog_config_from_env() -> BlogSchedulerConfig:
    return BlogSchedulerConfig(
        enabled=os.getenv("BLOG_AUTOGEN_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"},
        interval_hours=max(1, _int_from_env("BLOG_AUTOGEN_INTERVAL_HOURS", 24)),
        max_posts_per_run=max(1, _int_from_env("BLOG_AUTOGEN_MAX_POSTS_PER_RUN", 1)),
        run_on_start=os.getenv("BLOG_AUTOGEN_RUN_ON_START", "false").strip().lower() in {"1", "true", "yes", "on"},
    )


class BlogSchedulerRunner:
    def __init__(self, service, config: BlogSchedulerConfig | None = None):
        self.service = service
        self.config = config or blog_config_from_env()
        self.enabled = self.config.enabled
        self._task: asyncio.Task | None = None
        self.last_stats: dict | None = None

    def start(self) -> None:
        if not self.enabled:
            logger.info("Blog scheduler disabled")
            return
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop(), name="blog-autogen-scheduler")
        logger.info("Blog scheduler started with interval_hours=%s", self.config.interval_hours)

    async def shutdown(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def run_once(self) -> dict:
        self.last_stats = await run_blog_generation_once(self.service, config=self.config)
        return self.last_stats

    async def _run_loop(self) -> None:
        if self.config.run_on_start:
            await self._run_once_logged()
        while True:
            await asyncio.sleep(self.config.interval_hours * 3600)
            await self._run_once_logged()

    async def _run_once_logged(self) -> None:
        try:
            await self.run_once()
        except Exception:
            logger.exception("Blog scheduler run failed")


async def run_blog_generation_once(service, *, config: BlogSchedulerConfig | None = None) -> dict:
    config = config or BlogSchedulerConfig()
    if not config.enabled:
        return {"status": "disabled"}
    return await service.run_once(trigger="scheduler", max_posts=config.max_posts_per_run)


def _int_from_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer for %s=%r; using %s", name, raw, default)
        return default
