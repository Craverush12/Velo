#!/bin/bash
# =============================================================================
# WireGuard Key Generation Script — ThinkVelocity Mesh Network
# =============================================================================
# Run this script ONCE locally to generate key pairs for all 3 servers.
# After running, fill in the keys into the corresponding wg0.conf files.
#
# Usage:
#   chmod +x 00_generate_keys.sh
#   ./00_generate_keys.sh
#
# Output files created in the same directory:
#   server1_private, server1_public
#   server2_private, server2_public
#   server3_private, server3_public
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================"
echo " ThinkVelocity WireGuard Key Generation"
echo "============================================================"
echo ""
echo "Generating key pairs for all 3 servers..."
echo ""

# Server 1 — python-velocity-v1 (ubuntu@13.234.212.59, WireGuard IP: 10.100.0.2)
wg genkey | tee "$SCRIPT_DIR/server1_private" | wg pubkey > "$SCRIPT_DIR/server1_public"
chmod 600 "$SCRIPT_DIR/server1_private"
echo "[OK] Server 1 keys generated"
echo "     Private key file : $SCRIPT_DIR/server1_private"
echo "     Public key file  : $SCRIPT_DIR/server1_public"
echo "     Public key value : $(cat "$SCRIPT_DIR/server1_public")"
echo ""

# Server 2 — velocity-prod-large / HUB (ec2-user@13.203.181.76, WireGuard IP: 10.100.0.1)
wg genkey | tee "$SCRIPT_DIR/server2_private" | wg pubkey > "$SCRIPT_DIR/server2_public"
chmod 600 "$SCRIPT_DIR/server2_private"
echo "[OK] Server 2 keys generated"
echo "     Private key file : $SCRIPT_DIR/server2_private"
echo "     Public key file  : $SCRIPT_DIR/server2_public"
echo "     Public key value : $(cat "$SCRIPT_DIR/server2_public")"
echo ""

# Server 3 — enterprise (ubuntu@13.233.86.137, WireGuard IP: 10.100.0.3)
wg genkey | tee "$SCRIPT_DIR/server3_private" | wg pubkey > "$SCRIPT_DIR/server3_public"
chmod 600 "$SCRIPT_DIR/server3_private"
echo "[OK] Server 3 keys generated"
echo "     Private key file : $SCRIPT_DIR/server3_private"
echo "     Public key file  : $SCRIPT_DIR/server3_public"
echo "     Public key value : $(cat "$SCRIPT_DIR/server3_public")"
echo ""

echo "============================================================"
echo " NEXT STEPS"
echo "============================================================"
echo ""
echo "1. Open server1_wg0.conf and replace:"
echo "     REPLACE_WITH_SERVER1_PRIVATE_KEY  -> contents of server1_private"
echo "     REPLACE_WITH_SERVER2_PUBLIC_KEY   -> contents of server2_public"
echo ""
echo "2. Open server2_wg0.conf and replace:"
echo "     REPLACE_WITH_SERVER2_PRIVATE_KEY  -> contents of server2_private"
echo "     REPLACE_WITH_SERVER1_PUBLIC_KEY   -> contents of server1_public"
echo "     REPLACE_WITH_SERVER3_PUBLIC_KEY   -> contents of server3_public"
echo ""
echo "3. Open server3_wg0.conf and replace:"
echo "     REPLACE_WITH_SERVER3_PRIVATE_KEY  -> contents of server3_private"
echo "     REPLACE_WITH_SERVER2_PUBLIC_KEY   -> contents of server2_public"
echo ""
echo "4. Follow DEPLOY_INSTRUCTIONS.md to push configs to each server."
echo ""
echo "IMPORTANT: Keep private key files secret. Do NOT commit them to git."
echo "           Add server*_private to your .gitignore."
echo "============================================================"
