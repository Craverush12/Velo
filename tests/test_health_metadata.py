import unittest

from core.contracts import SCHEMA_VERSION
from main import health


class HealthMetadataTests(unittest.TestCase):
    def test_health_includes_prompt_and_schema_metadata(self):
        result = health()

        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertIn("enhance_prompt_hash", result)
        self.assertIn("refine_prompt_hash", result)
        self.assertEqual(len(result["enhance_prompt_hash"]), 64)
        self.assertEqual(len(result["refine_prompt_hash"]), 64)


if __name__ == "__main__":
    unittest.main()
