from __future__ import annotations

import asyncio
import importlib
import json
import pathlib
import sys
import unittest
from unittest.mock import patch


AI_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = AI_ROOT.parent
for path in (AI_ROOT, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


class TaxonomyBridgeTests(unittest.TestCase):
    def test_maps_context_taxonomy_to_enhance_taxonomy(self) -> None:
        bridge = importlib.import_module("shared.taxonomy_bridge")

        self.assertEqual(
            bridge.map_context_domain("software_data_engineering"),
            "software_engineering",
        )
        self.assertEqual(bridge.map_context_intent("operation"), "task_automation")
        self.assertEqual(bridge.map_context_domain("unknown_domain"), "general")
        self.assertEqual(bridge.map_context_intent("unknown_intent"), "general_qa")


class ContextHintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.enhance = importlib.import_module("routers.ai.enhance")

    def test_fetch_context_hint_returns_structured_session_context(self) -> None:
        essence = (
            "MASTER:\nBuild a FastAPI billing API using React.\n"
            "FLOW:\n- Add subscription endpoints\n- Keep Stripe webhook idempotent"
        )

        with patch.object(
            self.enhance,
            "_fetch_local_essences",
            return_value=[essence],
        ), patch("shared.settings.get_settings") as get_settings:
            get_settings.return_value.SUPERMEMORY_API_KEY = ""

            raw_hint = asyncio.run(
                self.enhance._fetch_context_hint("user_1", "billing api")
            )

        hint = json.loads(raw_hint)
        self.assertEqual(set(hint), {"session_context", "entities"})
        self.assertEqual(
            {
                key: value
                for key, value in hint["session_context"].items()
                if key != "frameworks"
            },
            {
                "user_goal": "Build a FastAPI billing API using React.",
                "current_focus": (
                    "Add subscription endpoints; Keep Stripe webhook idempotent"
                ),
                "context_intent": None,
                "context_domain": None,
                "enhance_domain_hint": None,
                "enhance_intent_hint": None,
            },
        )
        self.assertEqual(
            set(hint["session_context"]["frameworks"]), {"fastapi", "react"}
        )
        self.assertEqual(set(hint["entities"]["frameworks"]), {"fastapi", "react"})


if __name__ == "__main__":
    unittest.main()
