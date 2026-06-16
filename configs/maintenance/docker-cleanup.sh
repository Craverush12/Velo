#!/bin/bash
# docker-cleanup.sh — Weekly Docker housekeeping
# Install: /opt/maintenance/docker-cleanup.sh
# Cron:    0 4 * * 0 /opt/maintenance/docker-cleanup.sh
set -euo pipefail

LOG="/var/log/docker-cleanup.log"
SLACK_WEBHOOK="${DOCKER_CLEANUP_SLACK_WEBHOOK:-}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

log "=== Docker Cleanup Starting on $(hostname) ==="
log "Disk before: $(df -h / | tail -1)"

# Remove stopped containers older than 24h
REMOVED_CONTAINERS=$(docker container prune --filter "until=24h" -f --format "{{.SpaceReclaimed}}" 2>/dev/null || echo "0B")
log "Containers removed: ${REMOVED_CONTAINERS:-0B} freed"

# Remove unused images older than 7 days (168h)
REMOVED_IMAGES=$(docker image prune -a --filter "until=168h" -f --format "{{.SpaceReclaimed}}" 2>/dev/null || echo "0B")
log "Images pruned: ${REMOVED_IMAGES:-0B} freed"

# Remove dangling volumes (unattached)
log "Pruning dangling volumes..."
docker volume prune -f >> "$LOG" 2>&1

# Remove stale build cache older than 7 days
log "Pruning build cache..."
docker builder prune -f --filter "until=168h" >> "$LOG" 2>&1

log "Disk after: $(df -h / | tail -1)"
log "=== Docker Cleanup Complete ==="

# Notify Slack if webhook is configured
if [ -n "$SLACK_WEBHOOK" ]; then
  curl -s -X POST "$SLACK_WEBHOOK" \
    -H 'Content-type: application/json' \
    -d "{\"text\":\"🧹 Docker cleanup complete on $(hostname). Images freed: ${REMOVED_IMAGES:-0B}\"}" \
    --max-time 10 || true
fi
