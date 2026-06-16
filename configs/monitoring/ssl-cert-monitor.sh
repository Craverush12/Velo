#!/usr/bin/env bash
# =============================================================================
# ssl-cert-monitor.sh — Alert on SSL certificate expiry
# SOC2 CC6.6 — HTTPS / cert lifecycle monitoring
#
# Checks every domain's TLS cert; alerts Slack at 30 days and pages at 7 days.
# Designed to run from the consolidated production server (where certbot lives)
# but also works remotely (checks the live TLS handshake, not local files).
#
# Install:
#   sudo cp ssl-cert-monitor.sh /opt/monitoring/ssl-cert-monitor.sh
#   sudo chmod 700 /opt/monitoring/ssl-cert-monitor.sh
#
# Crontab (daily 06:00 IST):
#   0 6 * * * /opt/monitoring/ssl-cert-monitor.sh >> /var/log/ssl-cert-monitor.log 2>&1
#
# SLACK_WEBHOOK_URL is fetched from AWS Secrets Manager, or set as env var.
# =============================================================================

set -uo pipefail

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
DOMAINS=(
  "thinkvelocity.in"
  "www.thinkvelocity.in"
  "api.thinkvelocity.in"
  "enterprise.thinkvelocity.in"
  "grafana.thinkvelocity.in"
)

WARN_DAYS=30   # Slack warning threshold
CRIT_DAYS=7    # Slack critical/page threshold
PORT=443

# ----------------------------------------------------------------------------
# Resolve Slack webhook (SM → env fallback)
# ----------------------------------------------------------------------------
if [ -z "${SLACK_WEBHOOK_URL:-}" ] && command -v aws >/dev/null 2>&1; then
  SLACK_WEBHOOK_URL="$(aws secretsmanager get-secret-value \
    --secret-id thinkvelocity/production/slack-webhook \
    --query SecretString --output text 2>/dev/null \
    | sed -nE 's/.*"SLACK_WEBHOOK_URL"\s*:\s*"([^"]+)".*/\1/p')"
fi

notify_slack() {
  local emoji="$1" msg="$2"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ${emoji} ${msg}"
  [ -z "${SLACK_WEBHOOK_URL:-}" ] && return 0
  curl -sf -X POST -H 'Content-Type: application/json' \
    --data "$(printf '{"text":"%s SSL: %s"}' "$emoji" "$msg")" \
    "$SLACK_WEBHOOK_URL" >/dev/null 2>&1 || true
}

# ----------------------------------------------------------------------------
# Check each domain
# ----------------------------------------------------------------------------
EXIT_CODE=0
NOW_EPOCH=$(date +%s)

for domain in "${DOMAINS[@]}"; do
  # Fetch the cert via TLS handshake (SNI), extract notAfter
  not_after=$(echo | timeout 10 openssl s_client -servername "$domain" \
    -connect "${domain}:${PORT}" 2>/dev/null \
    | openssl x509 -noout -enddate 2>/dev/null \
    | sed -E 's/notAfter=//')

  if [ -z "$not_after" ]; then
    notify_slack ":x:" "Could NOT retrieve certificate for ${domain} (handshake failed or domain not yet live)"
    EXIT_CODE=1
    continue
  fi

  expiry_epoch=$(date -d "$not_after" +%s 2>/dev/null)
  if [ -z "$expiry_epoch" ]; then
    notify_slack ":x:" "Could not parse expiry date for ${domain}: ${not_after}"
    EXIT_CODE=1
    continue
  fi

  days_left=$(( (expiry_epoch - NOW_EPOCH) / 86400 ))

  if [ "$days_left" -lt 0 ]; then
    notify_slack ":rotating_light:" "${domain} certificate has EXPIRED (${days_left} days). Renew immediately: certbot renew --force-renewal"
    EXIT_CODE=2
  elif [ "$days_left" -le "$CRIT_DAYS" ]; then
    notify_slack ":rotating_light:" "${domain} expires in ${days_left} days (CRITICAL). Run: certbot renew"
    EXIT_CODE=2
  elif [ "$days_left" -le "$WARN_DAYS" ]; then
    notify_slack ":warning:" "${domain} expires in ${days_left} days. certbot auto-renew should handle this — verify the timer is active."
    [ "$EXIT_CODE" -lt 1 ] && EXIT_CODE=1
  else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] OK  ${domain} — ${days_left} days remaining"
  fi
done

exit "$EXIT_CODE"
