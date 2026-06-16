# Docker Cleanup Script — Deploy Instructions

## Overview

`docker-cleanup.sh` runs weekly on each server to reclaim disk space by removing:
- Stopped containers older than 24 hours
- Unused Docker images older than 7 days
- Dangling (unattached) volumes
- Stale build cache older than 7 days

Logs are written to `/var/log/docker-cleanup.log`.

---

## Installation (repeat on all 3 servers)

```bash
# 1. Create maintenance directory
sudo mkdir -p /opt/maintenance

# 2. Copy the script
sudo cp docker-cleanup.sh /opt/maintenance/docker-cleanup.sh

# 3. Make it executable
sudo chmod +x /opt/maintenance/docker-cleanup.sh

# 4. Verify
ls -la /opt/maintenance/docker-cleanup.sh
```

---

## Cron Setup

Add the weekly cron job (runs every Sunday at 4:00 AM server time):

```bash
sudo crontab -e
```

Add this line:

```
0 4 * * 0 DOCKER_CLEANUP_SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK/URL /opt/maintenance/docker-cleanup.sh
```

Or, to use a separate environment file (recommended):

```bash
# Create /etc/docker-cleanup.env
echo 'DOCKER_CLEANUP_SLACK_WEBHOOK=https://hooks.slack.com/services/YOUR/WEBHOOK/URL' | sudo tee /etc/docker-cleanup.env

# Cron entry:
0 4 * * 0 source /etc/docker-cleanup.env && /opt/maintenance/docker-cleanup.sh
```

Verify cron was saved:
```bash
sudo crontab -l
```

---

## Test Run

Run manually to verify it works before relying on the cron:

```bash
sudo /opt/maintenance/docker-cleanup.sh
```

Then check the log:
```bash
sudo tail -30 /var/log/docker-cleanup.log
```

---

## Server SSH Commands

```bash
# Server 1 — FastAPI Extension API
ssh -i "C:\Users\Arjun\Downloads\velo-python.pem" ubuntu@13.234.212.59

# Server 2 — Node.js + Python AI (main server)
ssh -i "C:\Users\Arjun\Downloads\velo-large-main-server-key.pem" ec2-user@13.203.181.76

# Server 3 — NestJS Enterprise + React + FastAPI ML
ssh -i "C:\Users\Arjun\Downloads\fr-img-tes-ap-south.pem" ubuntu@13.233.86.137
```

---

## Emergency Cleanup (Server 2 — Disk Critical)

If disk is > 90% full and you cannot wait for the cron:

```bash
# Force remove ALL unused images immediately (~28GB freed on Server 2)
sudo docker image prune -a -f

# Also clear old logs if needed
sudo truncate -s 0 /var/log/httpd/access_log
sudo truncate -s 0 /var/log/httpd/error_log
```
