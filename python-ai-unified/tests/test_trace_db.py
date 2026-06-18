from __future__ import annotations

import asyncio
import importlib
import pathlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


AI_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))


class TraceDbTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trace_db = importlib.import_module("shared.trace_db")
        self.trace_db._pool = None

    def tearDown(self) -> None:
        self.trace_db._pool = None

    def test_write_trace_noops_when_pool_is_not_initialized(self) -> None:
        asyncio.run(self.trace_db.write_trace({"user_id": "user_1"}))

    def test_init_trace_pool_uses_small_asyncpg_pool(self) -> None:
        fake_pool = object()
        fake_asyncpg = types.SimpleNamespace(
            create_pool=AsyncMock(return_value=fake_pool)
        )

        with patch.dict(sys.modules, {"asyncpg": fake_asyncpg}):
            asyncio.run(self.trace_db.init_trace_pool("postgresql://example/db"))

        fake_asyncpg.create_pool.assert_awaited_once_with(
            dsn="postgresql://example/db",
            min_size=2,
            max_size=5,
        )
        self.assertIs(self.trace_db._pool, fake_pool)

    def test_write_trace_maps_partial_dict_without_key_errors(self) -> None:
        fake_pool = MagicMock()
        fake_pool.execute = AsyncMock()
        self.trace_db._pool = fake_pool

        asyncio.run(self.trace_db.write_trace({"user_id": "user_1"}))

        fake_pool.execute.assert_awaited_once()
        args = fake_pool.execute.await_args.args
        self.assertIn("INSERT INTO prompt_traces", args[0])
        self.assertEqual(args[2], "user_1")

    def test_query_metrics_groups_counts_from_db_rows(self) -> None:
        fake_pool = MagicMock()
        fake_pool.fetchrow = AsyncMock(
            return_value={"total": 2, "avg_latency_ms": 100.5}
        )
        fake_pool.fetch = AsyncMock(
            side_effect=[
                [{"key": "software", "count": 2}],
                [{"key": "build", "count": 1}],
                [{"key": "claude", "count": 1}],
            ]
        )
        self.trace_db._pool = fake_pool

        metrics = asyncio.run(self.trace_db.query_metrics())

        self.assertEqual(metrics["total"], 2)
        self.assertEqual(metrics["avg_latency_ms"], 100.5)
        self.assertEqual(metrics["by_domain"], {"software": 2})
        self.assertEqual(metrics["by_intent"], {"build": 1})
        self.assertEqual(metrics["by_suggested_ai"], {"claude": 1})


class AnalyticsDbFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analytics = importlib.import_module("routers.admin.analytics")

    def test_db_list_traces_returns_none_when_trace_pool_uninitialized(self) -> None:
        with patch("shared.trace_db.is_trace_pool_initialized", return_value=False):
            result = asyncio.run(
                self.analytics._db_list_traces("user_1", "software", "build", 10, 0)
            )
        self.assertIsNone(result)

    def test_db_get_metrics_returns_none_when_trace_pool_uninitialized(self) -> None:
        with patch("shared.trace_db.is_trace_pool_initialized", return_value=False):
            result = asyncio.run(self.analytics._db_get_metrics())
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
