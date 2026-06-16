-- =============================================================================
-- 006_users_db.sql — PostgreSQL User Accounts & GRANT Statements
-- Purpose: Create per-service DB users with least-privilege access.
--          Each service gets ONLY what it needs. No shared superuser password.
-- Run order: SIXTH (after all schemas and tables exist)
-- SOC2: CC6.3 (Authorization — Least Privilege)
-- IMPORTANT: Replace REPLACE_WITH_* placeholders with values from AWS Secrets Manager
-- =============================================================================

-- =============================================================================
-- CREATE ROLES (non-login base roles for permission grouping)
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_consumer_rw') THEN
        CREATE ROLE role_consumer_rw;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_enterprise_rw') THEN
        CREATE ROLE role_enterprise_rw;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_extension_rw') THEN
        CREATE ROLE role_extension_rw;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'role_readonly') THEN
        CREATE ROLE role_readonly;
    END IF;
END
$$;

-- =============================================================================
-- CREATE LOGIN USERS
-- IMPORTANT: Passwords are placeholders — set via:
--   ALTER USER app_consumer PASSWORD 'actual-secret-from-sm';
-- =============================================================================

DO $$
BEGIN
    -- Node.js consumer backend + Python AI + context engine
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_consumer') THEN
        CREATE USER app_consumer WITH PASSWORD 'REPLACE_WITH_SM_KEY_consumer';
    END IF;

    -- NestJS enterprise backend
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_enterprise') THEN
        CREATE USER app_enterprise WITH PASSWORD 'REPLACE_WITH_SM_KEY_enterprise';
    END IF;

    -- Extension API (FastAPI Server 1 equivalent)
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_extension') THEN
        CREATE USER app_extension WITH PASSWORD 'REPLACE_WITH_SM_KEY_extension';
    END IF;

    -- Read-only: analytics, SOC2 evidence, monitoring
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_readonly') THEN
        CREATE USER app_readonly WITH PASSWORD 'REPLACE_WITH_SM_KEY_readonly';
    END IF;

    -- Backup user: pg_dump only, no writes
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'backup_user') THEN
        CREATE USER backup_user WITH PASSWORD 'REPLACE_WITH_SM_KEY_backup';
    END IF;
END
$$;

-- =============================================================================
-- SCHEMA USAGE GRANTS
-- =============================================================================

-- app_consumer: needs shared (read/write auth) + consumer (read/write) + extension (read for context)
GRANT USAGE ON SCHEMA shared    TO app_consumer;
GRANT USAGE ON SCHEMA consumer  TO app_consumer;
GRANT USAGE ON SCHEMA extension TO app_consumer;

-- app_enterprise: needs shared (read users for auth validation) + enterprise (read/write)
GRANT USAGE ON SCHEMA shared     TO app_enterprise;
GRANT USAGE ON SCHEMA enterprise TO app_enterprise;

-- app_extension: needs shared (auth) + consumer (prompt storage) + extension (own tables)
GRANT USAGE ON SCHEMA shared    TO app_extension;
GRANT USAGE ON SCHEMA consumer  TO app_extension;
GRANT USAGE ON SCHEMA extension TO app_extension;

-- app_readonly: all schemas read-only
GRANT USAGE ON SCHEMA shared     TO app_readonly;
GRANT USAGE ON SCHEMA consumer   TO app_readonly;
GRANT USAGE ON SCHEMA enterprise TO app_readonly;
GRANT USAGE ON SCHEMA extension  TO app_readonly;

-- backup_user: all schemas (needs to read for pg_dump)
GRANT USAGE ON SCHEMA shared     TO backup_user;
GRANT USAGE ON SCHEMA consumer   TO backup_user;
GRANT USAGE ON SCHEMA enterprise TO backup_user;
GRANT USAGE ON SCHEMA extension  TO backup_user;

-- =============================================================================
-- TABLE-LEVEL GRANTS — shared schema
-- =============================================================================

-- app_consumer: full CRUD on shared (manages auth)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA shared TO app_consumer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA shared TO app_consumer;

-- app_enterprise: READ users (for auth validation), WRITE nothing in shared
GRANT SELECT ON shared.users TO app_enterprise;
GRANT SELECT ON shared.user_status TO app_enterprise;

-- app_extension: full CRUD on shared (manages auth for extension users)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA shared TO app_extension;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA shared TO app_extension;

-- app_readonly, backup_user: SELECT only on shared
GRANT SELECT ON ALL TABLES IN SCHEMA shared TO app_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA shared TO backup_user;

-- =============================================================================
-- TABLE-LEVEL GRANTS — consumer schema
-- =============================================================================

-- app_consumer: full CRUD
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA consumer TO app_consumer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA consumer TO app_consumer;

-- app_extension: READ + limited WRITE (prompts, contexts, memories — but NOT billing/payments)
-- Explicit whitelist — extension cannot touch billing tables
GRANT SELECT, INSERT, UPDATE ON consumer.user_prompts          TO app_extension;
GRANT SELECT, INSERT, UPDATE ON consumer.save_enhance_prompt   TO app_extension;
GRANT SELECT, INSERT, UPDATE ON consumer.refine_prompt         TO app_extension;
GRANT SELECT, INSERT, UPDATE ON consumer.conversation_contexts TO app_extension;
GRANT SELECT, INSERT, UPDATE ON consumer.processed_contexts    TO app_extension;
GRANT SELECT, INSERT, UPDATE ON consumer.velocity_memories     TO app_extension;
GRANT SELECT, INSERT, UPDATE ON consumer.user_profiles         TO app_extension;
GRANT SELECT                 ON consumer.user_prompts          TO app_extension;  -- already above, explicit
GRANT SELECT                 ON consumer.billing_plans         TO app_extension;  -- read-only pricing
GRANT USAGE, SELECT ON SEQUENCE consumer.referral_relations_id_seq TO app_extension;

-- app_readonly, backup_user: SELECT only
GRANT SELECT ON ALL TABLES IN SCHEMA consumer TO app_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA consumer TO backup_user;

-- =============================================================================
-- TABLE-LEVEL GRANTS — enterprise schema
-- =============================================================================

-- app_enterprise: full CRUD
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA enterprise TO app_enterprise;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA enterprise TO app_enterprise;

-- app_readonly, backup_user: SELECT only
GRANT SELECT ON ALL TABLES IN SCHEMA enterprise TO app_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA enterprise TO backup_user;

-- =============================================================================
-- TABLE-LEVEL GRANTS — extension schema
-- =============================================================================

-- app_extension: full CRUD on own schema
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA extension TO app_extension;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA extension TO app_extension;

-- app_consumer: READ extension (for admin/analytics)
GRANT SELECT ON ALL TABLES IN SCHEMA extension TO app_consumer;

-- app_readonly, backup_user: SELECT only
GRANT SELECT ON ALL TABLES IN SCHEMA extension TO app_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA extension TO backup_user;

-- =============================================================================
-- DEFAULT PRIVILEGES (apply to future tables created in each schema)
-- =============================================================================

ALTER DEFAULT PRIVILEGES IN SCHEMA shared
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_consumer;
ALTER DEFAULT PRIVILEGES IN SCHEMA shared
    GRANT SELECT ON TABLES TO app_enterprise;
ALTER DEFAULT PRIVILEGES IN SCHEMA shared
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_extension;
ALTER DEFAULT PRIVILEGES IN SCHEMA shared
    GRANT SELECT ON TABLES TO app_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA shared
    GRANT SELECT ON TABLES TO backup_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA consumer
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_consumer;
ALTER DEFAULT PRIVILEGES IN SCHEMA consumer
    GRANT SELECT ON TABLES TO app_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA consumer
    GRANT SELECT ON TABLES TO backup_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA enterprise
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_enterprise;
ALTER DEFAULT PRIVILEGES IN SCHEMA enterprise
    GRANT SELECT ON TABLES TO app_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA enterprise
    GRANT SELECT ON TABLES TO backup_user;

ALTER DEFAULT PRIVILEGES IN SCHEMA extension
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_extension;
ALTER DEFAULT PRIVILEGES IN SCHEMA extension
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_consumer;
ALTER DEFAULT PRIVILEGES IN SCHEMA extension
    GRANT SELECT ON TABLES TO app_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA extension
    GRANT SELECT ON TABLES TO backup_user;

-- =============================================================================
-- REVOKE DANGEROUS DEFAULT PRIVILEGES
-- Remove public schema default access (PostgreSQL 14 and earlier default)
-- =============================================================================

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE thinkvelocity_prod FROM PUBLIC;

-- =============================================================================
-- SEARCH PATH — set per user so queries work without schema prefix
-- =============================================================================

-- Consumer backend: sees shared + consumer first
ALTER USER app_consumer  SET search_path TO consumer, shared, public;

-- Enterprise backend: sees enterprise + shared first
ALTER USER app_enterprise SET search_path TO enterprise, shared, public;

-- Extension API: sees shared + consumer + extension
ALTER USER app_extension  SET search_path TO extension, shared, consumer, public;

-- Read-only: sees everything
ALTER USER app_readonly   SET search_path TO shared, consumer, enterprise, extension, public;

-- Backup: sees everything
ALTER USER backup_user    SET search_path TO shared, consumer, enterprise, extension, public;

-- =============================================================================
-- GRANT BACKUP ROLE MEMBERSHIP (for pg_dump to work)
-- =============================================================================

GRANT pg_read_all_data TO backup_user;

-- =============================================================================
-- VERIFICATION QUERY (run after applying to confirm)
-- =============================================================================
-- SELECT grantee, table_schema, table_name, privilege_type
-- FROM information_schema.role_table_grants
-- WHERE grantee IN ('app_consumer', 'app_enterprise', 'app_extension', 'app_readonly', 'backup_user')
-- ORDER BY grantee, table_schema, table_name;
