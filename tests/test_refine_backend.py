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
            prompt_mode="caveman",
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
        payload = json.loads(message[message.index("{"):])

        self.assertIn("untrusted user data", message)
        self.assertEqual(payload["original_prompt"], "write a chart script")
        self.assertEqual(payload["target_ai"], "claude")
        self.assertEqual(payload["prompt_mode"], "caveman")
        self.assertEqual(payload["previous_enhanced_prompt"], "Create a clear Python charting script.")
        self.assertEqual(payload["previous_framework_used"], "RTF")
        self.assertIn("persona_injection", payload["previous_pe_techniques_applied"])
        self.assertEqual(payload["previous_annotated_segments"][0]["text"], "Create a clear Python charting script.")
        self.assertEqual(payload["clarification_qa"][0]["question"], "What chart?")
        self.assertEqual(payload["clarification_qa"][0]["answer"], "bar chart")

    def test_build_message_falls_back_when_previous_context_absent(self):
        request = refine_api.RefineRequest(
            original_prompt="write a chart script",
            clarification_qa=[{"question": "What chart?", "answer": "bar chart"}],
        )

        message = refine_api.build_refine_user_message(request)
        payload = json.loads(message[message.index("{"):])

        self.assertIn("If previous_enhanced_prompt is null", message)
        self.assertIsNone(payload["previous_enhanced_prompt"])
        self.assertEqual(payload["original_prompt"], "write a chart script")

    def test_invalid_empty_qa_answer_fails_validation(self):
        with self.assertRaises(ValidationError):
            refine_api.RefineRequest(
                original_prompt="write a chart script",
                clarification_qa=[{"question": "What chart?", "answer": ""}],
            )

    def test_invalid_target_ai_fails_validation(self):
        with self.assertRaises(ValidationError):
            refine_api.RefineRequest(
                original_prompt="write a chart script",
                target_ai="unknown-ai",
                clarification_qa=[{"question": "What chart?", "answer": "bar chart"}],
            )

    def test_invalid_prompt_mode_fails_validation(self):
        with self.assertRaises(ValidationError):
            refine_api.RefineRequest(
                original_prompt="write a chart script",
                prompt_mode="opera",
                clarification_qa=[{"question": "What chart?", "answer": "bar chart"}],
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
        self.assertIn("previous_enhanced_prompt", calls[0]["user_message"])
        self.assertEqual(result["framework_used"], "RTF")
        self.assertEqual(result["schema_version"], refine_api.parse_validate_with_repair.__globals__["SCHEMA_VERSION"])


if __name__ == "__main__":
    unittest.main()
