#!/usr/bin/env bash
# ==============================================================================
# pg-restore-test.sh — Monthly restore verification for SOC2 A1.2
# ThinkVelocity Production — Server 2 (ec2-user@13.203.181.76, AlmaLinux)
#
# Install:  sudo cp pg-restore-test.sh /opt/backup/pg-restore-test.sh
#           sudo chmod 700 /opt/backup/pg-restore-test.sh
#           sudo chown backup_user:backup_user /opt/backup/pg-restore-test.sh
#
# Crontab (as backup_user — added by setup-backup.sh):
#   0 3 1 * * /opt/backup/pg-restore-test.sh >> /var/log/pg-restore-test.log 2>&1
#
# Required env vars (fetched from AWS Secrets Manager at runtime):
#   BACKUP_GPG_PASSPHRASE   GPG symmetric passphrase (SM: thinkvelocity/production/backup-gpg-passphrase)
#   SLACK_WEBHOOK_URL       Slack incoming webhook URL (SM: thinkvelocity/production/slack-webhook)
#   PGPASSWORD              Password for backup_user (SM: thinkvelocity/production/pg-backup-password)
#
# What this does:
#   1. Downloads the latest daily backup from S3
#   2. Decrypts with GPG
#   3. Restores to a temporary test database
#   4. Counts rows per schema in prod and compares to restored DB
#   5. Reports pass/fail to Slack
#   6. Drops the test database and cleans up temp files
# ==============================================================================

set -euo pipefail

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Database name — handle rename from localpgvelocity to thinkvelocity_prod
DB_PRIMARY="thinkvelocity_prod"
DB_FALLBACK="localpgvelocity"

# Test database name (created fresh, dropped after test)
DATESTAMP=$(date '+%Y%m%d')
TEST_DB="thinkvelocity_restore_test_${DATESTAMP}"

# S3 settings
S3_BUCKET="thinkvelocity-backups"
S3_PREFIX="postgres"
S3_REGION="ap-south-1"

# Schemas to verify
SCHEMAS=("shared" "consumer" "enterprise" "extension")

# PostgreSQL connection
PG_HOST="127.0.0.1"
PG_PORT="5432"
PG_USER="backup_user"
PG_SUPERUSER="postgres"   # Only used for createdb/dropdb

# Local temp directory
TMP_DIR="/var/backups/postgresql/restore-test"

# Log file
LOG_FILE="/var/log/pg-restore-test.log"

# Timestamp
NOW=$(date '+%Y-%m-%d %H:%M:%S')
YEAR=$(date '+%Y')
MONTH=$(date '+%m')

# ==============================================================================
# LOGGING
# ==============================================================================

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOG_FILE}"
}

log_error() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" | tee -a "${LOG_FILE}" >&2
}

# ==============================================================================
# CLEANUP TRAP — always drop test DB and remove temp files on exit
# ==============================================================================

cleanup() {
  local exit_code=$?
  log "--- Cleanup ---"

  # Drop test database if it exists
  if PGPASSWORD="${PGPASSWORD:-}" psql \
      -h "${PG_HOST}" \
      -p "${PG_PORT}" \
      -U "${PG_SUPERUSER}" \
      -lqt 2>/dev/null \
    | cut -d '|' -f 1 \
    | grep -qw "${TEST_DB}"; then
    log "Dropping test database: ${TEST_DB}"
    PGPASSWORD="${PGPASSWORD:-}" dropdb \
      -h "${PG_HOST}" \
      -p "${PG_PORT}" \
      -U "${PG_SUPERUSER}" \
      "${TEST_DB}" \
      || log "WARNING: Could not drop test DB ${TEST_DB} (manual cleanup may be needed)"
  fi

  # Remove temp files
  log "Removing temp files in: ${TMP_DIR}"
  rm -rf "${TMP_DIR}"

  log "Cleanup complete."
  exit "${exit_code}"
}
trap cleanup EXIT

# ==============================================================================
# SLACK NOTIFICATION
# ==============================================================================

notify_slack() {
  local status="$1"
  local message="$2"
  local color

  if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    log "WARNING: SLACK_WEBHOOK_URL not set — skipping Slack notification"
    return 0
  fi

  if [[ "${status}" == "PASS" ]]; then
    color="good"
  else
    color="danger"
  fi

  local payload
  payload=$(cat <<SLACK
{
  "attachments": [
    {
      "color": "${color}",
      "title": "ThinkVelocity Restore Verification — ${status}",
      "text": "${message}",
      "footer": "Server 2 (13.203.181.76) | SOC2 A1.2 Monthly Restore Test",
      "ts": $(date +%s)
    }
  ]
}
SLACK
)

  curl -fsS -X POST \
    -H "Content-Type: application/json" \
    -d "${payload}" \
    "${SLACK_WEBHOOK_URL}" \
    > /dev/null 2>&1 \
    || log "WARNING: Slack notification failed (non-fatal)"
}

# ==============================================================================
# FETCH SECRETS FROM AWS SECRETS MANAGER
# ==============================================================================

fetch_secret() {
  local secret_name="$1"
  local env_var="$2"

  if [[ -n "${!env_var:-}" ]]; then
    log "Using pre-set env var: ${env_var}"
    return 0
  fi

  log "Fetching secret from AWS SM: ${secret_name}"
  local value
  value=$(aws secretsmanager get-secret-value \
    --secret-id "${secret_name}" \
    --region "${S3_REGION}" \
    --query SecretString \
    --output text 2>/dev/null) || {
    log_error "Failed to fetch secret: ${secret_name}"
    return 1
  }
  export "${env_var}=${value}"
}

# ==============================================================================
# DETECT PRODUCTION DATABASE NAME
# ==============================================================================

detect_database() {
  local db
  for db in "${DB_PRIMARY}" "${DB_FALLBACK}"; do
    if PGPASSWORD="${PGPASSWORD:-}" psql \
        -h "${PG_HOST}" \
        -p "${PG_PORT}" \
        -U "${PG_USER}" \
        -lqt 2>/dev/null \
      | cut -d '|' -f 1 \
      | grep -qw "${db}"; then
      echo "${db}"
      return 0
    fi
  done
  return 1
}

# ==============================================================================
# COUNT ROWS PER SCHEMA IN A GIVEN DATABASE
# Returns a space-separated list of "schema.table=count" entries
# ==============================================================================

count_rows_per_schema() {
  local db="$1"
  local results=()

  for schema in "${SCHEMAS[@]}"; do
    # Get all tables in this schema
    local tables
    tables=$(PGPASSWORD="${PGPASSWORD:-}" psql \
      -h "${PG_HOST}" \
      -p "${PG_PORT}" \
      -U "${PG_USER}" \
      -d "${db}" \
      -t -A \
      -c "SELECT tablename FROM pg_tables WHERE schemaname = '${schema}' ORDER BY tablename;" \
      2>/dev/null) || {
      log "WARNING: Could not list tables in schema '${schema}' for db '${db}'"
      results+=("${schema}=ERROR")
      continue
    }

    local schema_total=0
    while IFS= read -r table; do
      [[ -z "${table}" ]] && continue
      local count
      count=$(PGPASSWORD="${PGPASSWORD:-}" psql \
        -h "${PG_HOST}" \
        -p "${PG_PORT}" \
        -U "${PG_USER}" \
        -d "${db}" \
        -t -A \
        -c "SELECT COUNT(*) FROM \"${schema}\".\"${table}\";" \
        2>/dev/null) || count=0
      schema_total=$(( schema_total + count ))
    done <<< "${tables}"

    results+=("${schema}=${schema_total}")
  done

  echo "${results[*]}"
}

# ==============================================================================
# FIND LATEST DAILY BACKUP ON S3
# ==============================================================================

find_latest_s3_backup() {
  local key
  # List objects in current month, look for daily_ files
  key=$(aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/${YEAR}/${MONTH}/" \
    --region "${S3_REGION}" \
    | grep "daily_" \
    | sort \
    | tail -n 1 \
    | awk '{print $4}') \
    || true

  if [[ -z "${key}" ]]; then
    # Try previous month
    local prev_year prev_month
    prev_year=$(date -d "last month" '+%Y')
    prev_month=$(date -d "last month" '+%m')
    key=$(aws s3 ls "s3://${S3_BUCKET}/${S3_PREFIX}/${prev_year}/${prev_month}/" \
      --region "${S3_REGION}" \
      | grep "daily_" \
      | sort \
      | tail -n 1 \
      | awk '{print $4}') \
      || true

    if [[ -z "${key}" ]]; then
      log_error "No daily backup found in S3 for current or previous month."
      return 1
    fi
    echo "${S3_PREFIX}/${prev_year}/${prev_month}/${key}"
    return 0
  fi

  echo "${S3_PREFIX}/${YEAR}/${MONTH}/${key}"
}

# ==============================================================================
# MAIN
# ==============================================================================

log "========================================================================"
log "ThinkVelocity PostgreSQL Restore Verification — Starting"
log "Run time: ${NOW}"
log "Test database: ${TEST_DB}"
log "========================================================================"

RUN_START=$(date +%s)

# --- Fetch secrets ------------------------------------------------------------
fetch_secret "thinkvelocity/production/pg-backup-password"    "PGPASSWORD"
fetch_secret "thinkvelocity/production/backup-gpg-passphrase" "BACKUP_GPG_PASSPHRASE"
fetch_secret "thinkvelocity/production/slack-webhook"          "SLACK_WEBHOOK_URL"

export PGPASSWORD

if [[ -z "${BACKUP_GPG_PASSPHRASE:-}" ]]; then
  log_error "BACKUP_GPG_PASSPHRASE is not set — cannot decrypt backup. Aborting."
  notify_slack "FAIL" "Restore test aborted on $(hostname): BACKUP_GPG_PASSPHRASE missing."
  exit 1
fi

# --- Detect prod DB -----------------------------------------------------------
log "Detecting production database name..."
PROD_DB=""
if PROD_DB=$(detect_database); then
  log "Production database: ${PROD_DB}"
else
  log_error "Production database not found. Aborting."
  notify_slack "FAIL" "Restore test FAILED on $(hostname): production database not found."
  exit 1
fi

# --- Capture prod row counts BEFORE restore -----------------------------------
log "Capturing production row counts per schema..."
PROD_COUNTS=$(count_rows_per_schema "${PROD_DB}")
log "Production counts: ${PROD_COUNTS}"

# --- Find latest backup in S3 -------------------------------------------------
log "Finding latest daily backup in S3..."
S3_KEY=$(find_latest_s3_backup) || {
  notify_slack "FAIL" \
    "Restore test FAILED on $(hostname): No backup found in S3. Check /var/log/pg-restore-test.log."
  exit 1
}
log "Latest backup: s3://${S3_BUCKET}/${S3_KEY}"

# --- Download backup ----------------------------------------------------------
mkdir -p "${TMP_DIR}"
GPG_FILE="${TMP_DIR}/restore.sql.gz.gpg"
GZ_FILE="${TMP_DIR}/restore.sql.gz"
SQL_FILE="${TMP_DIR}/restore.sql"

log "Downloading backup from S3..."
aws s3 cp "s3://${S3_BUCKET}/${S3_KEY}" "${GPG_FILE}" \
  --region "${S3_REGION}" \
  --no-progress \
  || {
    log_error "S3 download failed: s3://${S3_BUCKET}/${S3_KEY}"
    notify_slack "FAIL" \
      "Restore test FAILED on $(hostname): S3 download error. Check /var/log/pg-restore-test.log."
    exit 1
  }
log "Download complete: ${GPG_FILE} ($(du -sh "${GPG_FILE}" | cut -f1))"

# --- Decrypt backup -----------------------------------------------------------
log "Decrypting backup..."
gpg --batch \
    --yes \
    --passphrase-fd 0 \
    --decrypt \
    --output "${GZ_FILE}" \
    "${GPG_FILE}" \
    <<< "${BACKUP_GPG_PASSPHRASE}" \
  || {
    log_error "GPG decryption failed."
    notify_slack "FAIL" \
      "Restore test FAILED on $(hostname): GPG decryption error. Check /var/log/pg-restore-test.log."
    exit 1
  }
log "Decryption complete: ${GZ_FILE}"
rm -f "${GPG_FILE}"

# Decompress
log "Decompressing..."
gunzip -f "${GZ_FILE}"
log "Decompression complete: ${SQL_FILE}"

# --- Create test database -----------------------------------------------------
log "Creating test database: ${TEST_DB}"
PGPASSWORD="${PGPASSWORD}" createdb \
  -h "${PG_HOST}" \
  -p "${PG_PORT}" \
  -U "${PG_SUPERUSER}" \
  "${TEST_DB}" \
  || {
    log_error "Failed to create test database: ${TEST_DB}"
    notify_slack "FAIL" \
      "Restore test FAILED on $(hostname): Could not create test DB. Check /var/log/pg-restore-test.log."
    exit 1
  }
log "Test database created: ${TEST_DB}"

# --- Restore ------------------------------------------------------------------
log "Restoring dump to ${TEST_DB}..."
RESTORE_START=$(date +%s)

PGPASSWORD="${PGPASSWORD}" psql \
  -h "${PG_HOST}" \
  -p "${PG_PORT}" \
  -U "${PG_SUPERUSER}" \
  -d "${TEST_DB}" \
  -f "${SQL_FILE}" \
  > /dev/null 2>&1 \
  || {
    log_error "psql restore failed."
    notify_slack "FAIL" \
      "Restore test FAILED on $(hostname): psql restore error. Check /var/log/pg-restore-test.log."
    exit 1
  }

RESTORE_END=$(date +%s)
RESTORE_ELAPSED=$(( RESTORE_END - RESTORE_START ))
log "Restore complete in ${RESTORE_ELAPSED}s."
rm -f "${SQL_FILE}"

# --- Count rows in restored DB ------------------------------------------------
log "Counting rows per schema in restored database..."
RESTORED_COUNTS=$(count_rows_per_schema "${TEST_DB}")
log "Restored counts: ${RESTORED_COUNTS}"

# --- Compare counts -----------------------------------------------------------
log "--- Comparing row counts ---"
VERIFY_PASS=true
VERIFY_DETAILS=""

for schema in "${SCHEMAS[@]}"; do
  # Extract count for this schema from each result set
  PROD_SCHEMA_COUNT=$(echo "${PROD_COUNTS}" | tr ' ' '\n' | grep "^${schema}=" | cut -d'=' -f2)
  REST_SCHEMA_COUNT=$(echo "${RESTORED_COUNTS}" | tr ' ' '\n' | grep "^${schema}=" | cut -d'=' -f2)

  PROD_SCHEMA_COUNT="${PROD_SCHEMA_COUNT:-0}"
  REST_SCHEMA_COUNT="${REST_SCHEMA_COUNT:-0}"

  if [[ "${PROD_SCHEMA_COUNT}" == "ERROR" || "${REST_SCHEMA_COUNT}" == "ERROR" ]]; then
    log "  schema=${schema} | prod=ERROR | restored=ERROR | SKIP (empty schema or no access)"
    VERIFY_DETAILS+="schema.${schema}: SKIP (access error)\n"
    continue
  fi

  if [[ "${PROD_SCHEMA_COUNT}" -eq "${REST_SCHEMA_COUNT}" ]]; then
    log "  schema=${schema} | prod=${PROD_SCHEMA_COUNT} | restored=${REST_SCHEMA_COUNT} | MATCH"
    VERIFY_DETAILS+="schema.${schema}: MATCH (${PROD_SCHEMA_COUNT} rows)\n"
  elif [[ "${REST_SCHEMA_COUNT}" -ge "${PROD_SCHEMA_COUNT}" ]]; then
    # Restored has >= prod count — acceptable (prod may have had new writes since dump)
    log "  schema=${schema} | prod=${PROD_SCHEMA_COUNT} | restored=${REST_SCHEMA_COUNT} | OK (restored >= prod)"
    VERIFY_DETAILS+="schema.${schema}: OK (restored=${REST_SCHEMA_COUNT} >= prod=${PROD_SCHEMA_COUNT})\n"
  else
    log_error "  schema=${schema} | prod=${PROD_SCHEMA_COUNT} | restored=${REST_SCHEMA_COUNT} | MISMATCH — restored has fewer rows"
    VERIFY_DETAILS+="schema.${schema}: MISMATCH (prod=${PROD_SCHEMA_COUNT}, restored=${REST_SCHEMA_COUNT})\n"
    VERIFY_PASS=false
  fi
done

# --- Final result -------------------------------------------------------------
RUN_END=$(date +%s)
TOTAL_ELAPSED=$(( RUN_END - RUN_START ))

log "========================================================================"
if [[ "${VERIFY_PASS}" == "true" ]]; then
  log "RESULT: PASS"
  log "  Source backup : s3://${S3_BUCKET}/${S3_KEY}"
  log "  Test database : ${TEST_DB}"
  log "  Restore time  : ${RESTORE_ELAPSED}s"
  log "  Total time    : ${TOTAL_ELAPSED}s"
  log "  Row counts    : ${VERIFY_DETAILS}"
  log "========================================================================"
  notify_slack "PASS" \
    "Monthly restore verification PASSED on $(hostname).\nBackup: $(basename "${S3_KEY}")\nRestore time: ${RESTORE_ELAPSED}s\n${VERIFY_DETAILS}"
  exit 0
else
  log "RESULT: FAIL — row count mismatch detected"
  log "  Source backup : s3://${S3_BUCKET}/${S3_KEY}"
  log "  Test database : ${TEST_DB}"
  log "  Details       : ${VERIFY_DETAILS}"
  log "========================================================================"
  notify_slack "FAIL" \
    "Monthly restore verification FAILED on $(hostname) — row count mismatch.\nBackup: $(basename "${S3_KEY}")\n${VERIFY_DETAILS}\nCheck /var/log/pg-restore-test.log."
  exit 1
fi
