import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from core import scheduler


class FakeRepository:
    def __init__(self, contexts):
        self.contexts = contexts
        self.saved = []

    def list_user_ids(self):
        return list(self.contexts)

    def get_user_context(self, user_id):
        return self.contexts[user_id]

    def save_user_context(self, user_id, context):
        self.contexts[user_id] = context
        self.saved.append(user_id)


class SchedulerJobTests(unittest.TestCase):
    def test_run_scheduled_jobs_persists_suggestions_and_memory_synthesis(self):
        now = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
        repo = FakeRepository(
            {
                "arjun": {
                    "user_id": "arjun",
                    "domains": ["frontend"],
                    "frameworks_used": ["React"],
                    "preferences": {"industry": "software"},
                    "recent_context": [
                        {
                            "intent": "ui_design",
                            "domain": "frontend",
                            "summary": "Build a React UI component with Tailwind.",
                            "framework": "React",
                            "at": now.isoformat(),
                        }
                    ],
                }
            }
        )

        stats = asyncio.run(scheduler.run_scheduled_jobs(repo, now=now))

        self.assertEqual(stats["users_seen"], 1)
        self.assertEqual(stats["users_updated"], 1)
        context = repo.contexts["arjun"]
        self.assertEqual(context["scheduler"]["last_run_at"], now.isoformat())
        self.assertEqual(
            context["memory_synthesis"]["summary"],
            "Recent work clusters around frontend with frequent intents: ui_design.",
        )
        self.assertEqual(context["memory_synthesis"]["top_frameworks"], ["React"])
        self.assertEqual(context["proactive_suggestions"][0]["id"], "v0-dev-connector")
        self.assertEqual(repo.saved, ["arjun"])

    def test_cleanup_removes_stale_context_without_deleting_all_history(self):
        now = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
        stale = now - timedelta(days=120)
        repo = FakeRepository(
            {
                "arjun": {
                    "user_id": "arjun",
                    "domains": [],
                    "frameworks_used": [],
                    "preferences": {},
                    "recent_context": [
                        {"summary": "new", "intent": "coding", "at": now.isoformat()},
                        {"summary": "old", "intent": "coding", "at": stale.isoformat()},
                        {"summary": "undated", "intent": "coding"},
                    ],
                }
            }
        )

        stats = asyncio.run(
            scheduler.run_scheduled_jobs(
                repo,
                now=now,
                config=scheduler.SchedulerConfig(stale_context_days=90),
            )
        )

        self.assertEqual(stats["stale_context_removed"], 1)
        remaining = [item["summary"] for item in repo.contexts["arjun"]["recent_context"]]
        self.assertEqual(remaining, ["new", "undated"])

    def test_scheduler_factory_is_disabled_by_default(self):
        runner = scheduler.create_scheduler()

        self.assertFalse(runner.enabled)


if __name__ == "__main__":
    unittest.main()
