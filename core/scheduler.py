import asyncio
import logging
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from core.active_memory import generate_proactive_suggestions
from storage import store

logger = logging.getLogger(__name__)


class ContextRepository(Protocol):
    def list_user_ids(self) -> list[str]:
        ...

    def get_user_context(self, user_id: str) -> dict:
        ...

    def save_user_context(self, user_id: str, context: dict) -> None:
        ...


@dataclass(frozen=True)
class SchedulerConfig:
    enabled: bool = False
    interval_seconds: int = 3600
    stale_context_days: int = 90
    max_users_per_run: int = 100
    run_on_start: bool = True


class LocalContextRepository:
    """Repository adapter over flat JSON storage; swappable for Postgres later."""

    def list_user_ids(self) -> list[str]:
        storage_dir = Path(store.storage_path())
        user_ids = []
        for path in sorted(storage_dir.glob("user_*.json")):
            if path.name.endswith(".json.tmp"):
                continue
            user_ids.append(path.stem.removeprefix("user_"))
        return user_ids

    def get_user_context(self, user_id: str) -> dict:
        return store.get_user_context(user_id)

    def save_user_context(self, user_id: str, context: dict) -> None:
        store.save_user_context(user_id, context)


def config_from_env() -> SchedulerConfig:
    enabled = os.getenv("VELOCITY_SCHEDULER_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    interval = _int_from_env("VELOCITY_SCHEDULER_INTERVAL_SECONDS", 3600)
    return SchedulerConfig(
        enabled=enabled,
        interval_seconds=max(60, interval),
        stale_context_days=_int_from_env("VELOCITY_STALE_CONTEXT_DAYS", 90),
        max_users_per_run=max(1, _int_from_env("VELOCITY_SCHEDULER_MAX_USERS", 100)),
        run_on_start=os.getenv("VELOCITY_SCHEDULER_RUN_ON_START", "true").strip().lower()
        not in {"0", "false", "no", "off"},
    )


def _int_from_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer for %s=%r; using %s", name, raw, default)
        return default


class SchedulerRunner:
    def __init__(
        self,
        repository: ContextRepository | None = None,
        config: SchedulerConfig | None = None,
    ):
        self.repository = repository or LocalContextRepository()
        self.config = config or config_from_env()
        self.enabled = self.config.enabled
        self._task: asyncio.Task | None = None
        self.last_stats: dict | None = None

    def start(self) -> None:
        if not self.enabled:
            logger.info("Velocity scheduler disabled")
            return
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop(), name="velocity-scheduler")
        logger.info(
            "Velocity scheduler started with interval=%ss stale_context_days=%s",
            self.config.interval_seconds,
            self.config.stale_context_days,
        )

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
        self.last_stats = await run_scheduled_jobs(self.repository, config=self.config)
        return self.last_stats

    async def _run_loop(self) -> None:
        if self.config.run_on_start:
            await self._run_once_logged()
        while True:
            await asyncio.sleep(self.config.interval_seconds)
            await self._run_once_logged()

    async def _run_once_logged(self) -> None:
        try:
            await self.run_once()
        except Exception:
            logger.exception("Velocity scheduler run failed")


def create_scheduler(
    repository: ContextRepository | None = None,
    config: SchedulerConfig | None = None,
) -> SchedulerRunner:
    return SchedulerRunner(repository=repository, config=config)


async def run_scheduled_jobs(
    repository: ContextRepository,
    *,
    now: datetime | None = None,
    config: SchedulerConfig | None = None,
) -> dict:
    config = config or SchedulerConfig()
    now = now or datetime.now(timezone.utc)
    stats = {
        "users_seen": 0,
        "users_updated": 0,
        "suggestions_generated": 0,
        "stale_context_removed": 0,
    }

    for user_id in repository.list_user_ids()[: config.max_users_per_run]:
        stats["users_seen"] += 1
        context = repository.get_user_context(user_id)
        before_count = len(context.get("recent_context", []))
        context["recent_context"] = prune_stale_context(
            context.get("recent_context", []),
            now=now,
            stale_context_days=config.stale_context_days,
        )
        removed = before_count - len(context["recent_context"])
        stats["stale_context_removed"] += removed

        synthesis = synthesize_memory(context, now=now)
        suggestions = generate_proactive_suggestions(context)
        context["memory_synthesis"] = synthesis
        context["proactive_suggestions"] = suggestions
        context["scheduler"] = {
            "last_run_at": now.isoformat(),
            "stale_context_days": config.stale_context_days,
            "suggestions_count": len(suggestions),
        }
        context["updated_at"] = now.isoformat()
        repository.save_user_context(user_id, context)

        stats["users_updated"] += 1
        stats["suggestions_generated"] += len(suggestions)

    return stats


def synthesize_memory(context: dict, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    history = context.get("recent_context", [])
    domains = _top_values(context.get("domains", []), limit=5)
    frameworks = _top_values(context.get("frameworks_used", []), limit=5)
    intents = _top_values(
        [item.get("intent", "") for item in history if item.get("intent")],
        limit=5,
    )

    if domains and intents:
        summary = (
            f"Recent work clusters around {', '.join(domains)} "
            f"with frequent intents: {', '.join(intents)}."
        )
    elif domains:
        summary = f"Recent work clusters around {', '.join(domains)}."
    elif intents:
        summary = f"Recent work shows frequent intents: {', '.join(intents)}."
    else:
        summary = "Not enough recent activity to synthesize stable memory."

    return {
        "generated_at": now.isoformat(),
        "summary": summary,
        "top_domains": domains,
        "top_frameworks": frameworks,
        "top_intents": intents,
        "recent_context_count": len(history),
        "last_activity_at": _last_activity_at(history),
    }


def prune_stale_context(
    recent_context: list[dict],
    *,
    now: datetime | None = None,
    stale_context_days: int = 90,
) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=stale_context_days)
    kept = []
    for item in recent_context:
        at = _parse_datetime(item.get("at"))
        if at is None or at >= cutoff:
            kept.append(item)
    return kept


def _top_values(values: list[str], *, limit: int) -> list[str]:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return [value for value, _ in Counter(cleaned).most_common(limit)]


def _last_activity_at(history: list[dict]) -> str | None:
    parsed = [_parse_datetime(item.get("at")) for item in history]
    parsed = [item for item in parsed if item is not None]
    if not parsed:
        return None
    return max(parsed).isoformat()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
