import json
import unittest

from api.enhance import EnhanceRequest, _prepare_enhance_input
from core import context_loader
from storage import store


def _entry(summary: str, domain: str = "software_engineering", intent: str = "code_generation") -> dict:
    return {
        "summary": summary,
        "domain": domain,
        "intent": intent,
        "original_prompt": summary,
        "enhanced_prompt": f"Enhanced: {summary}",
    }


class SemanticRetrievalTests(unittest.TestCase):
    def test_context_loader_prefers_semantically_relevant_history_over_newest(self):
        context = {
            "user_id": "semantic-user",
            "domains": ["software_engineering"],
            "preferences": {"expertise_level": "senior"},
            "recent_context": [
                _entry("Write a launch email sequence for a new feature", domain="marketing"),
                _entry("Create a social media content calendar", domain="marketing"),
                _entry("Draft customer support macros for refunds", domain="support"),
                _entry("Build a FastAPI dashboard with auth, filters, and charts"),
                _entry("Design a React analytics dashboard for paid-user cohorts"),
                _entry("Implement backend metrics endpoints for analytics dashboards"),
            ],
            "enhancement_count": 6,
        }

        block = context_loader.format_context_for_prompt(
            context,
            query="Need a better prompt for a paid user analytics dashboard with filters",
        )
        payload = json.loads(block)

        summaries = [item["summary"] for item in payload["recent_work"]]
        self.assertEqual(len(summaries), 5)
        self.assertIn("Design a React analytics dashboard for paid-user cohorts", summaries[:3])
        self.assertIn("Implement backend metrics endpoints for analytics dashboards", summaries[:3])
        self.assertNotEqual(summaries[0], "Write a launch email sequence for a new feature")

    def test_enhance_input_injects_semantic_context_for_prompt_query(self):
        user_id = "semantic-hook-user"
        context = store.reset_user_context(user_id)
        context["preferences"]["expertise_level"] = "senior"
        context["enhancement_count"] = 5
        context["recent_context"] = [
            _entry("Write onboarding email drip copy", domain="marketing"),
            _entry("Create support answer macros", domain="support"),
            _entry("Build a FastAPI analytics dashboard with filters"),
            _entry("Design paid-user retention charts for a dashboard"),
            _entry("Add API metrics endpoints for dashboard cohorts"),
        ]
        store.save_user_context(user_id, context)

        request = EnhanceRequest(
            prompt="Improve this prompt for paid user dashboard analytics",
            user_id=user_id,
        )
        _, _, user_message = _prepare_enhance_input(request)
        payload = json.loads(user_message.split("\n", 3)[3])
        recent_work = payload["user_context"]["recent_work"]
        summaries = [item["summary"] for item in recent_work]

        self.assertEqual(len(summaries), 5)
        self.assertEqual(summaries[0], "Design paid-user retention charts for a dashboard")
        self.assertNotIn("Write onboarding email drip copy", summaries[:3])


if __name__ == "__main__":
    unittest.main()
