# python-ai-unified/tests/test_reflexion.py
from __future__ import annotations
import pathlib, sys, unittest
from unittest.mock import AsyncMock, patch

AI_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))


class ReflexionTests(unittest.IsolatedAsyncioTestCase):
    async def test_high_score_skips_llm(self):
        from routers.ai import reflexion
        good = {"enhanced_prompt": "You are a senior expert. Output must be JSON. Do not guess.",
                "annotated_segments": [{"technique": t} for t in
                    ("persona_injection","task_clarification","output_format_spec",
                     "constraint_definition","negative_space")]}
        with patch.object(reflexion, "_groq_critique", new=AsyncMock()) as m:
            out = await reflexion.maybe_improve(good, raw_prompt="x", mode="best")
        m.assert_not_called()
        self.assertEqual(out["enhanced_prompt"], good["enhanced_prompt"])

    async def test_low_score_deep_mode_calls_llm_and_replaces(self):
        from routers.ai import reflexion
        weak = {"enhanced_prompt": "do the thing", "annotated_segments": []}
        better = {"enhanced_prompt": "You are an expert. Output sections. Do not invent facts.",
                  "annotated_segments": [{"technique": t} for t in
                    ("persona_injection","task_clarification","output_format_spec",
                     "constraint_definition","negative_space")]}
        with patch.object(reflexion, "_groq_critique", new=AsyncMock(return_value=better)):
            out = await reflexion.maybe_improve(weak, raw_prompt="x", mode="best")
        self.assertEqual(out["enhanced_prompt"], better["enhanced_prompt"])

    async def test_low_score_flash_mode_skips(self):
        from routers.ai import reflexion
        weak = {"enhanced_prompt": "do the thing", "annotated_segments": []}
        with patch.object(reflexion, "_groq_critique", new=AsyncMock()) as m:
            out = await reflexion.maybe_improve(weak, raw_prompt="x", mode="flash")
        m.assert_not_called()
        self.assertEqual(out, weak)

    async def test_llm_failure_degrades_to_original(self):
        from routers.ai import reflexion
        weak = {"enhanced_prompt": "do the thing", "annotated_segments": []}
        with patch.object(reflexion, "_groq_critique", new=AsyncMock(side_effect=RuntimeError("boom"))):
            out = await reflexion.maybe_improve(weak, raw_prompt="x", mode="best")
        self.assertEqual(out, weak)


if __name__ == "__main__":
    unittest.main()
