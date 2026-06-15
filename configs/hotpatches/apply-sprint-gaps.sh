#!/bin/bash
# =============================================================================
# Hot-patch: Sprint Gap Remediation — 8 commits from Production branch
# Run from ThinkVelocity project root on the server (35.154.138.184)
#
# What this patches:
#   1. core/llm.py          — LiteLLM fallback (Groq → OpenAI)
#   2. api/enhance.py       — Intent confidence + per-stage latency telemetry
#   3. python-ai-unified/routers/ai/enhance.py  — Attachment PII + injection
#                                                   detection + context gate
#   4. python-ai-unified/routers/context.py     — Entity extraction layer
#
# Containers affected:
#   tv-python-ai-unified   (port 8005) — all four files
#   tv-extension-api       (port 8000) — api/enhance.py + core/llm.py only
#
# Prerequisites:
#   - git pull already done (or run this script with SKIP_PULL=1 if done separately)
#   - POSTGRES_DSN exported (for the SQL migration), e.g.:
#       export POSTGRES_DSN="postgresql://thinkvelocity:password@localhost:5432/thinkvelocity"
#   - OPENAI_API_KEY exported if you want OpenAI fallback active immediately
#
# Usage:
#   cd /root   (or wherever the repo lives — adapt REPO_ROOT below)
#   bash configs/hotpatches/apply-sprint-gaps.sh
#
# Rollback: each changed file is backed up under /tmp/sprint-backup-<timestamp>/
# =============================================================================

set -e

REPO_ROOT="$(pwd)"
BACKUP_DIR="/tmp/sprint-backup-$(date +%Y%m%d-%H%M%S)"

# Container names — adjust if yours differ
PYTHON_AI_CONTAINER="${PYTHON_AI_CONTAINER:-tv-python-ai-unified}"
EXTENSION_API_CONTAINER="${EXTENSION_API_CONTAINER:-tv-extension-api}"

# App root inside each container
PYTHON_AI_APP="/app"
EXTENSION_API_APP="/app"

# Files that changed this sprint
CHANGED_CORE=(
  "core/llm.py"
  "api/enhance.py"
)
CHANGED_PYTHON_AI=(
  "python-ai-unified/routers/ai/enhance.py"
  "python-ai-unified/routers/context.py"
)

echo "================================================================"
echo "  ThinkVelocity — Sprint Gap Remediation Hot-Patch"
echo "  Backup: $BACKUP_DIR"
echo "================================================================"
echo ""

# ── 0. Git pull ─────────────────────────────────────────────────────────────
if [[ "${SKIP_PULL:-0}" != "1" ]]; then
  echo "[0/6] Pulling latest code from origin/Production..."
  git pull origin Production
  echo "      Done."
else
  echo "[0/6] Skipping git pull (SKIP_PULL=1)."
fi
echo ""

# ── 1. Validate containers are running ──────────────────────────────────────
echo "[1/6] Checking containers..."

check_container() {
  local NAME="$1"
  if docker inspect "$NAME" > /dev/null 2>&1; then
    local STATUS
    STATUS="$(docker inspect --format='{{.State.Status}}' "$NAME")"
    echo "      $NAME → $STATUS"
    if [[ "$STATUS" != "running" ]]; then
      echo "ERROR: Container $NAME is not running (status: $STATUS). Aborting."
      exit 1
    fi
  else
    echo "WARNING: Container $NAME not found — skipping patches for it."
    # Set flag so we can skip later steps
    eval "SKIP_${NAME//-/_}=1"
  fi
}

check_container "$PYTHON_AI_CONTAINER"
check_container "$EXTENSION_API_CONTAINER"
echo ""

# ── 2. Backup existing files ─────────────────────────────────────────────────
echo "[2/6] Backing up existing files from containers..."
mkdir -p "$BACKUP_DIR"

backup_from_container() {
  local CONTAINER="$1"
  local APP_ROOT="$2"
  shift 2
  local FILES=("$@")
  local SKIP_VAR="SKIP_${CONTAINER//-/_}"

  if [[ "${!SKIP_VAR:-0}" == "1" ]]; then return; fi

  mkdir -p "$BACKUP_DIR/$CONTAINER"
  for F in "${FILES[@]}"; do
    local DIR
    DIR="$(dirname "$F")"
    mkdir -p "$BACKUP_DIR/$CONTAINER/$DIR"
    docker cp "$CONTAINER:$APP_ROOT/$F" "$BACKUP_DIR/$CONTAINER/$F" 2>/dev/null \
      && echo "      Backed up $CONTAINER:$APP_ROOT/$F" \
      || echo "      WARNING: Could not back up $CONTAINER:$APP_ROOT/$F (may not exist yet)"
  done
}

backup_from_container "$PYTHON_AI_CONTAINER"   "$PYTHON_AI_APP"    "${CHANGED_CORE[@]}" "${CHANGED_PYTHON_AI[@]}"
backup_from_container "$EXTENSION_API_CONTAINER" "$EXTENSION_API_APP" "${CHANGED_CORE[@]}"
echo "      Backup complete: $BACKUP_DIR"
echo ""

# ── 3. Install litellm (NEW dependency — must happen before restart) ─────────
echo "[3/6] Installing litellm in containers..."

install_litellm() {
  local CONTAINER="$1"
  local SKIP_VAR="SKIP_${CONTAINER//-/_}"
  if [[ "${!SKIP_VAR:-0}" == "1" ]]; then return; fi

  echo "      Installing litellm in $CONTAINER..."
  docker exec "$CONTAINER" pip install --quiet "litellm>=1.40.0" \
    && echo "      litellm installed in $CONTAINER ✓" \
    || { echo "ERROR: pip install failed in $CONTAINER"; exit 1; }
}

install_litellm "$PYTHON_AI_CONTAINER"
install_litellm "$EXTENSION_API_CONTAINER"
echo ""

# ── 4. Copy patched Python files ─────────────────────────────────────────────
echo "[4/6] Copying patched files into containers..."

copy_to_container() {
  local CONTAINER="$1"
  local APP_ROOT="$2"
  shift 2
  local FILES=("$@")
  local SKIP_VAR="SKIP_${CONTAINER//-/_}"
  if [[ "${!SKIP_VAR:-0}" == "1" ]]; then return; fi

  for F in "${FILES[@]}"; do
    local SRC="$REPO_ROOT/$F"
    local DEST="$CONTAINER:$APP_ROOT/$F"
    if [[ ! -f "$SRC" ]]; then
      echo "      WARNING: Source file not found: $SRC — skipping"
      continue
    fi
    docker cp "$SRC" "$DEST" \
      && echo "      Copied $F → $DEST ✓" \
      || { echo "ERROR: docker cp failed for $F → $DEST"; exit 1; }
  done
}

copy_to_container "$PYTHON_AI_CONTAINER"     "$PYTHON_AI_APP"    "${CHANGED_CORE[@]}" "${CHANGED_PYTHON_AI[@]}"
copy_to_container "$EXTENSION_API_CONTAINER" "$EXTENSION_API_APP" "${CHANGED_CORE[@]}"
echo ""

# ── 5. SQL migration (tenant prompt_suffix column) ───────────────────────────
echo "[5/6] Running SQL migration..."

if [[ -z "${POSTGRES_DSN:-}" ]]; then
  echo "      WARNING: POSTGRES_DSN not set — skipping SQL migration."
  echo "      Run manually when ready:"
  echo "        psql \"\$POSTGRES_DSN\" -f $REPO_ROOT/IMPORTANT/migrations/add_tenant_prompt_suffix.sql"
else
  psql "$POSTGRES_DSN" -f "$REPO_ROOT/IMPORTANT/migrations/add_tenant_prompt_suffix.sql" \
    && echo "      Migration applied ✓" \
    || echo "      WARNING: Migration failed (column may already exist — check manually)"
fi
echo ""

# ── 6. Restart containers ────────────────────────────────────────────────────
echo "[6/6] Restarting containers..."

restart_and_verify() {
  local CONTAINER="$1"
  local HEALTH_URL="$2"
  local SKIP_VAR="SKIP_${CONTAINER//-/_}"
  if [[ "${!SKIP_VAR:-0}" == "1" ]]; then return; fi

  echo "      Restarting $CONTAINER..."
  docker restart "$CONTAINER"
  sleep 8

  local STATUS
  STATUS="$(docker inspect --format='{{.State.Status}}' "$CONTAINER")"
  echo "      Status: $STATUS"

  if [[ "$STATUS" != "running" ]]; then
    echo "ERROR: $CONTAINER not running after restart. Check logs:"
    echo "  docker logs $CONTAINER --tail 50"
    exit 1
  fi

  # Health check
  echo "      Health-checking $HEALTH_URL ..."
  for i in $(seq 1 10); do
    HTTP_CODE="$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 --max-time 5 "$HEALTH_URL" 2>/dev/null || echo "000")"
    if [[ "$HTTP_CODE" =~ ^2[0-9]{2}$ ]]; then
      echo "      $CONTAINER healthy (HTTP $HTTP_CODE) ✓"
      return 0
    fi
    echo "      Attempt $i/10: HTTP $HTTP_CODE — waiting 3s..."
    sleep 3
  done

  echo "ERROR: $CONTAINER failed health check after 30s. Last HTTP: $HTTP_CODE"
  echo "  docker logs $CONTAINER --tail 50"
  exit 1
}

restart_and_verify "$PYTHON_AI_CONTAINER"     "http://127.0.0.1:8005/health"
restart_and_verify "$EXTENSION_API_CONTAINER" "http://127.0.0.1:8000/health"
echo ""

echo "================================================================"
echo "  PATCH APPLIED SUCCESSFULLY"
echo "  Backup at: $BACKUP_DIR"
echo ""
echo "  To roll back any container:"
echo "    docker cp $BACKUP_DIR/<container>/<file> <container>:/app/<file>"
echo "    docker restart <container>"
echo ""
echo "  Verify the changes with a smoke test:"
echo "    curl -s -X POST http://127.0.0.1:8005/ai/enhance/chat \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{\"prompt\":\"build a React dashboard with real-time charts\",\"user_id\":\"smoke_test\"}'"
echo "================================================================"
