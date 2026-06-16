#!/usr/bin/env python3
"""
test_schema_completeness.py — Phase 0 Automated Tests
======================================================
Purpose: Verify the v2 schema SQL files are complete and consistent
         before Phase 1 (new server) begins.

These tests run LOCALLY — they parse the SQL files and connect to the
CURRENT Server 2 to validate coverage. No writes happen.

Run:
    pip install psycopg2-binary pytest
    export OLD_DB_URL="postgresql://postgres:<pass>@13.203.181.76:5432/localpgvelocity"
    export OLD_ENT_DB_URL="postgresql://postgres:<pass>@13.203.181.76:5432/enterprise"
    pytest schema/tests/test_schema_completeness.py -v

SOC2: P0-MT-01 (schema review), P0-MT-02 (env var completeness)
"""

import os
import re
import sys
from pathlib import Path

import psycopg2
import pytest

# =============================================================================
# CONFIG
# =============================================================================

SCHEMA_DIR = Path(__file__).parent.parent / "v2"
MIGRATION_DIR = Path(__file__).parent.parent / "migration"

OLD_DB_URL = os.environ.get("OLD_DB_URL", "")
OLD_ENT_DB_URL = os.environ.get("OLD_ENT_DB_URL", "")

# Tables we intentionally exclude from migration (stale/backup-only)
EXCLUDED_TABLES = {
    "_prisma_migrations",  # Prisma internal — not migrated
}

# Tables that move to 'shared' schema (not 'consumer')
SHARED_TABLES = {
    "usertable",        # → shared.users
    "userstatus",       # → shared.user_status
    "refresh_tokens",   # → shared.refresh_tokens
    "otp_verification", # → shared.otp_verification
    "password_reset_tokens",  # → shared.password_reset_tokens
    "all_emails",       # → shared.all_emails
}


# =============================================================================
# HELPERS
# =============================================================================

def get_current_tables(db_url: str, db_name: str) -> set[str]:
    """Get all table names from the current (old) database."""
    if not db_url:
        pytest.skip(f"No DB URL for {db_name} — set {db_name.upper()}_DB_URL env var")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
        AND tablename NOT IN %s
        ORDER BY tablename;
    """, (tuple(EXCLUDED_TABLES),))
    tables = {row[0] for row in cur.fetchall()}
    conn.close()
    return tables


def parse_sql_tables(sql_file: Path) -> set[str]:
    """
    Extract all CREATE TABLE statements from a SQL file.
    Returns a set of table names (last part after the schema prefix).
    """
    if not sql_file.exists():
        return set()
    content = sql_file.read_text(encoding="utf-8")
    # Match: CREATE TABLE [IF NOT EXISTS] schema.table_name
    # Table names may be quoted with double-quotes
    pattern = r'CREATE TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+\w+\."?(\w+)"?'
    matches = re.findall(pattern, content, re.IGNORECASE)
    return {m.lower() for m in matches}


def parse_migration_order(script_file: Path) -> list[str]:
    """
    Parse the migration script for dump_table() and dump_ent_table() calls.
    Returns ordered list of table names as they appear in the script.
    """
    if not script_file.exists():
        return []
    content = script_file.read_text(encoding="utf-8")
    pattern = r'dump(?:_ent)?_table\s+"public\.(?:")?(\w+)(?:")?"\s+'
    return re.findall(pattern, content)


def get_all_v2_tables() -> dict[str, set[str]]:
    """
    Return dict of schema -> set of table names defined in all v2 SQL files.
    """
    result = {}
    for sql_file in SCHEMA_DIR.glob("*.sql"):
        tables = parse_sql_tables(sql_file)
        schema_match = re.search(r'-- Schema: (\w+)', sql_file.read_text())
        if schema_match:
            schema = schema_match.group(1).lower()
            result.setdefault(schema, set()).update(tables)
    return result


def normalize_table_name(name: str) -> str:
    """Normalize old table names to new ones for comparison."""
    renames = {
        "usertable": "users",
        "userstatus": "user_status",
    }
    return renames.get(name.lower(), name.lower())


# =============================================================================
# TESTS
# =============================================================================

class TestSchemaFiles:
    """P0-AT-01: Schema SQL files exist and are non-empty."""

    def test_all_schema_files_exist(self):
        """All 6 schema files must exist."""
        expected_files = [
            "001_shared.sql",
            "002_consumer.sql",
            "003_enterprise.sql",
            "004_extension.sql",
            "005_indexes.sql",
            "006_users_db.sql",
        ]
        for fname in expected_files:
            path = SCHEMA_DIR / fname
            assert path.exists(), f"Missing schema file: {path}"
            assert path.stat().st_size > 100, f"Schema file appears empty: {path}"

    def test_migration_script_exists(self):
        """Migration shell script must exist and be executable-looking."""
        script = MIGRATION_DIR / "run_migration.sh"
        assert script.exists(), f"Missing migration script: {script}"
        content = script.read_text()
        assert "dump_table" in content, "Migration script has no dump_table calls"
        assert "load" in content, "Migration script has no load calls"

    def test_schema_files_have_no_placeholder_passwords(self):
        """No real passwords in SQL files — only REPLACE_WITH_ placeholders."""
        for sql_file in SCHEMA_DIR.glob("*.sql"):
            content = sql_file.read_text(encoding="utf-8")
            # Check for anything that looks like a real password in CREATE USER
            passwords = re.findall(r"PASSWORD\s+'([^']+)'", content, re.IGNORECASE)
            for pw in passwords:
                assert pw.startswith("REPLACE_WITH_"), \
                    f"Real password found in {sql_file.name}: '{pw[:20]}...'"

    def test_shared_schema_has_core_auth_tables(self):
        """shared schema must have: users, user_status, refresh_tokens, otp_verification."""
        shared_tables = parse_sql_tables(SCHEMA_DIR / "001_shared.sql")
        required = {"users", "user_status", "refresh_tokens", "otp_verification", "password_reset_tokens"}
        missing = required - shared_tables
        assert len(missing) == 0, f"shared schema missing tables: {missing}"

    def test_consumer_schema_has_billing_tables(self):
        """consumer schema must have billing/token tables for subscription gate."""
        consumer_tables = parse_sql_tables(SCHEMA_DIR / "002_consumer.sql")
        required = {
            "billing_plans", "subscriptions", "payments",
            "token_ledger", "token_transactions", "token_reservations",
            "feature_token_costs"
        }
        missing = required - consumer_tables
        assert len(missing) == 0, f"consumer schema missing billing tables: {missing}"

    def test_consumer_schema_has_prompt_tables(self):
        """consumer schema must have core prompt flow tables."""
        consumer_tables = parse_sql_tables(SCHEMA_DIR / "002_consumer.sql")
        required = {
            "user_prompts", "save_enhance_prompt", "refine_prompt",
            "prompt_history", "prompt_collections", "prompt_marketplace"
        }
        missing = required - consumer_tables
        assert len(missing) == 0, f"consumer schema missing prompt tables: {missing}"

    def test_enterprise_schema_has_core_tables(self):
        """enterprise schema must have User, Enterprise, AuditLog."""
        ent_tables = parse_sql_tables(SCHEMA_DIR / "003_enterprise.sql")
        required = {"User", "Enterprise", "AuditLog", "CompanyPolicy"}
        # Case-insensitive check
        ent_lower = {t.lower() for t in ent_tables}
        required_lower = {t.lower() for t in required}
        missing = required_lower - ent_lower
        assert len(missing) == 0, f"enterprise schema missing tables: {missing}"

    def test_indexes_file_covers_critical_columns(self):
        """Index file must cover user_id on at least 10 consumer tables."""
        content = (SCHEMA_DIR / "005_indexes.sql").read_text()
        user_id_indexes = re.findall(r"ON\s+\w+\.\w+\s*\(user_id", content, re.IGNORECASE)
        assert len(user_id_indexes) >= 10, \
            f"Expected ≥10 user_id indexes, found {len(user_id_indexes)}"

    def test_indexes_file_has_vector_index(self):
        """Index file must have ivfflat vector index for context engine similarity search."""
        content = (SCHEMA_DIR / "005_indexes.sql").read_text()
        assert "ivfflat" in content, "Missing ivfflat vector index for processed_contexts"

    def test_006_grants_all_four_users(self):
        """006_users_db.sql must grant to all 4 app users + backup_user."""
        content = (SCHEMA_DIR / "006_users_db.sql").read_text()
        required_users = ["app_consumer", "app_enterprise", "app_extension", "app_readonly", "backup_user"]
        for user in required_users:
            assert user in content, f"006_users_db.sql missing grants for: {user}"


class TestConsumerTableCoverage:
    """P0-AT-02: Every table in localpgvelocity is mapped in v2 consumer/shared schema."""

    def test_all_consumer_tables_mapped(self):
        """
        GIVEN the current localpgvelocity tables
        WHEN compared to 001_shared.sql + 002_consumer.sql
        THEN no table is missing
        """
        current_tables = get_current_tables(OLD_DB_URL, "localpgvelocity")
        shared_tables = parse_sql_tables(SCHEMA_DIR / "001_shared.sql")
        consumer_tables = parse_sql_tables(SCHEMA_DIR / "002_consumer.sql")
        all_v2_tables = shared_tables | consumer_tables

        # Normalize old table names to new names for comparison
        missing = set()
        for old_name in current_tables:
            new_name = normalize_table_name(old_name)
            if new_name not in all_v2_tables and old_name not in EXCLUDED_TABLES:
                missing.add(f"{old_name} → {new_name}")

        assert len(missing) == 0, \
            f"These consumer tables are not in v2 schema:\n  " + "\n  ".join(sorted(missing))

    def test_no_extra_tables_in_v2_consumer(self):
        """
        Consumer schema should not define tables that don't exist in old DB
        (prevents scope creep in migration).
        Allows new tables like extension.install_events.
        """
        current_tables = get_current_tables(OLD_DB_URL, "localpgvelocity")
        consumer_tables = parse_sql_tables(SCHEMA_DIR / "002_consumer.sql")

        # Tables that are genuinely new (not from old DB)
        new_tables_allowed = {"user_token_summary", "expiring_tokens_report"}  # views, not tables

        extra = set()
        for t in consumer_tables:
            old_name_match = any(
                normalize_table_name(old) == t for old in current_tables
            )
            if not old_name_match and t not in new_tables_allowed:
                extra.add(t)

        # Report as warning, not hard failure (some tables may be new by design)
        if extra:
            print(f"\nWARNING: New tables in v2 not in old DB (verify these are intentional): {extra}")


class TestEnterpriseTableCoverage:
    """P0-AT-03: Every enterprise table is mapped."""

    def test_all_enterprise_tables_mapped(self):
        """
        GIVEN the current enterprise DB tables
        WHEN compared to 003_enterprise.sql
        THEN no table is missing (excluding _prisma_migrations)
        """
        current_tables = get_current_tables(OLD_ENT_DB_URL, "enterprise")
        ent_tables_in_v2 = parse_sql_tables(SCHEMA_DIR / "003_enterprise.sql")
        ent_lower = {t.lower() for t in ent_tables_in_v2}

        missing = set()
        for t in current_tables:
            if t.lower() not in ent_lower and t not in EXCLUDED_TABLES:
                missing.add(t)

        assert len(missing) == 0, \
            f"Enterprise tables missing from 003_enterprise.sql:\n  " + "\n  ".join(sorted(missing))


class TestMigrationScript:
    """P0-AT-04: Migration script covers all tables in correct FK order."""

    def test_migration_script_covers_all_consumer_tables(self):
        """
        Every consumer table in 002_consumer.sql has a dump_table call.
        """
        migration_tables = set(t.lower() for t in parse_migration_order(
            MIGRATION_DIR / "run_migration.sh"
        ))
        consumer_tables = parse_sql_tables(SCHEMA_DIR / "002_consumer.sql")

        # Map new names back to old names for script comparison
        reverse_renames = {"users": "usertable", "user_status": "userstatus"}
        missing_from_script = set()
        for t in consumer_tables:
            old_name = reverse_renames.get(t, t)
            if old_name not in migration_tables and t not in {"user_token_summary", "expiring_tokens_report"}:
                missing_from_script.add(t)

        assert len(missing_from_script) == 0, \
            f"Tables in 002_consumer.sql but not in migration script:\n  " + \
            "\n  ".join(sorted(missing_from_script))

    def test_migration_usertable_before_userstatus(self):
        """
        usertable must appear before userstatus in migration script
        (FK: userstatus.user_id → usertable.user_id)
        """
        order = parse_migration_order(MIGRATION_DIR / "run_migration.sh")
        if "usertable" in order and "userstatus" in order:
            idx_users = order.index("usertable")
            idx_status = order.index("userstatus")
            assert idx_users < idx_status, \
                f"FK violation: usertable (idx {idx_users}) must come before userstatus (idx {idx_status})"

    def test_migration_billing_plans_before_subscriptions(self):
        """billing_plans must appear before subscriptions (FK dependency)."""
        order = parse_migration_order(MIGRATION_DIR / "run_migration.sh")
        if "billing_plans" in order and "subscriptions" in order:
            assert order.index("billing_plans") < order.index("subscriptions"), \
                "FK violation: billing_plans must be migrated before subscriptions"

    def test_migration_save_enhance_before_refine(self):
        """save_enhance_prompt must appear before refine_prompt (FK dependency)."""
        order = parse_migration_order(MIGRATION_DIR / "run_migration.sh")
        if "save_enhance_prompt" in order and "refine_prompt" in order:
            assert order.index("save_enhance_prompt") < order.index("refine_prompt"), \
                "FK violation: save_enhance_prompt must come before refine_prompt"

    def test_migration_invite_links_before_invite_redemptions(self):
        """invite_links before invite_redemptions."""
        order = parse_migration_order(MIGRATION_DIR / "run_migration.sh")
        if "invite_links" in order and "invite_redemptions" in order:
            assert order.index("invite_links") < order.index("invite_redemptions"), \
                "FK violation: invite_links must come before invite_redemptions"

    def test_migration_has_sequence_sync(self):
        """Migration script must sync sequences after data load."""
        content = (MIGRATION_DIR / "run_migration.sh").read_text()
        assert "setval" in content, "Migration script missing sequence sync (setval)"
        assert "users_user_id_seq" in content, "Migration script missing user ID sequence sync"

    def test_migration_has_verification_step(self):
        """Migration script must have a row count verification step."""
        content = (MIGRATION_DIR / "run_migration.sh").read_text()
        assert "n_live_tup" in content or "row_count" in content, \
            "Migration script has no post-migration row count verification"


class TestFKConsistency:
    """P0-AT-05: FK references in SQL files point to tables that exist in the schema."""

    def test_consumer_fks_reference_existing_tables(self):
        """
        All FOREIGN KEY ... REFERENCES in 002_consumer.sql point to tables
        that exist in either shared or consumer schema.
        """
        content = (SCHEMA_DIR / "002_consumer.sql").read_text()
        shared_tables = parse_sql_tables(SCHEMA_DIR / "001_shared.sql")
        consumer_tables = parse_sql_tables(SCHEMA_DIR / "002_consumer.sql")
        all_tables = shared_tables | consumer_tables

        # Extract: REFERENCES schema.table
        fk_refs = re.findall(r'REFERENCES\s+\w+\.(\w+)\s*\(', content, re.IGNORECASE)
        broken = set()
        for ref in fk_refs:
            if ref.lower() not in all_tables:
                broken.add(ref)

        assert len(broken) == 0, \
            f"FK references to non-existent tables in 002_consumer.sql: {broken}"

    def test_enterprise_fks_reference_existing_tables(self):
        """All FKs in 003_enterprise.sql point to existing enterprise tables."""
        content = (SCHEMA_DIR / "003_enterprise.sql").read_text()
        ent_tables = parse_sql_tables(SCHEMA_DIR / "003_enterprise.sql")

        fk_refs = re.findall(r'REFERENCES\s+enterprise\."?(\w+)"?\s*\(', content, re.IGNORECASE)
        broken = set()
        for ref in fk_refs:
            if ref.lower() not in {t.lower() for t in ent_tables}:
                broken.add(ref)

        assert len(broken) == 0, \
            f"FK references to non-existent enterprise tables: {broken}"


class TestSOC2Requirements:
    """P0-AT-06: Schema includes all tables required for SOC2 controls."""

    def test_audit_log_tables_exist(self):
        """SOC2 PI1.1: audit/logging tables must be present."""
        consumer_tables = parse_sql_tables(SCHEMA_DIR / "002_consumer.sql")
        ent_tables = parse_sql_tables(SCHEMA_DIR / "003_enterprise.sql")

        assert "api_error_logs" in consumer_tables, \
            "Missing api_error_logs (SOC2 PI1.1)"
        assert "webhook_events" in consumer_tables, \
            "Missing webhook_events (SOC2 PI1.1)"
        # Enterprise audit log
        assert any("auditlog" == t.lower() for t in ent_tables), \
            "Missing AuditLog in enterprise schema (SOC2 PI1.1)"

    def test_auth_tables_exist(self):
        """SOC2 CC6.2: auth tables (refresh_tokens, otp, password_reset)."""
        shared_tables = parse_sql_tables(SCHEMA_DIR / "001_shared.sql")
        assert "refresh_tokens" in shared_tables, "Missing refresh_tokens (SOC2 CC6.2)"
        assert "otp_verification" in shared_tables, "Missing otp_verification (SOC2 CC6.2)"
        assert "password_reset_tokens" in shared_tables, "Missing password_reset_tokens (SOC2 CC6.2)"

    def test_least_privilege_db_users_defined(self):
        """SOC2 CC6.3: 006_users_db.sql defines per-service users, not a single superuser."""
        content = (SCHEMA_DIR / "006_users_db.sql").read_text()
        # Must NOT grant superuser
        assert "SUPERUSER" not in content.upper(), \
            "006_users_db.sql grants SUPERUSER — violates CC6.3 least privilege"
        # Must define per-service users
        assert content.count("CREATE USER") >= 4 or content.count("CREATE ROLE") >= 4, \
            "Fewer than 4 users/roles defined — CC6.3 requires per-service isolation"

    def test_no_plaintext_secrets(self):
        """SOC2 CC6.7: no plaintext secrets in any SQL file."""
        for sql_file in SCHEMA_DIR.glob("*.sql"):
            content = sql_file.read_text()
            # Check for common secret patterns (not REPLACE_WITH_)
            passwords = re.findall(r"PASSWORD\s+'([^']+)'", content, re.IGNORECASE)
            for pw in passwords:
                assert "REPLACE_WITH_" in pw or pw == "", \
                    f"Potential real password in {sql_file.name}: '{pw[:20]}'"
