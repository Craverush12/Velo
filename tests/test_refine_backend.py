import json
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from api import refine as refine_api


def valid_refine_payload() -> dict:
    prompt = "You are a Python data visualization expert. Create a bar chart for revenue by date."
    return {
        "refined_prompt": prompt,
        "annotated_segments": [
            {
                "id": "r1",
                "text": "You are a Python data visualization expert. ",
                "technique": "persona_injection",
                "technique_label": "Persona Injection",
                "color_key": "indigo",
                "reason": "Sets the domain expertise needed for the answer.",
                "is_original": False,
                "original_text": None,
            },
            {
                "id": "r2",
                "text": "Create a bar chart for revenue by date.",
                "technique": "task_clarification",
                "technique_label": "Task Clarification",
                "color_key": "sky",
                "reason": "Applies the user's clarification answers.",
                "is_original": False,
                "original_text": None,
            },
        ],
        "placeholder_fields": [],
        "framework_used": "RTF",
        "pe_techniques_applied": ["persona_injection", "task_clarification"],
        "key_additions": ["Specified a bar chart using date and revenue columns."],
        "summary": "The prompt now includes the chart type and data columns.",
    }


class RefineBackendTests(unittest.IsolatedAsyncioTestCase):
    def test_build_message_includes_previous_enhancement_context(self):
        request = refine_api.RefineRequest(
            original_prompt="write a chart script",
            target_ai="claude",
            clarification_qa=[
                {"question": "What chart?", "answer": "bar chart"},
            ],
            previous_enhanced_prompt="Create a clear Python charting script.",
            previous_framework_used="RTF",
            previous_pe_techniques_applied=["persona_injection", "task_clarification"],
            previous_placeholder_fields=[],
            previous_annotated_segments=[
                {
                    "id": "s1",
                    "text": "Create a clear Python charting script.",
                    "technique": "task_clarification",
                    "technique_label": "Task Clarification",
                    "color_key": "sky",
                    "reason": "Clarifies the task.",
                    "is_original": False,
                    "original_text": None,
                }
            ],
        )

        message = refine_api.build_refine_user_message(request)

        self.assertIn("Original prompt: write a chart script", message)
        self.assertIn("Target AI: claude", message)
        self.assertIn("Previously enhanced prompt:", message)
        self.assertIn("Create a clear Python charting script.", message)
        self.assertIn("Previous framework used: RTF", message)
        self.assertIn("persona_injection", message)
        self.assertIn("Previous annotated segments JSON:", message)
        self.assertIn("Q1: What chart?", message)
        self.assertIn("A1: bar chart", message)

    def test_build_message_falls_back_when_previous_context_absent(self):
        request = refine_api.RefineRequest(
            original_prompt="write a chart script",
            clarification_qa=[{"question": "What chart?", "answer": "bar chart"}],
        )

        message = refine_api.build_refine_user_message(request)

        self.assertIn("Previously enhanced prompt: not provided", message)
        self.assertIn("Refine from the original prompt", message)

    def test_invalid_empty_qa_answer_fails_validation(self):
        with self.assertRaises(ValidationError):
            refine_api.RefineRequest(
                original_prompt="write a chart script",
                clarification_qa=[{"question": "What chart?", "answer": ""}],
            )

    async def test_refine_uses_temperature_point_three(self):
        calls = []

        async def fake_complete(system_prompt, user_message, temperature=0.7, max_tokens=4096):
            calls.append(
                {
                    "system_prompt": system_prompt,
                    "user_message": user_message,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
            )
            return json.dumps(valid_refine_payload())

        request = refine_api.RefineRequest(
            original_prompt="write a chart script",
            clarification_qa=[{"question": "What chart?", "answer": "bar chart"}],
            previous_enhanced_prompt="Create a Python charting script.",
        )

        with patch.object(refine_api, "complete", fake_complete):
            result = await refine_api.refine(request)

        self.assertEqual(calls[0]["temperature"], 0.3)
        self.assertIn("Previously enhanced prompt:", calls[0]["user_message"])
        self.assertEqual(result["framework_used"], "RTF")
        self.assertEqual(result["schema_version"], refine_api.parse_validate_with_repair.__globals__["SCHEMA_VERSION"])


if __name__ == "__main__":
    unittest.main()
