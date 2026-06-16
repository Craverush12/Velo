#!/usr/bin/env bash
# ==============================================================================
# deploy-static.sh — Zero-downtime static frontend deploy
# ThinkVelocity Production
#
# Usage:
#   ./deploy-static.sh <target> <build_dir>
#
# Arguments:
#   target      One of: consumer | enterprise
#   build_dir   Local path to the pre-built static files
#               (upload to prod server before calling this script)
#
# Examples:
#   ./deploy-static.sh consumer /tmp/velocity-build
#   ./deploy-static.sh enterprise /tmp/enterprise-build
#
# What it does:
#   1. rsync build_dir/ → /var/www/velocity or /var/www/enterprise
#      --checksum skips unchanged files; --delete removes stale files
#      nginx keeps serving existing files during rsync — zero downtime
#   2. nginx -t (config test — abort if broken)
#   3. nginx -s reload (graceful hot-reload — no connection drops)
#
# Environment variables:
#   SLACK_WEBHOOK_URL   Slack incoming webhook (optional but recommended)
#   CONSUMER_WWW        Override consumer web root (default: /var/www/velocity)
#   ENTERPRISE_WWW      Override enterprise web root (default: /var/www/enterprise)
#
# Logs: /var/log/deploys/YYYYMMDD_HHMMSS_static-<target>.log
# ==============================================================================

set -euo pipefail

# ==============================================================================
# CONFIGURATION
# ==============================================================================

SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
CONSUMER_WWW="${CONSUMER_WWW:-/var/www/velocity}"
ENTERPRISE_WWW="${ENTERPRISE_WWW:-/var/www/enterprise}"
LOG_DIR="/var/log/deploys"

DEPLOY_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"
DEPLOY_ID="$(date '+%Y%m%d_%H%M%S')"

# ==============================================================================
# ARGUMENT PARSING
# ==============================================================================

if [[ "${#}" -lt 2 ]]; then
  echo "Usage: $0 <target> <build_dir>" >&2
  echo "" >&2
  echo "  target:    consumer | enterprise" >&2
  echo "  build_dir: path to pre-built static files" >&2
  echo "" >&2
  echo "Examples:" >&2
  echo "  $0 consumer /tmp/velocity-build" >&2
  echo "  $0 enterprise /tmp/enterprise-build" >&2
  exit 1
fi

TARGET="$1"
BUILD_DIR="$2"

# ==============================================================================
# RESOLVE TARGET
# ==============================================================================

case "${TARGET}" in
  consumer)
    WWW_DIR="${CONSUMER_WWW}"
    LABEL="NextJS (consumer)"
    ;;
  enterprise)
    WWW_DIR="${ENTERPRISE_WWW}"
    LABEL="Enterprise React"
    ;;
  *)
    echo "ERROR: Unknown target '${TARGET}'. Expected: consumer | enterprise" >&2
    exit 1
    ;;
esac

# ==============================================================================
# LOGGING SETUP
# ==============================================================================

LOG_FILE="${LOG_DIR}/${DEPLOY_ID}_static-${TARGET}.log"
mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_FILE}") 2>&1

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [static-deploy:${TARGET}] $*"
}

log_error() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [static-deploy:${TARGET}] ERROR: $*" >&2
}

# ==============================================================================
# SLACK NOTIFICATION
# ==============================================================================

notify_slack() {
  local STATUS="$1"
  local MESSAGE="$2"

  [[ -z "${SLACK_WEBHOOK_URL}" ]] && return 0

  local COLOR
  [[ "${STATUS}" == "SUCCESS" ]] && COLOR="good" || COLOR="danger"

  curl -s -X POST \
    -H "Content-Type: application/json" \
    -d "{
      \"attachments\": [{
        \"color\": \"${COLOR}\",
        \"title\": \"Static Deploy ${STATUS}: ${LABEL}\",
        \"text\": \"${MESSAGE}\",
        \"fields\": [
          {\"title\": \"Build Dir\", \"value\": \"${BUILD_DIR}\", \"short\": true},
          {\"title\": \"Web Root\",  \"value\": \"${WWW_DIR}\",   \"short\": true},
          {\"title\": \"Deploy ID\", \"value\": \"${DEPLOY_ID}\", \"short\": true},
          {\"title\": \"Log\",       \"value\": \"${LOG_FILE}\",  \"short\": false}
        ],
        \"footer\": \"ThinkVelocity Static Deploy\",
        \"ts\": $(date +%s)
      }]
    }" \
    "${SLACK_WEBHOOK_URL}" \
    > /dev/null 2>&1 \
  || log "WARNING: Slack notification failed (non-fatal)"
}

# ==============================================================================
# FAILURE TRAP
# ==============================================================================

_on_exit() {
  local EXIT_CODE="$?"
  if [[ "${EXIT_CODE}" -ne 0 ]]; then
    log_error "Static deploy FAILED (exit ${EXIT_CODE})."
    notify_slack "FAILURE" \
      "Static deploy FAILED: *${LABEL}*.\nCheck log: \`${LOG_FILE}\`"
  fi
}
trap '_on_exit' EXIT

# ==============================================================================
# DEPLOY
# ==============================================================================

log "========================================================"
log "Static deploy: ${LABEL}"
log "  Source:    ${BUILD_DIR}"
log "  Target:    ${WWW_DIR}"
log "  Deploy ID: ${DEPLOY_ID}"
log "========================================================"

# --- Step 1: Validate source --------------------------------------------------
log "Step 1/3: Validating build directory..."

if [[ ! -d "${BUILD_DIR}" ]]; then
  log_error "Build directory not found: ${BUILD_DIR}"
  log_error "Upload build artifacts to the prod server before running this script:"
  log_error "  rsync -av ./out/ ubuntu@PROD_IP:${BUILD_DIR}/"
  exit 1
fi

FILE_COUNT="$(find "${BUILD_DIR}" -type f | wc -l)"
log "Build directory OK — ${FILE_COUNT} files found."

# Create web root if this is a first deploy
mkdir -p "${WWW_DIR}"

# --- Step 2: rsync ------------------------------------------------------------
log "Step 2/3: Syncing files to ${WWW_DIR}..."
log "(nginx continues serving existing files during rsync — zero user impact)"

# --checksum:     skip files whose content hasn't changed (faster, less inode churn)
# --delete:       remove files from WWW_DIR that no longer exist in BUILD_DIR
# --no-times:     let checksum drive decisions (avoids false mismatches on mtimes)
# --safe-links:   ignore symlinks outside build tree
# --backup-dir:   keep one generation of replaced files for emergency rollback
BACKUP_DIR="${WWW_DIR}/.rollback_${DEPLOY_ID}"
mkdir -p "${BACKUP_DIR}"

rsync -av \
  --checksum \
  --delete \
  --no-times \
  --safe-links \
  --backup \
  --backup-dir="${BACKUP_DIR}" \
  --exclude=".git" \
  --exclude=".rollback_*" \
  "${BUILD_DIR}/" \
  "${WWW_DIR}/"

log "rsync complete."
log "Rollback snapshot saved to: ${BACKUP_DIR}"
log "(To rollback: rsync -av --delete ${BACKUP_DIR}/ ${WWW_DIR}/ && nginx -s reload)"

# Remove backups older than 3 deploys to keep disk clean
log "Pruning old rollback snapshots (keeping 3 most recent)..."
ls -dt "${WWW_DIR}"/.rollback_* 2>/dev/null \
  | tail -n +4 \
  | xargs rm -rf \
  || true

# --- Step 3: nginx test + graceful reload ------------------------------------
log "Step 3/3: Testing nginx config..."
if ! nginx -t 2>&1; then
  log_error "nginx -t FAILED. Skipping reload to avoid breaking live traffic."
  log_error "Fix nginx config and rerun, or reload manually after fixing."
  exit 1
fi

log "nginx config OK. Reloading (graceful — zero dropped connections)..."
nginx -s reload
log "nginx reloaded."

# Disarm failure trap — success
trap - EXIT

# ==============================================================================
# SUCCESS
# ==============================================================================

log "========================================================"
log "Static deploy SUCCESS: ${LABEL}"
log "  Web root:  ${WWW_DIR}"
log "  Files:     ${FILE_COUNT}"
log "  Rollback:  ${BACKUP_DIR}"
log "  Deploy ID: ${DEPLOY_ID}"
log "========================================================"

notify_slack "SUCCESS" \
  "Static deploy successful: *${LABEL}*\n${BUILD_DIR} → ${WWW_DIR} (${FILE_COUNT} files)"

exit 0
