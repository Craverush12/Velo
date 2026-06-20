# python-ai-unified/tests/test_quality_mirror.py
from __future__ import annotations
import importlib, pathlib, sys, unittest
from unittest.mock import AsyncMock, patch

AI_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))
from fastapi.testclient import TestClient  # noqa: E402


class QualityMirrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Guard against repo-root main.py shadowing (local_app prepends repo root
        # to sys.path); force this service dir and reimport a clean main.
        sys.path.insert(0, str(AI_ROOT))
        sys.modules.pop("main", None)
        cls.main = importlib.import_module("main")
        from routers.admin import analytics
        cls.analytics = analytics
        # Bypass bearer auth for the handler-logic test.
        cls.main.app.dependency_overrides[analytics._require_bearer] = lambda: {"auth_type": "test"}
        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls):
        cls.main.app.dependency_overrides.pop(cls.analytics._require_bearer, None)

    def test_returns_outcome_metrics(self):
        fake = {"total": 100, "avg_latency_ms": 130.0, "by_domain": {},
                "by_intent": {}, "by_suggested_ai": {},
                "by_outcome": {"copied": 60, "thumbs_down": 5, "none": 35},
                "outcome_rate": 0.65}
        with patch("shared.trace_db.query_metrics", new=AsyncMock(return_value=fake)):
            r = self.client.get("/admin/api/quality-mirror")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["outcome_rate"], 0.65)
        self.assertEqual(body["by_outcome"]["copied"], 60)


if __name__ == "__main__":
    unittest.main()
