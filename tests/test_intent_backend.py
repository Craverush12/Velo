import json
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from api import intent as intent_api
from core.contracts import GAP_FIELDS, detect_gaps, compute_confidence, build_gap_questions
from core.source_catalog import load_source_catalog, recommend_sources


def valid_classification() -> dict:
    return {
        "intent": "design_brief",
        "domain": "design_ux",
        "interpreted_need": "Create a better UI prompt for a SaaS dashboard.",
        "deliverable": "A confirmed prompt enhancement plan for a dashboard UI.",
        "target_audience": "SaaS product teams",
        "output_format": "Annotated enhanced prompt",
        "key_constraints": ["Use accessible component patterns."],
        "assumptions": ["The user wants a browser UI."],
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

    def test_detect_gaps_returns_empty_when_all_filled(self):
        classification = {
            "target_audience": "developers",
            "output_format": "markdown",
            "key_constraints": ["keep it short"],
        }
        gaps = detect_gaps(classification)
        self.assertEqual(gaps, [])

    def test_detect_gaps_detects_missing_fields(self):
        classification = {
            "target_audience": "",
            "output_format": "markdown",
            "key_constraints": [],
        }
        gaps = detect_gaps(classification)
        self.assertEqual(gaps, ["target_audience", "key_constraints"])

    def test_detect_gaps_returns_all_when_all_missing(self):
        gaps = detect_gaps({})
        self.assertEqual(set(gaps), set(GAP_FIELDS))

    def test_compute_confidence_full(self):
        classification = {
            "target_audience": "devs",
            "output_format": "doc",
            "key_constraints": ["fast"],
        }
        self.assertEqual(compute_confidence(classification), 1.0)

    def test_compute_confidence_partial(self):
        classification = {
            "target_audience": "devs",
            "output_format": "",
            "key_constraints": [],
        }
        self.assertAlmostEqual(compute_confidence(classification), 1.0 / 3.0)

    def test_compute_confidence_zero(self):
        self.assertEqual(compute_confidence({}), 0.0)

    def test_build_gap_questions_returns_persuasive_questions(self):
        questions = build_gap_questions(["target_audience", "key_constraints"])
        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0].id, "target_audience")
        self.assertIn("tailor", questions[0].question.lower())
        self.assertEqual(questions[1].id, "key_constraints")
        self.assertIn("guardrails", questions[1].question.lower())

    async def test_confirm_intent_returns_normalized_classification(self):
        calls = []

        async def fake_complete(system_prompt, user_message, temperature=0.7, max_tokens=4096):
            calls.append({
                "system_prompt": system_prompt,
                "user_message": user_message,
                "temperature": temperature,
                "max_tokens": max_tokens,
            })
            return json.dumps(valid_classification())

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
        self.assertEqual(result["target_audience"], "SaaS product teams")
        self.assertEqual(result["output_format"], "Annotated enhanced prompt")
        self.assertEqual(result["key_constraints"], ["Use accessible component patterns."])
        self.assertGreaterEqual(len(result["source_inspirations"]), 1)
        # Computed fields
        self.assertTrue("is_finalized" in result)
        self.assertTrue("confidence" in result)
        self.assertTrue("questions" in result)
        self.assertTrue("questions_total" in result)
        # No gaps in our test data → no questions
        self.assertEqual(result["questions"], [])
        self.assertEqual(result["questions_total"], 0)
        self.assertTrue(result["is_finalized"])
        self.assertEqual(result["confidence"], 1.0)

    async def test_confirm_intent_detects_gaps_and_creates_questions(self):
        partial = valid_classification()
        partial["target_audience"] = ""
        partial["key_constraints"] = []

        calls = []

        async def fake_complete(system_prompt, user_message, temperature=0.7, max_tokens=4096):
            calls.append({"user_message": user_message})
            return json.dumps(partial)

        request = intent_api.IntentConfirmRequest(
            prompt="Write a post about AI",
            user_id="intent-test",
        )

        with patch.object(intent_api, "complete", fake_complete):
            result = await intent_api.confirm_intent(request)

        self.assertFalse(result["is_finalized"])
        self.assertAlmostEqual(result["confidence"], 1.0 / 3.0)
        self.assertEqual(result["questions_total"], 2)
        self.assertEqual(len(result["questions"]), 2)
        self.assertEqual(result["questions"][0]["id"], "target_audience")
        self.assertEqual(result["questions"][1]["id"], "key_constraints")


if __name__ == "__main__":
    unittest.main()
