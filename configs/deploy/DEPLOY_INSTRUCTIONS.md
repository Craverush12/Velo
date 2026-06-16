# Zero-Downtime Deploy Script — Usage Instructions

**Script:** `configs/deploy/deploy.sh`
**Install path (per server):** `/opt/deploy/deploy.sh`

---

## How It Works

1. Pulls the new Docker image from the registry
2. Starts a `_new` container (without binding production ports) using the same
   env vars, volumes, and network as the current container
3. Maps the production `localhost:<port>` health URL to the matching internal
   container port and health-checks the `_new` container directly by Docker
   network IP every 5 seconds for up to 60 seconds
4. If health passes: stops the old container, starts the canonical container
   with the new image on the correct ports
5. If health fails: removes the new container and exits with error —
   **the old container keeps running throughout**

Result: production port is only briefly unavailable during the `docker stop` →
`docker run` swap (typically under 1 second).

---

## Installation

```bash
# Copy to each server that runs containers (Server 2, Server 3):
sudo mkdir -p /opt/deploy
sudo cp deploy.sh /opt/deploy/deploy.sh
sudo chmod +x /opt/deploy/deploy.sh
```

---

## Usage

```bash
/opt/deploy/deploy.sh SERVICE_NAME NEW_IMAGE HEALTH_URL
```

| Argument | Description |
|----------|-------------|
| `SERVICE_NAME` | Docker container name (must match existing running container) |
| `NEW_IMAGE` | Full image reference including tag |
| `HEALTH_URL` | HTTP endpoint that returns 2xx when healthy |

---

## Service Deploy Commands

### Server 2 — Node.js Backend

```bash
/opt/deploy/deploy.sh \
  nodejs-backend \
  thinkvelocity24/thinkvelocity-backend:latest \
  http://localhost:3005/health
```

### Server 2 — Python AI Service

```bash
/opt/deploy/deploy.sh \
  python-ai \
  thinkvelocity24/thinkvelocity-python:latest \
  http://localhost:8005/health
```

### Server 3 — NestJS Enterprise Backend

```bash
/opt/deploy/deploy.sh \
  enterprise-backend \
  enterprise-backend:latest \
  http://localhost:3000/health
```

### Server 1 — FastAPI Extension Service

```bash
/opt/deploy/deploy.sh \
  thinkvelocity-ext \
  thinkvelocity24/thinkvelocity-ext:latest \
  http://localhost:8000/health
```

---

## Slack Notifications (Optional)

Set the `DEPLOY_NOTIFY_SLACK` environment variable to receive a Slack message
on every deploy success or failure:

```bash
export DEPLOY_NOTIFY_SLACK="https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
/opt/deploy/deploy.sh nodejs-backend thinkvelocity24/thinkvelocity-backend:latest http://localhost:3005/health
```

Or add it to a deploy wrapper script:

```bash
#!/usr/bin/env bash
export DEPLOY_NOTIFY_SLACK="https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"
/opt/deploy/deploy.sh "$@"
```

---

## Health Check Safety

The script requires `HEALTH_URL` to use `localhost` or `127.0.0.1` with an
explicit port, such as `http://localhost:3005/health`. Before promotion, it
maps that host port to the current container's exposed internal port and calls
the `_new` container directly. If the mapping cannot be resolved, the deploy
fails closed so it cannot accidentally validate the old container.

## Tuning Health Check Timing

```bash
# Check every 3 seconds, time out after 90 seconds:
HEALTH_CHECK_INTERVAL=3 HEALTH_CHECK_TIMEOUT=90 \
  /opt/deploy/deploy.sh nodejs-backend thinkvelocity24/thinkvelocity-backend:latest http://localhost:3005/health
```

---

## Integrating with GitHub Actions (T-042, T-043)

Add a deploy step to `.github/workflows/deploy.yml`:

```yaml
- name: Deploy Node.js backend (zero-downtime)
  run: |
    ssh -o StrictHostKeyChecking=no ec2-user@13.203.181.76 \
      "DEPLOY_NOTIFY_SLACK=${{ secrets.SLACK_WEBHOOK }} \
       /opt/deploy/deploy.sh nodejs-backend \
         thinkvelocity24/thinkvelocity-backend:${{ github.sha }} \
         http://localhost:3005/health"
```

---

## What Happens if the Deploy Fails

1. The `_new` container is stopped and removed automatically
2. The old container continues running on all production ports
3. The script exits with code 1 (triggers CI failure if used in workflows)
4. A Slack notification is sent (if configured)
5. The log shows the last 50 lines of the new container's output to aid debugging

Example failure log:
```
[2026-05-25 02:31:00] [deploy:nodejs-backend] Step 4/6: Health-checking new container...
[2026-05-25 02:32:00] [deploy:nodejs-backend] Health check: HTTP 000 (60s elapsed)
[2026-05-25 02:32:00] [deploy:nodejs-backend] ERROR: Health check FAILED after 60s.
[2026-05-25 02:32:00] [deploy:nodejs-backend] ERROR: New container logs:
... (last 50 lines of container stderr/stdout)
[2026-05-25 02:32:01] [deploy:nodejs-backend] Deployment failed (exit code: 1). Cleaning up...
[2026-05-25 02:32:01] [deploy:nodejs-backend] Stopping failed new container: nodejs-backend_new
[2026-05-25 02:32:01] [deploy:nodejs-backend] New container removed. Old container 'nodejs-backend' continues running.
```

---

## Deploying a Specific Tag (not latest)

```bash
/opt/deploy/deploy.sh \
  nodejs-backend \
  thinkvelocity24/thinkvelocity-backend:v1.4.2 \
  http://localhost:3005/health
```

---

## Rollback

To roll back to a previous image tag:

```bash
/opt/deploy/deploy.sh \
  nodejs-backend \
  thinkvelocity24/thinkvelocity-backend:v1.4.1 \
  http://localhost:3005/health
```

The rollback follows the same zero-downtime process — the old container is
replaced with the rollback image only after the health check passes.
