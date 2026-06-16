#!/usr/bin/env bash
# ==============================================================================
# setup-backup.sh — One-time setup for ThinkVelocity PostgreSQL backup system
# Run once as root on Server 2 (AlmaLinux / RHEL-based)
#
# Usage:
#   sudo bash /tmp/setup-backup.sh
#
# What this does:
#   1. Installs awscli, gnupg if not present (using dnf)
#   2. Creates /opt/backup/ and copies scripts
#   3. Creates log files with correct permissions
#   4. Sets up crontab entries for backup_user
#   5. Verifies the installation
# ==============================================================================

set -euo pipefail

# ==============================================================================
# MUST RUN AS ROOT
# ==============================================================================
if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: This script must be run as root (sudo bash setup-backup.sh)"
  exit 1
fi

# ==============================================================================
# CONFIGURATION
# ==============================================================================

BACKUP_USER="backup_user"
INSTALL_DIR="/opt/backup"
LOG_DIR="/var/log"
BACKUP_LOG="${LOG_DIR}/pg-backup.log"
RESTORE_LOG="${LOG_DIR}/pg-restore-test.log"

# Scripts to install (must be in same directory as this setup script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/pg-backup.sh"
RESTORE_SCRIPT="${SCRIPT_DIR}/pg-restore-test.sh"

# ==============================================================================
# LOGGING
# ==============================================================================

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log_error() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2
}

log "========================================================================"
log "ThinkVelocity Backup Setup — Starting"
log "Installing as: ${BACKUP_USER}"
log "Install dir  : ${INSTALL_DIR}"
log "========================================================================"

# ==============================================================================
# STEP 1: Verify backup_user exists
# ==============================================================================

log "--- Step 1: Verifying OS user ---"
if ! id "${BACKUP_USER}" &>/dev/null; then
  log_error "OS user '${BACKUP_USER}' does not exist."
  log_error "Create it first: useradd -r -s /bin/bash -m ${BACKUP_USER}"
  exit 1
fi
log "OS user '${BACKUP_USER}' exists."

# Also verify backup_user exists in PostgreSQL
if ! sudo -u "${BACKUP_USER}" \
    psql -h 127.0.0.1 -U "${BACKUP_USER}" -c '\q' postgres &>/dev/null 2>&1; then
  log "WARNING: Cannot verify PostgreSQL user '${BACKUP_USER}' — make sure PGPASSWORD is set."
  log "         Continuing setup (you can verify connectivity manually later)."
fi

# ==============================================================================
# STEP 2: Install required packages (awscli, gnupg)
# ==============================================================================

log "--- Step 2: Installing required packages ---"

install_if_missing() {
  local pkg="$1"
  local cmd="${2:-$1}"

  if command -v "${cmd}" &>/dev/null; then
    log "Already installed: ${cmd}"
  else
    log "Installing: ${pkg}"
    dnf install -y "${pkg}" || {
      log_error "Failed to install ${pkg}"
      exit 1
    }
    log "Installed: ${pkg}"
  fi
}

# awscli v2 — check for 'aws' command
if command -v aws &>/dev/null; then
  log "awscli already installed: $(aws --version 2>&1 | head -1)"
else
  log "Installing AWS CLI v2..."
  # AWS CLI v2 is not in default dnf repos — install from official package
  AWSCLI_TMP=$(mktemp -d)
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" \
    -o "${AWSCLI_TMP}/awscliv2.zip" \
    || { log_error "Failed to download AWS CLI v2"; exit 1; }
  cd "${AWSCLI_TMP}"
  unzip -q awscliv2.zip
  ./aws/install --update
  cd /
  rm -rf "${AWSCLI_TMP}"
  log "AWS CLI v2 installed: $(aws --version 2>&1 | head -1)"
fi

install_if_missing "gnupg2" "gpg"
install_if_missing "curl"   "curl"
install_if_missing "gzip"   "gzip"

# ==============================================================================
# STEP 3: Create install directory
# ==============================================================================

log "--- Step 3: Creating install directory ---"
mkdir -p "${INSTALL_DIR}"
log "Created: ${INSTALL_DIR}"

# ==============================================================================
# STEP 4: Copy backup scripts
# ==============================================================================

log "--- Step 4: Installing backup scripts ---"

if [[ ! -f "${BACKUP_SCRIPT}" ]]; then
  log_error "Backup script not found: ${BACKUP_SCRIPT}"
  log_error "Run this setup script from the same directory as pg-backup.sh"
  exit 1
fi

if [[ ! -f "${RESTORE_SCRIPT}" ]]; then
  log_error "Restore script not found: ${RESTORE_SCRIPT}"
  log_error "Run this setup script from the same directory as pg-restore-test.sh"
  exit 1
fi

cp "${BACKUP_SCRIPT}"  "${INSTALL_DIR}/pg-backup.sh"
cp "${RESTORE_SCRIPT}" "${INSTALL_DIR}/pg-restore-test.sh"

# Set ownership and strict permissions (no group/other read)
chown "${BACKUP_USER}:${BACKUP_USER}" \
  "${INSTALL_DIR}/pg-backup.sh" \
  "${INSTALL_DIR}/pg-restore-test.sh"

chmod 700 "${INSTALL_DIR}/pg-backup.sh"
chmod 700 "${INSTALL_DIR}/pg-restore-test.sh"
chmod 700 "${INSTALL_DIR}"

log "Installed scripts:"
log "  ${INSTALL_DIR}/pg-backup.sh      (mode 700, owner ${BACKUP_USER})"
log "  ${INSTALL_DIR}/pg-restore-test.sh (mode 700, owner ${BACKUP_USER})"

# ==============================================================================
# STEP 5: Create log files with correct ownership
# ==============================================================================

log "--- Step 5: Creating log files ---"

for logfile in "${BACKUP_LOG}" "${RESTORE_LOG}"; do
  if [[ ! -f "${logfile}" ]]; then
    touch "${logfile}"
    log "Created log file: ${logfile}"
  else
    log "Log file already exists: ${logfile}"
  fi
  chown "${BACKUP_USER}:${BACKUP_USER}" "${logfile}"
  chmod 640 "${logfile}"
done

log "Log files ready (mode 640, owner ${BACKUP_USER})"

# ==============================================================================
# STEP 6: Create local backup staging directory
# ==============================================================================

log "--- Step 6: Creating local backup staging directory ---"
LOCAL_BACKUP_DIR="/var/backups/postgresql"
mkdir -p "${LOCAL_BACKUP_DIR}"
chown "${BACKUP_USER}:${BACKUP_USER}" "${LOCAL_BACKUP_DIR}"
chmod 700 "${LOCAL_BACKUP_DIR}"
log "Staging dir: ${LOCAL_BACKUP_DIR} (mode 700, owner ${BACKUP_USER})"

# ==============================================================================
# STEP 7: Set up crontab for backup_user
# ==============================================================================

log "--- Step 7: Setting up crontab for ${BACKUP_USER} ---"

# Build the new crontab content
CRON_BACKUP="0 2 * * * ${INSTALL_DIR}/pg-backup.sh >> ${BACKUP_LOG} 2>&1"
CRON_RESTORE="0 3 1 * * ${INSTALL_DIR}/pg-restore-test.sh >> ${RESTORE_LOG} 2>&1"

# Fetch existing crontab (may be empty)
EXISTING_CRON=$(crontab -u "${BACKUP_USER}" -l 2>/dev/null || true)

# Check if entries already exist; add if missing
CRON_UPDATED=false

if echo "${EXISTING_CRON}" | grep -qF "pg-backup.sh"; then
  log "Cron entry for pg-backup.sh already exists — skipping."
else
  EXISTING_CRON="${EXISTING_CRON}
${CRON_BACKUP}"
  CRON_UPDATED=true
  log "Added cron entry: ${CRON_BACKUP}"
fi

if echo "${EXISTING_CRON}" | grep -qF "pg-restore-test.sh"; then
  log "Cron entry for pg-restore-test.sh already exists — skipping."
else
  EXISTING_CRON="${EXISTING_CRON}
${CRON_RESTORE}"
  CRON_UPDATED=true
  log "Added cron entry: ${CRON_RESTORE}"
fi

if [[ "${CRON_UPDATED}" == "true" ]]; then
  echo "${EXISTING_CRON}" | crontab -u "${BACKUP_USER}" -
  log "Crontab updated for user: ${BACKUP_USER}"
fi

log "Current crontab for ${BACKUP_USER}:"
crontab -u "${BACKUP_USER}" -l 2>/dev/null | while IFS= read -r line; do
  log "  ${line}"
done

# ==============================================================================
# STEP 8: Verify AWS CLI can reach S3 (assumes IAM role is attached)
# ==============================================================================

log "--- Step 8: Verifying AWS connectivity ---"
if sudo -u "${BACKUP_USER}" aws s3 ls s3://thinkvelocity-backups \
    --region ap-south-1 &>/dev/null 2>&1; then
  log "AWS S3 connectivity: OK (IAM role/credentials working)"
else
  log "WARNING: Could not list s3://thinkvelocity-backups — verify that:"
  log "  - The EC2 instance has an IAM role with S3 permissions attached"
  log "  - OR that AWS credentials are configured for ${BACKUP_USER}"
  log "  (Backup scripts will still be installed; fix IAM before first run)"
fi

# ==============================================================================
# DONE
# ==============================================================================

log "========================================================================"
log "Setup complete!"
log ""
log "Next steps:"
log "  1. Ensure AWS Secrets Manager has these secrets:"
log "       thinkvelocity/production/pg-backup-password"
log "       thinkvelocity/production/backup-gpg-passphrase"
log "       thinkvelocity/production/slack-webhook"
log "  2. Ensure the EC2 IAM role has secretsmanager:GetSecretValue permission"
log "  3. Do a manual dry run to verify:"
log "       sudo -u ${BACKUP_USER} ${INSTALL_DIR}/pg-backup.sh --dry-run"
log "  4. Do a full live run to verify end-to-end:"
log "       sudo -u ${BACKUP_USER} ${INSTALL_DIR}/pg-backup.sh"
log "  5. Check the log:"
log "       tail -50 ${BACKUP_LOG}"
log ""
log "Crontab schedule:"
log "  Daily backup   : 02:00 server time (UTC+5:30 IST)"
log "  Monthly restore: 03:00 on 1st of each month"
log "========================================================================"
