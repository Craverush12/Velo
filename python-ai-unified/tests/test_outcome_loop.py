# python-ai-unified/tests/test_outcome_loop.py
from __future__ import annotations

import importlib
import pathlib
import sys
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

AI_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))

VALID_UUID = "123e4567-e89b-12d3-a456-426614174000"


class RecordOutcomeTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_pool_returns_false(self):
        from shared import trace_db
        with patch.object(trace_db, "_pool", None):
            self.assertFalse(await trace_db.record_outcome(VALID_UUID, "copied"))

    async def test_invalid_outcome_rejected(self):
        from shared import trace_db
        with patch.object(trace_db, "_pool", AsyncMock()):
            self.assertFalse(await trace_db.record_outcome(VALID_UUID, "banana"))

    async def test_bad_uuid_rejected(self):
        from shared import trace_db
        with patch.object(trace_db, "_pool", AsyncMock()):
            self.assertFalse(await trace_db.record_outcome("not-a-uuid", "copied"))

    async def test_happy_path_updates_and_reports_true(self):
        from shared import trace_db
        pool = AsyncMock()
        pool.execute.return_value = "UPDATE 1"
        with patch.object(trace_db, "_pool", pool):
            ok = await trace_db.record_outcome(VALID_UUID, "thumbs_up")
        self.assertTrue(ok)
        self.assertTrue(pool.execute.called)
        sql = pool.execute.call_args.args[0]
        self.assertIn("UPDATE prompt_traces", sql)
        self.assertIn("$1", sql)  # parameterized, never f-string values

    async def test_unknown_trace_reports_false(self):
        from shared import trace_db
        pool = AsyncMock()
        pool.execute.return_value = "UPDATE 0"
        with patch.object(trace_db, "_pool", pool):
            self.assertFalse(await trace_db.record_outcome(VALID_UUID, "copied"))


class FeedbackEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        main = importlib.import_module("main")
        cls.client = TestClient(main.app)

    def test_records_valid_outcome(self):
        with patch("shared.trace_db.record_outcome", new=AsyncMock(return_value=True)):
            r = self.client.post(
                "/ai/enhance/feedback",
                json={"trace_id": VALID_UUID, "outcome": "copied", "user_id": "u1"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "recorded")

    def test_invalid_outcome_degrades_to_ignored(self):
        with patch("shared.trace_db.record_outcome", new=AsyncMock(return_value=False)):
            r = self.client.post(
                "/ai/enhance/feedback",
                json={"trace_id": VALID_UUID, "outcome": "banana"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ignored")


if __name__ == "__main__":
    unittest.main()
