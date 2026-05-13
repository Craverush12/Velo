import json
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from api import intent as intent_api
from core.source_catalog import load_source_catalog, recommend_sources


def valid_intent_payload() -> dict:
    return {
        "schema_version": intent_api.INTENT_CONFIRMATION_VERSION,
        "intent": "design_brief",
        "domain": "design_ux",
        "interpreted_need": "Create a better UI prompt for a SaaS dashboard.",
        "deliverable": "A confirmed prompt enhancement plan for a dashboard UI.",
        "target_audience": "SaaS product teams",
        "output_format": "Annotated enhanced prompt",
        "key_constraints": ["Use accessible component patterns."],
        "assumptions": ["The user wants a browser UI."],
        "missing_context": ["Dashboard user role"],
        "confirmation_question": "Should ThinkVelocity optimize this as a SaaS dashboard UI prompt?",
        "confidence": 0.82,
        "suggested_prompt_mode": "normal",
        "suggested_techniques": ["task_clarification", "structured_output"],
        "enhancement_strategy": ["Add role, constraints, UI sections, and output format."],
        "source_inspirations": [],
    }


class IntentBackendTests(unittest.IsolatedAsyncioTestCase):
    def test_source_catalog_loads_scraping_sources(self):
        sources = load_source_catalog()

        self.assertGreaterEqual(len(sources), 30)
        self.assertTrue(any(source["name"] == "ShadCN UI" for source in sources))
        self.assertTrue(any(source["name"] == "v0 by Vercel" for source in sources))
        self.assertFalse(any("â" in source["category"] for source in sources))

    def test_recommend_sources_uses_prompt_context(self):
        sources = recommend_sources("Build an animated landing page UI prompt for v0")
        names = {source["name"] for source in sources}

        self.assertIn("v0 by Vercel", names)
        self.assertTrue({"Aceternity UI", "Magic UI", "Motion Primitives"} & names)

    def test_invalid_prompt_mode_fails_validation(self):
        with self.assertRaises(ValidationError):
            intent_api.IntentConfirmRequest(prompt="make UI", prompt_mode="wizard")

    async def test_confirm_intent_returns_normalized_confirmation(self):
        calls = []

        async def fake_complete(system_prompt, user_message, temperature=0.7, max_tokens=4096):
            calls.append({
                "system_prompt": system_prompt,
                "user_message": user_message,
                "temperature": temperature,
                "max_tokens": max_tokens,
            })
            return json.dumps(valid_intent_payload())

        request = intent_api.IntentConfirmRequest(
            prompt="Make my dashboard UI prompt better",
            target_ai="v0",
            prompt_mode="caveman",
            user_id="intent-test",
        )

        with patch.object(intent_api, "complete", fake_complete):
            result = await intent_api.confirm_intent(request)

        payload = json.loads(calls[0]["user_message"][calls[0]["user_message"].index("{"):])
        self.assertEqual(calls[0]["temperature"], 0.2)
        self.assertIn("source_catalog", payload)
        self.assertEqual(result["target_ai"], "bolt")
        self.assertEqual(result["prompt_mode"], "caveman")
        self.assertEqual(result["suggested_prompt_mode"], "normal")
        self.assertEqual(result["intent"], "design_brief")
        self.assertGreaterEqual(len(result["source_inspirations"]), 1)

    async def test_update_intent_normalizes_user_edits_without_llm(self):
        edited = valid_intent_payload()
        edited.update({
            "intent": "marketing",
            "domain": "marketing_growth",
            "interpreted_need": "Create a homepage prompt for a CRM launch.",
            "deliverable": "A launch homepage prompt.",
            "suggested_prompt_mode": "cave",
            "suggested_techniques": ["made_up", "contrastive", "structured_output"],
            "enhancement_strategy": ["Make sections conversion-focused."],
        })
        request = intent_api.IntentUpdateRequest(
            prompt="make landing page",
            target_ai="chatgpt",
            prompt_mode="normal",
            user_id="intent-test",
            confirmation=edited,
        )

        with patch.object(intent_api, "complete") as complete_mock:
            result = await intent_api.update_intent(request)

        complete_mock.assert_not_called()
        self.assertTrue(result["_updated"])
        self.assertEqual(result["intent"], "marketing")
        self.assertEqual(result["domain"], "marketing_growth")
        self.assertEqual(result["suggested_prompt_mode"], "caveman")
        self.assertEqual(result["suggested_techniques"], ["contrastive", "structured_output"])
        self.assertEqual(result["target_ai"], "chatgpt")


if __name__ == "__main__":
    unittest.main()
