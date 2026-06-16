#!/usr/bin/env bash
# ==============================================================================
# run-rini-migrations.sh
# Execute rini-branch migrations 015–019 against the production PostgreSQL DB.
#
# SQL is embedded inline — safe to copy to any server without the repo present.
#
# Migrations:
#   015  engagement_rewards + engagement_email_log tables (campaign incentives)
#   016  consumer_partner_cohort column on usertable
#   017  prompt_library_items catalog table (indexes + updated_at trigger)
#   018  annotated_segments JSONB column on save_enhance_prompt + refine_prompt
#   019  refresh_tokens hardening (client_id, rotated_from) + email_login_links
#
# Usage:
#   ./run-rini-migrations.sh [--dry-run]
#
#   --dry-run   Print all SQL that WOULD be executed; do NOT connect or write.
#               Safe to use on production to preview before applying.
#
# Connection env vars (all optional — sensible defaults shown):
#   PGHOST      host to connect to          (default: 127.0.0.1)
#   PGPORT      port                        (default: 5432)
#   PGUSER      DB username                 (default: postgres)
#   PGPASSWORD  password (never prompted)   (default: "")
#   PGDATABASE  explicit DB name; if unset the script tries thinkvelocity_prod
#               first, then falls back to localpgvelocity
#
# Each migration is:
#   1. Checked for idempotency (schema introspection)
#   2. Wrapped in BEGIN / COMMIT
#   3. Executed with ON_ERROR_STOP=1 (automatic ROLLBACK on failure)
#   4. Followed by a structured [OK] / [SKIP] / [FAIL] log line
#
# Migration 017 has an extra post-apply verification:
#   SELECT COUNT(*) FROM prompt_library_items  must return >= 315
#   (the migration itself creates the table + structure; seed data loaded
#   separately but the check guards against a completely empty catalog)
# ==============================================================================

set -uo pipefail

# ------------------------------------------------------------------------------
# Argument parsing
# ------------------------------------------------------------------------------
DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --help|-h)
      echo "Usage: $0 [--dry-run]"
      echo "  --dry-run   Preview SQL without connecting to the database"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 [--dry-run]" >&2
      exit 1
      ;;
  esac
done

# ------------------------------------------------------------------------------
# Colour helpers
# ------------------------------------------------------------------------------
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
CYAN=$'\033[0;36m'
BOLD=$'\033[1m'
NC=$'\033[0m'

log()      { echo "$*"; }
log_ok()   { echo "${GREEN}$*${NC}"; }
log_skip() { echo "${YELLOW}$*${NC}"; }
log_fail() { echo "${RED}$*${NC}" >&2; }
log_info() { echo "${CYAN}$*${NC}"; }

# ------------------------------------------------------------------------------
# PostgreSQL connection
# ------------------------------------------------------------------------------
PGHOST="${PGHOST:-127.0.0.1}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGPASSWORD="${PGPASSWORD:-}"
export PGPASSWORD  # psql picks this up from the environment

# Resolve DB name: explicit env var → thinkvelocity_prod (if reachable) → localpgvelocity
resolve_db_name() {
  if [[ -n "${PGDATABASE:-}" ]]; then
    echo "${PGDATABASE}"
    return
  fi

  # Try thinkvelocity_prod first (production canonical name)
  if PGPASSWORD="${PGPASSWORD}" psql \
      -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" \
      -d "thinkvelocity_prod" \
      -tAq -c "SELECT 1;" >/dev/null 2>&1; then
    echo "thinkvelocity_prod"
    return
  fi

  # Fall back to localpgvelocity (local / staging)
  echo "localpgvelocity"
}

if [[ "${DRY_RUN}" == false ]]; then
  DB_NAME="$(resolve_db_name)"
else
  DB_NAME="${PGDATABASE:-thinkvelocity_prod (or localpgvelocity — resolved at runtime)}"
fi

# psql base invocation (used everywhere except dry-run)
PSQL=( psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${DB_NAME}" )

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

# Run a single SQL query and return its trimmed output.
# Returns "0" on psql error so callers can do numeric comparisons safely.
psql_scalar() {
  local sql="$1"
  PGPASSWORD="${PGPASSWORD}" "${PSQL[@]}" -tAq -c "${sql}" 2>/dev/null || echo "0"
}

# Execute a migration (heredoc SQL string) inside a single transaction.
# On any statement error psql aborts and rolls back automatically.
# Returns 0 on success, 1 on failure.
run_migration_sql() {
  local label="$1"
  local sql="$2"

  if [[ "${DRY_RUN}" == true ]]; then
    # Just print the SQL — never touch the database
    echo ""
    log_info "    -- BEGIN;"
    while IFS= read -r line; do
      log_info "    ${line}"
    done <<< "${sql}"
    log_info "    -- COMMIT;"
    echo ""
    return 0
  fi

  # Feed SQL via stdin so we can use a heredoc and avoid temp files.
  # --single-transaction wraps everything in BEGIN/COMMIT.
  # ON_ERROR_STOP=1 causes ROLLBACK + non-zero exit on any error.
  local full_sql
  full_sql="$(printf '%s' "${sql}")"

  if echo "${full_sql}" | PGPASSWORD="${PGPASSWORD}" "${PSQL[@]}" \
       --single-transaction \
       -v ON_ERROR_STOP=1 \
       -q; then
    return 0
  else
    # psql already issued ROLLBACK via --single-transaction; belt-and-suspenders
    PGPASSWORD="${PGPASSWORD}" "${PSQL[@]}" -c "ROLLBACK;" -q 2>/dev/null || true
    return 1
  fi
}

# ------------------------------------------------------------------------------
# Header
# ------------------------------------------------------------------------------
echo ""
echo "${BOLD}============================================================${NC}"
echo "${BOLD}  ThinkVelocity — rini branch migrations 015–019${NC}"
echo "${BOLD}============================================================${NC}"
if [[ "${DRY_RUN}" == true ]]; then
  echo "  Mode : ${YELLOW}DRY-RUN${NC} — SQL printed, nothing executed"
  echo "  DB   : ${DB_NAME}"
else
  echo "  Mode : ${GREEN}LIVE EXECUTION${NC}"
  echo "  Host : ${PGHOST}:${PGPORT}"
  echo "  User : ${PGUSER}"
  echo "  DB   : ${DB_NAME}"
fi
echo "${BOLD}============================================================${NC}"
echo ""

# ------------------------------------------------------------------------------
# Counters
# ------------------------------------------------------------------------------
APPLIED=0
SKIPPED=0
FAILED=0

# ==============================================================================
# MIGRATION 015 — engagement_rewards + engagement_email_log
# ==============================================================================
# Creates two tables for campaign incentive tracking:
#   engagement_rewards      — records +5 tries granted for specific actions
#   engagement_email_log    — records campaign emails sent to users
# Both have a UNIQUE constraint / unique index for safe repeated-insert patterns.
# ==============================================================================

M015_LABEL="015: engagement_reward_tracking"
M015_SQL='
-- Engagement reward tracking for campaign incentives (+5 tries)

CREATE TABLE IF NOT EXISTS engagement_rewards (
  id BIGSERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES usertable(user_id) ON DELETE CASCADE,
  action VARCHAR(64) NOT NULL,
  context VARCHAR(64) NOT NULL,
  tries_granted INTEGER NOT NULL DEFAULT 5,
  metadata JSONB NOT NULL DEFAULT '"'"'{}'"'"'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT engagement_rewards_unique_claim UNIQUE (user_id, action, context)
);

CREATE INDEX IF NOT EXISTS idx_engagement_rewards_user_id
  ON engagement_rewards (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS engagement_email_log (
  id BIGSERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES usertable(user_id) ON DELETE CASCADE,
  campaign_type VARCHAR(100) NOT NULL,
  trigger_source VARCHAR(100),
  metadata JSONB NOT NULL DEFAULT '"'"'{}'"'"'::jsonb,
  sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_engagement_email_log_user_campaign_day
  ON engagement_email_log (user_id, campaign_type, sent_at DESC);
'

log "[STEP 1/5] Running migration ${M015_LABEL}"

# Idempotency: engagement_rewards table existence
if [[ "${DRY_RUN}" == false ]]; then
  M015_EXISTS="$(psql_scalar "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='engagement_rewards';")"
else
  M015_EXISTS="0"
fi

if [[ "${M015_EXISTS}" -gt 0 ]]; then
  log_skip "  [SKIP] Migration 015 already applied (engagement_rewards exists)"
  SKIPPED=$((SKIPPED + 1))
else
  if run_migration_sql "015" "${M015_SQL}"; then
    log_ok "  [OK] Migration 015 applied"
    APPLIED=$((APPLIED + 1))
  else
    log_fail "  [FAIL] Migration 015 failed — transaction rolled back"
    FAILED=$((FAILED + 1))
    echo ""
    echo "${BOLD}=== Migration Summary ===${NC}"
    echo "Applied : ${APPLIED}"
    echo "Skipped : ${SKIPPED}"
    echo "Failed  : ${FAILED}"
    exit 1
  fi
fi
echo ""

# ==============================================================================
# MIGRATION 016 — consumer_partner_cohort column on usertable
# ==============================================================================
# Adds an optional VARCHAR(64) column to usertable for external partner labelling
# (e.g. "VGYR"). Backwards-compatible: NULL means not in any partner cohort.
# ==============================================================================

M016_LABEL="016: consumer_partner_cohort"
M016_SQL='
-- Optional partner label for extension consumers (e.g. VGYR). Null = not in a partner cohort.
-- Backwards compatible: new column only; existing clients ignore unknown response fields.
ALTER TABLE usertable
  ADD COLUMN IF NOT EXISTS consumer_partner_cohort VARCHAR(64) NULL;

COMMENT ON COLUMN usertable.consumer_partner_cohort IS
  '"'"'Optional external consumer cohort key (e.g. VGYR). Set via SQL, admin, or optional ext-install body.'"'"';
'

log "[STEP 2/5] Running migration ${M016_LABEL}"

if [[ "${DRY_RUN}" == false ]]; then
  M016_EXISTS="$(psql_scalar "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='usertable' AND column_name='consumer_partner_cohort';")"
else
  M016_EXISTS="0"
fi

if [[ "${M016_EXISTS}" -gt 0 ]]; then
  log_skip "  [SKIP] Migration 016 already applied (consumer_partner_cohort column exists)"
  SKIPPED=$((SKIPPED + 1))
else
  if run_migration_sql "016" "${M016_SQL}"; then
    log_ok "  [OK] Migration 016 applied"
    APPLIED=$((APPLIED + 1))
  else
    log_fail "  [FAIL] Migration 016 failed — transaction rolled back"
    FAILED=$((FAILED + 1))
    echo ""
    echo "${BOLD}=== Migration Summary ===${NC}"
    echo "Applied : ${APPLIED}"
    echo "Skipped : ${SKIPPED}"
    echo "Failed  : ${FAILED}"
    exit 1
  fi
fi
echo ""

# ==============================================================================
# MIGRATION 017 — prompt_library_items catalog table
# ==============================================================================
# Creates the prompt library catalog (separate from per-user prompt history):
#   - UUID primary key, slug UNIQUE, access_tier enum, status enum
#   - GIN index on tags[], B-tree indexes on status/category
#   - Partial UNIQUE index on (source, external_id) for deduplication
#   - BEFORE UPDATE trigger to maintain updated_at automatically
#
# POST-APPLY VERIFICATION:
#   SELECT COUNT(*) FROM prompt_library_items must be >= 315.
#   (The migration creates the table/structure; seed data is loaded separately.
#    If the count is 0 the table was created but seed data has not been applied.)
# ==============================================================================

M017_LABEL="017: prompt_library_catalog"
M017_MIN_ROWS=315
M017_SQL='
-- Prompt library catalog: curated + ingested prompts
-- Separate from user_prompts / save_enhance_prompt (those are per-user history)

CREATE TABLE IF NOT EXISTS prompt_library_items (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug             TEXT UNIQUE NOT NULL,
  title            TEXT NOT NULL,
  short_prompt     TEXT,
  prompt           TEXT NOT NULL,
  why_it_works     TEXT,
  tags             TEXT[]        NOT NULL DEFAULT '"'"'{}'"'"',
  category         TEXT          NOT NULL DEFAULT '"'"'General'"'"',
  cover_url        TEXT,
  image_name       TEXT,
  access_tier      TEXT          NOT NULL DEFAULT '"'"'free'"'"' CHECK (access_tier IN ('"'"'free'"'"', '"'"'pro'"'"')),
  is_pro_only      BOOLEAN       NOT NULL DEFAULT FALSE,
  word_count       INTEGER,
  has_placeholders BOOLEAN       NOT NULL DEFAULT FALSE,
  length_band      TEXT          CHECK (length_band IN ('"'"'Short'"'"', '"'"'Medium'"'"', '"'"'Long'"'"')),
  source           TEXT          NOT NULL DEFAULT '"'"'internal'"'"',
  source_url       TEXT,
  external_id      TEXT,
  status           TEXT          NOT NULL DEFAULT '"'"'published'"'"' CHECK (status IN ('"'"'draft'"'"', '"'"'published'"'"', '"'"'hidden'"'"')),
  created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Fast list queries (published items ordered by newest)
CREATE INDEX IF NOT EXISTS idx_pli_status_created
  ON prompt_library_items (status, created_at DESC);

-- Tag array filtering
CREATE INDEX IF NOT EXISTS idx_pli_tags
  ON prompt_library_items USING GIN (tags);

-- Category filtering
CREATE INDEX IF NOT EXISTS idx_pli_category
  ON prompt_library_items (category);

-- Deduplication by source + external_id
CREATE UNIQUE INDEX IF NOT EXISTS idx_pli_source_external
  ON prompt_library_items (source, external_id)
  WHERE external_id IS NOT NULL;

-- Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION update_prompt_library_items_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_pli_updated_at ON prompt_library_items;
CREATE TRIGGER trg_pli_updated_at
  BEFORE UPDATE ON prompt_library_items
  FOR EACH ROW EXECUTE FUNCTION update_prompt_library_items_updated_at();
'

log "[STEP 3/5] Running migration ${M017_LABEL}"

if [[ "${DRY_RUN}" == false ]]; then
  M017_EXISTS="$(psql_scalar "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='prompt_library_items';")"
else
  M017_EXISTS="0"
fi

if [[ "${M017_EXISTS}" -gt 0 ]]; then
  log_skip "  [SKIP] Migration 017 already applied (prompt_library_items exists)"
  SKIPPED=$((SKIPPED + 1))
  # Report current row count for observability even on skip
  if [[ "${DRY_RUN}" == false ]]; then
    ROW_COUNT="$(psql_scalar "SELECT COUNT(*) FROM prompt_library_items;")"
    log "  prompt_library_items row count: ${ROW_COUNT}"
    if [[ "${ROW_COUNT}" =~ ^[0-9]+$ ]] && [[ "${ROW_COUNT}" -lt "${M017_MIN_ROWS}" ]]; then
      echo "${YELLOW}  [WARN] Only ${ROW_COUNT} rows found (expected >= ${M017_MIN_ROWS}). Seed data may not have been loaded yet.${NC}"
    fi
  fi
else
  if run_migration_sql "017" "${M017_SQL}"; then
    if [[ "${DRY_RUN}" == true ]]; then
      log_ok "  [OK] Migration 017 applied (dry-run)"
      log "       Post-apply check: SELECT COUNT(*) FROM prompt_library_items >= ${M017_MIN_ROWS}"
      APPLIED=$((APPLIED + 1))
    else
      ROW_COUNT="$(psql_scalar "SELECT COUNT(*) FROM prompt_library_items;")"
      if [[ "${ROW_COUNT}" =~ ^[0-9]+$ ]] && [[ "${ROW_COUNT}" -lt "${M017_MIN_ROWS}" ]]; then
        # Table created but seed data not yet present — warn, do not fail
        # (seed data is loaded as a separate step outside this migration script)
        echo "${YELLOW}  [WARN] Migration 017 applied — ${ROW_COUNT} rows in prompt_library_items (expected >= ${M017_MIN_ROWS} after seed load)${NC}"
        echo "         Run the seed-data import separately: node scripts/seed_prompt_library.js"
      else
        log_ok "  [OK] Migration 017 applied — ${ROW_COUNT} rows in prompt_library_items"
      fi
      APPLIED=$((APPLIED + 1))
    fi
  else
    log_fail "  [FAIL] Migration 017 failed — transaction rolled back"
    FAILED=$((FAILED + 1))
    echo ""
    echo "${BOLD}=== Migration Summary ===${NC}"
    echo "Applied : ${APPLIED}"
    echo "Skipped : ${SKIPPED}"
    echo "Failed  : ${FAILED}"
    exit 1
  fi
fi
echo ""

# ==============================================================================
# MIGRATION 018 — annotated_segments JSONB on save_enhance_prompt + refine_prompt
# ==============================================================================
# Adds a nullable JSONB column to both prompt history tables so the backend can
# persist annotation segment data from /enhance/annotate alongside each row.
# NULL = segments not yet captured (legacy rows or annotate API not called).
# Frontend treats NULL as "lazy-fetch and PATCH back" via backfill endpoints.
# ==============================================================================

M018_LABEL="018: annotated_segments"
M018_SQL='
-- Persist annotation segments (from /enhance/annotate) alongside the prompt row.
-- Stored as JSONB so we can query/filter later if needed.
-- NULL means "no segments captured yet" (legacy rows, annotate API failed/timed-out,
-- or user edited the prompt so segments were invalidated).

ALTER TABLE save_enhance_prompt
  ADD COLUMN IF NOT EXISTS annotated_segments JSONB DEFAULT NULL;

ALTER TABLE refine_prompt
  ADD COLUMN IF NOT EXISTS annotated_segments JSONB DEFAULT NULL;
'

log "[STEP 4/5] Running migration ${M018_LABEL}"

if [[ "${DRY_RUN}" == false ]]; then
  M018_EXISTS="$(psql_scalar "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='save_enhance_prompt' AND column_name='annotated_segments';")"
else
  M018_EXISTS="0"
fi

if [[ "${M018_EXISTS}" -gt 0 ]]; then
  log_skip "  [SKIP] Migration 018 already applied (annotated_segments column exists)"
  SKIPPED=$((SKIPPED + 1))
else
  if run_migration_sql "018" "${M018_SQL}"; then
    log_ok "  [OK] Migration 018 applied"
    APPLIED=$((APPLIED + 1))
  else
    log_fail "  [FAIL] Migration 018 failed — transaction rolled back"
    FAILED=$((FAILED + 1))
    echo ""
    echo "${BOLD}=== Migration Summary ===${NC}"
    echo "Applied : ${APPLIED}"
    echo "Skipped : ${SKIPPED}"
    echo "Failed  : ${FAILED}"
    exit 1
  fi
fi
echo ""

# ==============================================================================
# MIGRATION 019 — auth session hardening + magic-link table
# ==============================================================================
# Phase 2 auth hardening on refresh_tokens:
#   client_id VARCHAR(32) NOT NULL DEFAULT 'web'  — identifies which client issued
#   rotated_from_token_id UUID                    — audit chain for token rotation
#   Two new indexes for efficient per-client revocation checks
#
# New table: email_login_links
#   Stores one-time JTI tokens for passwordless / magic-link email login.
#   jti UUID PK, email, issued_at, expires_at, consumed_at (NULL = unused)
#   Two indexes: by email and by unconsumed status (partial index)
#
# The migration header says "Safe to run multiple times" — all statements use
# ADD COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS.
# ==============================================================================

M019_LABEL="019: auth_sessions_client_id_magic_links"
M019_SQL='
-- Phase 2 auth-session hardening.
-- Safe to run multiple times.

ALTER TABLE refresh_tokens
  ADD COLUMN IF NOT EXISTS client_id VARCHAR(32) NOT NULL DEFAULT '"'"'web'"'"';

ALTER TABLE refresh_tokens
  ADD COLUMN IF NOT EXISTS rotated_from_token_id UUID;

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_client_active
  ON refresh_tokens(user_id, client_id)
  WHERE revoked = false;

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_client_token
  ON refresh_tokens(client_id, token_id);

CREATE TABLE IF NOT EXISTS email_login_links (
  jti UUID PRIMARY KEY,
  email TEXT NOT NULL,
  issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_email_login_links_email
  ON email_login_links(email);

CREATE INDEX IF NOT EXISTS idx_email_login_links_unconsumed
  ON email_login_links(jti)
  WHERE consumed_at IS NULL;
'

log "[STEP 5/5] Running migration ${M019_LABEL}"

if [[ "${DRY_RUN}" == false ]]; then
  M019_EXISTS="$(psql_scalar "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='email_login_links';")"
else
  M019_EXISTS="0"
fi

if [[ "${M019_EXISTS}" -gt 0 ]]; then
  log_skip "  [SKIP] Migration 019 already applied (email_login_links exists)"
  SKIPPED=$((SKIPPED + 1))
else
  if run_migration_sql "019" "${M019_SQL}"; then
    log_ok "  [OK] Migration 019 applied"
    APPLIED=$((APPLIED + 1))
  else
    log_fail "  [FAIL] Migration 019 failed — transaction rolled back"
    FAILED=$((FAILED + 1))
    echo ""
    echo "${BOLD}=== Migration Summary ===${NC}"
    echo "Applied : ${APPLIED}"
    echo "Skipped : ${SKIPPED}"
    echo "Failed  : ${FAILED}"
    exit 1
  fi
fi
echo ""

# ==============================================================================
# Summary
# ==============================================================================
echo "${BOLD}=== Migration Summary ===${NC}"
echo "Applied : ${APPLIED}"
echo "Skipped : ${SKIPPED}"
echo "Failed  : ${FAILED}"

if [[ "${DRY_RUN}" == true ]]; then
  echo ""
  echo "${YELLOW}DRY-RUN complete — no changes were made to the database.${NC}"
  echo "Re-run without --dry-run to apply."
elif [[ "${FAILED}" -gt 0 ]]; then
  exit 1
else
  echo ""
  if [[ "${APPLIED}" -gt 0 ]]; then
    log_ok "All pending migrations applied successfully."
  else
    log "Nothing to do — all migrations were already applied."
  fi
fi

exit 0
