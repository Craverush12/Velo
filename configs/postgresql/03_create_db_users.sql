-- ==============================================================================
-- 03_create_db_users.sql — Per-service PostgreSQL user creation
-- ThinkVelocity Production — Server 2
-- Generated: 2026-05-25
--
-- Run as: sudo -u postgres psql -f 03_create_db_users.sql
--
-- BEFORE RUNNING:
--   Replace every REPLACE_WITH_STRONG_32CHAR_PASSWORD placeholder with a
--   unique 32-character random password. Generate with:
--     openssl rand -base64 32
--
-- NOTE: This script does NOT alter or drop the existing postgres superuser.
--       The postgres superuser is left untouched.
-- ==============================================================================

\echo '=== ThinkVelocity DB User Creation Script ==='
\echo 'Ensure all REPLACE_WITH_STRONG_32CHAR_PASSWORD values have been set.'
\echo ''

-- ==============================================================================
-- SECTION 1: CREATE USERS
-- ==============================================================================

-- app_consumer: Used by the Node.js backend and Python AI service on Server 2
-- to read/write the consumer product database (thinkvelocity_prod).
-- Also used by Prompt Enhance on Server 3 (over WireGuard).
CREATE USER app_consumer WITH
  PASSWORD 'REPLACE_WITH_STRONG_32CHAR_PASSWORD'
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  LOGIN;

-- app_enterprise: Used exclusively by the NestJS enterprise backend on Server 3
-- to read/write the enterprise database.
CREATE USER app_enterprise WITH
  PASSWORD 'REPLACE_WITH_STRONG_32CHAR_PASSWORD'
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  LOGIN;

-- app_extension: Used by the FastAPI extension service on Server 1
-- to read/write the thinkvelocity_ext database.
CREATE USER app_extension WITH
  PASSWORD 'REPLACE_WITH_STRONG_32CHAR_PASSWORD'
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  LOGIN;

-- app_readonly: Read-only access to thinkvelocity_prod.
-- Used for reporting queries, analytics dashboards, and monitoring checks.
-- Cannot INSERT, UPDATE, DELETE, or DROP anything.
CREATE USER app_readonly WITH
  PASSWORD 'REPLACE_WITH_STRONG_32CHAR_PASSWORD'
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  LOGIN;

-- backup_user: Used by the automated pg_dump backup script (/opt/backup/pg-backup.sh).
-- Needs CONNECT to each database and REPLICATION privilege for consistent backups.
-- Does NOT need write access to any table.
CREATE USER backup_user WITH
  PASSWORD 'REPLACE_WITH_STRONG_32CHAR_PASSWORD'
  NOSUPERUSER
  NOCREATEDB
  NOCREATEROLE
  REPLICATION    -- Required for pg_basebackup; also enables consistent pg_dump snapshots
  LOGIN;

\echo 'Users created: app_consumer, app_enterprise, app_extension, app_readonly, backup_user'
\echo ''

-- ==============================================================================
-- SECTION 2: GRANT PRIVILEGES — thinkvelocity_prod (app_consumer)
-- ==============================================================================

\echo 'Granting privileges on thinkvelocity_prod to app_consumer...'

-- Allow app_consumer to connect to the consumer product database
GRANT CONNECT ON DATABASE thinkvelocity_prod TO app_consumer;

-- Grant app_consumer access to the public schema and all existing tables/sequences
\connect thinkvelocity_prod
GRANT USAGE ON SCHEMA public TO app_consumer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_consumer;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO app_consumer;

-- Ensure future tables and sequences (created by postgres or migrations) also
-- inherit the same grants automatically — avoids permission drift after migrations.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_consumer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_consumer;

-- ==============================================================================
-- SECTION 3: GRANT PRIVILEGES — thinkvelocity_prod (app_readonly)
-- ==============================================================================

\echo 'Granting privileges on thinkvelocity_prod to app_readonly...'

-- Allow app_readonly to connect to the consumer product database
GRANT CONNECT ON DATABASE thinkvelocity_prod TO app_readonly;

-- Read-only: USAGE on schema and SELECT on all tables (no INSERT/UPDATE/DELETE)
GRANT USAGE ON SCHEMA public TO app_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_readonly;

-- Future tables also readable by app_readonly
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO app_readonly;

-- ==============================================================================
-- SECTION 4: GRANT PRIVILEGES — thinkvelocity_prod (backup_user)
-- ==============================================================================

\echo 'Granting backup_user CONNECT on thinkvelocity_prod...'

-- backup_user needs CONNECT to run pg_dump on thinkvelocity_prod
GRANT CONNECT ON DATABASE thinkvelocity_prod TO backup_user;
GRANT USAGE ON SCHEMA public TO backup_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO backup_user;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO backup_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO backup_user;

-- ==============================================================================
-- SECTION 5: GRANT PRIVILEGES — enterprise (app_enterprise)
-- ==============================================================================

\echo 'Granting privileges on enterprise to app_enterprise...'
\connect enterprise

GRANT CONNECT ON DATABASE enterprise TO app_enterprise;
GRANT USAGE ON SCHEMA public TO app_enterprise;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_enterprise;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO app_enterprise;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_enterprise;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_enterprise;

-- backup_user also needs CONNECT + SELECT on enterprise for pg_dump
GRANT CONNECT ON DATABASE enterprise TO backup_user;
GRANT USAGE ON SCHEMA public TO backup_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO backup_user;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO backup_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO backup_user;

-- ==============================================================================
-- SECTION 6: GRANT PRIVILEGES — thinkvelocity_ext (app_extension)
-- ==============================================================================

\echo 'Granting privileges on thinkvelocity_ext to app_extension...'
\connect thinkvelocity_ext

GRANT CONNECT ON DATABASE thinkvelocity_ext TO app_extension;
GRANT USAGE ON SCHEMA public TO app_extension;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_extension;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO app_extension;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_extension;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_extension;

-- backup_user also needs CONNECT + SELECT on thinkvelocity_ext for pg_dump
GRANT CONNECT ON DATABASE thinkvelocity_ext TO backup_user;
GRANT USAGE ON SCHEMA public TO backup_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO backup_user;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO backup_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO backup_user;

-- ==============================================================================
-- SECTION 7: VERIFICATION QUERIES
-- ==============================================================================

\connect postgres

\echo ''
\echo '=== VERIFICATION: Users created ==='
SELECT usename, usesuper, usecreatedb, usecreaterole, userepl
FROM pg_user
WHERE usename LIKE 'app_%' OR usename = 'backup_user'
ORDER BY usename;

\echo ''
\echo '=== VERIFICATION: Database grants ==='
SELECT datname, has_database_privilege('app_consumer',   datname, 'CONNECT') AS consumer_connect,
                has_database_privilege('app_enterprise',  datname, 'CONNECT') AS enterprise_connect,
                has_database_privilege('app_extension',   datname, 'CONNECT') AS extension_connect,
                has_database_privilege('backup_user',     datname, 'CONNECT') AS backup_connect
FROM pg_database
WHERE datname IN ('thinkvelocity_prod', 'enterprise', 'thinkvelocity_ext')
ORDER BY datname;

\echo ''
\echo '=== Script complete. Review output above for any errors. ==='
\echo 'Next step: Update app .env files to use new credentials (T-017).'
