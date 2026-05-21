import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from storage import store
from core import context_loader


def extracted_profile_payload() -> dict:
    return {
        "preferences": {
            "output_style": "concise",
            "expertise_level": "senior",
            "preferred_tools": ["FastAPI", "Cursor"],
            "industry": "SaaS",
            "tone": "direct",
            "default_target_ai": "claude",
            "format_preferences": ["implementation checklist", "acceptance criteria"],
            "must_include": ["risks", "verification steps"],
            "avoid": ["generic advice", "long intros"],
            "examples_preference": "only_when_useful",
        },
        "summary": "Prefers concise senior engineering prompts with explicit verification.",
        "confidence": 0.91,
        "warnings": [],
    }


class PersonalizationBackendTests(unittest.IsolatedAsyncioTestCase):
    def test_context_loader_includes_saved_preferences_before_first_enhancement(self):
        context = {
            "user_id": "profile-first",
            "domains": [],
            "frameworks_used": [],
            "placeholder_count": 0,
            "preferences": {
                "output_style": "concise",
                "expertise_level": "senior",
                "preferred_tools": ["FastAPI"],
                "industry": "SaaS",
                "tone": "direct",
                "default_target_ai": "claude",
                "format_preferences": ["checklist"],
                "must_include": ["tests"],
                "avoid": ["fluff"],
                "examples_preference": "only_when_useful",
            },
            "recent_context": [],
            "personalization_notes": "Prefer direct senior-level implementation plans.",
            "enhancement_count": 0,
        }

        block = context_loader.format_context_for_prompt(context)
        payload = json.loads(block)

        self.assertIn("Untrusted preference data", payload["note"])
        self.assertEqual(payload["expertise_level"], "senior")
        self.assertEqual(payload["tone"], "direct")
        self.assertEqual(payload["default_target_ai"], "claude")
        self.assertEqual(payload["format_preferences"], ["checklist"])
        self.assertEqual(payload["must_include"], ["tests"])
        self.assertEqual(payload["avoid"], ["fluff"])

    async def test_extract_preview_does_not_write_profile(self):
        from api import personalization as personalization_api

        async def fake_complete(system_prompt, user_message, temperature=0.7, max_tokens=4096):
            return json.dumps(extracted_profile_payload())

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store, "_STORAGE_PATH", Path(tmp).resolve()):
                with patch.object(personalization_api, "complete", fake_complete):
                    result = await personalization_api.extract_personalization(
                        "profile-user",
                        personalization_api.PersonalizationExtractRequest(
                            notes="I prefer concise senior technical checklists.",
                            apply=False,
                        ),
                    )
                context = store.get_user_context("profile-user")

        self.assertFalse(result["applied"])
        self.assertEqual(result["preferences"]["output_style"], "concise")
        self.assertEqual(context["preferences"]["output_style"], "balanced")
        self.assertEqual(context["personalization_notes"], "")

    async def test_extract_apply_saves_profile(self):
        from api import personalization as personalization_api

        async def fake_complete(system_prompt, user_message, temperature=0.7, max_tokens=4096):
            return json.dumps(extracted_profile_payload())

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(store, "_STORAGE_PATH", Path(tmp).resolve()):
                with patch.object(personalization_api, "complete", fake_complete):
                    result = await personalization_api.extract_personalization(
                        "profile-user",
                        personalization_api.PersonalizationExtractRequest(
                            notes="I prefer concise senior technical checklists.",
                            apply=True,
                        ),
                    )
                context = store.get_user_context("profile-user")

        self.assertTrue(result["applied"])
        self.assertEqual(context["preferences"]["expertise_level"], "senior")
        self.assertEqual(context["preferences"]["tone"], "direct")
        self.assertEqual(
            context["personalization_notes"],
            "I prefer concise senior technical checklists.",
        )


if __name__ == "__main__":
    unittest.main()
