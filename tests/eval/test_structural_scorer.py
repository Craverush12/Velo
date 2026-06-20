# tests/eval/test_structural_scorer.py
import pathlib, sys
import unittest

EVAL_DIR = pathlib.Path(__file__).resolve().parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

from structural_scorer import score_enhancement  # noqa: E402


class StructuralScorerTests(unittest.TestCase):
    def _good(self):
        return {
            "enhanced_prompt": (
                "You are a senior Python engineer. Your task is to write a function. "
                "Output must be a single code block with type hints. Do not use eval(). "
                "Provide [TEST_CASES] as examples."
            ),
            "annotated_segments": [
                {"technique": "persona_injection"}, {"technique": "task_clarification"},
                {"technique": "output_format_spec"}, {"technique": "constraint_definition"},
                {"technique": "negative_space"},
            ],
            "raw_prompt": "write a python function to dedupe a list",
        }

    def test_good_enhancement_scores_high(self):
        s = score_enhancement(self._good())
        self.assertGreaterEqual(s["score"], 0.8)
        self.assertTrue(s["checks"]["has_role"])
        self.assertTrue(s["checks"]["five_techniques"])
        self.assertTrue(s["checks"]["has_output_format"])

    def test_empty_enhancement_scores_zero(self):
        s = score_enhancement({"enhanced_prompt": "", "annotated_segments": [], "raw_prompt": "x"})
        self.assertEqual(s["score"], 0.0)

    def test_not_substantively_different_flunks_delta(self):
        same = {"enhanced_prompt": "write a function", "annotated_segments": [], "raw_prompt": "write a function"}
        s = score_enhancement(same)
        self.assertFalse(s["checks"]["length_delta"])


if __name__ == "__main__":
    unittest.main()
