# python-ai-unified/tests/test_icp_classifier.py
from __future__ import annotations

import importlib
import os
import pathlib
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

AI_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))

_VALID_CATEGORIES = {"developer", "content_creator", "marketer", "student", "researcher", "business_operator"}

_SAMPLE_SIGNAL = {
    "title": "How do I write better prompts for ChatGPT?",
    "text": "I keep getting generic answers and wasting time rephrasing things.",
    "url": "https://reddit.com/r/ChatGPT/123",
    "source": "reddit",
    "source_score": 150,
}

_GROQ_GOOD_RESPONSE = {
    "icp_category": "content_creator",
    "problem_tags": ["generic AI output", "prompt writing", "time waste", "rephrasing fatigue"],
    "stage": "awareness",
    "emotion": "frustrated",
    "product_relevance": 0.85,
    "content_brief": "This user struggles with generic AI output and needs better prompting strategies.",
    "confidence": 0.88,
}

_GROQ_LOW_RELEVANCE_RESPONSE = {
    "icp_category": "developer",
    "problem_tags": ["api rate limits"],
    "stage": "consideration",
    "emotion": "curious",
    "product_relevance": 0.4,
    "content_brief": None,
    "confidence": 0.7,
}


def _make_groq_mock(payload: dict) -> AsyncMock:
    import json
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(payload)
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return AsyncMock(return_value=mock_response)


class ClassifySignalTests(unittest.IsolatedAsyncioTestCase):

    async def test_classify_signal_returns_required_fields(self):
        from routers.intel import icp_classifier
        mock = _make_groq_mock(_GROQ_GOOD_RESPONSE)
        with patch("shared.groq_client.groq_pool.async_chat", new=mock):
            result = await icp_classifier.classify_signal(_SAMPLE_SIGNAL)

        required = {"icp_category", "problem_tags", "stage", "emotion",
                    "product_relevance", "content_brief", "confidence"}
        for key in required:
            self.assertIn(key, result, f"Missing required key: {key}")

    async def test_classify_signal_degrades_on_groq_failure(self):
        from routers.intel import icp_classifier
        with patch("shared.groq_client.groq_pool.async_chat", new=AsyncMock(side_effect=RuntimeError("api down"))):
            result = await icp_classifier.classify_signal(_SAMPLE_SIGNAL)

        self.assertEqual(result["icp_category"], "unknown")
        self.assertEqual(result["product_relevance"], 0.0)
        self.assertIsNone(result["content_brief"])
        self.assertLess(result["confidence"], 0.3)

    async def test_product_relevance_below_threshold_no_brief(self):
        from routers.intel import icp_classifier
        mock = _make_groq_mock(_GROQ_LOW_RELEVANCE_RESPONSE)
        with patch("shared.groq_client.groq_pool.async_chat", new=mock):
            result = await icp_classifier.classify_signal(_SAMPLE_SIGNAL)

        self.assertLess(result["product_relevance"], 0.6)
        self.assertIsNone(result["content_brief"])

    async def test_product_relevance_above_threshold_has_brief(self):
        from routers.intel import icp_classifier
        mock = _make_groq_mock(_GROQ_GOOD_RESPONSE)
        with patch("shared.groq_client.groq_pool.async_chat", new=mock):
            result = await icp_classifier.classify_signal(_SAMPLE_SIGNAL)

        self.assertGreaterEqual(result["product_relevance"], 0.6)
        self.assertIsInstance(result["content_brief"], str)
        self.assertTrue(result["content_brief"].strip())

    async def test_icp_category_constrained_to_known_values(self):
        from routers.intel import icp_classifier
        mock = _make_groq_mock(_GROQ_GOOD_RESPONSE)
        with patch("shared.groq_client.groq_pool.async_chat", new=mock):
            result = await icp_classifier.classify_signal(_SAMPLE_SIGNAL)

        self.assertIn(result["icp_category"], _VALID_CATEGORIES,
                      f"icp_category '{result['icp_category']}' not in valid set")

    async def test_icp_category_unknown_on_bad_groq_value(self):
        from routers.intel import icp_classifier
        bad_payload = dict(_GROQ_GOOD_RESPONSE, icp_category="wizard", product_relevance=0.9)
        mock = _make_groq_mock(bad_payload)
        with patch("shared.groq_client.groq_pool.async_chat", new=mock):
            result = await icp_classifier.classify_signal(_SAMPLE_SIGNAL)

        self.assertEqual(result["icp_category"], "unknown")

    async def test_signal_id_passed_through(self):
        from routers.intel import icp_classifier
        signal = dict(_SAMPLE_SIGNAL, signal_id="abc-123")
        mock = _make_groq_mock(_GROQ_GOOD_RESPONSE)
        with patch("shared.groq_client.groq_pool.async_chat", new=mock):
            result = await icp_classifier.classify_signal(signal)

        self.assertEqual(result.get("signal_id"), "abc-123")

    async def test_problem_tags_capped_at_five(self):
        from routers.intel import icp_classifier
        payload = dict(_GROQ_GOOD_RESPONSE, problem_tags=["a", "b", "c", "d", "e", "f", "g"])
        mock = _make_groq_mock(payload)
        with patch("shared.groq_client.groq_pool.async_chat", new=mock):
            result = await icp_classifier.classify_signal(_SAMPLE_SIGNAL)

        self.assertLessEqual(len(result["problem_tags"]), 5)


class BriefQueueTests(unittest.TestCase):

    def test_brief_queue_push_respects_threshold(self):
        from shared.brief_queue import BriefQueue
        q = BriefQueue()
        q.push({"product_relevance": 0.4, "content_brief": None, "icp_category": "developer"})
        self.assertEqual(q.size(), 0)

        q.push({"product_relevance": 0.7, "content_brief": "A brief", "icp_category": "marketer"})
        self.assertEqual(q.size(), 1)

    def test_brief_queue_maxlen_evicts_oldest(self):
        from shared.brief_queue import BriefQueue
        q = BriefQueue()
        for i in range(501):
            q.push({"product_relevance": 0.9, "content_brief": f"brief-{i}", "icp_category": "developer"})
        self.assertEqual(q.size(), 500)

    def test_brief_queue_pop_all_drains(self):
        from shared.brief_queue import BriefQueue
        q = BriefQueue()
        for i in range(3):
            q.push({"product_relevance": 0.8, "content_brief": f"brief-{i}", "icp_category": "developer"})
        items = q.pop_all()
        self.assertEqual(len(items), 3)
        self.assertEqual(q.size(), 0)

    def test_brief_queue_peek_is_non_destructive(self):
        from shared.brief_queue import BriefQueue
        q = BriefQueue()
        q.push({"product_relevance": 0.9, "content_brief": "a", "icp_category": "student"})
        first = q.peek()
        second = q.peek()
        self.assertEqual(len(first), len(second))
        self.assertEqual(q.size(), 1)

    def test_brief_queue_peek_limit(self):
        from shared.brief_queue import BriefQueue
        q = BriefQueue()
        for i in range(60):
            q.push({"product_relevance": 0.9, "content_brief": f"b{i}", "icp_category": "marketer"})
        result = q.peek(limit=10)
        self.assertEqual(len(result), 10)
        self.assertEqual(q.size(), 60)


class IntelRouterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(AI_ROOT))
        sys.modules.pop("main", None)
        cls.main = importlib.import_module("main")
        from fastapi.testclient import TestClient
        cls.client = TestClient(cls.main.app)
        cls.token = "test-intel-token-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"

    def _post_classify(self, signals, token=None):
        headers = {}
        if token is not None:
            headers["X-Admin-Token"] = token
        return self.client.post("/intel/classify", json={"signals": signals}, headers=headers)

    def test_classify_endpoint_requires_auth(self):
        r = self._post_classify([_SAMPLE_SIGNAL])
        self.assertIn(r.status_code, (401, 403))

    def test_classify_endpoint_rejects_more_than_20_signals(self):
        signals = [_SAMPLE_SIGNAL] * 21
        with patch.dict(os.environ, {"PROMPT_ANALYTICS_API_TOKEN": self.token}):
            r = self._post_classify(signals, token=self.token)
        self.assertEqual(r.status_code, 422)

    def test_classify_endpoint_returns_results(self):
        import json

        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps(_GROQ_GOOD_RESPONSE)
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]

        with patch.dict(os.environ, {"PROMPT_ANALYTICS_API_TOKEN": self.token}):
            with patch("shared.groq_client.groq_pool.async_chat", new=AsyncMock(return_value=mock_resp)):
                r = self._post_classify([_SAMPLE_SIGNAL], token=self.token)

        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("results", body)
        self.assertEqual(len(body["results"]), 1)

    def test_briefs_get_returns_list(self):
        with patch.dict(os.environ, {"PROMPT_ANALYTICS_API_TOKEN": self.token}):
            r = self.client.get("/intel/briefs", headers={"X-Admin-Token": self.token})
        self.assertEqual(r.status_code, 200)
        self.assertIn("briefs", r.json())

    def test_briefs_delete_drains(self):
        with patch.dict(os.environ, {"PROMPT_ANALYTICS_API_TOKEN": self.token}):
            r = self.client.delete("/intel/briefs", headers={"X-Admin-Token": self.token})
        self.assertEqual(r.status_code, 200)
        self.assertIn("drained", r.json())

    def test_classify_endpoint_empty_signals_returns_empty_results(self):
        with patch.dict(os.environ, {"PROMPT_ANALYTICS_API_TOKEN": self.token}):
            r = self._post_classify([], token=self.token)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["results"], [])


if __name__ == "__main__":
    unittest.main()
