import json
import unittest

from core.contracts import SCHEMA_VERSION, TECHNIQUE_COLORS
from core.output_validator import (
    OutputValidationError,
    _repair_prompt,
    parse_validate_with_repair,
    validate_enhance_result,
    validate_refine_result,
)


def valid_enhance_payload() -> dict:
    prompt = "You are a senior Python engineer. Write a function that parses nested JSON."
    return {
        "enhanced_prompt": prompt,
        "annotated_segments": [
            {
                "id": "s1",
                "text": "You are a senior Python engineer. ",
                "technique": "persona_injection",
                "technique_label": "Persona Injection",
                "color_key": "red",
                "reason": "Sets the correct implementation role.",
                "is_original": False,
                "original_text": None,
            },
            {
                "id": "s2",
                "text": "Write a function that parses nested JSON.",
                "technique": "task_clarification",
                "technique_label": "Task Clarification",
                "color_key": "sky",
                "reason": "Clarifies the user's task.",
                "is_original": True,
                "original_text": "parse JSON",
            },
        ],
        "placeholder_fields": [],
        "framework_used": "RTF",
        "framework_rationale": "RTF fits a direct coding deliverable.",
        "pe_techniques_applied": ["persona_injection"],
        "intent": "code_generation",
        "domain": "software_engineering",
        "prompt_quality_score": 0.9,
        "target_ai_optimized": False,
        "clarification_questions": ["Which Python version should this support?"],
        "summary": "The prompt now specifies role and task clearly.",
    }


def valid_refine_payload() -> dict:
    prompt = "You are a senior Python engineer. Write a Python 3.12 function that parses nested JSON."
    return {
        "refined_prompt": prompt,
        "annotated_segments": [
            {
                "id": "r1",
                "text": "You are a senior Python engineer. ",
                "technique": "persona_injection",
                "technique_label": "Persona Injection",
                "color_key": "indigo",
                "reason": "Keeps the useful expert role.",
                "is_original": False,
                "original_text": None,
            },
            {
                "id": "r2",
                "text": "Write a Python 3.12 function that parses nested JSON.",
                "technique": "task_clarification",
                "technique_label": "Task Clarification",
                "color_key": "sky",
                "reason": "Adds the clarified Python version.",
                "is_original": False,
                "original_text": None,
            },
        ],
        "placeholder_fields": [],
        "framework_used": "RTF",
        "pe_techniques_applied": ["task_clarification"],
        "key_additions": ["Added Python 3.12."],
        "summary": "The prompt now includes the requested runtime.",
    }


class OutputValidatorTests(unittest.IsolatedAsyncioTestCase):
    def test_validate_enhance_repairs_color_and_normalizes_techniques(self):
        result = validate_enhance_result(
            valid_enhance_payload(),
            raw_prompt="parse JSON",
            prompt_hash="abc123",
            prompt_mode="caveman",
        )

        self.assertEqual(result["annotated_segments"][0]["color_key"], "indigo")
        self.assertEqual(
            result["pe_techniques_applied"],
            ["persona_injection", "task_clarification"],
        )
        self.assertEqual(result["prompt_version"], "abc123")
        self.assertEqual(result["prompt_mode"], "caveman")
        self.assertEqual(result["schema_version"], SCHEMA_VERSION)
        self.assertLessEqual(result["prompt_quality_score"], 0.18)
        self.assertEqual(result["clarification_questions"][0]["question"], "Which Python version should this support?")

    def test_segment_whitespace_repair(self):
        payload = valid_refine_payload()
        payload["annotated_segments"][0]["text"] = payload["annotated_segments"][0]["text"].strip()
        result = validate_refine_result(payload)

        self.assertEqual(
            "".join(seg["text"] for seg in result["annotated_segments"]),
            result["refined_prompt"],
        )

    def test_invalid_technique_fails(self):
        payload = valid_refine_payload()
        payload["annotated_segments"][0]["technique"] = "made_up"

        with self.assertRaises(OutputValidationError):
            validate_refine_result(payload)

    def test_all_allowed_techniques_have_matching_colors(self):
        prompt = "".join(f"{key}. " for key in TECHNIQUE_COLORS)
        payload = {
            "refined_prompt": prompt,
            "annotated_segments": [
                {
                    "id": f"r{i}",
                    "text": f"{key}. ",
                    "technique": key,
                    "technique_label": key.replace("_", " ").title(),
                    "color_key": "red",
                    "reason": f"Exercises {key}.",
                    "is_original": False,
                    "original_text": None,
                }
                for i, key in enumerate(TECHNIQUE_COLORS, 1)
            ],
            "placeholder_fields": [],
            "framework_used": "RTF",
            "pe_techniques_applied": [],
            "key_additions": [],
            "summary": "All techniques validate.",
        }

        result = validate_refine_result(payload)

        self.assertEqual(
            [seg["color_key"] for seg in result["annotated_segments"]],
            [TECHNIQUE_COLORS[seg["technique"]] for seg in result["annotated_segments"]],
        )

    def test_placeholder_mismatch_fails(self):
        payload = valid_refine_payload()
        payload["refined_prompt"] += " Use [TARGET_AUDIENCE]."
        payload["annotated_segments"][-1]["text"] += " Use [TARGET_AUDIENCE]."

        with self.assertRaises(OutputValidationError) as ctx:
            validate_refine_result(payload)

        self.assertEqual(ctx.exception.error_code, "placeholder_mismatch")

    async def test_parse_validate_with_repair_uses_repair_callback(self):
        bad_raw = json.dumps({"refined_prompt": "missing required fields"})
        repaired_raw = json.dumps(valid_refine_payload())
        calls = []

        async def repair_callback(kind, raw, repair_prompt):
            calls.append((kind, raw, repair_prompt))
            return repaired_raw

        result = await parse_validate_with_repair(
            "refine",
            bad_raw,
            repair_callback=repair_callback,
        )

        self.assertEqual(calls[0][0], "refine")
        self.assertEqual(result["_repair_status"], "llm_repaired")
        self.assertEqual(result["framework_used"], "RTF")

    def test_repair_prompt_is_conservative_and_lists_enums(self):
        error = OutputValidationError("bad", validation_errors=[{"field": "x"}])
        repair_prompt = _repair_prompt("enhance", '{"bad": true}', error)

        self.assertIn("Preserve the final prompt text exactly", repair_prompt)
        self.assertIn("tree_of_thought", repair_prompt)
        self.assertIn("structured_output", repair_prompt)
        self.assertIn("Allowed color keys", repair_prompt)


if __name__ == "__main__":
    unittest.main()
