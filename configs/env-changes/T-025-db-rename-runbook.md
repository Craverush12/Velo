# T-025 — Database Rename Runbook
## `localpgvelocity` → `thinkvelocity_prod`

**Estimated downtime:** 30–45 seconds  
**When to run:** After all services are deployed to the consolidated server and confirmed healthy  
**Who runs it:** Engineer with SSH access to the production server  
**Rollback time:** < 2 minutes (rename back)

---

## Pre-flight Checklist (before maintenance window)

Run these checks at least 30 minutes before the rename:

```bash
# 1. Confirm current DB name
docker exec tv-postgres psql -U postgres -tAc "SELECT datname FROM pg_database WHERE datname LIKE '%velocity%';"
# Expected: localpgvelocity

# 2. Count active connections (plan for this number to drop cleanly)
docker exec tv-postgres psql -U postgres -tAc \
  "SELECT count(*) FROM pg_stat_activity WHERE datname = 'localpgvelocity' AND state != 'idle';"

# 3. Verify all services are healthy before starting
curl -sf http://127.0.0.1:3005/health && echo "consumer-backend OK"
curl -sf http://127.0.0.1:8005/health && echo "python-ai OK"
curl -sf http://127.0.0.1:3000/backend/health && echo "enterprise-backend OK"
curl -sf http://127.0.0.1:8000/health && echo "extension-api OK"

# 4. Confirm nginx config is valid
sudo nginx -t

# 5. Note current connection counts in all service health endpoints (for post-rename comparison)
```

---

## Step 1 — Maintenance Mode (put nginx in 503)

**Duration:** Holds for ~60s while rename runs. Remove immediately after services are healthy.

```bash
# Create the maintenance page (do this in advance, before the window)
sudo tee /var/www/maintenance.html > /dev/null <<'EOF'
<!DOCTYPE html>
<html>
<head><title>Maintenance</title></head>
<body>
  <h1>Scheduled maintenance in progress</h1>
  <p>ThinkVelocity will be back in under 60 seconds.</p>
</body>
</html>
EOF

# Add maintenance block to nginx (activate during the window)
# Edit the appropriate nginx vhost file(s):
#   /etc/nginx/sites-enabled/thinkvelocity.conf
#   /etc/nginx/sites-enabled/api.thinkvelocity.conf
#   /etc/nginx/sites-enabled/enterprise.thinkvelocity.conf
#
# Add this block INSIDE the server{} block, BEFORE the location / block:

# location / {
#     return 503;
# }
# error_page 503 /maintenance.html;
# location = /maintenance.html {
#     root /var/www;
#     internal;
# }

# Apply:
sudo nginx -t && sudo nginx -s reload

# Verify users see 503:
curl -o /dev/null -w "%{http_code}" https://thinkvelocity.in/
# Expected: 503
```

---

## Step 2 — Terminate All Connections to the Old Database

The `ALTER DATABASE ... RENAME` command requires zero active connections.

```bash
# Terminate all non-superuser connections to localpgvelocity
docker exec tv-postgres psql -U postgres -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE datname = 'localpgvelocity'
    AND pid <> pg_backend_pid()
    AND usename <> 'postgres';
"

# Confirm zero connections remain (allow 2s for stragglers)
sleep 2
docker exec tv-postgres psql -U postgres -tAc \
  "SELECT count(*) FROM pg_stat_activity WHERE datname = 'localpgvelocity' AND state != 'idle';"
# Expected: 0
```

---

## Step 3 — Rename the Database

```bash
# Perform the rename (requires zero active connections — instant, no data moved)
docker exec tv-postgres psql -U postgres -c \
  "ALTER DATABASE localpgvelocity RENAME TO thinkvelocity_prod;"

# Confirm rename succeeded
docker exec tv-postgres psql -U postgres -tAc \
  "SELECT datname FROM pg_database WHERE datname = 'thinkvelocity_prod';"
# Expected: thinkvelocity_prod
```

> **Why it's fast:** `ALTER DATABASE ... RENAME` only updates the system catalog entry.  
> No data is moved. No vacuuming. Lock is released immediately after commit.  
> Typical wall-clock time: < 100ms.

---

## Step 4 — Update Connection Strings

Run the T-017 script (adapted for the new DB name), or apply these sed commands directly:

```bash
COMPOSE_DIR="/var/www/thinkvelocity"
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.yml"

# Backup first
cp "${COMPOSE_FILE}" "${COMPOSE_FILE}.bak.T025.$(date +%Y%m%d_%H%M%S)"

# Replace old DB name in all DATABASE_URL lines
sed -i 's|/localpgvelocity|/thinkvelocity_prod|g' "${COMPOSE_FILE}"
sed -i 's|/localpgvelocity?|/thinkvelocity_prod?|g' "${COMPOSE_FILE}"

# Also update the .env file if DATABASE_URL is set there instead of compose
DOT_ENV="${COMPOSE_DIR}/.env"
sed -i 's|/localpgvelocity|/thinkvelocity_prod|g' "${DOT_ENV}"

# Verify the changes
grep "DATABASE_URL" "${COMPOSE_FILE}"
```

---

## Step 5 — Restart All Services

```bash
cd /var/www/thinkvelocity

# Restart all app services (postgres itself keeps running — no container restart needed)
docker compose up -d --no-deps consumer-backend python-ai enterprise-backend extension-api

# Wait for startup
sleep 20
```

---

## Step 6 — Health Checks and Remove Maintenance Mode

```bash
# Check health endpoints
for URL in \
  "http://127.0.0.1:3005/health" \
  "http://127.0.0.1:8005/health" \
  "http://127.0.0.1:3000/backend/health" \
  "http://127.0.0.1:8000/health"; do
  HTTP="$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "${URL}")"
  echo "${URL}: HTTP ${HTTP}"
done

# All should return 200. If any return non-2xx, do NOT remove maintenance mode yet.
# Check: docker compose logs <service>

# Verify DB name in live service (should show thinkvelocity_prod)
docker exec tv-postgres psql -U postgres -tAc \
  "SELECT datname FROM pg_database WHERE datname = 'thinkvelocity_prod';"

# Verify a service can actually query (not just connect)
docker exec tv-consumer-backend \
  sh -c 'psql "$DATABASE_URL" -tAc "SELECT current_database();"' 2>/dev/null \
  || echo "(psql not in container — check app logs instead)"

# All healthy → remove maintenance mode from nginx
# Revert the maintenance block added in Step 1 (delete or comment it out)
sudo nginx -t && sudo nginx -s reload

# Confirm public access restored:
curl -o /dev/null -w "%{http_code}" https://thinkvelocity.in/
# Expected: 200 or 301 (redirect to www)
```

---

## Estimated Timeline

| Step | Action | Duration |
|------|--------|----------|
| Pre-flight | Health checks, connection count | 5 min (before window) |
| 1 | Enable maintenance mode (nginx 503) | 30 sec |
| 2 | Terminate connections | 5 sec |
| 3 | ALTER DATABASE RENAME | < 1 sec |
| 4 | Update connection strings | 15 sec |
| 5 | Restart services | 20 sec |
| 6 | Health checks | 15 sec |
| 6 | Remove maintenance mode | 5 sec |
| **Total user-facing downtime** | **(Steps 1–6)** | **~90 sec** |

> Note: Downtime starts at Step 1 (maintenance mode on) and ends when nginx reloads in Step 6.
> The rename itself (Step 3) is < 1 second. Most of the window is startup time.

---

## Rollback

If anything goes wrong after Step 3 but before Step 6:

```bash
# Rename back (same command, reversed)
docker exec tv-postgres psql -U postgres -c \
  "ALTER DATABASE thinkvelocity_prod RENAME TO localpgvelocity;"

# Revert compose file
cp "${COMPOSE_FILE}.bak.T025.*" "${COMPOSE_FILE}"
cp "${DOT_ENV}.bak.T025.*"     "${DOT_ENV}"  # if applicable

# Restart services
cd /var/www/thinkvelocity
docker compose up -d --no-deps consumer-backend python-ai enterprise-backend extension-api

# Remove maintenance mode
sudo nginx -t && sudo nginx -s reload
```

Rollback time: < 2 minutes.

---

## Post-Rename Cleanup (next day)

```bash
# Confirm old DB name is fully gone
docker exec tv-postgres psql -U postgres -tAc \
  "SELECT datname FROM pg_database ORDER BY datname;"
# localpgvelocity should NOT appear

# Remove backup files (after confirming all is stable for 24h)
rm "${COMPOSE_FILE}".bak.T025.*
rm "${DOT_ENV}".bak.T025.* 2>/dev/null || true
```
