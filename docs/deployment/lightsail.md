# ThinkVelocity Lightsail Runbook

This runbook deploys the current single FastAPI service to an Ubuntu Amazon Lightsail instance.

## Runtime Contract

- App: one FastAPI process, served by Uvicorn.
- Public entrypoint: Nginx on ports 80 and 443.
- Internal app port: `127.0.0.1:8000`.
- Storage: local JSON files only. Use a persistent Docker volume or `/var/lib/thinkvelocity`.
- Required secret: `GROQ_API_KEY`.
- Recommended process count: one worker. CoThinker sessions are in memory.
- CORS: all origins are allowed by design for local dev and direct HTML usage.

AWS references:

- Lightsail firewall rules: https://docs.aws.amazon.com/lightsail/latest/userguide/understanding-firewall-and-port-mappings-in-amazon-lightsail.html
- Lightsail SSH username for Ubuntu instances: https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-ssh-using-terminal.html

## 1. Create The Instance

1. Create a Lightsail instance with Ubuntu.
2. Use at least 1 GB RAM for basic testing. Use 2 GB RAM if you expect CoThinker audio and multiple users.
3. Attach a static IP in Lightsail.
4. In the Lightsail firewall, open:
   - TCP 22 from your IP only
   - TCP 80 from anywhere
   - TCP 443 from anywhere
5. Do not open TCP 8000 publicly when Nginx is used.

SSH into the instance:

```bash
ssh -i /path/to/lightsail-key.pem ubuntu@YOUR_STATIC_IP
```

## 2. Install Server Packages

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx git curl
sudo usermod -aG docker ubuntu
newgrp docker
```

Confirm Docker works:

```bash
docker --version
docker compose version
```

## 3. Deploy With Docker Compose

Clone the repo:

```bash
sudo mkdir -p /opt/thinkvelocity
sudo chown ubuntu:ubuntu /opt/thinkvelocity
git clone YOUR_REPO_URL /opt/thinkvelocity
cd /opt/thinkvelocity
```

Create the environment file:

```bash
cp .env.example .env
nano .env
```

Set these values:

```env
GROQ_API_KEY=your_real_groq_key
APP_ENV=production
PORT=8000
STORAGE_BACKEND=local
STORAGE_PATH=/data
VELOCITY_USER_ID=production
VELOCITY_API_URL=https://your-domain.example
ENABLE_REMOTE_TEST_RUNNER=false
# SERPER_API_KEY=optional_serper_key
```

Start the app:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100
```

Local container checks:

```bash
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/ready
```

`/ready` must return `"status":"ok"` before putting Nginx in front of it.

## 4. Configure Nginx

Create `/etc/nginx/sites-available/thinkvelocity`:

```nginx
server {
    listen 80;
    server_name your-domain.example;

    client_max_body_size 25m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_buffering off;
        proxy_read_timeout 300;
    }
}
```

Enable it:

```bash
sudo ln -s /etc/nginx/sites-available/thinkvelocity /etc/nginx/sites-enabled/thinkvelocity
sudo nginx -t
sudo systemctl reload nginx
```

Before TLS, test:

```bash
curl -fsS http://your-domain.example/health
curl -fsS http://your-domain.example/ready
```

## 5. Add TLS

Point your DNS `A` record to the Lightsail static IP, then run:

```bash
sudo certbot --nginx -d your-domain.example
sudo systemctl reload nginx
```

Test HTTPS:

```bash
curl -fsS https://your-domain.example/health
curl -fsS https://your-domain.example/ready
```

## 6. Smoke-Test The APIs

Basic smoke test, no paid LLM calls:

```bash
cd /opt/thinkvelocity
bash scripts/smoke_api.sh https://your-domain.example
```

Full API smoke test, including Groq LLM calls:

```bash
RUN_LLM_SMOKE=1 bash scripts/smoke_api.sh https://your-domain.example
```

Include server-side unit tests during deployment verification:

```bash
sed -i 's/^ENABLE_REMOTE_TEST_RUNNER=.*/ENABLE_REMOTE_TEST_RUNNER=true/' .env
docker compose up -d
RUN_SERVER_TESTS=1 bash scripts/smoke_api.sh https://your-domain.example
sed -i 's/^ENABLE_REMOTE_TEST_RUNNER=.*/ENABLE_REMOTE_TEST_RUNNER=false/' .env
docker compose up -d
```

Optional CoThinker audio checks:

```bash
RUN_AUDIO_SMOKE=1 bash scripts/smoke_api.sh https://your-domain.example
AUDIO_FILE=/path/to/sample.webm bash scripts/smoke_api.sh https://your-domain.example
```

Optional MCP SSE check:

```bash
RUN_MCP_SMOKE=1 bash scripts/smoke_api.sh https://your-domain.example
```

## 7. Manual API Test Commands

Health:

```bash
curl -fsS https://your-domain.example/health
curl -fsS https://your-domain.example/ready
```

Context:

```bash
curl -fsS https://your-domain.example/context/demo-user
curl -fsS -X PATCH https://your-domain.example/context/demo-user \
  -H 'Content-Type: application/json' \
  --data '{"preferences":{"output_style":"concise"},"personalization_notes":"Prefer direct prompts."}'
curl -fsS https://your-domain.example/history/demo-user
```

Intent update without LLM:

```bash
curl -fsS -X POST https://your-domain.example/intent/update \
  -H 'Content-Type: application/json' \
  --data '{
    "prompt":"Create a launch email for a new AI writing tool.",
    "target_ai":"chatgpt",
    "prompt_mode":"normal",
    "confirmation":{
      "intent":"marketing",
      "domain":"marketing_growth",
      "interpreted_need":"Create a launch email for a new AI writing tool.",
      "deliverable":"A launch email prompt.",
      "confidence":0.9,
      "confirmation_question":"",
      "suggested_prompt_mode":"normal"
    }
  }'
```

Enhance streaming:

```bash
curl -N -X POST https://your-domain.example/enhance \
  -H 'Content-Type: application/json' \
  --data '{"prompt":"Improve this prompt: summarize a sales call.","target_ai":"chatgpt","incognito":true}'
```

Enhance compare:

```bash
curl -fsS -X POST https://your-domain.example/enhance/compare \
  -H 'Content-Type: application/json' \
  --data '{"prompt":"Write a churn-risk analysis prompt.","target_ai":"chatgpt","incognito":true,"modes":["normal"]}'
```

Refine:

```bash
curl -fsS -X POST https://your-domain.example/refine \
  -H 'Content-Type: application/json' \
  --data '{
    "original_prompt":"Summarize customer feedback.",
    "previous_enhanced_prompt":"Summarize customer feedback into themes, risks, and next actions.",
    "clarification_qa":[{"question":"Who is the audience?","answer":"Product managers"}],
    "target_ai":"chatgpt",
    "incognito":true
  }'
```

CoThinker:

```bash
curl -fsS -X POST https://your-domain.example/cothinker/turn \
  -H 'Content-Type: application/json' \
  --data '{"user_message":"I need a prompt that helps me plan a product roadmap from interview notes."}'

curl -fsS -X POST https://your-domain.example/cothinker/speak \
  -H 'Content-Type: application/json' \
  --data '{"text":"ThinkVelocity is online."}' \
  --output speak.mp3

curl -fsS -X POST https://your-domain.example/cothinker/transcribe \
  -F 'audio=@sample.webm'
```

Diagnostics:

```bash
curl -fsS https://your-domain.example/diagnostics/systems
curl -fsS https://your-domain.example/diagnostics/mcp-tools
curl -fsS https://your-domain.example/diagnostics/sources
curl -fsS https://your-domain.example/diagnostics/context-smoke/demo-user
```

## 8. Updates

```bash
cd /opt/thinkvelocity
git pull
docker compose up -d --build
docker compose logs -f --tail=100
curl -fsS http://127.0.0.1:8000/ready
```

Run the smoke script after each deploy:

```bash
bash scripts/smoke_api.sh https://your-domain.example
```

## 9. Backups

Docker Compose stores JSON data in the `thinkvelocity-data` volume.

Create a backup:

```bash
mkdir -p /opt/thinkvelocity/backups
docker run --rm \
  -v thinkvelocity-data:/data:ro \
  -v /opt/thinkvelocity/backups:/backup \
  busybox tar czf /backup/thinkvelocity-data-$(date +%Y%m%d-%H%M%S).tgz -C /data .
```

Restore a backup:

```bash
docker compose down
docker run --rm \
  -v thinkvelocity-data:/data \
  -v /opt/thinkvelocity/backups:/backup \
  busybox sh -c 'rm -rf /data/* && tar xzf /backup/BACKUP_FILE.tgz -C /data'
docker compose up -d
```

## 10. Operations

View logs:

```bash
docker compose logs -f --tail=200
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

Restart:

```bash
docker compose restart
sudo systemctl reload nginx
```

Check disk:

```bash
df -h
docker system df
```

Clean unused Docker build cache:

```bash
docker builder prune
```

## 11. Native Systemd Alternative

Use this only if you do not want Docker.

```bash
sudo mkdir -p /opt/thinkvelocity /var/lib/thinkvelocity /etc/thinkvelocity
sudo chown -R ubuntu:ubuntu /opt/thinkvelocity /var/lib/thinkvelocity
git clone YOUR_REPO_URL /opt/thinkvelocity
cd /opt/thinkvelocity
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Create `/etc/thinkvelocity/thinkvelocity.env`:

```env
GROQ_API_KEY=your_real_groq_key
APP_ENV=production
PORT=8000
STORAGE_BACKEND=local
STORAGE_PATH=/var/lib/thinkvelocity
VELOCITY_USER_ID=production
VELOCITY_API_URL=https://your-domain.example
ENABLE_REMOTE_TEST_RUNNER=false
```

Create `/etc/systemd/system/thinkvelocity.service`:

```systemd
[Unit]
Description=ThinkVelocity FastAPI service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/thinkvelocity
EnvironmentFile=/etc/thinkvelocity/thinkvelocity.env
ExecStart=/opt/thinkvelocity/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now thinkvelocity
sudo systemctl status thinkvelocity
curl -fsS http://127.0.0.1:8000/ready
```

Use the same Nginx and TLS steps above.
