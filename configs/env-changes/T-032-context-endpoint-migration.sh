#!/usr/bin/env bash
# =============================================================================
# T-032-context-endpoint-migration.sh
# Find + update all callers of the standalone Context Engine (:8001) to the
# unified Python AI service (:8005/context/).
#
# Depends on: T-031 (Context Engine merged into Python AI — /context/* router live)
#
# This script is SAFE to run in --scan mode first (read-only discovery).
# Only with --apply does it edit files (with .bak backups).
#
# Run on Server 2 (ec2-user@13.203.181.76) where the callers live.
#
# Usage:
#   ./T-032-context-endpoint-migration.sh --scan     # discovery only (default)
#   ./T-032-context-endpoint-migration.sh --apply     # edit files + restart
# =============================================================================

set -uo pipefail

MODE="${1:---scan}"

# ----------------------------------------------------------------------------
# What we are migrating
# ----------------------------------------------------------------------------
# OLD endpoint forms the standalone container exposed:
#   http://127.0.0.1:8001/api/process-context
#   http://127.0.0.1:8001/api/process-essence
#   http://127.0.0.1:8001/api/user/{id}/profile
#   http://127.0.0.1:8001/api/search/contexts
#   http://context-engine-container-dev:8001/...   (docker network name)
#
# NEW unified endpoint (Python AI :8005, /context/ router):
#   http://127.0.0.1:8005/context/process-context
#   ...etc (path /api/ → /context/ ; port 8001 → 8005)
#
# Search roots on Server 2 (host source dirs that are bind-mounted/baked):
SEARCH_DIRS=(
  "/root/nodejs-backend"
  "/var/www"
  "/root/python-ai"
)

# Patterns that indicate a context-engine caller
PATTERNS=(
  "127.0.0.1:8001"
  "localhost:8001"
  ":8001/api/"
  "context-engine-container-dev:8001"
  "context-engine-container:8001"
  "CONTEXT_ENGINE_URL"
  "CONTEXT_ENGINE_BASE"
)

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'; BOLD=$'\033[1m'; NC=$'\033[0m'

echo "${BOLD}T-032 — Context Engine endpoint migration (${MODE})${NC}"
echo "============================================================"

# ----------------------------------------------------------------------------
# Step 1 — Discovery
# ----------------------------------------------------------------------------
declare -a HITS=()
for dir in "${SEARCH_DIRS[@]}"; do
  [ -d "$dir" ] || continue
  for pat in "${PATTERNS[@]}"; do
    while IFS= read -r match; do
      [ -n "$match" ] && HITS+=("$match")
    done < <(grep -rnI --exclude-dir=node_modules --exclude-dir=.git \
              --exclude='*.bak' -F "$pat" "$dir" 2>/dev/null)
  done
done

# De-duplicate
mapfile -t HITS < <(printf '%s\n' "${HITS[@]}" | sort -u)

if [ "${#HITS[@]}" -eq 0 ]; then
  echo "${GREEN}No references to the standalone context engine (:8001) found.${NC}"
  echo "Either migration is already complete, or callers use a different form."
  echo "Double-check container env vars:  docker exec <container> printenv | grep -i context"
  exit 0
fi

echo "${YELLOW}Found ${#HITS[@]} reference(s) to context engine:${NC}"
for h in "${HITS[@]}"; do
  echo "  $h"
done
echo ""

# Unique files touched
mapfile -t FILES < <(printf '%s\n' "${HITS[@]}" | cut -d: -f1 | sort -u)
echo "${BOLD}Files to update (${#FILES[@]}):${NC}"
printf '  %s\n' "${FILES[@]}"
echo ""

# ----------------------------------------------------------------------------
# Step 2 — Apply (only with --apply)
# ----------------------------------------------------------------------------
if [ "$MODE" != "--apply" ]; then
  echo "${YELLOW}SCAN mode — no files changed.${NC}"
  echo "Re-run with --apply to perform the edits (backups created as *.bak)."
  exit 0
fi

echo "${BOLD}Applying edits...${NC}"
for f in "${FILES[@]}"; do
  cp "$f" "${f}.bak"
  # Port + host rewrites
  sed -i -E \
    -e 's#(127\.0\.0\.1|localhost):8001/api/#127.0.0.1:8005/context/#g' \
    -e 's#context-engine-container(-dev)?:8001/api/#127.0.0.1:8005/context/#g' \
    -e 's#(127\.0\.0\.1|localhost):8001#127.0.0.1:8005#g' \
    -e 's#context-engine-container(-dev)?:8001#127.0.0.1:8005#g' \
    "$f"
  echo "  ${GREEN}updated${NC} $f  (backup: ${f}.bak)"
done

echo ""
echo "${BOLD}Manual follow-ups (cannot be safely auto-edited):${NC}"
echo "  - Any CONTEXT_ENGINE_URL / CONTEXT_ENGINE_BASE env var: set to"
echo "      http://127.0.0.1:8005/context"
echo "    in the relevant .env / docker-compose.yml, then restart the service."
echo "  - Verify the /context/ paths match the unified service's router prefix"
echo "    (see docs/python-ai-endpoint-map.md for the path mapping)."
echo ""
echo "${BOLD}Restart affected services:${NC}"
echo "  cd /var/www/thinkvelocity && docker compose up -d --no-deps consumer-backend python-ai"
echo ""
echo "${BOLD}Verify:${NC}"
echo "  curl -s http://127.0.0.1:8005/context/health || echo 'check /context/ router'"
echo ""
echo "${GREEN}Done. Backups (*.bak) left in place — remove after verification.${NC}"
