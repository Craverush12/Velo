from __future__ import annotations

import importlib
import pathlib
import sys
import unittest
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient


AI_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))


class ConnectivityRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        main = importlib.import_module("main")
        cls.client = TestClient(main.app)

    def test_api_v1_quality_health_is_json_compatibility_alias(self) -> None:
        response = self.client.get("/api/v1/quality/health")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("application/json"))
        body = response.json()
        self.assertEqual(body["status"], "healthy")
        self.assertIn("samples", body)

    def test_moderation_examples_returns_bundled_kb_summary(self) -> None:
        response = self.client.get("/ai/moderation/examples")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], len(body["examples"]))
        self.assertGreater(body["count"], 0)
        self.assertIn("decisions", body)
        self.assertIn("labels", body)
        self.assertIn("text", body["examples"][0])
        self.assertIn("label", body["examples"][0])
        self.assertIn("decision", body["examples"][0])

    def test_moderation_cache_delete_clears_verdict_keys(self) -> None:
        moderation = importlib.import_module("routers.ai.moderation")
        deleted: list[str] = []
        verdict_key_a = "ai:mod:" + ("a" * 64)
        verdict_key_b = "ai:mod:" + ("b" * 64)

        class FakeRedis:
            async def scan_iter(self, match: str) -> Any:
                self.match = match
                for key in (
                    verdict_key_a,
                    verdict_key_b.encode("utf-8"),
                    "ai:mod:stats",
                    "ai:mod:rl:127.0.0.1",
                    "other:key",
                ):
                    yield key

            async def delete(self, *keys: str) -> int:
                deleted.extend(keys)
                return len(keys)

        fake = FakeRedis()
        with patch.object(moderation, "get_redis", return_value=fake):
            response = self.client.delete("/ai/moderation/cache")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "cleared")
        self.assertEqual(body["deleted"], 2)
        self.assertEqual(body["pattern"], "ai:mod:*")
        self.assertEqual(deleted, [verdict_key_a, verdict_key_b])


if __name__ == "__main__":
    unittest.main()
