"""
Static analysis tests for distribution-engine schema migrations 006-010.
These tests parse the SQL files — no live database connection required.
Live-DB tests are marked with @unittest.skip and can be run manually.

Run:
    cd python-ai-unified && python -m pytest tests/test_schema_migrations.py -v
"""
from __future__ import annotations

import pathlib
import re
import unittest

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[1] / "migrations"

MIGRATION_FILES = {
    "006": "006_suppressions.sql",
    "007": "007_contacts.sql",
    "008": "008_campaigns.sql",
    "009": "009_agent_runs.sql",
    "010": "010_workflow_runs.sql",
}


def _read(filename: str) -> str:
    """Read a migration file and return its contents."""
    path = MIGRATIONS_DIR / filename
    return path.read_text(encoding="utf-8")


def _sql(filename: str) -> str:
    """Return upper-cased SQL for case-insensitive pattern matching."""
    return _read(filename).upper()


# ---------------------------------------------------------------------------
# 1. File existence
# ---------------------------------------------------------------------------

class TestFilesExist(unittest.TestCase):

    def test_006_suppressions_exists(self):
        self.assertTrue(
            (MIGRATIONS_DIR / MIGRATION_FILES["006"]).exists(),
            "006_suppressions.sql not found in migrations/",
        )

    def test_007_contacts_exists(self):
        self.assertTrue(
            (MIGRATIONS_DIR / MIGRATION_FILES["007"]).exists(),
            "007_contacts.sql not found in migrations/",
        )

    def test_008_campaigns_exists(self):
        self.assertTrue(
            (MIGRATIONS_DIR / MIGRATION_FILES["008"]).exists(),
            "008_campaigns.sql not found in migrations/",
        )

    def test_009_agent_runs_exists(self):
        self.assertTrue(
            (MIGRATIONS_DIR / MIGRATION_FILES["009"]).exists(),
            "009_agent_runs.sql not found in migrations/",
        )

    def test_010_workflow_runs_exists(self):
        self.assertTrue(
            (MIGRATIONS_DIR / MIGRATION_FILES["010"]).exists(),
            "010_workflow_runs.sql not found in migrations/",
        )


# ---------------------------------------------------------------------------
# 2. Idempotency — every file must use IF NOT EXISTS
# ---------------------------------------------------------------------------

class TestIdempotency(unittest.TestCase):

    def _assert_if_not_exists(self, key: str):
        sql = _sql(MIGRATION_FILES[key])
        self.assertIn(
            "IF NOT EXISTS",
            sql,
            f"{MIGRATION_FILES[key]} must use IF NOT EXISTS for idempotent application",
        )

    def test_006_idempotent(self): self._assert_if_not_exists("006")
    def test_007_idempotent(self): self._assert_if_not_exists("007")
    def test_008_idempotent(self): self._assert_if_not_exists("008")
    def test_009_idempotent(self): self._assert_if_not_exists("009")
    def test_010_idempotent(self): self._assert_if_not_exists("010")


# ---------------------------------------------------------------------------
# 3. Table names present in CREATE TABLE statements
# ---------------------------------------------------------------------------

class TestTableNames(unittest.TestCase):

    def _assert_table(self, key: str, table: str):
        sql = _sql(MIGRATION_FILES[key])
        pattern = rf"CREATE TABLE IF NOT EXISTS\s+{table}"
        self.assertRegex(
            sql, pattern,
            f"{MIGRATION_FILES[key]} must contain CREATE TABLE IF NOT EXISTS {table}",
        )

    def test_006_creates_suppressions(self):
        self._assert_table("006", "SUPPRESSIONS")

    def test_007_creates_contacts(self):
        self._assert_table("007", "CONTACTS")

    def test_008_creates_campaigns(self):
        self._assert_table("008", "CAMPAIGNS")

    def test_009_creates_agent_runs(self):
        self._assert_table("009", "AGENT_RUNS")

    def test_010_creates_workflow_runs(self):
        self._assert_table("010", "WORKFLOW_RUNS")


# ---------------------------------------------------------------------------
# 4. Primary keys use gen_random_uuid()
# ---------------------------------------------------------------------------

class TestPrimaryKeys(unittest.TestCase):

    def _assert_uuid_pk(self, key: str, col: str):
        sql = _sql(MIGRATION_FILES[key])
        self.assertIn("GEN_RANDOM_UUID()", sql,
                      f"{MIGRATION_FILES[key]} must use gen_random_uuid() for PK default")
        self.assertIn(col.upper(), sql,
                      f"{MIGRATION_FILES[key]} must define column {col}")
        self.assertIn("PRIMARY KEY", sql)

    def test_006_suppression_id_pk(self):
        self._assert_uuid_pk("006", "suppression_id")

    def test_007_contact_id_pk(self):
        self._assert_uuid_pk("007", "contact_id")

    def test_008_campaign_id_pk(self):
        self._assert_uuid_pk("008", "campaign_id")

    def test_009_run_id_pk(self):
        self._assert_uuid_pk("009", "run_id")

    def test_010_workflow_run_id_pk(self):
        self._assert_uuid_pk("010", "workflow_run_id")


# ---------------------------------------------------------------------------
# 5. CHECK constraints
# ---------------------------------------------------------------------------

class TestCheckConstraints(unittest.TestCase):

    def test_006_reason_check_values(self):
        sql = _sql(MIGRATION_FILES["006"])
        for val in ("UNSUBSCRIBE", "BOUNCE", "COMPLAINT", "MANUAL", "DUPLICATE"):
            self.assertIn(val, sql,
                          f"006_suppressions.sql CHECK on reason must include '{val}'")

    def test_007_icp_score_range_check(self):
        sql = _sql(MIGRATION_FILES["007"])
        self.assertIn("ICP_SCORE", sql)
        self.assertIn("BETWEEN", sql,
                      "007_contacts.sql must have BETWEEN check on icp_score")
        self.assertIn("0.0", sql)
        self.assertIn("1.0", sql)

    def test_008_type_check_values(self):
        sql = _sql(MIGRATION_FILES["008"])
        for val in ("OUTBOUND", "LIFECYCLE", "CONTENT", "PARTNERSHIP"):
            self.assertIn(val, sql,
                          f"008_campaigns.sql CHECK on type must include '{val}'")

    def test_008_status_check_values(self):
        sql = _sql(MIGRATION_FILES["008"])
        for val in ("DRAFT", "ACTIVE", "PAUSED", "COMPLETED", "KILLED"):
            self.assertIn(val, sql,
                          f"008_campaigns.sql CHECK on status must include '{val}'")

    def test_009_confidence_range_check(self):
        sql = _sql(MIGRATION_FILES["009"])
        self.assertIn("CONFIDENCE", sql)
        self.assertIn("BETWEEN", sql,
                      "009_agent_runs.sql must have BETWEEN check on confidence")

    def test_009_status_check_values(self):
        sql = _sql(MIGRATION_FILES["009"])
        for val in ("RUNNING", "COMPLETED", "FAILED", "KILLED"):
            self.assertIn(val, sql,
                          f"009_agent_runs.sql CHECK on status must include '{val}'")

    def test_010_status_check_values(self):
        sql = _sql(MIGRATION_FILES["010"])
        for val in ("PENDING", "RUNNING", "COMPLETED", "FAILED", "KILLED"):
            self.assertIn(val, sql,
                          f"010_workflow_runs.sql CHECK on status must include '{val}'")

    def test_010_trigger_check_values(self):
        sql = _sql(MIGRATION_FILES["010"])
        for val in ("SCHEDULE", "WEBHOOK", "MANUAL"):
            self.assertIn(val, sql,
                          f"010_workflow_runs.sql CHECK on trigger must include '{val}'")


# ---------------------------------------------------------------------------
# 6. Indexes
# ---------------------------------------------------------------------------

class TestIndexes(unittest.TestCase):

    def _assert_index(self, key: str, index_name: str):
        sql = _sql(MIGRATION_FILES[key])
        self.assertIn(
            index_name.upper(), sql,
            f"{MIGRATION_FILES[key]} missing index {index_name}",
        )

    # 006 suppressions
    def test_006_idx_email(self):
        self._assert_index("006", "IDX_SUPPRESSIONS_EMAIL")

    def test_006_idx_reason(self):
        self._assert_index("006", "IDX_SUPPRESSIONS_REASON")

    # 007 contacts
    def test_007_idx_email(self):
        self._assert_index("007", "IDX_CONTACTS_EMAIL")

    def test_007_idx_icp_category(self):
        self._assert_index("007", "IDX_CONTACTS_ICP_CATEGORY")

    def test_007_idx_is_suppressed(self):
        self._assert_index("007", "IDX_CONTACTS_IS_SUPPRESSED")

    # 008 campaigns
    def test_008_idx_status(self):
        self._assert_index("008", "IDX_CAMPAIGNS_STATUS")

    def test_008_idx_type(self):
        self._assert_index("008", "IDX_CAMPAIGNS_TYPE")

    # 009 agent_runs
    def test_009_idx_agent(self):
        self._assert_index("009", "IDX_AGENT_RUNS_AGENT")

    def test_009_idx_status(self):
        self._assert_index("009", "IDX_AGENT_RUNS_STATUS")

    def test_009_idx_campaign_id(self):
        self._assert_index("009", "IDX_AGENT_RUNS_CAMPAIGN_ID")

    def test_009_idx_started_at(self):
        self._assert_index("009", "IDX_AGENT_RUNS_STARTED_AT")

    # 010 workflow_runs
    def test_010_idx_workflow(self):
        self._assert_index("010", "IDX_WORKFLOW_RUNS_WORKFLOW")

    def test_010_idx_status(self):
        self._assert_index("010", "IDX_WORKFLOW_RUNS_STATUS")

    def test_010_idx_started_at(self):
        self._assert_index("010", "IDX_WORKFLOW_RUNS_STARTED_AT")


# ---------------------------------------------------------------------------
# 7. Foreign key: agent_runs.campaign_id → campaigns.campaign_id
# ---------------------------------------------------------------------------

class TestForeignKeys(unittest.TestCase):

    def test_009_agent_runs_fk_references_campaigns(self):
        sql = _sql(MIGRATION_FILES["009"])
        self.assertIn("REFERENCES CAMPAIGNS", sql,
                      "009_agent_runs.sql must reference campaigns table via FK")
        self.assertIn("CAMPAIGN_ID", sql,
                      "009_agent_runs.sql must have campaign_id FK column")
        self.assertIn("ON DELETE SET NULL", sql,
                      "009_agent_runs.sql FK must use ON DELETE SET NULL")


# ---------------------------------------------------------------------------
# 8. UNIQUE constraints
# ---------------------------------------------------------------------------

class TestUniqueConstraints(unittest.TestCase):

    def test_006_email_unique(self):
        sql = _sql(MIGRATION_FILES["006"])
        self.assertIn("SUPPRESSIONS_EMAIL_UNIQUE", sql,
                      "006_suppressions.sql must define UNIQUE constraint on email")

    def test_007_email_unique(self):
        sql = _sql(MIGRATION_FILES["007"])
        self.assertIn("CONTACTS_EMAIL_UNIQUE", sql,
                      "007_contacts.sql must define UNIQUE constraint on email")

    def test_010_idempotency_key_unique(self):
        sql = _sql(MIGRATION_FILES["010"])
        self.assertIn("WORKFLOW_RUNS_IDEMPOTENCY_UNIQUE", sql,
                      "010_workflow_runs.sql must define UNIQUE constraint on idempotency_key")


# ---------------------------------------------------------------------------
# 9. Required columns present
# ---------------------------------------------------------------------------

class TestRequiredColumns(unittest.TestCase):

    def test_006_required_columns(self):
        sql = _sql(MIGRATION_FILES["006"])
        for col in ("EMAIL", "REASON", "SOURCE", "SUPPRESSED_AT", "EXPIRES_AT"):
            self.assertIn(col, sql, f"006_suppressions.sql missing column: {col}")

    def test_007_required_columns(self):
        sql = _sql(MIGRATION_FILES["007"])
        for col in ("EMAIL", "FULL_NAME", "COMPANY", "TITLE", "SOURCE",
                    "ICP_SCORE", "ICP_CATEGORY", "IS_SUPPRESSED",
                    "ENRICHED_AT", "CREATED_AT", "METADATA"):
            self.assertIn(col, sql, f"007_contacts.sql missing column: {col}")

    def test_008_required_columns(self):
        sql = _sql(MIGRATION_FILES["008"])
        for col in ("NAME", "TYPE", "ICP_TARGET", "STATUS", "OWNER",
                    "DAILY_LIMIT", "KILL_RULE", "STARTED_AT", "ENDED_AT",
                    "CREATED_AT", "METADATA"):
            self.assertIn(col, sql, f"008_campaigns.sql missing column: {col}")

    def test_009_required_columns(self):
        sql = _sql(MIGRATION_FILES["009"])
        for col in ("AGENT", "VERSION", "CAMPAIGN_ID", "INPUT_SUMMARY",
                    "OUTPUT_SUMMARY", "CONFIDENCE", "DECISION", "WARNINGS",
                    "STATUS", "COST_USD", "STARTED_AT", "COMPLETED_AT",
                    "ERROR_MESSAGE"):
            self.assertIn(col, sql, f"009_agent_runs.sql missing column: {col}")

    def test_010_required_columns(self):
        sql = _sql(MIGRATION_FILES["010"])
        for col in ("WORKFLOW", "IDEMPOTENCY_KEY", "STATUS", "TRIGGER",
                    "RECORDS_PROCESSED", "RECORDS_FAILED", "STARTED_AT",
                    "COMPLETED_AT", "ERROR_MESSAGE", "METADATA"):
            self.assertIn(col, sql, f"010_workflow_runs.sql missing column: {col}")


# ---------------------------------------------------------------------------
# 10. JSONB columns use correct type
# ---------------------------------------------------------------------------

class TestJsonbColumns(unittest.TestCase):

    def test_007_metadata_is_jsonb(self):
        sql = _sql(MIGRATION_FILES["007"])
        self.assertIn("METADATA JSONB", sql,
                      "007_contacts.sql: metadata must be JSONB type")

    def test_008_metadata_is_jsonb(self):
        sql = _sql(MIGRATION_FILES["008"])
        self.assertIn("METADATA JSONB", sql,
                      "008_campaigns.sql: metadata must be JSONB type")

    def test_009_input_summary_is_jsonb(self):
        sql = _sql(MIGRATION_FILES["009"])
        self.assertIn("INPUT_SUMMARY JSONB", sql,
                      "009_agent_runs.sql: input_summary must be JSONB type")

    def test_009_output_summary_is_jsonb(self):
        sql = _sql(MIGRATION_FILES["009"])
        self.assertIn("OUTPUT_SUMMARY JSONB", sql,
                      "009_agent_runs.sql: output_summary must be JSONB type")

    def test_009_warnings_is_jsonb(self):
        sql = _sql(MIGRATION_FILES["009"])
        self.assertIn("WARNINGS JSONB", sql,
                      "009_agent_runs.sql: warnings must be JSONB type")

    def test_010_metadata_is_jsonb(self):
        sql = _sql(MIGRATION_FILES["010"])
        self.assertIn("METADATA JSONB", sql,
                      "010_workflow_runs.sql: metadata must be JSONB type")


# ---------------------------------------------------------------------------
# 11. DEFAULT values present for JSONB and boolean columns
# ---------------------------------------------------------------------------

class TestDefaults(unittest.TestCase):

    def test_007_is_suppressed_default_false(self):
        sql = _sql(MIGRATION_FILES["007"])
        self.assertIn("IS_SUPPRESSED BOOLEAN DEFAULT FALSE", sql,
                      "007_contacts.sql: is_suppressed must default to FALSE")

    def test_008_status_default_draft(self):
        sql = _sql(MIGRATION_FILES["008"])
        self.assertIn("'DRAFT'", sql,
                      "008_campaigns.sql: status must default to 'draft'")

    def test_009_status_default_running(self):
        sql = _sql(MIGRATION_FILES["009"])
        self.assertIn("'RUNNING'", sql,
                      "009_agent_runs.sql: status must default to 'running'")

    def test_009_version_default(self):
        sql = _sql(MIGRATION_FILES["009"])
        self.assertIn("DEFAULT '1.0.0'", sql,
                      "009_agent_runs.sql: version must default to '1.0.0'")

    def test_010_status_default_pending(self):
        sql = _sql(MIGRATION_FILES["010"])
        self.assertIn("'PENDING'", sql,
                      "010_workflow_runs.sql: status must default to 'pending'")

    def test_010_records_processed_default_zero(self):
        sql = _sql(MIGRATION_FILES["010"])
        self.assertIn("RECORDS_PROCESSED INT DEFAULT 0", sql,
                      "010_workflow_runs.sql: records_processed must default to 0")

    def test_010_records_failed_default_zero(self):
        sql = _sql(MIGRATION_FILES["010"])
        self.assertIn("RECORDS_FAILED INT DEFAULT 0", sql,
                      "010_workflow_runs.sql: records_failed must default to 0")


# ---------------------------------------------------------------------------
# 12. Existing migrations are not modified (smoke check file count)
# ---------------------------------------------------------------------------

class TestExistingMigrationsUntouched(unittest.TestCase):

    def test_003_still_exists(self):
        self.assertTrue(
            (MIGRATIONS_DIR / "003_prompt_traces_table.sql").exists(),
            "003_prompt_traces_table.sql must not be deleted",
        )

    def test_004_still_exists(self):
        self.assertTrue(
            (MIGRATIONS_DIR / "004_attachments_table.sql").exists(),
            "004_attachments_table.sql must not be deleted",
        )

    def test_005_still_exists(self):
        self.assertTrue(
            (MIGRATIONS_DIR / "005_trace_outcome.sql").exists(),
            "005_trace_outcome.sql must not be deleted",
        )


# ---------------------------------------------------------------------------
# 13. Live DB tests (skipped for offline CI)
# ---------------------------------------------------------------------------

@unittest.skip("Requires live PostgreSQL connection — run manually on server")
class TestLiveDatabase(unittest.TestCase):
    """
    Manual verification after deployment.
    Run on server:
        docker exec postgres17 psql -U postgres -d thinkvelocity_prod -c "\\dt suppressions contacts campaigns agent_runs workflow_runs"
    """

    def test_suppressions_table_exists(self):
        import asyncpg, asyncio, os
        async def check():
            conn = await asyncpg.connect(os.environ["DATABASE_URL"])
            result = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'suppressions'"
            )
            await conn.close()
            return result
        count = asyncio.run(check())
        self.assertEqual(count, 1)

    def test_contacts_table_exists(self):
        import asyncpg, asyncio, os
        async def check():
            conn = await asyncpg.connect(os.environ["DATABASE_URL"])
            result = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'contacts'"
            )
            await conn.close()
            return result
        count = asyncio.run(check())
        self.assertEqual(count, 1)

    def test_campaigns_table_exists(self):
        import asyncpg, asyncio, os
        async def check():
            conn = await asyncpg.connect(os.environ["DATABASE_URL"])
            result = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'campaigns'"
            )
            await conn.close()
            return result
        count = asyncio.run(check())
        self.assertEqual(count, 1)

    def test_agent_runs_table_exists(self):
        import asyncpg, asyncio, os
        async def check():
            conn = await asyncpg.connect(os.environ["DATABASE_URL"])
            result = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'agent_runs'"
            )
            await conn.close()
            return result
        count = asyncio.run(check())
        self.assertEqual(count, 1)

    def test_workflow_runs_table_exists(self):
        import asyncpg, asyncio, os
        async def check():
            conn = await asyncpg.connect(os.environ["DATABASE_URL"])
            result = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'workflow_runs'"
            )
            await conn.close()
            return result
        count = asyncio.run(check())
        self.assertEqual(count, 1)

    def test_agent_runs_fk_to_campaigns(self):
        import asyncpg, asyncio, os
        async def check():
            conn = await asyncpg.connect(os.environ["DATABASE_URL"])
            result = await conn.fetchval("""
                SELECT COUNT(*) FROM information_schema.referential_constraints rc
                JOIN information_schema.key_column_usage kcu
                    ON rc.constraint_name = kcu.constraint_name
                WHERE kcu.table_name = 'agent_runs'
                AND kcu.column_name = 'campaign_id'
            """)
            await conn.close()
            return result
        count = asyncio.run(check())
        self.assertGreater(count, 0, "FK from agent_runs.campaign_id to campaigns not found")

    def test_idempotent_rerun_006(self):
        """Running 006 twice must not error."""
        import subprocess
        sql_path = MIGRATIONS_DIR / MIGRATION_FILES["006"]
        result = subprocess.run(
            ["docker", "exec", "-i", "postgres17", "psql", "-U", "postgres",
             "-d", "thinkvelocity_prod"],
            input=sql_path.read_text(encoding="utf-8"),
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
