#!/bin/bash
# Hot-patch: fix moderation URL + fail-closed behavior on tv-nestjs-enterprise
# Run from ThinkVelocity project root on the server (35.154.138.184)
# Decision D-030: enterprise moderation failures must be fail-closed

set -e

CONTAINER=tv-nestjs-enterprise
BACKUP_DIR=/tmp/guardrail-backup-$(date +%Y%m%d-%H%M%S)

echo "[1/5] Finding guardrail service file in container..."
# Find the compiled guardrail service
GUARDRAIL_FILE=$(docker exec $CONTAINER find /app -name "guardrail.service.js" 2>/dev/null | head -1)
if [ -z "$GUARDRAIL_FILE" ]; then
  echo "ERROR: Could not find guardrail.service.js in container"
  exit 1
fi
echo "Found: $GUARDRAIL_FILE"

echo "[2/5] Backing up original..."
docker exec $CONTAINER mkdir -p $BACKUP_DIR
docker exec $CONTAINER cp "$GUARDRAIL_FILE" "$BACKUP_DIR/guardrail.service.js.bak"
echo "Backup at container:$BACKUP_DIR"

echo "[3/5] Patching fail-open -> fail-closed..."
# Replace the fail-open ALLOW return with fail-closed BLOCK return
# This targets the catch block in callModerationService
docker exec $CONTAINER sed -i \
  "s/decision: 'ALLOW', confidence: 0, reason: 'moderation service error'/decision: 'BLOCK', confidence: 1, reason: 'moderation_service_unavailable', guardrail: 'moderation_unavailable'/g" \
  "$GUARDRAIL_FILE"

# Verify the patch was applied
PATCHED=$(docker exec $CONTAINER grep -c "moderation_service_unavailable" "$GUARDRAIL_FILE" || true)
if [ "$PATCHED" = "0" ]; then
  echo "WARNING: sed substitution matched nothing — the catch block text may differ from expected."
  echo "Manual inspection required: docker exec $CONTAINER grep -n 'ALLOW\|BLOCK\|moderation' $GUARDRAIL_FILE"
fi

echo "[4/5] Fixing MODERATION_SERVICE_URL env var..."
# Append override to /app/.env so it takes precedence at next process start
# NOTE: This only persists until container is recreated — proper fix needs docker-compose update
docker exec $CONTAINER sh -c 'echo "" >> /app/.env 2>/dev/null; echo "MODERATION_SERVICE_URL=http://tv-python-ai-unified:8005/ai" >> /app/.env 2>/dev/null || true'

# Also patch the docker-compose on the host (if accessible) for durability
COMPOSE_FILE="/root/enterprise-backend/docker-compose.yml"
if [ -f "$COMPOSE_FILE" ]; then
  echo "Patching docker-compose.yml for permanent env var fix..."
  sed -i \
    's|MODERATION_SERVICE_URL=http://tv-python-ai-unified:8005/ai/enhance|MODERATION_SERVICE_URL=http://tv-python-ai-unified:8005/ai|g' \
    "$COMPOSE_FILE"
  echo "docker-compose.yml updated. Run 'docker compose up -d' to apply persistently."
else
  echo "NOTE: $COMPOSE_FILE not found — env var fix is transient (container restart only)."
  echo "Manually update docker-compose.yml: MODERATION_SERVICE_URL=http://tv-python-ai-unified:8005/ai"
fi

echo "[5/5] Restarting container..."
docker restart $CONTAINER
sleep 5

echo "Verifying..."
STATUS=$(docker inspect --format='{{.State.Status}}' $CONTAINER)
echo "Container status: $STATUS"

if [ "$STATUS" = "running" ]; then
  echo "SUCCESS: Container restarted."
  echo ""
  echo "Test with:"
  echo "  curl -X POST http://127.0.0.1:8005/ai/moderation/check \\"
  echo "    -H 'Content-Type: application/json' \\"
  echo "    -d '{\"content\":\"my ssn is 123-45-6789\"}'"
  echo ""
  echo "Expected: {\"decision\": \"REDACT\", ...}"
  echo ""
  echo "Also verify the NestJS enterprise guardrail route works end-to-end:"
  echo "  docker logs $CONTAINER --tail 20"
else
  echo "FAIL: Container not running. Check logs:"
  echo "  docker logs $CONTAINER --tail 50"
  echo ""
  echo "Restore from backup if needed:"
  echo "  docker cp guardrail-backup:/guardrail.service.js.bak <path>"
fi
