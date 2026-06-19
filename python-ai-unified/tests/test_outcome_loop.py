# python-ai-unified/tests/test_outcome_loop.py
from __future__ import annotations

import asyncio
import importlib
import json as _json
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
        mock_ro = AsyncMock(return_value=True)
        with patch("shared.trace_db.record_outcome", new=mock_ro):
            r = self.client.post(
                "/ai/enhance/feedback",
                json={"trace_id": VALID_UUID, "outcome": "copied", "user_id": "u1"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "recorded")
        self.assertEqual(r.json()["trace_id"], VALID_UUID)
        mock_ro.assert_awaited_once()  # guards against the patch going vacuous

    def test_invalid_outcome_degrades_to_ignored(self):
        mock_ro = AsyncMock(return_value=False)
        with patch("shared.trace_db.record_outcome", new=mock_ro):
            r = self.client.post(
                "/ai/enhance/feedback",
                json={"trace_id": VALID_UUID, "outcome": "banana"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ignored")
        mock_ro.assert_awaited_once()


class AdaptStreamTraceIdTests(unittest.IsolatedAsyncioTestCase):
    async def test_complete_event_carries_trace_id_and_writes_trace(self):
        from routers.ai import enhance as enh

        class _Inner:
            async def _gen(self):
                done = {"type": "done", "result": {
                    "enhanced_prompt": "ENHANCED",
                    "annotated_segments": [],
                    "domain": "software_engineering",
                    "intent": "code_generation",
                    "summary": "s",
                }}
                yield ("data: " + _json.dumps(done) + "\n\n").encode("utf-8")

            @property
            def body_iterator(self):
                return self._gen()

        captured = {}
        with patch.object(enh, "write_trace", new=AsyncMock(side_effect=lambda r: captured.update(r))):
            out = []
            async for ev in enh._adapt_stream(
                _Inner(),
                trace_id="TID-123",
                trace_ctx={"user_id": "u1", "mode": "best", "raw_prompt": "raw"},
            ):
                out.append(ev)
            await asyncio.sleep(0)  # let the fire-and-forget task run

        joined = "".join(out)
        self.assertIn("\"trace_id\": \"TID-123\"", joined)
        self.assertEqual(captured.get("trace_id"), "TID-123")
        self.assertEqual(captured.get("user_id"), "u1")


class OutcomeMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_metrics_includes_outcome_block(self):
        from shared import trace_db
        pool = AsyncMock()
        pool.fetchrow.return_value = {"total": 10, "avg_latency_ms": 120.0}

        async def _fetch(sql, *a):
            if "outcome" in sql:
                return [{"key": "copied", "count": 6}, {"key": "thumbs_down", "count": 1}]
            return [{"key": "software_engineering", "count": 10}]
        pool.fetch.side_effect = _fetch

        with patch.object(trace_db, "_pool", pool):
            m = await trace_db.query_metrics()

        self.assertIn("by_outcome", m)
        self.assertEqual(m["by_outcome"]["copied"], 6)
        self.assertIn("outcome_rate", m)  # share of traces with any outcome


if __name__ == "__main__":
    unittest.main()
