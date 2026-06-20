import asyncio
import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from routers import context as context_router  # noqa: E402


class ContextEngineQualityTests(unittest.TestCase):
    def test_compress_flow_uses_oldest_and_newest_specific_bullets(self):
        essence = """MASTER:
Building durable context memory for product workflows.

FLOW:
- mapping the current context engine persistence contract
- checking compression behavior against stale summaries
- wiring observability around incremental updates"""

        result = context_router._compress_flow_to_limit(essence, max_bullets=2)

        self.assertIn("- previously: mapping the current context engine persistence contract", result)
        self.assertIn("- wiring observability around incremental updates", result)
        self.assertNotIn("refining context for", result)
        flow_bullets = [
            line for line in result.splitlines() if line.strip().startswith("- ")
        ]
        self.assertEqual(len(flow_bullets), 2)

    def test_master_similarity_uses_alpha_tokens_at_least_four_chars(self):
        current = "Build reliable FastAPI context memory observability"
        previous = "Build reliable FastAPI prompt memory tracing operations"

        similarity = context_router._master_similarity(current, previous)

        self.assertAlmostEqual(similarity, 4 / 7)

    def test_extract_context_warns_when_incremental_master_drifts(self):
        raw_llm_response = """PrimaryDomain: software_data_engineering
SecondaryDomains: context_engine
PrimaryIntent: construction
SecondaryIntent: improving_context_quality
Essence:
MASTER:
Designing restaurant menu pricing and hospitality operations analytics.

FLOW:
- validating a pricing model"""
        previous = """MASTER:
Building reliable FastAPI context memory with durable observability.

FLOW:
- hardening incremental context updates"""

        async def run_test():
            with self.assertLogs(context_router.logger.name, level="WARNING") as logs:
                with patch.object(
                    context_router.groq_pool,
                    "async_chat",
                    new=AsyncMock(return_value=raw_llm_response),
                ):
                    await context_router._extract_context(
                        [context_router.ChatMessage(role="user", content="Continue")],
                        previous_essence=previous,
                    )
            return logs.output

        output = asyncio.run(run_test())

        self.assertTrue(any("MASTER drift detected for incremental update" in line for line in output))

    def test_supermemory_shadow_write_includes_secondary_intent_metadata(self):
        request = context_router.ProcessContextRequest(
            user_id="user-1",
            session_id="session-1",
            messages=[context_router.ChatMessage(role="user", content="Ship the context engine")],
            platform="chatgpt",
        )
        previous = context_router.ProcessedContextData(
            session_id="user-1_software_data_engineering",
            user_id="user-1",
            essence="MASTER:\nBuild context memory.\n\nFLOW:\n- previous work",
            intent="construction",
            secondary_intent="previous_focus",
            domains=["software_data_engineering"],
            version=1,
            update_type="full",
        )
        first_extraction = {
            "essence": "MASTER:\nBuild context memory.",
            "intent": "construction",
            "secondary_intent": "routing_context",
            "domains": ["software_data_engineering"],
            "primary_domain": "software_data_engineering",
        }
        final_extraction = {
            "essence": "MASTER:\nBuild context memory.\n\nFLOW:\n- improving metadata",
            "intent": "construction",
            "secondary_intent": "improving_metadata_quality",
            "domains": ["software_data_engineering"],
            "primary_domain": "software_data_engineering",
        }
        captured = {}

        async def fake_add_memory(**kwargs):
            captured.update(kwargs)
            return "doc-1"

        async def run_test():
            scheduled = []

            def immediate_task(coro):
                task = asyncio.get_running_loop().create_task(coro)
                scheduled.append(task)
                return task

            with patch.object(
                context_router,
                "_extract_context",
                new=AsyncMock(side_effect=[first_extraction, final_extraction]),
            ), patch.object(
                context_router,
                "_fetch_previous_context",
                new=AsyncMock(return_value=previous),
            ), patch.object(
                context_router,
                "_save_to_node",
                new=AsyncMock(return_value=None),
            ), patch.object(
                context_router,
                "generate_embedding",
                new=AsyncMock(return_value=[0.1, 0.2]),
            ), patch.object(
                context_router,
                "get_settings",
                return_value=type("Settings", (), {"SUPERMEMORY_API_KEY": "test-key", "EMBEDDING_MODEL": ""})(),
            ), patch(
                "shared.supermemory_client.add_memory",
                new=fake_add_memory,
            ), patch.object(
                context_router.asyncio,
                "create_task",
                side_effect=immediate_task,
            ):
                await context_router._run_processing_pipeline(request)
                if scheduled:
                    await asyncio.gather(*scheduled)

        asyncio.run(run_test())

        self.assertEqual(
            captured["metadata"]["secondary_intent"],
            "improving_metadata_quality",
        )

    def test_supermemory_shadow_write_skips_near_duplicate_essence(self):
        request = context_router.ProcessContextRequest(
            user_id="user-1",
            session_id="session-1",
            messages=[context_router.ChatMessage(role="user", content="Ship the context engine")],
            platform="chatgpt",
        )
        extraction = {
            "essence": "Build reliable FastAPI context memory with durable observability",
            "intent": "construction",
            "secondary_intent": "routing_context",
            "domains": ["software_data_engineering"],
            "primary_domain": "software_data_engineering",
        }
        add_calls = []

        async def fake_search_memories(*_args, **_kwargs):
            return ["Build reliable FastAPI context memory with durable observability"]

        async def fake_add_memory(**kwargs):
            add_calls.append(kwargs)
            return "doc-1"

        async def run_test():
            with patch.object(
                context_router,
                "_extract_context",
                new=AsyncMock(return_value=extraction),
            ), patch.object(
                context_router,
                "_fetch_previous_context",
                new=AsyncMock(return_value=None),
            ), patch.object(
                context_router,
                "_save_to_node",
                new=AsyncMock(return_value=None),
            ), patch.object(
                context_router,
                "generate_embedding",
                new=AsyncMock(return_value=[0.1, 0.2]),
            ), patch.object(
                context_router,
                "get_settings",
                return_value=type("Settings", (), {"SUPERMEMORY_API_KEY": "test-key", "EMBEDDING_MODEL": ""})(),
            ), patch(
                "shared.supermemory_client.search_memories",
                new=fake_search_memories,
            ), patch(
                "shared.supermemory_client.add_memory",
                new=fake_add_memory,
            ):
                await context_router._run_processing_pipeline(request)

        with self.assertLogs(context_router.logger.name, level="INFO") as logs:
            asyncio.run(run_test())

        self.assertEqual(add_calls, [])
        self.assertTrue(
            any("supermemory: skipping near-duplicate write" in line for line in logs.output)
        )

    def test_supermemory_shadow_write_proceeds_when_duplicate_search_fails(self):
        request = context_router.ProcessContextRequest(
            user_id="user-1",
            session_id="session-1",
            messages=[context_router.ChatMessage(role="user", content="Ship the context engine")],
            platform="chatgpt",
        )
        extraction = {
            "essence": "Build reliable FastAPI context memory with durable observability",
            "intent": "construction",
            "secondary_intent": "routing_context",
            "domains": ["software_data_engineering"],
            "primary_domain": "software_data_engineering",
        }
        captured = {}

        async def fake_search_memories(*_args, **_kwargs):
            raise RuntimeError("supermemory unavailable")

        async def fake_add_memory(**kwargs):
            captured.update(kwargs)
            return "doc-1"

        async def run_test():
            scheduled = []

            def immediate_task(coro):
                task = asyncio.get_running_loop().create_task(coro)
                scheduled.append(task)
                return task

            with patch.object(
                context_router,
                "_extract_context",
                new=AsyncMock(return_value=extraction),
            ), patch.object(
                context_router,
                "_fetch_previous_context",
                new=AsyncMock(return_value=None),
            ), patch.object(
                context_router,
                "_save_to_node",
                new=AsyncMock(return_value=None),
            ), patch.object(
                context_router,
                "generate_embedding",
                new=AsyncMock(return_value=[0.1, 0.2]),
            ), patch.object(
                context_router,
                "get_settings",
                return_value=type("Settings", (), {"SUPERMEMORY_API_KEY": "test-key", "EMBEDDING_MODEL": ""})(),
            ), patch(
                "shared.supermemory_client.search_memories",
                new=fake_search_memories,
            ), patch(
                "shared.supermemory_client.add_memory",
                new=fake_add_memory,
            ), patch.object(
                context_router.asyncio,
                "create_task",
                side_effect=immediate_task,
            ):
                await context_router._run_processing_pipeline(request)
                if scheduled:
                    await asyncio.gather(*scheduled)

        asyncio.run(run_test())

        self.assertEqual(captured["content"], extraction["essence"])


if __name__ == "__main__":
    unittest.main()
