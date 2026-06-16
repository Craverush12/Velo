#!/usr/bin/env bash
# ==============================================================================
# pg-backup.sh — Automated PostgreSQL backup to S3 with GPG encryption
# ThinkVelocity Production — Server 2 (ec2-user@13.203.181.76, AlmaLinux)
#
# Install:  sudo cp pg-backup.sh /opt/backup/pg-backup.sh
#           sudo chmod 700 /opt/backup/pg-backup.sh
#           sudo chown backup_user:backup_user /opt/backup/pg-backup.sh
#
# Crontab (as backup_user — added by setup-backup.sh):
#   0 2 * * * /opt/backup/pg-backup.sh >> /var/log/pg-backup.log 2>&1
#
# Required env vars (fetched from AWS Secrets Manager at runtime):
#   BACKUP_GPG_PASSPHRASE   GPG symmetric passphrase (SM: thinkvelocity/production/backup-gpg-passphrase)
#   SLACK_WEBHOOK_URL       Slack incoming webhook URL (SM: thinkvelocity/production/slack-webhook)
#   PGPASSWORD              Password for backup_user (SM: thinkvelocity/production/pg-backup-password)
#
# Usage:
#   /opt/backup/pg-backup.sh           # Full backup
#   /opt/backup/pg-backup.sh --dry-run # Test without uploading to S3
# ==============================================================================

set -euo pipefail

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Database name — handle rename from localpgvelocity to thinkvelocity_prod
DB_PRIMARY="thinkvelocity_prod"
DB_FALLBACK="localpgvelocity"

# S3 destination
S3_BUCKET="thinkvelocity-backups"
S3_PREFIX="postgres"
S3_REGION="ap-south-1"

# Local staging directory (cleaned up after upload)
LOCAL_BACKUP_DIR="/var/backups/postgresql"

# PostgreSQL connection settings
PG_HOST="127.0.0.1"
PG_PORT="5432"
PG_USER="backup_user"

# Retention policy
DAILY_RETENTION_DAYS=30
MONTHLY_RETENTION_DAYS=365   # 12 months = ~365 days

# Log file
LOG_FILE="/var/log/pg-backup.log"

# Timestamp for this run
RUN_START=$(date +%s)
NOW=$(date '+%Y-%m-%d %H:%M:%S')
YEAR=$(date '+%Y')
MONTH=$(date '+%m')
DAY=$(date '+%d')
DATESTAMP=$(date '+%Y%m%d')
YEARMONTH=$(date '+%Y%m')

# Dry run flag
DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
fi

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
# SLACK NOTIFICATION
# ==============================================================================

notify_slack() {
  local status="$1"    # SUCCESS or FAILURE
  local message="$2"
  local color

  if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    log "WARNING: SLACK_WEBHOOK_URL not set — skipping Slack notification"
    return 0
  fi

  if [[ "${status}" == "SUCCESS" ]]; then
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
      "title": "ThinkVelocity PostgreSQL Backup — ${status}",
      "text": "${message}",
      "footer": "Server 2 (13.203.181.76) | SOC2 A1.2",
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
# Fetches each secret by name if the env var is not already set.
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
# DETECT DATABASE NAME (handle rename)
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
# GPG ENCRYPTION
# ==============================================================================

gpg_encrypt() {
  local input_file="$1"
  local output_file="${input_file}.gpg"

  log "Encrypting: ${input_file} → ${output_file}"
  gpg --batch \
      --yes \
      --passphrase-fd 0 \
      --symmetric \
      --cipher-algo AES256 \
      --output "${output_file}" \
      "${input_file}" \
      <<< "${BACKUP_GPG_PASSPHRASE}" \
    || {
      log_error "GPG encryption failed for: ${input_file}"
      rm -f "${output_file}"
      return 1
    }

  echo "${output_file}"
}

# ==============================================================================
# S3 UPLOAD WITH VERIFICATION
# ==============================================================================

s3_upload_and_verify() {
  local local_file="$1"
  local s3_path="$2"

  log "Uploading to S3: s3://${S3_BUCKET}/${s3_path}"

  aws s3 cp "${local_file}" "s3://${S3_BUCKET}/${s3_path}" \
    --region "${S3_REGION}" \
    --no-progress \
    || {
      log_error "S3 upload failed: s3://${S3_BUCKET}/${s3_path}"
      return 1
    }

  # Verify: confirm the object exists and has non-zero size
  local s3_size
  s3_size=$(aws s3 ls "s3://${S3_BUCKET}/${s3_path}" \
    --region "${S3_REGION}" \
    | awk '{print $3}') \
    || {
      log_error "S3 verification ls failed: s3://${S3_BUCKET}/${s3_path}"
      return 1
    }

  if [[ -z "${s3_size}" || "${s3_size}" -eq 0 ]]; then
    log_error "S3 verification failed — object is empty or missing: s3://${S3_BUCKET}/${s3_path}"
    return 1
  fi

  log "S3 upload verified: s3://${S3_BUCKET}/${s3_path} (${s3_size} bytes)"
  return 0
}

# ==============================================================================
# S3 RETENTION CLEANUP
# ==============================================================================

s3_retention_cleanup() {
  local prefix="$1"
  local pattern="$2"        # grep pattern to match filenames (daily_ or monthly_)
  local retention_days="$3"

  log "Retention cleanup: s3://${S3_BUCKET}/${prefix} | pattern=${pattern} | older than ${retention_days} days"

  local cutoff_epoch
  cutoff_epoch=$(date -d "-${retention_days} days" +%s)

  # List objects and filter by pattern, then check date
  aws s3 ls "s3://${S3_BUCKET}/${prefix}" \
    --region "${S3_REGION}" \
    | grep "${pattern}" \
    | while read -r obj_date obj_time obj_size obj_key; do
        local obj_epoch
        obj_epoch=$(date -d "${obj_date} ${obj_time}" +%s 2>/dev/null || echo 0)
        if [[ "${obj_epoch}" -lt "${cutoff_epoch}" ]]; then
          local full_key="${prefix}${obj_key}"
          log "Deleting expired backup: s3://${S3_BUCKET}/${full_key} (${obj_date})"
          if [[ "${DRY_RUN}" == "false" ]]; then
            aws s3 rm "s3://${S3_BUCKET}/${full_key}" \
              --region "${S3_REGION}" \
              || log "WARNING: Failed to delete s3://${S3_BUCKET}/${full_key} (non-fatal)"
          else
            log "[DRY RUN] Would delete: s3://${S3_BUCKET}/${full_key}"
          fi
        fi
      done \
    || log "WARNING: Retention cleanup encountered errors (non-fatal)"
}

# ==============================================================================
# MAIN
# ==============================================================================

log "========================================================================"
log "ThinkVelocity PostgreSQL Backup — Starting"
log "Run time: ${NOW}"
if [[ "${DRY_RUN}" == "true" ]]; then
  log "DRY RUN MODE — no uploads will be performed"
fi
log "========================================================================"

# --- Fetch secrets from AWS SM ------------------------------------------------
fetch_secret "thinkvelocity/production/pg-backup-password"   "PGPASSWORD"
fetch_secret "thinkvelocity/production/backup-gpg-passphrase" "BACKUP_GPG_PASSPHRASE"
fetch_secret "thinkvelocity/production/slack-webhook"         "SLACK_WEBHOOK_URL"

export PGPASSWORD

# Validate required secrets
if [[ -z "${BACKUP_GPG_PASSPHRASE:-}" ]]; then
  log_error "BACKUP_GPG_PASSPHRASE is not set — cannot encrypt backup. Aborting."
  notify_slack "FAILURE" "Backup aborted on $(hostname): BACKUP_GPG_PASSPHRASE missing."
  exit 1
fi

# --- Detect database ----------------------------------------------------------
log "Detecting database name..."
DB_NAME=""
if DB_NAME=$(detect_database); then
  log "Using database: ${DB_NAME}"
else
  log_error "Neither '${DB_PRIMARY}' nor '${DB_FALLBACK}' found. Cannot proceed."
  notify_slack "FAILURE" \
    "Backup FAILED on $(hostname): Could not find database '${DB_PRIMARY}' or '${DB_FALLBACK}'."
  exit 1
fi

# --- Prepare local staging dir ------------------------------------------------
mkdir -p "${LOCAL_BACKUP_DIR}"

# --- Run pg_dump --------------------------------------------------------------
DUMP_FILE="${LOCAL_BACKUP_DIR}/${DB_NAME}_${DATESTAMP}.sql"
GZ_FILE="${DUMP_FILE}.gz"

log "Running pg_dump for database: ${DB_NAME}..."
DUMP_START=$(date +%s)

pg_dump \
  --host="${PG_HOST}" \
  --port="${PG_PORT}" \
  --username="${PG_USER}" \
  --no-password \
  --format=plain \
  --schema=shared \
  --schema=consumer \
  --schema=enterprise \
  --schema=extension \
  "${DB_NAME}" \
  | gzip -9 > "${GZ_FILE}" \
  || {
    log_error "pg_dump failed for database: ${DB_NAME}"
    rm -f "${GZ_FILE}"
    notify_slack "FAILURE" \
      "pg_dump FAILED on $(hostname) for database '${DB_NAME}'. Check /var/log/pg-backup.log."
    exit 1
  }

DUMP_END=$(date +%s)
DUMP_ELAPSED=$(( DUMP_END - DUMP_START ))
GZ_SIZE_BYTES=$(stat -c%s "${GZ_FILE}")
GZ_SIZE_HUMAN=$(du -sh "${GZ_FILE}" | cut -f1)

log "pg_dump complete: ${GZ_FILE}"
log "  Size: ${GZ_SIZE_HUMAN} (${GZ_SIZE_BYTES} bytes)"
log "  Time: ${DUMP_ELAPSED}s"

# --- GPG encrypt --------------------------------------------------------------
log "Encrypting backup..."
ENCRYPT_START=$(date +%s)

GPG_FILE=$(gpg_encrypt "${GZ_FILE}") || {
  notify_slack "FAILURE" \
    "GPG encryption FAILED on $(hostname). Check /var/log/pg-backup.log."
  rm -f "${GZ_FILE}"
  exit 1
}

ENCRYPT_END=$(date +%s)
ENCRYPT_ELAPSED=$(( ENCRYPT_END - ENCRYPT_START ))
GPG_SIZE_HUMAN=$(du -sh "${GPG_FILE}" | cut -f1)
log "Encryption complete: ${GPG_FILE} (${GPG_SIZE_HUMAN}) in ${ENCRYPT_ELAPSED}s"

# Remove unencrypted gzip (keep only the .gpg)
rm -f "${GZ_FILE}"

# --- Determine S3 paths -------------------------------------------------------
DAILY_S3_KEY="${S3_PREFIX}/${YEAR}/${MONTH}/daily_${DATESTAMP}.sql.gz.gpg"

# On 1st of month, also upload a monthly snapshot
IS_FIRST_OF_MONTH=false
if [[ "${DAY}" == "01" ]]; then
  IS_FIRST_OF_MONTH=true
  MONTHLY_S3_KEY="${S3_PREFIX}/${YEAR}/${MONTH}/monthly_${YEARMONTH}.sql.gz.gpg"
fi

# --- Upload daily backup ------------------------------------------------------
if [[ "${DRY_RUN}" == "true" ]]; then
  log "[DRY RUN] Would upload daily: s3://${S3_BUCKET}/${DAILY_S3_KEY}"
else
  s3_upload_and_verify "${GPG_FILE}" "${DAILY_S3_KEY}" || {
    notify_slack "FAILURE" \
      "S3 upload FAILED on $(hostname) for daily backup. Check /var/log/pg-backup.log."
    rm -f "${GPG_FILE}"
    exit 1
  }
fi

# --- Upload monthly snapshot (1st of month only) ------------------------------
if [[ "${IS_FIRST_OF_MONTH}" == "true" ]]; then
  if [[ "${DRY_RUN}" == "true" ]]; then
    log "[DRY RUN] Would upload monthly: s3://${S3_BUCKET}/${MONTHLY_S3_KEY}"
  else
    log "1st of month — uploading monthly snapshot..."
    s3_upload_and_verify "${GPG_FILE}" "${MONTHLY_S3_KEY}" \
      || log "WARNING: Monthly snapshot upload failed (daily backup already succeeded)"
  fi
fi

# --- Clean up local temp file -------------------------------------------------
log "Removing local encrypted file: ${GPG_FILE}"
rm -f "${GPG_FILE}"

# --- S3 retention cleanup -----------------------------------------------------
log "--- Running S3 retention cleanup ---"
RETENTION_PREFIX="${S3_PREFIX}/${YEAR}/${MONTH}/"
s3_retention_cleanup "${RETENTION_PREFIX}" "daily_"   "${DAILY_RETENTION_DAYS}"
s3_retention_cleanup "${RETENTION_PREFIX}" "monthly_" "${MONTHLY_RETENTION_DAYS}"

# Also clean prior months in rolling window (walk back through months)
for i in 1 2; do
  PREV_YEAR=$(date -d "-${i} months" '+%Y')
  PREV_MONTH=$(date -d "-${i} months" '+%m')
  PREV_PREFIX="${S3_PREFIX}/${PREV_YEAR}/${PREV_MONTH}/"
  s3_retention_cleanup "${PREV_PREFIX}" "daily_"   "${DAILY_RETENTION_DAYS}"
  s3_retention_cleanup "${PREV_PREFIX}" "monthly_" "${MONTHLY_RETENTION_DAYS}"
done

# --- Final summary ------------------------------------------------------------
RUN_END=$(date +%s)
TOTAL_ELAPSED=$(( RUN_END - RUN_START ))

log "========================================================================"
log "Backup complete — SUCCESS"
log "  Database   : ${DB_NAME}"
log "  Dump size  : ${GZ_SIZE_HUMAN} (pre-encryption)"
log "  Dump time  : ${DUMP_ELAPSED}s"
log "  Encrypt    : ${ENCRYPT_ELAPSED}s"
log "  Total time : ${TOTAL_ELAPSED}s"
log "  Daily S3   : s3://${S3_BUCKET}/${DAILY_S3_KEY}"
if [[ "${IS_FIRST_OF_MONTH}" == "true" ]]; then
  log "  Monthly S3 : s3://${S3_BUCKET}/${MONTHLY_S3_KEY}"
fi
log "========================================================================"

notify_slack "SUCCESS" \
  "PostgreSQL backup succeeded on $(hostname).\nDB: ${DB_NAME} | Size: ${GZ_SIZE_HUMAN} | Time: ${TOTAL_ELAPSED}s\nS3: s3://${S3_BUCKET}/${DAILY_S3_KEY}"

exit 0
