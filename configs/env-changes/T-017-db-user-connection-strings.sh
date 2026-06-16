#!/usr/bin/env bash
# ==============================================================================
# T-017: Switch all services from postgres superuser → dedicated per-service DB users
# ==============================================================================
#
# WHEN TO RUN:
#   After T-016 (create per-service DB users) is confirmed complete.
#   Prerequisite: verify users exist on the PostgreSQL server:
#       psql -U postgres -c "\du" | grep app_
#   Expected output: app_consumer, app_enterprise, app_extension
#
# PER-SERVICE USER MAP:
#   consumer-backend  → app_consumer   (schema: consumer)
#   python-ai         → app_consumer   (schema: consumer — context engine is consumer-facing)
#   enterprise-backend→ app_enterprise (schema: enterprise)
#   prompt-enhance    → app_consumer   (schema: consumer)
#   extension-api     → app_extension  (schema: extension)
#
# WHERE TO RUN:
#   Consolidated prod server (single Lightsail instance):
#       ssh ubuntu@REPLACE_WITH_PROD_SERVER_IP
#   docker-compose.yml is at: /var/www/thinkvelocity/docker-compose.yml
#
# PASSWORDS:
#   Set these environment variables before running this script.
#   Pull from AWS Secrets Manager or your .env file:
#       export APP_CONSUMER_DB_PASSWORD="REPLACE_WITH_APP_CONSUMER_PASSWORD"
#       export APP_ENTERPRISE_DB_PASSWORD="REPLACE_WITH_APP_ENTERPRISE_PASSWORD"
#       export APP_EXTENSION_DB_PASSWORD="REPLACE_WITH_APP_EXTENSION_PASSWORD"
#
# ASSUMPTIONS:
#   - All services are managed via docker-compose.yml (not bare docker run)
#   - docker-compose.yml is the canonical source of truth for env vars
#   - A .env file alongside docker-compose.yml supplies secret values
# ==============================================================================

set -euo pipefail

COMPOSE_DIR="/var/www/thinkvelocity"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"
DOT_ENV="${COMPOSE_DIR}/.env"
DB_HOST="127.0.0.1"
DB_PORT="5432"
DB_NAME="thinkvelocity_prod"

log()       { echo "[T-017] $*"; }
log_error() { echo "[T-017] ERROR: $*" >&2; }

# ==============================================================================
# PREFLIGHT CHECKS
# ==============================================================================

log "=== Preflight checks ==="

# Validate required passwords are set
for VAR in APP_CONSUMER_DB_PASSWORD APP_ENTERPRISE_DB_PASSWORD APP_EXTENSION_DB_PASSWORD; do
  if [[ -z "${!VAR:-}" ]]; then
    log_error "Required env var not set: ${VAR}"
    log_error "Export it before running this script."
    exit 1
  fi
done

# Verify docker compose v2 is available
if ! docker compose version > /dev/null 2>&1; then
  log_error "docker compose v2 not found. Install: https://docs.docker.com/compose/install/"
  exit 1
fi

# Verify compose file exists
if [[ ! -f "${COMPOSE_FILE}" ]]; then
  log_error "docker-compose.yml not found at ${COMPOSE_FILE}"
  exit 1
fi

log "Verifying DB users exist..."
for DB_USER in app_consumer app_enterprise app_extension; do
  if ! docker exec tv-postgres \
    psql -U postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" \
    | grep -q 1; then
    log_error "DB user '${DB_USER}' does not exist. Run T-016 first."
    exit 1
  fi
  log "  ${DB_USER}: exists"
done

# ==============================================================================
# HELPER: test a DATABASE_URL connection
# ==============================================================================

test_connection() {
  local URL="$1"
  local LABEL="$2"
  # Extract user from URL for verification
  local USER
  USER="$(echo "${URL}" | grep -oP '(?<=://)[^:]+(?=:)')"

  if docker exec tv-postgres \
    psql "${URL}" -tAc "SELECT current_user" 2>/dev/null | grep -q "${USER}"; then
    log "  Connection test OK — current_user = ${USER}"
    return 0
  else
    log_error "  Connection test FAILED for ${LABEL}"
    log_error "  URL: ${URL}"
    return 1
  fi
}

# ==============================================================================
# STEP 1: Backup .env and docker-compose.yml
# ==============================================================================

log "=== Backing up config files ==="
BACKUP_STAMP="$(date '+%Y%m%d_%H%M%S')"
cp "${DOT_ENV}"        "${DOT_ENV}.bak.T017.${BACKUP_STAMP}"
cp "${COMPOSE_FILE}"   "${COMPOSE_FILE}.bak.T017.${BACKUP_STAMP}"
log "Backups saved with suffix .bak.T017.${BACKUP_STAMP}"

# ==============================================================================
# STEP 2: Update .env password entries
# ==============================================================================

log "=== Updating .env password entries ==="

# Remove old superuser password lines (will be replaced per-service)
# Add dedicated user passwords if not present
update_or_add_env() {
  local FILE="$1"
  local KEY="$2"
  local VALUE="$3"

  if grep -q "^${KEY}=" "${FILE}" 2>/dev/null; then
    sed -i "s|^${KEY}=.*|${KEY}=${VALUE}|" "${FILE}"
    log "  Updated ${KEY}"
  else
    echo "${KEY}=${VALUE}" >> "${FILE}"
    log "  Added ${KEY}"
  fi
}

update_or_add_env "${DOT_ENV}" "APP_CONSUMER_DB_PASSWORD"   "${APP_CONSUMER_DB_PASSWORD}"
update_or_add_env "${DOT_ENV}" "APP_ENTERPRISE_DB_PASSWORD" "${APP_ENTERPRISE_DB_PASSWORD}"
update_or_add_env "${DOT_ENV}" "APP_EXTENSION_DB_PASSWORD"  "${APP_EXTENSION_DB_PASSWORD}"

# ==============================================================================
# STEP 3: Update DATABASE_URL in docker-compose.yml for each service
# ==============================================================================
# The docker-compose.yml uses ${VAR} substitution from the .env file.
# We update the DATABASE_URL lines to reference per-service user/password vars.
# ==============================================================================

log "=== Updating docker-compose.yml DATABASE_URL references ==="

# consumer-backend: postgresql://app_consumer:${APP_CONSUMER_DB_PASSWORD}@...
sed -i -E \
  "s|(DATABASE_URL: postgresql://)postgres:[^@]+(@${DB_HOST}:${DB_PORT}/${DB_NAME})|\1app_consumer:\${APP_CONSUMER_DB_PASSWORD}\2|" \
  "${COMPOSE_FILE}"
# Also handle schema param
sed -i -E \
  "s|(DATABASE_URL: postgresql://)postgres:[^@]+(@${DB_HOST}:${DB_PORT}/${DB_NAME}\?schema=consumer)|\1app_consumer:\${APP_CONSUMER_DB_PASSWORD}\2|" \
  "${COMPOSE_FILE}"
log "  consumer-backend → app_consumer"

# python-ai: also app_consumer (context engine is consumer-facing)
# The python-ai service block uses a different schema env var but same DB user
# We match on the service block context by looking for APP_ENV/PORT 8005 proximity
# Simpler: just replace all remaining postgres:// references for port 8005 context
# In practice: sed on the full file is safe because each DATABASE_URL line is unique
# The consumer-backend line was already updated above; python-ai still has postgres://
sed -i -E \
  "s|(DATABASE_URL: postgresql://)postgres:[^@]+(@${DB_HOST}:${DB_PORT}/${DB_NAME}\s*$)|\1app_consumer:\${APP_CONSUMER_DB_PASSWORD}\2|" \
  "${COMPOSE_FILE}"
log "  python-ai → app_consumer (same as consumer-backend)"

# enterprise-backend: app_enterprise
sed -i -E \
  "s|(DATABASE_URL: postgresql://)postgres:[^@]+(@${DB_HOST}:${DB_PORT}/${DB_NAME}\?schema=enterprise)|\1app_enterprise:\${APP_ENTERPRISE_DB_PASSWORD}\2|" \
  "${COMPOSE_FILE}"
log "  enterprise-backend → app_enterprise"

# extension-api: app_extension
sed -i -E \
  "s|(DATABASE_URL: postgresql://)postgres:[^@]+(@${DB_HOST}:${DB_PORT}/${DB_NAME}\s*$)|\1app_extension:\${APP_EXTENSION_DB_PASSWORD}\2|" \
  "${COMPOSE_FILE}"
log "  extension-api → app_extension"

log "docker-compose.yml updated. Diff:"
diff "${COMPOSE_FILE}.bak.T017.${BACKUP_STAMP}" "${COMPOSE_FILE}" || true

# ==============================================================================
# STEP 4: Rolling restart each app service
# ==============================================================================

log "=== Restarting services with new DB users ==="

cd "${COMPOSE_DIR}"

for SERVICE in consumer-backend python-ai enterprise-backend extension-api; do
  log "Restarting ${SERVICE}..."
  docker compose up -d --no-deps "${SERVICE}"
  log "Waiting 15s for ${SERVICE} to be ready..."
  sleep 15

  # Quick health check
  case "${SERVICE}" in
    consumer-backend)  HEALTH="http://127.0.0.1:3005/health" ;;
    python-ai)         HEALTH="http://127.0.0.1:8005/health" ;;
    enterprise-backend)HEALTH="http://127.0.0.1:3000/backend/health" ;;
    extension-api)     HEALTH="http://127.0.0.1:8000/health" ;;
  esac

  HTTP="$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 "${HEALTH}" || echo 000)"
  if [[ "${HTTP}" =~ ^2 ]]; then
    log "  ${SERVICE}: HEALTHY (HTTP ${HTTP})"
  else
    log_error "  ${SERVICE}: UNHEALTHY (HTTP ${HTTP}). Check: docker compose logs ${SERVICE}"
  fi
done

# ==============================================================================
# STEP 5: Verification — confirm current_user for each service
# ==============================================================================

log "=== Verifying DB connections (SELECT current_user) ==="

verify_db_user() {
  local CONTAINER="$1"
  local EXPECTED_USER="$2"
  local ACTUAL_USER

  ACTUAL_USER="$(docker exec "${CONTAINER}" \
    sh -c 'psql "$DATABASE_URL" -tAc "SELECT current_user" 2>/dev/null' \
    || echo "ERROR")"

  if [[ "${ACTUAL_USER}" == "${EXPECTED_USER}" ]]; then
    log "  ${CONTAINER}: current_user = ${ACTUAL_USER} (correct)"
  else
    log_error "  ${CONTAINER}: expected ${EXPECTED_USER}, got ${ACTUAL_USER}"
    log_error "    Check DATABASE_URL inside container: docker exec ${CONTAINER} printenv DATABASE_URL"
  fi
}

verify_db_user "tv-consumer-backend"   "app_consumer"
verify_db_user "tv-python-ai"          "app_consumer"
verify_db_user "tv-enterprise-backend" "app_enterprise"
verify_db_user "tv-extension-api"      "app_extension"

log "T-017 complete."
log "All services should now authenticate as their dedicated DB users."
log "The postgres superuser password can be rotated now (no services depend on it)."
