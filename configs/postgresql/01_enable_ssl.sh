#!/usr/bin/env bash
# ==============================================================================
# 01_enable_ssl.sh — Generate self-signed SSL cert for PostgreSQL on Server 2
# Run as: sudo bash 01_enable_ssl.sh
# Server: ec2-user@13.203.181.76 (Server 2)
# PostgreSQL data dir: /var/lib/pgsql/17/data/
# ==============================================================================

set -euo pipefail

PG_DATA="/var/lib/pgsql/17/data"
CERT_FILE="${PG_DATA}/server.crt"
KEY_FILE="${PG_DATA}/server.key"
LOG_PREFIX="[SSL SETUP $(date '+%Y-%m-%d %H:%M:%S')]"

echo "${LOG_PREFIX} Starting PostgreSQL SSL certificate generation..."

# --- 1. Ensure we are running as root ----------------------------------------
if [[ "${EUID}" -ne 0 ]]; then
  echo "${LOG_PREFIX} ERROR: This script must be run as root (sudo)." >&2
  exit 1
fi

# --- 2. Ensure the PostgreSQL data directory exists --------------------------
if [[ ! -d "${PG_DATA}" ]]; then
  echo "${LOG_PREFIX} ERROR: PostgreSQL data directory not found: ${PG_DATA}" >&2
  exit 1
fi

# --- 3. Generate self-signed certificate (1-year validity) --------------------
echo "${LOG_PREFIX} Generating self-signed SSL certificate (365 days)..."
openssl req -new -x509 -days 365 \
  -nodes \
  -out "${CERT_FILE}" \
  -keyout "${KEY_FILE}" \
  -subj "/C=IN/ST=Karnataka/L=Bengaluru/O=ThinkVelocity/CN=thinkvelocity-db"

echo "${LOG_PREFIX} Certificate generated at: ${CERT_FILE}"
echo "${LOG_PREFIX} Private key generated at:  ${KEY_FILE}"

# --- 4. Set correct ownership (postgres:postgres) -----------------------------
chown postgres:postgres "${CERT_FILE}" "${KEY_FILE}"
echo "${LOG_PREFIX} Ownership set to postgres:postgres"

# --- 5. Set correct permissions -----------------------------------------------
chmod 644 "${CERT_FILE}"   # cert can be world-readable
chmod 600 "${KEY_FILE}"    # private key: owner read-only
echo "${LOG_PREFIX} Permissions set: cert=644, key=600"

# --- 6. Enable ssl = on in postgresql.conf (idempotent) ----------------------
PG_CONF="${PG_DATA}/postgresql.conf"

if grep -qE "^#?\s*ssl\s*=" "${PG_CONF}"; then
  # Replace existing (possibly commented-out) ssl line
  sed -i "s|^#\?\s*ssl\s*=.*|ssl = on|" "${PG_CONF}"
  echo "${LOG_PREFIX} Updated ssl = on in postgresql.conf"
else
  # Append if not present at all
  echo "ssl = on" >> "${PG_CONF}"
  echo "${LOG_PREFIX} Appended ssl = on to postgresql.conf"
fi

# --- 7. Verify cert/key pair --------------------------------------------------
echo "${LOG_PREFIX} Verifying certificate/key pair consistency..."
CERT_MODULUS=$(openssl x509 -noout -modulus -in "${CERT_FILE}" | md5sum)
KEY_MODULUS=$(openssl rsa -noout -modulus -in "${KEY_FILE}" | md5sum)

if [[ "${CERT_MODULUS}" != "${KEY_MODULUS}" ]]; then
  echo "${LOG_PREFIX} ERROR: Certificate and key do not match!" >&2
  exit 1
fi
echo "${LOG_PREFIX} Certificate/key pair verified successfully."

# --- 8. Show certificate details ----------------------------------------------
echo ""
echo "=== Certificate Details ==="
openssl x509 -noout -subject -dates -in "${CERT_FILE}"
echo "==========================="
echo ""

echo "${LOG_PREFIX} SSL cert generated successfully."
echo ""
echo "NEXT STEP: Apply pg_hba.conf and run 02_postgresql_conf_changes.sh"
echo "           before restarting PostgreSQL."
echo ""
echo "SSL cert generated. Now apply pg_hba.conf changes before restarting PostgreSQL."
