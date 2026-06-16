# ThinkVelocity — Observability Stack Deployment

**Target:** Single production server (8 GB AWS Lightsail, Ubuntu, ap-south-1)
**Stack:** Prometheus · Loki · Grafana · Alertmanager · node_exporter · cAdvisor · Promtail

SOC2 mapping:
- Prometheus + Alertmanager → CC7.2 (availability monitoring)
- Loki logs (90-day retention) → PI1.1 (processing integrity / audit trail) + A1.2

---

## Prerequisites

SSH into the production server and run:

```bash
# Docker Engine (Ubuntu)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker

# Docker Compose v2 plugin (bundled with Docker CE >= 23; verify)
docker compose version

# Nginx + Certbot
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx

# Create deployment directory
sudo mkdir -p /opt/observability
sudo chown $USER:$USER /opt/observability
```

---

## Step 1 — Copy configuration files

From your local machine:

```bash
# Replace user@PROD_IP with the actual server address
scp -r configs/observability/* user@PROD_IP:/opt/observability/
```

Or clone the repo on the server:

```bash
git clone <repo-url> /tmp/thinkvelocity
cp -r /tmp/thinkvelocity/configs/observability/* /opt/observability/
```

After copying, the layout on the server should be:

```
/opt/observability/
├── docker-compose.yml
├── grafana-datasources.yml
├── prometheus/
│   ├── prometheus.yml
│   └── alert-rules.yml
├── alertmanager/
│   └── alertmanager.yml
├── loki/
│   └── loki.yml
├── promtail/
│   └── promtail.yml
└── nginx/
    └── grafana.conf
```

---

## Step 2 — Set secrets

Create the `.env` file that docker-compose reads for Grafana's admin password:

```bash
cd /opt/observability

cat > .env <<'EOF'
# Grafana admin password — change on first login
GF_SECURITY_ADMIN_PASSWORD=REPLACE_WITH_STRONG_PASSWORD
EOF

chmod 600 .env
```

Inject the Slack webhook URL into the Alertmanager config (the config uses
the literal string `REPLACE_WITH_SM_KEY_slack_webhook` as a placeholder):

```bash
# Retrieve from AWS Secrets Manager
SLACK_WEBHOOK=$(aws secretsmanager get-secret-value \
    --secret-id thinkvelocity/slack_webhook \
    --query SecretString \
    --output text \
    --region ap-south-1)

# Inject into alertmanager config
sed -i "s|REPLACE_WITH_SM_KEY_slack_webhook|${SLACK_WEBHOOK}|g" \
    /opt/observability/alertmanager/alertmanager.yml

# Verify (should show the webhook URL, not the placeholder)
grep api_url /opt/observability/alertmanager/alertmanager.yml | head -1
```

---

## Step 3 — Start the observability stack

```bash
cd /opt/observability

docker compose up -d

# Watch startup logs
docker compose logs -f --tail=50
```

Verify all containers are healthy (takes ~30 seconds for health checks to pass):

```bash
docker compose ps
```

Expected output — all services should show `healthy`:

```
NAME            IMAGE                           STATUS
alertmanager    prom/alertmanager:v0.27.0       Up (healthy)
cadvisor        gcr.io/cadvisor/cadvisor:...    Up (healthy)
grafana         grafana/grafana:10.4.2          Up (healthy)
loki            grafana/loki:2.9.8              Up (healthy)
node_exporter   prom/node-exporter:v1.7.0       Up (healthy)
prometheus      prom/prometheus:v2.50.1         Up (healthy)
promtail        grafana/promtail:2.9.8          Up (healthy)
```

**Exact command to start the stack:**

```bash
cd /opt/observability && docker compose up -d
```

---

## Step 4 — Expose Grafana via Nginx

### 4a. DNS record

In your DNS provider, add:

| Name              | Type | Value           | TTL |
|-------------------|------|-----------------|-----|
| grafana           | A    | `<PROD_SERVER_IP>` | 300 |

### 4b. Set the IP allowlist

Edit the Nginx config and replace `REPLACE_WITH_OFFICE_IP` with your static
egress IP (find it with `curl -s https://ifconfig.me`):

```bash
sudo sed -i 's/REPLACE_WITH_OFFICE_IP/<your-static-ip>/g' \
    /opt/observability/nginx/grafana.conf
```

### 4c. Deploy the Nginx vhost

```bash
sudo cp /opt/observability/nginx/grafana.conf \
    /etc/nginx/conf.d/grafana.thinkvelocity.in.conf

sudo nginx -t && sudo systemctl reload nginx
```

### 4d. Obtain an SSL certificate

```bash
sudo certbot --nginx -d grafana.thinkvelocity.in
# Follow prompts; Certbot patches the vhost with SSL directives automatically.
sudo nginx -t && sudo systemctl reload nginx
```

Auto-renewal runs via systemd timer — confirm it is active:

```bash
sudo systemctl status certbot.timer
```

---

## Step 5 — Access Grafana

URL: **https://grafana.thinkvelocity.in**

Default credentials:
- **Username:** `admin`
- **Password:** the value you set for `GF_SECURITY_ADMIN_PASSWORD` in `.env`

**Change the password on first login** (Grafana will prompt you automatically).

---

## Step 6 — Verify datasources

Grafana is pre-provisioned with Prometheus and Loki datasources via
`grafana-datasources.yml`. To confirm they are connected:

1. Log in to Grafana.
2. Go to **Connections → Data Sources**.
3. Click **Prometheus** → **Save & Test** → should return "Data source is working".
4. Click **Loki** → **Save & Test** → should return "Data source connected and labels found".

If Loki shows "no labels found" it means Promtail has not shipped any logs yet.
Check Promtail: `docker compose logs promtail --tail 50`

---

## Step 7 — Import dashboards

In Grafana: **Dashboards → New → Import**

| Dashboard                        | Grafana ID | Datasource |
|----------------------------------|------------|------------|
| Node Exporter Full               | `1860`     | Prometheus |
| Docker / cAdvisor                | `14282`    | Prometheus |
| Loki Log Search                  | `13639`    | Loki       |
| Prometheus 2 Stats               | `3662`     | Prometheus |

For each:
1. Enter the ID → **Load**
2. Select the matching datasource
3. **Import**

---

## Step 8 — Verify alerts reach Slack

Temporarily lower a threshold to force a test alert:

```bash
cd /opt/observability

# Example: trigger DiskUsageHigh by setting threshold to 1%
sed -i 's/> 80/> 1/' prometheus/alert-rules.yml

# Hot-reload Prometheus (no restart needed)
curl -s -X POST http://localhost:9090/-/reload

# Wait ~60 seconds, then check the Prometheus alerts page
curl -s http://localhost:9090/api/v1/alerts | python3 -m json.tool | grep state

# Alert should appear in #thinkvelocity-alerts within 2 minutes.
# Revert:
sed -i 's/> 1/> 80/' prometheus/alert-rules.yml
curl -s -X POST http://localhost:9090/-/reload
```

---

## Maintenance

| Task                         | Command                                                       |
|------------------------------|---------------------------------------------------------------|
| Restart the stack            | `cd /opt/observability && docker compose restart`             |
| View all logs                | `docker compose logs -f`                                      |
| Update images                | `docker compose pull && docker compose up -d`                 |
| Reload Prometheus config     | `curl -X POST http://localhost:9090/-/reload`                 |
| Reload Alertmanager config   | `curl -X POST http://localhost:9093/-/reload`                 |
| Check Loki labels            | `curl http://localhost:3100/loki/api/v1/labels`               |
| Grafana admin password       | Edit `.env` → `GF_SECURITY_ADMIN_PASSWORD`, restart grafana   |
| SSL renewal test             | `sudo certbot renew --dry-run`                                |

### Data retention

| Component  | Retention | Config location                              |
|------------|-----------|----------------------------------------------|
| Prometheus | 30 days   | `docker-compose.yml` (--storage.tsdb.retention.time=30d) |
| Loki       | 90 days   | `loki/loki.yml` (retention_period: 2160h)    |

### Storage usage estimates (8 GB server)

| Data              | Estimate     |
|-------------------|--------------|
| Prometheus (30d)  | ~3–5 GB      |
| Loki (90d)        | ~5–10 GB     |
| Grafana           | ~50 MB       |
| Alertmanager      | ~10 MB       |

Monitor disk usage with:

```bash
df -h /
docker system df
du -sh /var/lib/docker/volumes/*
```
