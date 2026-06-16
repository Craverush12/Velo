# Observability Stack — Deployment Instructions

**Target:** Tasks T-036 (Loki/Grafana/Prometheus stack) and T-037 (Alertmanager alerts)

**Observability server:** Server 2 — 13.203.181.76 (AlmaLinux, Apache → will add Nginx for metrics subdomain)

> **WireGuard prerequisite:** Steps that scrape Server 1 (10.100.0.2) and Server 3 (10.100.0.3)
> require the WireGuard VPN mesh to be active. Those jobs will show as DOWN in Prometheus until
> WireGuard is configured. Set up WireGuard first or deploy the stack and add remote targets later.

---

## Step 0 — Prerequisites on Server 2

```bash
# Install Docker + Docker Compose (if not already present — AlmaLinux)
sudo dnf install -y docker docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER

# Install Nginx (for the metrics subdomain proxy)
sudo dnf install -y nginx
sudo systemctl enable --now nginx

# Install certbot
sudo dnf install -y certbot python3-certbot-nginx
```

---

## Step 1 — Install node_exporter on ALL 3 servers

Run on each server (Server 1 = Ubuntu, Server 2 = AlmaLinux, Server 3 = Ubuntu).

```bash
NODE_EXPORTER_VERSION="1.7.0"
cd /tmp
wget https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/node_exporter-${NODE_EXPORTER_VERSION}.linux-amd64.tar.gz
tar xvf node_exporter-*.tar.gz
sudo cp node_exporter-*/node_exporter /usr/local/bin/
sudo useradd -rs /bin/false node_exporter 2>/dev/null || true
```

Create the systemd service. Replace `<WG_IP>` with:
- Server 1: `10.100.0.2`
- Server 2: `10.100.0.1`
- Server 3: `10.100.0.3`

```bash
# Get the WireGuard interface name (typically wg0)
WG_IFACE=$(ip link show type wireguard 2>/dev/null | awk -F': ' '{print $2}' | head -1)
WG_IP=$(ip addr show ${WG_IFACE} 2>/dev/null | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)

sudo tee /etc/systemd/system/node_exporter.service > /dev/null <<EOF
[Unit]
Description=Prometheus Node Exporter
After=network.target

[Service]
User=node_exporter
Group=node_exporter
Type=simple
ExecStart=/usr/local/bin/node_exporter \
    --web.listen-address=127.0.0.1:9100 \
    --web.listen-address=${WG_IP}:9100 \
    --collector.systemd \
    --collector.processes
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now node_exporter

# Verify
curl -s http://127.0.0.1:9100/metrics | head -5
```

**Firewall (WireGuard interface only — NOT public):**
```bash
# On Server 1 and Server 3 (Ubuntu, ufw)
sudo ufw allow in on wg0 to any port 9100
sudo ufw allow in on wg0 to any port 9200

# On Server 2 (AlmaLinux, firewalld)
sudo firewall-cmd --permanent --zone=internal --add-port=9100/tcp
sudo firewall-cmd --permanent --zone=internal --add-port=9200/tcp
sudo firewall-cmd --reload
```

---

## Step 2 — Install cAdvisor on ALL 3 servers (port 9200)

```bash
sudo docker run -d \
  --name cadvisor \
  --restart unless-stopped \
  --publish 127.0.0.1:9200:8080 \
  --volume /:/rootfs:ro \
  --volume /var/run:/var/run:ro \
  --volume /sys:/sys:ro \
  --volume /var/lib/docker/:/var/lib/docker:ro \
  --volume /dev/disk/:/dev/disk:ro \
  --privileged \
  --device /dev/kmsg \
  gcr.io/cadvisor/cadvisor:v0.47.2

# Verify
curl -s http://localhost:9200/metrics | head -5
```

> On Server 1 and Server 3, also bind cAdvisor to the WireGuard IP:
> Replace `--publish 127.0.0.1:9200:8080` with
> `--publish 127.0.0.1:9200:8080 --publish <WG_IP>:9200:8080`

---

## Step 3 — Install Promtail on all 3 servers

```bash
PROMTAIL_VERSION="2.9.0"
cd /tmp
wget https://github.com/grafana/loki/releases/download/v${PROMTAIL_VERSION}/promtail-linux-amd64.zip
unzip promtail-linux-amd64.zip
sudo cp promtail-linux-amd64 /usr/local/bin/promtail
sudo chmod +x /usr/local/bin/promtail
sudo useradd -rs /bin/false promtail 2>/dev/null || true

# Add promtail user to docker group (to read container logs)
sudo usermod -aG docker promtail
# Add promtail user to systemd-journal group (to read journal)
sudo usermod -aG systemd-journal promtail
sudo usermod -aG adm promtail  # Ubuntu — for /var/log access
```

Copy the server-specific config (use SCP from your local machine or paste inline):
- Server 1: `configs/observability/promtail-server1.yml` → `/etc/promtail/config.yml`
- Server 2: `configs/observability/promtail-server2.yml` → `/etc/promtail/config.yml`
- Server 3: `configs/observability/promtail-server3.yml` → `/etc/promtail/config.yml`

```bash
sudo mkdir -p /etc/promtail

sudo tee /etc/systemd/system/promtail.service > /dev/null <<'EOF'
[Unit]
Description=Promtail — Loki log shipper
After=network.target

[Service]
User=promtail
Group=promtail
Type=simple
ExecStart=/usr/local/bin/promtail -config.file=/etc/promtail/config.yml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now promtail

# Check it is sending logs
sudo journalctl -u promtail -f --no-pager
```

---

## Step 4 — Deploy the observability stack on Server 2

```bash
# Clone or copy the configs directory to Server 2
# (adjust path to wherever you put the configs)
cd /opt/observability
cp /path/to/configs/observability/* .

# Create the .env file with secrets
cat > .env <<'ENVEOF'
GF_SECURITY_ADMIN_PASSWORD=REPLACE_WITH_STRONG_PASSWORD
SLACK_WEBHOOK_URL=REPLACE_WITH_SLACK_WEBHOOK_URL
ENVEOF
chmod 600 .env

# Start the stack
docker compose up -d

# Verify all containers are healthy
docker compose ps
docker compose logs --tail=50
```

Services started:
| Container    | Port (localhost) | Purpose                    |
|--------------|------------------|----------------------------|
| loki         | 3100             | Log aggregation             |
| grafana      | 3200             | Dashboards (Nginx proxies) |
| prometheus   | 9090             | Metrics scraping            |
| alertmanager | 9093             | Alert routing               |

---

## Step 5 — WireGuard: open ports for Prometheus scraping

Prometheus on Server 2 scrapes node_exporter (9100) and cAdvisor (9200) on Servers 1 and 3
via WireGuard. Those machines must accept inbound connections on the WireGuard interface.

```bash
# On Server 1 and Server 3 (Ubuntu + ufw):
sudo ufw allow in on wg0 to any port 9100 proto tcp comment "Prometheus node_exporter"
sudo ufw allow in on wg0 to any port 9200 proto tcp comment "Prometheus cAdvisor"
sudo ufw reload
```

Also ensure Promtail on Servers 1 & 3 can reach Loki (port 3100) on Server 2:
```bash
# On Server 2 (AlmaLinux + firewalld), allow inbound 3100 from WireGuard peers:
sudo firewall-cmd --permanent --zone=internal --add-port=3100/tcp
sudo firewall-cmd --reload

# OR just bind loki to the WireGuard IP in docker-compose.yml:
# "10.100.0.1:3100:3100" instead of "127.0.0.1:3100:3100"
```

---

## Step 6 — Set up Grafana domain (DNS + Nginx)

1. **DNS:** Add an A record in your DNS provider:
   - Name: `metrics.thinkvelocity.in`
   - Type: `A`
   - Value: `13.203.181.76`
   - TTL: 300

2. **Place the Nginx vhost config:**
   ```bash
   sudo cp nginx-metrics-vhost.conf /etc/nginx/conf.d/metrics.thinkvelocity.in.conf
   sudo nginx -t
   sudo systemctl reload nginx
   ```

3. **Set up access control** (edit the vhost and uncomment your preferred option):
   - Option A: `sudo htpasswd -c /etc/nginx/.htpasswd grafana-admin`
   - Option B: Uncomment IP allowlist lines with your team's public IPs

---

## Step 7 — Obtain SSL certificate

```bash
sudo certbot --nginx -d metrics.thinkvelocity.in
# Follow prompts; Certbot will auto-modify the Nginx vhost with SSL directives
sudo nginx -t && sudo systemctl reload nginx
```

Auto-renewal is handled by the certbot timer installed with the package:
```bash
sudo systemctl status certbot.timer
```

---

## Step 8 — Set the Slack webhook URL

The webhook is in AWS Secrets Manager. Retrieve it and inject it into the alertmanager config:

```bash
# Option A — env var in .env file (already supported by docker-compose.yml)
# The alertmanager.yml uses a literal placeholder. Inject at deploy time:
SLACK_WEBHOOK=$(aws secretsmanager get-secret-value \
    --secret-id SLACK_WEBHOOK_URL \
    --query SecretString \
    --output text \
    --region ap-south-1)

sed -i "s|REPLACE_WITH_SLACK_WEBHOOK_URL|${SLACK_WEBHOOK}|g" alertmanager.yml

# Restart alertmanager to pick up the change
docker compose restart alertmanager

# Verify the config was loaded
curl -s http://localhost:9093/api/v1/status | python3 -m json.tool
```

---

## Step 9 — Import community Grafana dashboards

Open `https://metrics.thinkvelocity.in` and log in with the admin password.

1. **Node Exporter Full** — Dashboard ID `1860`
   - Grafana → Dashboards → Import → Enter ID `1860` → Load
   - Set datasource: `Prometheus`

2. **Docker / cAdvisor** — Dashboard ID `14282`
   - Grafana → Dashboards → Import → Enter ID `14282` → Load
   - Set datasource: `Prometheus`

3. **Loki logs** — Dashboard ID `13639` (Loki Dashboard Quick Search)
   - Set datasource: `Loki`

---

## Step 10 — Verify alerts are working

Temporarily lower a threshold to trigger a test alert, confirm it appears in Slack, then revert.

```bash
# Example: lower disk warning to 99% (will fire immediately on any server)
# Edit alerts.yml: change  < 20  to  < 99  for DiskWarning
# Then reload Prometheus config without restart:
curl -X POST http://localhost:9090/-/reload

# Watch Prometheus alerts page
open https://metrics.thinkvelocity.in  # → Alerting tab (or http://localhost:9090/alerts)

# Wait ~1 min for DiskWarning to fire → should appear in #thinkvelocity-alerts
# Revert the threshold and reload again when confirmed
```

Also verify Loki is receiving logs:
```bash
curl -s http://localhost:3100/loki/api/v1/labels | python3 -m json.tool
# Should show labels like: job, server, container_id, etc.
```

---

## Maintenance Notes

- **Prometheus data retention:** 31 days (set in docker-compose.yml `--storage.tsdb.retention.time=31d`)
- **Loki log retention:** 31 days (set in loki-config.yml `retention_period: 744h`)
- **Grafana admin password:** stored in `.env` on Server 2 — back up this file
- **SSL renewal:** Certbot timer handles this automatically; verify with `certbot renew --dry-run`
- **Stack updates:** `docker compose pull && docker compose up -d`

---

## WireGuard-dependent components summary

The following will NOT work until WireGuard is active:

| Component                      | Depends on WG?    | Notes                                   |
|-------------------------------|-------------------|-----------------------------------------|
| `node-server1` scrape job      | Yes (10.100.0.2)  | Server 1 node_exporter                  |
| `node-server3` scrape job      | Yes (10.100.0.3)  | Server 3 node_exporter                  |
| `cadvisor-server1` scrape job  | Yes (10.100.0.2)  | Server 1 cAdvisor                       |
| `cadvisor-server3` scrape job  | Yes (10.100.0.3)  | Server 3 cAdvisor                       |
| `app-health` NestJS endpoint   | Yes (10.100.0.3)  | enterprise-backend health check         |
| `app-health` FastAPI endpoint  | Yes (10.100.0.2)  | FastAPI extension API health check      |
| Promtail → Loki (Server 1)    | Yes               | Logs from Server 1 won't appear in Loki |
| Promtail → Loki (Server 3)    | Yes               | Logs from Server 3 won't appear in Loki |

Server 2 (local) components work immediately without WireGuard:
- Loki, Grafana, Prometheus, Alertmanager
- node_exporter, cAdvisor, postgres_exporter on Server 2
- Container logs from Server 2
