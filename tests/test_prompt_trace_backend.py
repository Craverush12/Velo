from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api import enhance as enhance_api
from api import refine as refine_api
from api.admin import get_admin_store, get_prompt_trace_store
from core.contracts import ClarificationQA
from core.output_validator import OutputValidationError
from main import app
from storage.admin_store import AdminStore
from storage.prompt_trace_store import PromptTraceStore


VALID_ENHANCE_PAYLOAD = {
    "enhanced_prompt": "You are a senior Python engineer. Build a FastAPI API with tests.",
    "annotated_segments": [
        {
            "id": "s1",
            "text": "You are a senior Python engineer. Build a FastAPI API with tests.",
            "technique": "persona_injection",
            "technique_label": "Persona Injection",
            "color_key": "indigo",
            "reason": "Sets expert role and task.",
            "is_original": False,
            "original_text": None,
        }
    ],
    "placeholder_fields": [],
    "framework_used": "RTF",
    "framework_rationale": "Role-task-format fits implementation prompts.",
    "pe_techniques_applied": ["persona_injection"],
    "intent": "code_generation",
    "domain": "software_engineering",
    "prompt_quality_score": 0.82,
    "target_ai_optimized": False,
    "target_ai_recommendations": [],
    "clarification_questions": [],
    "recommended_connectors": [],
    "summary": "Enhancement focused the prompt on FastAPI delivery.",
}

VALID_REFINE_PAYLOAD = {
    "refined_prompt": "You are a senior Python engineer. Ship the trace API with tests and docs.",
    "annotated_segments": [
        {
            "id": "r1",
            "text": "You are a senior Python engineer. Ship the trace API with tests and docs.",
            "technique": "task_clarification",
            "technique_label": "Task Clarification",
            "color_key": "sky",
            "reason": "Applies clarification to delivery requirements.",
            "is_original": False,
            "original_text": None,
        }
    ],
    "placeholder_fields": [],
    "framework_used": "RTF",
    "framework_rationale": "Role-task-format fits refinement.",
    "pe_techniques_applied": ["task_clarification"],
    "prompt_quality_score": 0.86,
    "quality_delta": 0.12,
    "key_additions": ["Added tests and docs."],
    "recommended_connectors": [],
    "summary": "Refined with testing and documentation constraints.",
}


class PromptTraceStoreTests(unittest.TestCase):
    def test_store_records_lists_and_summarizes_prompt_traces(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = PromptTraceStore.local(Path(tmp))

            saved = store.record(
                {
                    "flow": "enhance",
                    "status": "completed",
                    "user_id": "user_1",
                    "session_id": "session_1",
                    "prompt_mode": "research",
                    "target_ai": "claude",
                    "model": "groq/llama-3.3-70b-versatile",
                    "prompt_version": "abc123",
                    "prompt_files": ["enhance_system.md", "enhance_research_overlay.md"],
                    "input": {"raw_prompt": "write api", "redacted_prompt": "write api"},
                    "output": {
                        "final_text": "You are an API expert. Write the API.",
                        "quality_score": 0.82,
                    },
                    "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                    "timings": {"total_ms": 123, "llm_ms": 100},
                    "validation": {"status": "valid", "repair_status": "not_needed"},
                    "before_after": {
                        "before": "write api",
                        "after": "You are an API expert. Write the API.",
                    },
                }
            )

            listed = store.list_traces()
            metrics = store.metrics()
            fetched = store.get(saved["trace_id"])

            self.assertEqual(listed["total"], 1)
            self.assertEqual(fetched["trace_id"], saved["trace_id"])
            self.assertEqual(metrics["totals"]["traces"], 1)
            self.assertEqual(metrics["totals"]["tokens"], 30)
            self.assertEqual(metrics["by_flow"]["enhance"]["count"], 1)
            self.assertGreater(metrics["quality"]["average_score"], 0.8)


class EnhanceTraceCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_enhance_once_writes_trace_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_store = PromptTraceStore.local(Path(tmp))
            request = enhance_api.EnhanceRequest(
                prompt="Write a FastAPI endpoint for traces.",
                user_id="trace_user",
                session_id="trace_session",
                prompt_mode="research",
                target_ai="claude",
            )
            bundle = MagicMock()
            bundle.text = "System prompt text"
            bundle.version = "trace-version"
            bundle.mode = "research"
            bundle.files = ("enhance_system.md", "enhance_research_overlay.md")

            async def fake_complete_with_usage(system, user, model=None, **kwargs):
                return json.dumps(VALID_ENHANCE_PAYLOAD), {
                    "prompt_tokens": 11,
                    "completion_tokens": 22,
                    "total_tokens": 33,
                }

            with patch.object(enhance_api, "complete_with_usage", fake_complete_with_usage), \
                 patch.object(enhance_api, "get_prompt_trace_store", return_value=trace_store), \
                 patch.object(enhance_api, "store", MagicMock(get_user_context=MagicMock(return_value={}))), \
                 patch("core.context_loader.retrieve_relevant_context", return_value=[]):
                result = await enhance_api._run_enhance_once(request, bundle)

            traces = trace_store.list_traces()["items"]
            self.assertEqual(len(traces), 1)
            self.assertEqual(result["_trace_id"], traces[0]["trace_id"])
            self.assertEqual(traces[0]["flow"], "enhance")
            self.assertEqual(traces[0]["status"], "completed")
            self.assertEqual(traces[0]["prompt_version"], "trace-version")

    async def test_run_enhance_once_writes_failed_trace_when_validation_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_store = PromptTraceStore.local(Path(tmp))
            request = enhance_api.EnhanceRequest(
                prompt="Write a FastAPI endpoint for traces.",
                user_id="trace_user",
                prompt_mode="research",
            )
            bundle = MagicMock()
            bundle.text = "System prompt text"
            bundle.version = "trace-version"
            bundle.mode = "research"
            bundle.files = ("enhance_system.md",)

            async def fake_complete_with_usage(system, user, model=None, **kwargs):
                return "not json", {"total_tokens": 7}

            async def failing_repair(kind, raw, repair_prompt):
                return "still not json"

            with patch.object(enhance_api, "complete_with_usage", fake_complete_with_usage), \
                 patch.object(enhance_api, "_repair_output", failing_repair), \
                 patch.object(enhance_api, "get_prompt_trace_store", return_value=trace_store), \
                 patch.object(enhance_api, "store", MagicMock(get_user_context=MagicMock(return_value={}))), \
                 patch("core.context_loader.retrieve_relevant_context", return_value=[]):
                with self.assertRaises(OutputValidationError):
                    await enhance_api._run_enhance_once(request, bundle)

            traces = trace_store.list_traces(include_payload=True)["items"]
            self.assertEqual(len(traces), 1)
            self.assertEqual(traces[0]["status"], "failed")
            self.assertEqual(traces[0]["validation"]["status"], "error")


class RefineTraceCaptureTests(unittest.IsolatedAsyncioTestCase):
    async def test_refine_writes_trace_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_store = PromptTraceStore.local(Path(tmp))
            request = refine_api.RefineRequest(
                original_prompt="Ship trace API",
                previous_enhanced_prompt="Ship trace API with backend tests",
                clarification_qa=[
                    ClarificationQA(question="What else is required?", answer="Docs for dashboard integration"),
                ],
                user_id="trace_user",
                prompt_mode="research",
            )

            async def fake_complete(system, user, temperature=0.7, max_tokens=4096, model=None):
                return json.dumps(VALID_REFINE_PAYLOAD)

            with patch.object(refine_api, "complete", fake_complete), \
                 patch.object(refine_api, "get_prompt_trace_store", return_value=trace_store):
                result = await refine_api.refine(request)

            traces = trace_store.list_traces()["items"]
            self.assertEqual(len(traces), 1)
            self.assertEqual(result["_trace_id"], traces[0]["trace_id"])
            trace = trace_store.get(result["_trace_id"])
            self.assertEqual(traces[0]["flow"], "refine")
            self.assertEqual(traces[0]["status"], "completed")
            self.assertEqual(trace["before_after"]["before"], "Ship trace API with backend tests")


class PromptTraceApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.admin_store = AdminStore.local(Path(self.tmp.name) / "admin")
        self.admin_store.ensure_bootstrap_admin("owner@example.com", "change-me-now")
        self.trace_store = PromptTraceStore.local(Path(self.tmp.name) / "traces")
        self.trace = self.trace_store.record(
            {
                "flow": "enhance",
                "status": "completed",
                "user_id": "dash_user",
                "prompt_mode": "fast_build",
                "target_ai": "cursor",
                "input": {"raw_prompt": "ship api", "redacted_prompt": "ship api"},
                "output": {"final_text": "Ship the API with tests.", "quality_score": 0.9},
                "usage": {"total_tokens": 44},
                "timings": {"total_ms": 88},
                "validation": {"status": "valid"},
                "before_after": {"before": "ship api", "after": "Ship the API with tests."},
            }
        )
        app.dependency_overrides[get_admin_store] = lambda: self.admin_store
        app.dependency_overrides[get_prompt_trace_store] = lambda: self.trace_store
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.tmp.cleanup()
        os.environ.pop("PROMPT_ANALYTICS_API_TOKEN", None)

    def _login(self):
        response = self.client.post(
            "/admin/api/login",
            json={"email": "owner@example.com", "password": "change-me-now"},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_admin_session_can_list_fetch_and_diff_traces(self):
        self._login()

        traces = self.client.get("/admin/api/prompt-traces")
        fetched = self.client.get(f"/admin/api/prompt-traces/{self.trace['trace_id']}")
        diff = self.client.get(f"/admin/api/prompt-traces/{self.trace['trace_id']}/diff")
        metrics = self.client.get("/admin/api/prompt-metrics")

        self.assertEqual(traces.status_code, 200, traces.text)
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(diff.status_code, 200, diff.text)
        self.assertEqual(metrics.status_code, 200, metrics.text)
        self.assertEqual(traces.json()["total"], 1)
        self.assertEqual(fetched.json()["trace"]["trace_id"], self.trace["trace_id"])
        self.assertIn("-ship api", diff.json()["unified_diff"])
        self.assertEqual(metrics.json()["metrics"]["totals"]["traces"], 1)

    def test_bearer_token_can_access_dashboard_contract_endpoints(self):
        os.environ["PROMPT_ANALYTICS_API_TOKEN"] = "dashboard-secret"

        unauthenticated = self.client.get("/admin/api/prompt-metrics")
        authorized = self.client.get(
            "/admin/api/prompt-metrics",
            headers={"Authorization": "Bearer dashboard-secret"},
        )

        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(authorized.status_code, 200, authorized.text)
        self.assertEqual(authorized.json()["metrics"]["totals"]["traces"], 1)


if __name__ == "__main__":
    unittest.main()
