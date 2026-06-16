#!/usr/bin/env bash
# =============================================================================
# T-031-fetch-canonical-source.sh
# Extract the CANONICAL source code out of the running production containers so
# it can be reconciled against the new unified service in python-ai-unified/.
#
# WHY: docs/python-ai-merge-plan.md confirms the source baked into the live
# images is the authoritative build (Server 3 `prompt-enhance` is the canonical
# /ai/* code; `context-engine-container-dev` is the /context/* code). The host
# source trees may be stale, so we copy straight OUT of the containers with
# `docker cp` (read-only on the container — nothing is restarted or modified).
#
# This feeds RECONCILE.md: you diff ./_canonical/* against the hand-ported
# routers in python-ai-unified/routers/ and resolve each discrepancy.
#
# SAFETY: --scan (default) is fully read-only — it only runs `docker ps` and
# prints what it WOULD copy. --pull performs the actual `docker cp`. Neither
# mode ever stops, restarts, execs into, or writes to a container.
#
# WHERE TO RUN: this script targets containers on TWO hosts, so run the
# relevant section on each:
#   - Server 3 (ec2-user@13.233.86.137) — `prompt-enhance`
#   - Server 2 (ec2-user@13.203.181.76) — `context-engine-container-dev`
# Run with --scan on each first, then --pull on each, then scp the tarballs to
# one workstation for reconciliation.
#
# Usage:
#   ./T-031-fetch-canonical-source.sh            # --scan (default, read-only)
#   ./T-031-fetch-canonical-source.sh --scan
#   ./T-031-fetch-canonical-source.sh --pull     # actually docker cp the source
# =============================================================================

set -uo pipefail

MODE="${1:---scan}"

# ── Container → destination map ──────────────────────────────────────────────
# Each entry: "<container_name>:<container_src_path>:<local_dest_dir>"
SOURCES=(
  "prompt-enhance:/app:./_canonical/prompt-enhance"
  "context-engine-container-dev:/app:./_canonical/context-engine"
)

DEST_ROOT="./_canonical"
TARBALL="canonical-source-$(date '+%Y%m%d_%H%M%S').tar.gz"

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'; BOLD=$'\033[1m'; NC=$'\033[0m'

echo "${BOLD}T-031 — fetch canonical source from running containers (${MODE})${NC}"
echo "============================================================"

# ── Preflight: docker available ───────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  echo "${RED}docker not found on PATH. Run this on the server host.${NC}" >&2
  exit 1
fi

echo "${BOLD}Running containers on this host:${NC}"
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' || {
  echo "${RED}Could not run 'docker ps' (is the docker daemon up / do you have perms?).${NC}" >&2
  exit 1
}
echo ""

# ── Determine which target containers are present on THIS host ────────────────
declare -a PRESENT=()
declare -a ABSENT=()
for entry in "${SOURCES[@]}"; do
  name="${entry%%:*}"
  if docker ps --format '{{.Names}}' | grep -qx "${name}"; then
    PRESENT+=("$entry")
  else
    ABSENT+=("$name")
  fi
done

if [ "${#PRESENT[@]}" -eq 0 ]; then
  echo "${YELLOW}None of the target containers are running on this host.${NC}"
  echo "Expected one of: $(printf '%s ' "${SOURCES[@]%%:*}")"
  echo "Run the matching section on the other server (see header)."
  exit 0
fi

echo "${BOLD}Target containers present on this host:${NC}"
for entry in "${PRESENT[@]}"; do
  name="${entry%%:*}"; rest="${entry#*:}"; src="${rest%%:*}"; dest="${rest#*:}"
  echo "  ${GREEN}${name}${NC}  ${src}  ->  ${dest}"
done
if [ "${#ABSENT[@]}" -gt 0 ]; then
  echo "${YELLOW}Not on this host (fetch on the other server):${NC} ${ABSENT[*]}"
fi
echo ""

# ── SCAN mode — read-only, just report ────────────────────────────────────────
if [ "$MODE" != "--pull" ]; then
  echo "${YELLOW}SCAN mode — nothing copied. The above is what --pull WOULD extract.${NC}"
  echo "Re-run with --pull to perform the read-only 'docker cp' extraction:"
  echo "  ./T-031-fetch-canonical-source.sh --pull"
  exit 0
fi

# ── PULL mode — docker cp OUT of each present container (read-only on container)
echo "${BOLD}Extracting source via 'docker cp' (read-only on the container)…${NC}"
mkdir -p "${DEST_ROOT}"

for entry in "${PRESENT[@]}"; do
  name="${entry%%:*}"; rest="${entry#*:}"; src="${rest%%:*}"; dest="${rest#*:}"
  echo "  copying ${name}:${src} -> ${dest}"
  rm -rf "${dest}"
  mkdir -p "$(dirname "${dest}")"
  if docker cp "${name}:${src}" "${dest}"; then
    echo "    ${GREEN}done${NC}"
  else
    echo "    ${RED}FAILED${NC} to copy from ${name}" >&2
  fi
done
echo ""

# ── Package for transfer ──────────────────────────────────────────────────────
echo "${BOLD}Packaging extracted source into a tarball:${NC}"
if tar -czf "${TARBALL}" -C "$(dirname "${DEST_ROOT}")" "$(basename "${DEST_ROOT}")"; then
  echo "  ${GREEN}created${NC} ${TARBALL}"
else
  echo "  ${RED}tar failed${NC} — copy the ${DEST_ROOT}/ directory manually." >&2
fi
echo ""

# ── scp-back instructions ─────────────────────────────────────────────────────
echo "${BOLD}Next — copy the tarball to your reconciliation workstation:${NC}"
echo "  # from your laptop, pull it down:"
echo "  scp ec2-user@<this-server-ip>:\$(pwd)/${TARBALL} ./"
echo "  tar -xzf ${TARBALL}     # extracts ./_canonical/"
echo ""
echo "${BOLD}Then reconcile (see python-ai-unified/RECONCILE.md):${NC}"
echo "  diff -ru ./_canonical/prompt-enhance/app/src \\"
echo "           ./python-ai-unified/routers/ai"
echo "  diff -ru ./_canonical/context-engine/app/src \\"
echo "           ./python-ai-unified/routers"
echo "  # resolve each discrepancy as a RECONCILE.md checklist item."
echo ""
echo "${GREEN}Done. No containers were stopped, restarted, or modified.${NC}"
