import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.contracts import PROMPT_MODE_VALUES, SCHEMA_VERSION
from main import health, ready
from storage import store


class HealthMetadataTests(unittest.TestCase):
    def test_health_includes_prompt_and_schema_metadata(self):
        result = health()

        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertIn("enhance_prompt_hash", result)
        self.assertIn("refine_prompt_hash", result)
        self.assertIn("intent_prompt_hash", result)
        self.assertIn("prompt_versions", result)
        self.assertEqual(result["prompt_modes"], list(PROMPT_MODE_VALUES))
        self.assertEqual(len(result["enhance_prompt_hash"]), 64)
        self.assertEqual(len(result["refine_prompt_hash"]), 64)
        self.assertEqual(len(result["intent_prompt_hash"]), 64)
        self.assertEqual(len(result["prompt_versions"]["enhance"]["caveman"]), 64)
        self.assertNotEqual(
            result["prompt_versions"]["enhance"]["normal"],
            result["prompt_versions"]["enhance"]["caveman"],
        )

    def test_ready_checks_storage_and_groq_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store, "_STORAGE_PATH", Path(tmp).resolve()):
                with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}, clear=False):
                    result = ready()

        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["checks"]["groq_api_key"])
        self.assertTrue(result["checks"]["storage"]["ok"])


if __name__ == "__main__":
    unittest.main()
