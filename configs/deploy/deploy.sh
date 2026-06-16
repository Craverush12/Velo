#!/usr/bin/env bash
# ==============================================================================
# deploy.sh — Zero-downtime rolling container replacement
# ThinkVelocity Production (consolidated single-server Lightsail)
#
# Usage:
#   ./deploy.sh <service> [<image_tag>]
#
# Arguments:
#   service    One of: consumer-backend | python-ai | enterprise-backend |
#              extension-api | frontend-consumer | frontend-enterprise | all
#   image_tag  Docker image tag to deploy (default: latest)
#              Ignored for frontend-* services (static rsync — no image)
#
# Examples:
#   ./deploy.sh consumer-backend v1.2.3
#   ./deploy.sh python-ai latest
#   ./deploy.sh all                      # deploy all app containers sequentially
#   ./deploy.sh frontend-consumer        # rsync NextJS build → /var/www/velocity
#   ./deploy.sh frontend-enterprise      # rsync Enterprise React → /var/www/enterprise
#
# Rolling restart strategy (containers):
#   1. Pull new image
#   2. Start _new container on Docker-internal network (no host port conflict)
#   3. Health-check _new container by its bridge IP (10 retries × 5s = 50s max)
#   4. If healthy → stop old → remove old → start canonical with new image + ports
#   5. If unhealthy → stop _new, old stays running → Slack alert → exit 1
#   Never leaves service down: either new is up or old stays.
#
# Static frontend strategy (no container):
#   rsync new build → /var/www/velocity or /var/www/enterprise
#   nginx -t && nginx -s reload
#   Zero downtime — nginx serves existing files during rsync, atomic at inode.
#
# Environment variables:
#   SLACK_WEBHOOK_URL      Slack incoming webhook URL (required for notifications)
#   COMPOSE_FILE           Path to docker-compose.yml (default: /var/www/thinkvelocity/docker-compose.yml)
#   HEALTH_CHECK_RETRIES   Retries before giving up (default: 10)
#   HEALTH_CHECK_INTERVAL  Seconds between retries (default: 5)
#
# Logs: /var/log/deploys/YYYYMMDD_HHMMSS_<service>.log
# ==============================================================================

set -euo pipefail

# ==============================================================================
# CONFIGURATION
# ==============================================================================

COMPOSE_FILE="${COMPOSE_FILE:-/var/www/thinkvelocity/docker-compose.yml}"
COMPOSE_DIR="$(dirname "${COMPOSE_FILE}")"
LOG_DIR="/var/log/deploys"
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
HEALTH_CHECK_RETRIES="${HEALTH_CHECK_RETRIES:-10}"
HEALTH_CHECK_INTERVAL="${HEALTH_CHECK_INTERVAL:-5}"

# Static frontend paths
FRONTEND_CONSUMER_BUILD="/tmp/velocity-build"
FRONTEND_CONSUMER_WWW="/var/www/velocity"
FRONTEND_ENTERPRISE_BUILD="/tmp/enterprise-build"
FRONTEND_ENTERPRISE_WWW="/var/www/enterprise"

# Service → image name mapping (matches docker-compose.yml images)
declare -A SERVICE_IMAGE=(
  [consumer-backend]="thinkvelocity/consumer-backend"
  [python-ai]="thinkvelocity/python-ai"
  [enterprise-backend]="thinkvelocity/enterprise-backend"
  [extension-api]="thinkvelocity/extension-api"
)

# Service → container name mapping (matches docker-compose.yml container_name)
declare -A SERVICE_CONTAINER=(
  [consumer-backend]="tv-consumer-backend"
  [python-ai]="tv-python-ai"
  [enterprise-backend]="tv-enterprise-backend"
  [extension-api]="tv-extension-api"
)

# Service → health check URL (all bind on 127.0.0.1 only — nginx proxies externally)
declare -A SERVICE_HEALTH=(
  [consumer-backend]="http://127.0.0.1:3005/health"
  [python-ai]="http://127.0.0.1:8005/health"
  [enterprise-backend]="http://127.0.0.1:3000/backend/health"
  [extension-api]="http://127.0.0.1:8000/health"
)

# Ordered list for "all" deploys (databases and redis are not cycled here)
ALL_SERVICES=(consumer-backend python-ai enterprise-backend extension-api)

# ==============================================================================
# ARGUMENT PARSING
# ==============================================================================

if [[ "${#}" -lt 1 ]]; then
  echo "Usage: $0 <service> [<image_tag>]" >&2
  echo "" >&2
  echo "Services: consumer-backend | python-ai | enterprise-backend | extension-api | frontend-consumer | frontend-enterprise | all" >&2
  exit 1
fi

TARGET_SERVICE="$1"
IMAGE_TAG="${2:-latest}"

# ==============================================================================
# LOGGING SETUP
# ==============================================================================

DEPLOY_TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"
DEPLOY_ID="$(date '+%Y%m%d_%H%M%S')"
LOG_FILE="${LOG_DIR}/${DEPLOY_ID}_${TARGET_SERVICE}.log"

mkdir -p "${LOG_DIR}"

# Tee all output to the log file
exec > >(tee -a "${LOG_FILE}") 2>&1

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [deploy:${TARGET_SERVICE}] $*"
}

log_error() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [deploy:${TARGET_SERVICE}] ERROR: $*" >&2
}

log "Log file: ${LOG_FILE}"

# ==============================================================================
# SLACK NOTIFICATION
# ==============================================================================

notify_slack() {
  local STATUS="$1"   # SUCCESS or FAILURE
  local MESSAGE="$2"
  local COLOR

  if [[ -z "${SLACK_WEBHOOK_URL}" ]]; then
    log "WARNING: SLACK_WEBHOOK_URL not set — skipping Slack notification"
    return 0
  fi

  [[ "${STATUS}" == "SUCCESS" ]] && COLOR="good" || COLOR="danger"

  local HOST_NAME
  HOST_NAME="$(hostname -s 2>/dev/null || echo "prod-server")"

  curl -s -X POST \
    -H "Content-Type: application/json" \
    -d "{
      \"attachments\": [{
        \"color\": \"${COLOR}\",
        \"title\": \"Deploy ${STATUS}: ${TARGET_SERVICE}\",
        \"text\": \"${MESSAGE}\",
        \"fields\": [
          {\"title\": \"Tag\",     \"value\": \"${IMAGE_TAG}\", \"short\": true},
          {\"title\": \"Host\",    \"value\": \"${HOST_NAME}\", \"short\": true},
          {\"title\": \"Deploy ID\", \"value\": \"${DEPLOY_ID}\", \"short\": true},
          {\"title\": \"Log\",     \"value\": \"${LOG_FILE}\",  \"short\": false}
        ],
        \"footer\": \"ThinkVelocity Deploy\",
        \"ts\": $(date +%s)
      }]
    }" \
    "${SLACK_WEBHOOK_URL}" \
    > /dev/null 2>&1 \
  || log "WARNING: Slack notification failed (non-fatal)"
}

# ==============================================================================
# HEALTH CHECK HELPER
# ==============================================================================

# wait_healthy URL [retries] [interval]
# Returns 0 if healthy within retries*interval seconds, 1 otherwise.
wait_healthy() {
  local URL="$1"
  local RETRIES="${2:-${HEALTH_CHECK_RETRIES}}"
  local INTERVAL="${3:-${HEALTH_CHECK_INTERVAL}}"
  local ATTEMPT=0
  local HTTP_CODE

  while [[ "${ATTEMPT}" -lt "${RETRIES}" ]]; do
    HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" \
      --connect-timeout 3 --max-time 5 \
      "${URL}" 2>/dev/null || echo "000")"

    if [[ "${HTTP_CODE}" =~ ^2[0-9]{2}$ ]]; then
      log "  Health OK (HTTP ${HTTP_CODE}) on attempt $((ATTEMPT + 1))/${RETRIES}"
      return 0
    fi

    ATTEMPT=$((ATTEMPT + 1))
    log "  Health attempt ${ATTEMPT}/${RETRIES}: HTTP ${HTTP_CODE} — waiting ${INTERVAL}s..."
    sleep "${INTERVAL}"
  done

  log_error "Health check failed after $((RETRIES * INTERVAL))s. Last HTTP: ${HTTP_CODE}"
  return 1
}

# ==============================================================================
# SINGLE CONTAINER ROLLING DEPLOY
# ==============================================================================

deploy_container() {
  local SERVICE="$1"
  local TAG="$2"

  local IMAGE="${SERVICE_IMAGE[${SERVICE}]}:${TAG}"
  local CONTAINER="${SERVICE_CONTAINER[${SERVICE}]}"
  local NEW_CONTAINER="${CONTAINER}_new"
  local HEALTH_URL="${SERVICE_HEALTH[${SERVICE}]}"

  log "========================================================"
  log "Rolling deploy: ${SERVICE}"
  log "  Image:    ${IMAGE}"
  log "  Health:   ${HEALTH_URL}"
  log "  Deploy ID: ${DEPLOY_ID}"
  log "========================================================"

  # Cleanup trap — fires on any failure, removes _new, keeps old running
  _cleanup_new_container() {
    local EXIT_CODE="$?"
    if [[ "${EXIT_CODE}" -ne 0 ]]; then
      log "Deploy failed (exit ${EXIT_CODE}) — cleaning up _new container..."
      if docker inspect "${NEW_CONTAINER}" > /dev/null 2>&1; then
        docker stop "${NEW_CONTAINER}" > /dev/null 2>&1 || true
        docker rm   "${NEW_CONTAINER}" > /dev/null 2>&1 || true
        log "Removed ${NEW_CONTAINER}. Old container '${CONTAINER}' continues running."
      fi
      log_error "Deploy FAILED: ${SERVICE}. Old container unchanged — no downtime."
      notify_slack "FAILURE" \
        "Deploy FAILED for *${SERVICE}* (\`${TAG}\`).\nOld container still running — no downtime.\nCheck log: \`${LOG_FILE}\`"
    fi
  }
  trap '_cleanup_new_container' EXIT

  # --- Step 1: Pull new image -------------------------------------------------
  log "Step 1/6: Pulling ${IMAGE}..."
  if ! docker pull "${IMAGE}"; then
    log_error "docker pull failed for ${IMAGE}"
    exit 1
  fi
  log "Image pulled."

  # --- Step 2: Verify old container is running --------------------------------
  log "Step 2/6: Checking old container ${CONTAINER}..."
  if ! docker inspect "${CONTAINER}" > /dev/null 2>&1; then
    log_error "Container '${CONTAINER}' not found. Cannot do zero-downtime replace."
    log_error "For a first-time start: cd ${COMPOSE_DIR} && docker compose up -d ${SERVICE}"
    exit 1
  fi

  # Capture config from running container (env, volumes, network, restart)
  local CONTAINER_ENV CONTAINER_VOLUMES CONTAINER_NETWORK CONTAINER_RESTART CONTAINER_PORTS
  CONTAINER_ENV="$(docker inspect \
    --format='{{range .Config.Env}}--env {{.}} {{end}}' "${CONTAINER}")"
  CONTAINER_VOLUMES="$(docker inspect \
    --format='{{range .Mounts}}{{if eq .Type "bind"}}-v {{.Source}}:{{.Destination}} {{end}}{{end}}' "${CONTAINER}")"
  CONTAINER_NETWORK="$(docker inspect \
    --format='{{range $net, $_ := .NetworkSettings.Networks}}--network {{$net}} {{end}}' "${CONTAINER}")"
  CONTAINER_RESTART="$(docker inspect \
    --format='--restart {{.HostConfig.RestartPolicy.Name}}' "${CONTAINER}")"
  CONTAINER_PORTS="$(docker inspect \
    --format='{{range $p,$bindings := .HostConfig.PortBindings}}{{range $bindings}}-p {{.HostIp}}:{{.HostPort}}:{{$p}} {{end}}{{end}}' \
    "${CONTAINER}")"

  log "Old container config captured."

  # --- Step 3: Start _new container (no host port binding) --------------------
  log "Step 3/6: Starting _new container: ${NEW_CONTAINER}..."

  # Remove any stale _new from a previous failed deploy
  if docker inspect "${NEW_CONTAINER}" > /dev/null 2>&1; then
    log "  Removing stale ${NEW_CONTAINER}..."
    docker stop "${NEW_CONTAINER}" > /dev/null 2>&1 || true
    docker rm   "${NEW_CONTAINER}" > /dev/null 2>&1 || true
  fi

  # Start without -p flags — health check via Docker bridge IP, no port conflict
  # shellcheck disable=SC2086
  eval docker run -d \
    --name "${NEW_CONTAINER}" \
    ${CONTAINER_ENV} \
    ${CONTAINER_VOLUMES} \
    ${CONTAINER_NETWORK} \
    ${CONTAINER_RESTART} \
    "${IMAGE}" \
    > /dev/null

  log "_new container started."

  # Resolve Docker bridge IP for direct health check (bypasses host port)
  local NEW_IP
  NEW_IP="$(docker inspect \
    --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{"\n"}}{{end}}' \
    "${NEW_CONTAINER}" | awk 'NF{print;exit}')"

  if [[ -z "${NEW_IP}" ]]; then
    log_error "Cannot resolve bridge IP of ${NEW_CONTAINER} — cannot health-check safely."
    exit 1
  fi

  # Derive container-internal port from the health URL port
  local HOST_PORT CONTAINER_PORT
  HOST_PORT="$(echo "${HEALTH_URL}" | grep -oP '(?<=:)\d+(?=/|$)')"
  CONTAINER_PORT="$(docker port "${CONTAINER}" | awk -v hp="${HOST_PORT}" '
    /->/{
      split($1, a, "/"); split($NF, b, ":");
      if (b[length(b)] == hp){ print a[1]; exit }
    }')"

  if [[ -z "${CONTAINER_PORT}" ]]; then
    log_error "Cannot map host port ${HOST_PORT} to a container port — refusing to proceed."
    exit 1
  fi

  local NEW_HEALTH_URL="http://${NEW_IP}:${CONTAINER_PORT}/health"
  log "_new container health URL: ${NEW_HEALTH_URL}"

  # Brief startup grace
  sleep 3

  # --- Step 4: Health check _new container ------------------------------------
  log "Step 4/6: Health-checking _new container (${HEALTH_CHECK_RETRIES} × ${HEALTH_CHECK_INTERVAL}s)..."

  if ! wait_healthy "${NEW_HEALTH_URL}"; then
    log_error "_new container logs (last 50 lines):"
    docker logs "${NEW_CONTAINER}" --tail 50 >&2 || true
    exit 1
  fi

  # --- Step 5: Promote new → canonical ----------------------------------------
  log "Step 5/6: Promoting _new → canonical..."

  # Stop and remove old
  log "  Stopping old: ${CONTAINER}"
  docker stop "${CONTAINER}" > /dev/null 2>&1 || true
  docker rm   "${CONTAINER}" > /dev/null 2>&1 || true

  # Stop _new so we can restart it with canonical name + ports
  docker stop "${NEW_CONTAINER}" > /dev/null 2>&1

  log "  Starting canonical: ${CONTAINER}"
  # shellcheck disable=SC2086
  eval docker run -d \
    --name "${CONTAINER}" \
    ${CONTAINER_ENV} \
    ${CONTAINER_PORTS} \
    ${CONTAINER_VOLUMES} \
    ${CONTAINER_NETWORK} \
    ${CONTAINER_RESTART} \
    "${IMAGE}" \
    > /dev/null

  docker rm "${NEW_CONTAINER}" > /dev/null 2>&1 || true
  log "Canonical container running."

  # --- Step 6: Final production health check ----------------------------------
  log "Step 6/6: Final health check on ${HEALTH_URL}..."
  sleep 3

  if ! wait_healthy "${HEALTH_URL}" 5 3; then
    log_error "Canonical container failed final health check."
    log_error "Check: docker logs ${CONTAINER}"
    exit 1
  fi

  # Disarm trap — success
  trap - EXIT

  log "========================================================"
  log "Deploy SUCCESS: ${SERVICE} → ${IMAGE}"
  log "Deploy ID: ${DEPLOY_ID}"
  log "========================================================"

  notify_slack "SUCCESS" \
    "Deploy successful: *${SERVICE}* → \`${TAG}\`\nHealth: ${HEALTH_URL} OK"
}

# ==============================================================================
# STATIC FRONTEND DEPLOY (no container — rsync only)
# ==============================================================================

deploy_static() {
  local FRONTEND="$1"  # consumer or enterprise
  local BUILD_DIR WWW_DIR

  case "${FRONTEND}" in
    consumer)
      BUILD_DIR="${FRONTEND_CONSUMER_BUILD}"
      WWW_DIR="${FRONTEND_CONSUMER_WWW}"
      ;;
    enterprise)
      BUILD_DIR="${FRONTEND_ENTERPRISE_BUILD}"
      WWW_DIR="${FRONTEND_ENTERPRISE_WWW}"
      ;;
    *)
      log_error "Unknown frontend: ${FRONTEND}. Expected: consumer | enterprise"
      exit 1
      ;;
  esac

  log "========================================================"
  log "Static deploy: frontend-${FRONTEND}"
  log "  Source:  ${BUILD_DIR}"
  log "  Target:  ${WWW_DIR}"
  log "  Deploy ID: ${DEPLOY_ID}"
  log "========================================================"

  # Validate source
  if [[ ! -d "${BUILD_DIR}" ]]; then
    log_error "Build directory not found: ${BUILD_DIR}"
    log_error "Upload your build artifacts there before running this script."
    exit 1
  fi

  # Ensure target exists
  mkdir -p "${WWW_DIR}"

  log "Step 1/3: rsyncing ${BUILD_DIR}/ → ${WWW_DIR}/"
  # --checksum: skip files that haven't changed (avoids unnecessary inode churn)
  # --delete:   remove files from www that no longer exist in build
  # No downtime: nginx serves the existing inode until rsync replaces it atomically
  rsync -av --checksum --delete \
    --exclude=".git" \
    --exclude="*.map" \
    "${BUILD_DIR}/" \
    "${WWW_DIR}/"

  log "rsync complete."

  log "Step 2/3: Testing nginx config..."
  if ! nginx -t 2>&1; then
    log_error "nginx config test failed — NOT reloading. Investigate before retrying."
    exit 1
  fi

  log "Step 3/3: Reloading nginx (graceful — zero downtime)..."
  nginx -s reload
  log "nginx reloaded."

  log "========================================================"
  log "Static deploy SUCCESS: frontend-${FRONTEND}"
  log "Deploy ID: ${DEPLOY_ID}"
  log "========================================================"

  notify_slack "SUCCESS" \
    "Static deploy successful: *frontend-${FRONTEND}*\n${BUILD_DIR} → ${WWW_DIR}"
}

# ==============================================================================
# DISPATCH
# ==============================================================================

log "ThinkVelocity Deploy — started at ${DEPLOY_TIMESTAMP}"
log "Target: ${TARGET_SERVICE} | Tag: ${IMAGE_TAG}"

case "${TARGET_SERVICE}" in

  all)
    log "Deploying ALL app services sequentially..."
    FAILED_SERVICES=()
    for SVC in "${ALL_SERVICES[@]}"; do
      log "--- Deploying ${SVC} ---"
      if deploy_container "${SVC}" "${IMAGE_TAG}"; then
        log "--- ${SVC}: OK ---"
      else
        log_error "--- ${SVC}: FAILED ---"
        FAILED_SERVICES+=("${SVC}")
      fi
    done

    if [[ "${#FAILED_SERVICES[@]}" -gt 0 ]]; then
      log_error "The following services failed to deploy: ${FAILED_SERVICES[*]}"
      notify_slack "FAILURE" \
        "Deploy 'all' completed with FAILURES.\nFailed: \`${FAILED_SERVICES[*]}\`\nLog: \`${LOG_FILE}\`"
      exit 1
    fi

    log "All services deployed successfully."
    notify_slack "SUCCESS" \
      "Deploy 'all' completed successfully.\nTag: \`${IMAGE_TAG}\`\nServices: ${ALL_SERVICES[*]}"
    ;;

  frontend-consumer)
    deploy_static "consumer"
    ;;

  frontend-enterprise)
    deploy_static "enterprise"
    ;;

  consumer-backend|python-ai|enterprise-backend|extension-api)
    deploy_container "${TARGET_SERVICE}" "${IMAGE_TAG}"
    ;;

  *)
    log_error "Unknown service: '${TARGET_SERVICE}'"
    log_error "Valid services: ${ALL_SERVICES[*]} | frontend-consumer | frontend-enterprise | all"
    exit 1
    ;;

esac

log "Deploy complete. Log saved: ${LOG_FILE}"
exit 0
