import unittest

from core.contracts import SCHEMA_VERSION
from main import health


class HealthMetadataTests(unittest.TestCase):
    def test_health_includes_prompt_and_schema_metadata(self):
        result = health()

        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertIn("enhance_prompt_hash", result)
        self.assertIn("refine_prompt_hash", result)
        self.assertIn("intent_prompt_hash", result)
        self.assertIn("prompt_versions", result)
        self.assertEqual(result["prompt_modes"], ["normal", "caveman"])
        self.assertEqual(len(result["enhance_prompt_hash"]), 64)
        self.assertEqual(len(result["refine_prompt_hash"]), 64)
        self.assertEqual(len(result["intent_prompt_hash"]), 64)
        self.assertEqual(len(result["prompt_versions"]["enhance"]["caveman"]), 64)
        self.assertNotEqual(
            result["prompt_versions"]["enhance"]["normal"],
            result["prompt_versions"]["enhance"]["caveman"],
        )


if __name__ == "__main__":
    unittest.main()
