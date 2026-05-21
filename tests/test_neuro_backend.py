import json
import unittest
from unittest.mock import patch


def neuro_score_payload() -> dict:
    return {
        "overall_score": 87,
        "score_delta": 41,
        "label": "High Signal",
        "dimensions": {
            "clarity": 92,
            "sensory_specificity": 70,
            "temporal_structure": 85,
            "attention_salience": 90,
            "cognitive_load": 78,
            "output_grounding": 88,
            "multimodal_readiness": 65,
            "personal_fit": 91,
        },
        "strengths": ["Clear task role", "Strong output grounding"],
        "risks": ["Could include one concrete example"],
        "suggested_improvements": ["Add an acceptance checklist"],
    }


class NeuroBackendTests(unittest.IsolatedAsyncioTestCase):
    async def test_neuro_score_returns_valid_scorecard(self):
        from api import neuro as neuro_api

        async def fake_complete(system_prompt, user_message, temperature=0.7, max_tokens=4096):
            return json.dumps(neuro_score_payload())

        request = neuro_api.NeuroScoreRequest(
            raw_prompt="write a plan",
            enhanced_prompt="Write a senior engineering implementation plan with tests.",
            target_ai="claude",
            prompt_mode="normal",
            personalization_context={
                "tone": "direct",
                "format_preferences": ["implementation checklist"],
            },
        )

        with patch.object(neuro_api, "complete", fake_complete):
            result = await neuro_api.score_neuroprompt(request)

        self.assertEqual(result["schema_version"], "2026-05-21.neuro-score.v1")
        self.assertEqual(result["overall_score"], 87)
        self.assertEqual(result["dimensions"]["personal_fit"], 91)
        self.assertIn("not fMRI prediction", result["disclaimer"])

    def test_empty_raw_prompt_fails_validation(self):
        from api import neuro as neuro_api

        with self.assertRaises(ValueError):
            neuro_api.NeuroScoreRequest(raw_prompt="")

    def test_neuro_label_alias_is_normalized(self):
        from core.neuro_contracts import NeuroScoreResult

        payload = neuro_score_payload()
        payload["label"] = "Strong Signal"

        result = NeuroScoreResult.model_validate(payload)

        self.assertEqual(result.label, "Strong")


if __name__ == "__main__":
    unittest.main()
