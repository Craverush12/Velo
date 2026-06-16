#!/usr/bin/env bash
# ==============================================================================
# T-013: Switch Server 3 connection strings from public IP → WireGuard IP
# ==============================================================================
#
# WHEN TO RUN:
#   After T-009 → T-012 (WireGuard setup) is confirmed working.
#   Prerequisite: from Server 3, run:
#       ping -c 3 10.100.0.1   # must succeed (Server 1 WireGuard IP)
#       ping -c 3 10.100.0.2   # must succeed (Server 2 WireGuard IP)
#
# WHERE TO RUN:
#   SSH to Server 3:
#       ssh -i ~/.ssh/fr-img-tes-ap-south.pem ubuntu@13.233.86.137
#
# WHAT IT CHANGES:
#   - enterprise-backend: DATABASE_URL host → 10.100.0.2 (Server 2 WireGuard IP)
#   - prompt-enhance:     DATABASE_URL host → 10.100.0.2 (Server 2 WireGuard IP)
#   Both services currently connect to PostgreSQL on Server 2 by public IP.
#   After WireGuard, traffic stays on the private VPN tunnel (encrypted, faster).
#
# WireGuard IP map:
#   Server 1 (ext API):        10.100.0.1
#   Server 2 (consumer+DB):    10.100.0.2
#   Server 3 (enterprise):     10.100.0.3
#
# REPLACE_WITH_* values below must be confirmed from each server's actual .env
# ==============================================================================

set -euo pipefail

WIREGUARD_DB_HOST="10.100.0.2"   # Server 2 WireGuard IP (PostgreSQL is here)

log() { echo "[T-013] $*"; }
log_error() { echo "[T-013] ERROR: $*" >&2; }

# ==============================================================================
# PREFLIGHT: verify WireGuard is up before touching anything
# ==============================================================================

log "Verifying WireGuard connectivity to ${WIREGUARD_DB_HOST}..."
if ! ping -c 3 -W 2 "${WIREGUARD_DB_HOST}" > /dev/null 2>&1; then
  log_error "Cannot reach ${WIREGUARD_DB_HOST} via WireGuard."
  log_error "Ensure WireGuard is running: sudo wg show"
  log_error "Do NOT proceed — connection strings would break all DB access."
  exit 1
fi
log "WireGuard reachable. Proceeding."

# ==============================================================================
# HELPER: locate .env file for a container, print it
# ==============================================================================

find_env_file() {
  local CONTAINER_NAME="$1"
  local CANDIDATES=(
    "/var/www/enterprise-backend/.env"
    "/var/www/enterprise-backend/apps/enterprise-backend/.env"
    "/opt/enterprise-backend/.env"
    "/home/ubuntu/enterprise-backend/.env"
    "/var/www/prompt-enhance/.env"
    "/opt/prompt-enhance/.env"
    "/home/ubuntu/prompt-enhance/.env"
  )

  # First: ask Docker where the .env is mounted
  local MOUNTED
  MOUNTED="$(docker inspect \
    --format='{{range .Mounts}}{{if eq .Type "bind"}}{{.Source}} {{end}}{{end}}' \
    "${CONTAINER_NAME}" 2>/dev/null || echo "")"

  for MOUNT in ${MOUNTED}; do
    if [[ "${MOUNT}" == *".env"* && -f "${MOUNT}" ]]; then
      echo "${MOUNT}"
      return 0
    fi
  done

  # Fallback: check well-known paths
  for C in "${CANDIDATES[@]}"; do
    if [[ -f "${C}" ]]; then
      echo "${C}"
      return 0
    fi
  done

  return 1
}

# ==============================================================================
# STEP 1: enterprise-backend
# ==============================================================================

log "=== enterprise-backend ==="

log "Current DATABASE_URL:"
docker exec enterprise-backend printenv DATABASE_URL 2>/dev/null \
  || log "  (could not read from container env — will update .env file directly)"

ENV_FILE=""
if ENV_FILE="$(find_env_file enterprise-backend 2>/dev/null)"; then
  log "Found .env at: ${ENV_FILE}"
else
  log_error "Could not auto-locate enterprise-backend .env file."
  log_error "Set ENV_FILE manually and rerun, or edit the file manually:"
  log_error "  grep -r DATABASE_URL /var/www/enterprise-backend/"
  exit 1
fi

# Backup before editing
cp "${ENV_FILE}" "${ENV_FILE}.bak.T013.$(date +%Y%m%d_%H%M%S)"
log "Backup saved: ${ENV_FILE}.bak.T013.*"

log "Replacing public IP with WireGuard IP in DATABASE_URL..."
# Matches any IPv4 host in the postgres:// connection string (between @ and /)
# Handles both:
#   DATABASE_URL=postgresql://user:pass@13.x.x.x:5432/dbname
#   DATABASE_URL=postgres://user:pass@13.x.x.x:5432/dbname
sed -i -E \
  "s|(@)[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(:[0-9]+/)|\1${WIREGUARD_DB_HOST}\2|g" \
  "${ENV_FILE}"

log "Updated DATABASE_URL in ${ENV_FILE}:"
grep "DATABASE_URL" "${ENV_FILE}"

# ==============================================================================
# STEP 2: prompt-enhance (may be called prompt-enhance or thinkvelocity-enhance)
# ==============================================================================

log "=== prompt-enhance ==="

# Find the running container (may have different name)
ENHANCE_CONTAINER=""
for NAME in "prompt-enhance" "thinkvelocity-enhance" "enhance-api"; do
  if docker inspect "${NAME}" > /dev/null 2>&1; then
    ENHANCE_CONTAINER="${NAME}"
    break
  fi
done

if [[ -z "${ENHANCE_CONTAINER}" ]]; then
  log_error "Cannot find prompt-enhance container. Tried: prompt-enhance, thinkvelocity-enhance, enhance-api"
  log_error "Run: docker ps | grep enhance"
  exit 1
fi

log "Found container: ${ENHANCE_CONTAINER}"
log "Current DATABASE_URL:"
docker exec "${ENHANCE_CONTAINER}" printenv DATABASE_URL 2>/dev/null \
  || log "  (not set or container uses different var name)"

ENHANCE_ENV=""
if ENHANCE_ENV="$(find_env_file "${ENHANCE_CONTAINER}" 2>/dev/null)"; then
  log "Found .env at: ${ENHANCE_ENV}"
else
  log_error "Could not auto-locate ${ENHANCE_CONTAINER} .env file."
  log_error "Run: docker inspect ${ENHANCE_CONTAINER} | grep -i env"
  exit 1
fi

cp "${ENHANCE_ENV}" "${ENHANCE_ENV}.bak.T013.$(date +%Y%m%d_%H%M%S)"
log "Backup saved."

sed -i -E \
  "s|(@)[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(:[0-9]+/)|\1${WIREGUARD_DB_HOST}\2|g" \
  "${ENHANCE_ENV}"

log "Updated DATABASE_URL in ${ENHANCE_ENV}:"
grep "DATABASE_URL" "${ENHANCE_ENV}" || log "  (DATABASE_URL not found — check DB_HOST or POSTGRES_HOST vars)"

# Also patch standalone DB_HOST / POSTGRES_HOST / PG_HOST vars if present
for VAR in DB_HOST POSTGRES_HOST PG_HOST; do
  if grep -q "^${VAR}=" "${ENHANCE_ENV}" 2>/dev/null; then
    sed -i -E "s|^(${VAR}=)[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+|\1${WIREGUARD_DB_HOST}|" "${ENHANCE_ENV}"
    log "Updated ${VAR} → ${WIREGUARD_DB_HOST}"
  fi
done

# ==============================================================================
# STEP 3: Rebuild / restart containers with new env
# ==============================================================================

log "=== Restarting containers to pick up new env ==="

log "Restarting enterprise-backend..."
docker restart enterprise-backend
log "Waiting 10s for startup..."
sleep 10

log "Restarting ${ENHANCE_CONTAINER}..."
docker restart "${ENHANCE_CONTAINER}"
sleep 10

# ==============================================================================
# STEP 4: Verification
# ==============================================================================

log "=== Verification ==="

log "enterprise-backend DATABASE_URL after restart:"
docker exec enterprise-backend printenv DATABASE_URL 2>/dev/null \
  || log "  (env not exposed — check with: docker inspect enterprise-backend)"

log "Checking enterprise-backend health..."
HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" \
  --connect-timeout 5 --max-time 10 \
  "http://127.0.0.1:3000/backend/health" 2>/dev/null || echo "000")"
log "  HTTP ${HTTP_CODE}"
[[ "${HTTP_CODE}" =~ ^2 ]] && log "  enterprise-backend: HEALTHY" \
  || log_error "  enterprise-backend: UNHEALTHY — check docker logs enterprise-backend"

log "Checking ${ENHANCE_CONTAINER} health..."
# Port may vary — use 3002 as default; adjust if different
ENHANCE_PORT="${ENHANCE_PORT:-3002}"
HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" \
  --connect-timeout 5 --max-time 10 \
  "http://127.0.0.1:${ENHANCE_PORT}/health" 2>/dev/null || echo "000")"
log "  HTTP ${HTTP_CODE}"
[[ "${HTTP_CODE}" =~ ^2 ]] && log "  ${ENHANCE_CONTAINER}: HEALTHY" \
  || log_error "  ${ENHANCE_CONTAINER}: UNHEALTHY — check docker logs ${ENHANCE_CONTAINER}"

log "T-013 complete. Both services should now route DB traffic over WireGuard."
log "Verify with: sudo tcpdump -i eth0 'host REPLACE_WITH_SERVER2_PUBLIC_IP and port 5432'"
log "(should see NO new packets if WireGuard is handling all DB traffic)"
