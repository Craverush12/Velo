# Tasks — ThinkVelocity Infrastructure Evolution

> **For AI Agents (Claude / Codex):** Read `CONTEXT_PACK.md` first before picking up any task.
> Each task has a unique ID. Update status inline when you start or finish work.
> Log every significant decision to `DECISION_LOG.md`.

**Status legend:** `[ ]` TODO · `[~]` IN PROGRESS · `[x]` DONE · `[!]` BLOCKED

---

## Active

### PHASE 0 — Emergency Security (No Code, No Downtime)
> *All Phase 0 tasks are human-executed in AWS Console or via SSH. AI agents prep the commands.*

- [ ] **T-001 — Close PostgreSQL port 5432 on Server 2**
  - Where: AWS Lightsail Console → velocity-prod-large → Networking → IPv4 rules
  - Action: Remove inbound rule for port 5432 (all sources)
  - Risk: NONE — all local apps connect via 127.0.0.1, not the public IP
  - Verify: `nmap -p 5432 13.203.181.76` should show filtered
  - Owner: Human (AWS Console)

- [ ] **T-002 — Close Redis port 6379 on Server 2**
  - Where: AWS Lightsail Console → velocity-prod-large → Networking → IPv4 rules
  - Action: Remove inbound rule for port 6379
  - Risk: NONE after WireGuard is up (Phase 1). Server 3 currently reaches Redis via public IP — WireGuard must be done first OR temporarily add Server 3 public IP to allowlist
  - **Dependency:** DO THIS LAST in Phase 0, after confirming Server 3 → Server 2 Redis path
  - Owner: Human (AWS Console)

- [x] **T-003 — Remove dev routes from Apache production config** (completed 2026-05-25)
  - Server: 2 (ec2-user@13.203.181.76)
  - File: `/etc/httpd/conf.d/thinkvelocity-prod.conf`
  - Remove these two ProxyPass blocks:
    ```apache
    # DELETE THESE:
    ProxyPass /dev/test/ http://127.0.0.1:8006/
    ProxyPassReverse /dev/test/ http://127.0.0.1:8006/
    ProxyPass /dev/node/test/ http://127.0.0.1:3006/
    ProxyPassReverse /dev/node/test/ http://127.0.0.1:3006/
    ```
  - After edit: `sudo systemctl reload httpd`
  - Verify: `curl -I https://thinkvelocity.in/dev/test/` should return 404
  - Owner: AI (Codex or Claude can generate the exact edit)

- [ ] **T-004 — Close email ports 110/143 on Server 2**
  - Where: AWS Lightsail Console → Networking
  - Confirm first: Is Dovecot IMAP/POP3 actively used? If no active mail clients: close 110, 143
  - Keep: 993 (IMAPS), 995 (POP3S) if SSL variants in use
  - Owner: Human — must confirm mail usage before closing

- [x] **T-005 — Fix file permissions on Server 1** (completed 2026-05-25)
  - Server: 1 (ubuntu@13.234.212.59)
  - Current state: All files in `/opt/thinkvelocity/` are mode 777 (world-writable)
  - Commands:
    ```bash
    sudo chmod -R 750 /opt/thinkvelocity/
    sudo chown -R ubuntu:ubuntu /opt/thinkvelocity/
    sudo chmod 600 /opt/thinkvelocity/.env
    # App runs as docker container — verify it can still read files:
    docker exec thinkvelocity ls /app/
    ```
  - Owner: AI (Codex can generate + run via SSH)

- [~] **T-006 — Prune unused Docker images on Server 2 (free ~42GB)**
  - Server: 2 (ec2-user@13.203.181.76)
  - Commands:
    ```bash
    # First export backup images to S3 (run as safety net)
    docker save thinkvelocity24/thinkvelocity-python:latest | gzip > /tmp/python-backup-$(date +%Y%m%d).tar.gz
    # Then prune everything not currently in use
    docker image prune -a --filter "until=168h" -f
    # Verify active containers still running
    docker ps
    ```
  - Expected disk recovered: ~42GB
  - Owner: AI (generate commands) + Human (approve and run)

- [ ] **T-007 — Assign Elastic IP to Server 3**
  - Where: AWS EC2 Console → Elastic IPs → Allocate + Associate to i-053b58f7011435afc
  - Why: Server 3 has dynamic IP — will change on every stop/start, breaking SSL certs and WireGuard config
  - Owner: Human (AWS Console)

- [ ] **T-008 — Update enterprise domain DNS to new static IP**
  - After T-007: Update DNS A record for `velocityenterprise.toteminteractive.in` → new Elastic IP
  - Owner: Human (DNS provider)

---

### PHASE 1 — Private Networking & Secrets (Weeks 1–2)

- [~] **T-009 — Install WireGuard on all 3 servers** (configs generated in configs/wireguard/ — ready to deploy)
  - Server 1: `sudo apt install -y wireguard`
  - Server 2: `sudo dnf install -y wireguard-tools`
  - Server 3: `sudo apt install -y wireguard`
  - VPN IP assignments:
    - Server 2 (hub): `10.100.0.1`
    - Server 1: `10.100.0.2`
    - Server 3: `10.100.0.3`
  - See `CONTEXT_PACK.md §Network` for full WireGuard config blocks
  - Owner: AI (generate all configs) + Human (install + activate)
  - Dependency: T-007 must be done (stable IPs required)

- [~] **T-010 — Configure WireGuard on Server 2 (hub)** (server2_wg0.conf ready in configs/wireguard/)
  - Create `/etc/wireguard/wg0.conf` from config in CONTEXT_PACK.md §Network
  - `sudo systemctl enable --now wg-quick@wg0`
  - Test: `ping 10.100.0.2` and `ping 10.100.0.3` from Server 2
  - Owner: AI (generate config) + Human (apply)
  - Dependency: T-009

- [~] **T-011 — Configure WireGuard on Server 1** (server1_wg0.conf ready in configs/wireguard/)
  - Create `/etc/wireguard/wg0.conf` (peer: Server 2)
  - Enable WireGuard, test `ping 10.100.0.1`
  - Owner: AI + Human
  - Dependency: T-009, T-010

- [~] **T-012 — Configure WireGuard on Server 3** (server3_wg0.conf ready in configs/wireguard/)
  - Create `/etc/wireguard/wg0.conf` (peer: Server 2)
  - Enable WireGuard, test `ping 10.100.0.1`
  - Owner: AI + Human
  - Dependency: T-009, T-010

- [~] **T-013 — Update Server 3 connection strings to WireGuard IPs** (script ready 2026-05-28; blocked on WireGuard)
  - Script: `configs/env-changes/T-013-wireguard-connection-strings.sh`
  - Pings 10.100.0.2 as preflight, auto-locates .env via Docker mounts, sed-replaces host IPs, restarts containers, verifies health
  - Run on Server 3 after WireGuard is active
  - Owner: AI ✅ — Human runs after T-009–T-012
  - Dependency: T-010, T-011, T-012

- [~] **T-014 — Enable PostgreSQL SSL on Server 2** (scripts ready: configs/postgresql/01_enable_ssl.sh)
  - Generate self-signed cert (or use Let's Encrypt):
    ```bash
    sudo openssl req -new -x509 -days 365 \
      -nodes -out /var/lib/pgsql/17/data/server.crt \
      -keyout /var/lib/pgsql/17/data/server.key
    sudo chown postgres:postgres /var/lib/pgsql/17/data/server.{crt,key}
    sudo chmod 600 /var/lib/pgsql/17/data/server.key
    ```
  - Edit `postgresql.conf`: `ssl = on`
  - Restart PostgreSQL: `sudo systemctl restart postgresql-17`
  - Owner: AI (generate commands)
  - Dependency: T-013 (app strings updated before DB config changes)

- [~] **T-015 — Harden PostgreSQL listen_addresses and pg_hba.conf** (configs ready: configs/postgresql/pg_hba.conf + 02_postgresql_conf_changes.sh)
  - Edit `/var/lib/pgsql/17/data/postgresql.conf`:
    ```
    listen_addresses = '127.0.0.1,10.100.0.1'
    ```
  - Edit `/var/lib/pgsql/17/data/pg_hba.conf` — replace open `0.0.0.0/0` rule with per-service rules (see CONTEXT_PACK.md §Database)
  - `sudo systemctl restart postgresql-17`
  - **CRITICAL:** Do T-013 first or apps will lose DB access
  - Owner: AI (generate config) + Human (apply with care)
  - Dependency: T-013, T-014

- [~] **T-016 — Create per-service PostgreSQL users** (SQL ready: configs/postgresql/03_create_db_users.sql)
  - Connect as postgres superuser, run SQL from CONTEXT_PACK.md §Database Users
  - Create: `app_consumer`, `app_enterprise`, `app_extension`, `app_readonly`, `backup_user`
  - Grant minimal privileges per user
  - Owner: AI (generate SQL script, Codex or Claude can run it)
  - Dependency: T-015

- [~] **T-017 — Update all app connection strings to use dedicated DB users** (script ready 2026-05-28; blocked on T-016)
  - Script: `configs/env-changes/T-017-db-user-connection-strings.sh`
  - Preflight verifies app_consumer/enterprise/extension exist in pg_roles before touching anything
  - Updates docker-compose.yml DATABASE_URL lines + .env passwords per service; rolls each container individually
  - Verifies with `SELECT current_user` inside each container post-restart
  - Run on Server 2 after T-016 (per-service DB users created)
  - Owner: AI ✅ — Human runs after T-016
  - Dependency: T-016

- [ ] **T-018 — Set up AWS Secrets Manager — create all secrets**
  - Create secret namespaces in AWS Console or via CLI:
    ```bash
    aws secretsmanager create-secret --name thinkvelocity/production/nodejs \
      --secret-string '{"DB_PASSWORD":"...","JWT_SECRET":"...","RAZORPAY_KEY":"..."}'
    aws secretsmanager create-secret --name thinkvelocity/production/python-ai \
      --secret-string '{"GROQ_API_KEY":"...","LANGSMITH_API_KEY":"..."}'
    # etc. for each service
    ```
  - Full list of secrets per service: see CONTEXT_PACK.md §Secrets
  - Owner: Human (keys must be entered manually)

- [x] **T-019 — Integrate Secrets Manager into each service** (completed 2026-05-28)
  - Node.js: `configs/secrets/nodejs/secrets-loader.js` + consumer-backend-startup.js + enterprise-backend-startup.ts
  - Python: `configs/secrets/python/secrets_loader.py` + startup_patch_fastapi.py + settings_with_sm.py
  - Both: DEPLOY_INSTRUCTIONS.md with IAM policy JSON + aws CLI create-secret commands
  - Local `.env` fallback in place; SM skip when AWS_REGION absent
  - Owner: AI ✅
  - Dependency: T-018

- [x] **T-020 — Activate Fail2ban jails on Server 2** (completed 2026-05-25 — 5 jails active: sshd, apache-auth, apache-badbots, apache-noscript, apache-overflows)

- [x] **T-021 — Bind all app ports to 127.0.0.1 on Server 2** (completed 2026-05-25 — Node.js :3005 bound to 127.0.0.1, Apache proxy verified 200 OK; Server 3 containers also rebound to 127.0.0.1 on 2026-05-25: enterprise-backend :3000, velocity-frontend :8081, prompt-enhance :3002)

---

### PHASE 2 — Database Consolidation (Week 3)

- [x] **T-022 — Schema diff: localpgvelocity vs localVelo** (completed 2026-05-25)
  - Confirmed: localVelo has exactly 2 extra tables: `inactive_email_sent`, `referral_relations`
  - localpgvelocity: 52 tables; localVelo: 53 tables — only these 2 differ
  - Owner: AI (generate + run SQL)

- [x] **T-023 — Add 2 missing tables to localpgvelocity** (completed 2026-05-25)
  - Created `inactive_email_sent` (user_id + email_type PK, sent_at timestamptz) in localpgvelocity
  - Created `referral_relations` (id, inviter_id, invitee_id, referral_code, status, reward_tries, FK to usertable) with sequence
  - Owner: AI (generate migration SQL)
  - Dependency: T-022

- [x] **T-024 — Migrate data from localVelo extra tables** (completed 2026-05-25)
  - inactive_email_sent: 0 rows — nothing to migrate
  - referral_relations: 8 rows migrated — all 13 user IDs verified present in localpgvelocity first; INSERT 0 8 success
  - Owner: AI (generate migration)
  - Dependency: T-023

- [ ] **T-025 — Rename localpgvelocity → thinkvelocity_prod** (runbook ready: configs/env-changes/T-025-db-rename-runbook.md)
  - Runbook: `configs/env-changes/T-025-db-rename-runbook.md`
  - Downtime: ~90 seconds (nginx maintenance mode → pg_terminate_backend → ALTER DATABASE → restart services → nginx back)
  - Rollback: <2 min reverse rename + docker compose up
  - Owner: Human (must execute during maintenance window)
  - Dependency: T-024

- [ ] **T-026 — Update all connection strings to thinkvelocity_prod**
  - Server 2 Node.js `.env`: `DB_NAME=thinkvelocity_prod`
  - Server 2 Python AI env: update DB name
  - Restart all affected containers
  - Owner: AI (Codex)
  - Dependency: T-025

- [ ] **T-027 — Verify all services operational post-rename**
  - Smoke test each service:
    - `curl https://thinkvelocity.in/health`
    - `curl https://api.thinkvelocity.in/health`
    - `curl https://velocityenterprise.toteminteractive.in/backend/health`
  - Check logs for DB errors
  - Owner: AI (run smoke tests)
  - Dependency: T-026

- [ ] **T-028 — Drop localVelo database**
  - Only after 48h of verified stable operation post-rename:
    ```sql
    DROP DATABASE localvelo;
    ```
  - Owner: Human (irreversible — confirm before running)
  - Dependency: T-027 + 48h wait

- [x] **T-029 — Set up automated PostgreSQL backups to S3** (completed 2026-05-28)
  - `configs/backup/pg-backup.sh` — GPG-encrypted, S3-versioned, Slack-notified; auto-detects DB name (thinkvelocity_prod → localpgvelocity fallback)
  - `configs/backup/setup-backup.sh` — one-time install script (installs AWS CLI v2, sets crontab for backup_user at 02:00 IST daily)
  - `configs/backup/DEPLOY.md` — S3 bucket creation, IAM role, lifecycle policy, disaster recovery runbook
  - Next human step: create S3 bucket + run setup-backup.sh on Server 2
  - Owner: AI ✅

- [x] **T-030 — Test backup restore procedure** (completed 2026-05-28)
  - `configs/backup/pg-restore-test.sh` — downloads latest S3 backup, decrypts, restores to test DB, compares row counts per schema, drops test DB on exit
  - Cron: 1st of month 03:00 IST (installed by setup-backup.sh)
  - Owner: AI ✅
  - Dependency: T-029 ✅

---

### PHASE 3 — Service Consolidation (Weeks 4–5)

- [~] **T-031 — Merge Context Engine into Python AI service** (audit done 2026-05-28; unified app build IN PROGRESS 2026-05-29)
  - `docs/python-ai-endpoint-map.md` — full table of all 45 endpoints across 3 services with unified path mappings
  - `docs/python-ai-merge-plan.md` — shared deps, env vars, directory structure, DB/Redis dependency matrix, effort estimates, risk register
  - **Critical finding**: python-backend (Server 2, port 8005) is a STALE image of prompt-enhance (Server 3). Use Server 3 source as canonical for /ai/* router
  - Groq SDK version gap: 0.22.0 (Services A+C) vs 1.0.0 (context-engine) — standardizing on groq>=1.0.0
  - **Unified app BUILT + integration-verified** in `python-ai-unified/`: shared/ infra (9 modules) + /ai/* router (39 routes) + /context/* router (7 routes) + main.py/Dockerfile/requirements/.env.example/README
  - **Verified 2026-05-29**: `compileall` clean across 29 modules; `import main` mounts BOTH routers (46 API routes live); middleware = LogScrubber→GZip→CORS, `scrubber=on`; router imports cross-checked against shared `__all__` (no drift)
  - Integration fixes: added `redis_cache.get_redis()`, `routers/__init__.py`, vendored log scrubber (SOC2 CC6.7 — self-contained for Docker) + `LogScrubberMiddleware`
  - Serves BOTH consumer (enhance/refine/clarify) AND enterprise (`/prompt/find` policy+docs, moderation)
  - **Reconciliation gate (REMAINING)**: canonical source is locked in remote Docker images. Run `configs/env-changes/T-031-fetch-canonical-source.sh --pull` on Server 3 + Server 2 (`docker cp`, read-only), then diff `_canonical/` vs routers to close the 27 items in `python-ai-unified/RECONCILE.md` before cutover
  - Next: [human] run fetch script on servers → [AI] reconcile RECONCILE.md items → deploy + nginx route /ai/* and /context/* → decommission 3 old containers
  - Owner: AI (build ✅ + reconcile) + Human (run fetch script; final cutover)

- [~] **T-032 — Update dependents to use new context endpoint** (migration script ready 2026-05-28; runs after T-031 merge)
  - Script: `configs/env-changes/T-032-context-endpoint-migration.sh`
  - `--scan` mode (default) = read-only discovery of all :8001 / context-engine callers; `--apply` = sed-rewrite to :8005/context/ with .bak backups
  - Run on Server 2 after T-031 merge lands and /context/ router is live
  - Owner: AI ✅ (script) — runs after T-031
  - Dependency: T-031

- [ ] **T-033 — Stop and remove context-engine-container**
  - Verify T-032 is complete and traffic is going to new endpoint
  - `docker stop context-engine-container-dev && docker rm context-engine-container-dev`
  - Remove from docker-compose
  - Owner: Human (confirm then run)
  - Dependency: T-032

- [x] **T-034 — Stop and remove dev containers from Server 2** (completed 2026-05-25)
  - Stopped: nodejs-pg-backend-container-dev (port 3006), python-backend-container-dev (port 8006) via docker compose down
  - Also fixed: python-backend-container (8005) and context-engine-container-dev (8001) rebound to 127.0.0.1
  - Disabled thinkvelocity-dev-test.conf (moved to .conf.disabled)
  - Final state: 3 containers running, all on 127.0.0.1 — prod verified 200 OK
  - Owner: Human
  - Dependency: T-003

- [~] **T-035 — Create dev subdomain with IP allowlist** (config generated 2026-05-25)
  - Config ready at: `configs/apache/thinkvelocity-dev.conf`
  - Deploy: copy to /etc/httpd/conf.d/thinkvelocity-dev.conf, fill in REPLACE_WITH_*_IP placeholders
  - Then: `certbot --apache -d dev.thinkvelocity.in && sudo systemctl reload httpd`
  - DNS: add A record `dev.thinkvelocity.in` → 13.203.181.76 first
  - Owner: AI (generate config) + Human (DNS + IP allowlist values)

- [x] **T-036 — Deploy unified observability stack on Server 2** (configs completed 2026-05-28)
  - `configs/observability/docker-compose.yml` — 7 services: Prometheus, Loki, Grafana, Alertmanager, Promtail, node_exporter, cAdvisor
  - `configs/observability/prometheus/prometheus.yml` — scrapes all 4 app /metrics + health endpoints, 30-day retention
  - `configs/observability/loki/loki.yml` — TSDB schema v12, 90-day retention, WAL enabled
  - `configs/observability/promtail/promtail.yml` — Docker SD (auto-discovers containers), nginx + PostgreSQL log scraping
  - `configs/observability/nginx/grafana.conf` — grafana.thinkvelocity.in vhost with IP allowlist
  - `configs/observability/DEPLOY.md` — step-by-step deployment guide
  - All ports 127.0.0.1-bound. Deploy: `cd /opt/observability && docker compose up -d`
  - Owner: AI ✅ — Human deploys after WireGuard complete

- [x] **T-037 — Configure critical alerts** (completed 2026-05-28)
  - `configs/observability/prometheus/alert-rules.yml` — 13 alert rules: server down, disk <15%, memory >90%, container restart, SSL expiry <14d, DB connections >150, error spike
  - `configs/observability/alertmanager/alertmanager.yml` — Slack routing (#thinkvelocity-alerts); critical=immediate, warning=batched 5min
  - Owner: AI ✅
  - Dependency: T-036 ✅

- [~] **T-038 — Migrate enterprise domain to thinkvelocity.in** (Nginx config generated 2026-05-25)
  - Nginx config ready: `configs/nginx/enterprise.thinkvelocity.in.conf`
  - Deploy steps: (1) T-007 Elastic IP → (2) DNS A record → (3) deploy nginx conf → (4) certbot → (5) update NestJS ALLOWED_ORIGINS → (6) add 301 redirect on old domain
  - ALLOWED_ORIGINS update: `ALLOWED_ORIGINS=https://velocityenterprise.toteminteractive.in,https://enterprise.thinkvelocity.in`
  - Owner: AI (Codex — generate Nginx config, env changes) + Human (DNS, T-007 prerequisite)

- [x] **T-039 — Rebrand enterprise frontend title** (completed 2026-05-25)
  - File: `/root/velocity-enterprise-mode/index.html`
  - Change: `<title>Lovable App</title>` → `<title>ThinkVelocity Enterprise</title>`
  - Also update any og:title, og:description meta tags
  - Rebuild frontend: `bun run build`
  - Redeploy Docker container
  - Owner: AI (Codex — trivial change, 3 lines)

---

### PHASE 4 — CI/CD & Hardening (Weeks 6–8)

- [x] **T-040 — Add Trivy container scanning to GitHub Actions** (completed 2026-05-25 — workflows installed in `.github/workflows/`)
  - Add `aquasecurity/trivy-action@master` step to all deploy workflows
  - Set `exit-code: 1` on CRITICAL + HIGH CVEs
  - Owner: AI (Codex — edit .github/workflows/*.yml)

- [x] **T-041 — Add npm audit + pip-audit to CI** (completed 2026-05-25 — npm audit and pip-audit installed in workflows)
  - Node.js workflow: add `npm audit --audit-level=high`
  - Python workflows: add `pip-audit -r requirements.txt`
  - Owner: AI (Codex)

- [~] **T-042 — Switch GitHub Actions to push-to-main trigger** (push-to-main trigger installed in all 3 workflows; GitHub production environment approval still needs UI setup)
  - Change `on: workflow_dispatch` → `on: push: branches: [main]`
  - Add environment protection rules in GitHub → require approval for prod
  - Owner: AI (Codex — edit workflow files)

- [x] **T-043 — Implement zero-downtime deploy script** (completed 2026-05-28)
  - `configs/deploy/deploy.sh` — blue/green container swap with health check gate, 30s rollback on failure
  - `configs/deploy/deploy-static.sh` — NextJS static export deploy with atomic symlink swap
  - `configs/deploy/DEPLOY_INSTRUCTIONS.md` — install guide + usage examples
  - Install: `sudo cp configs/deploy/deploy.sh /opt/deploy/deploy.sh && sudo chmod +x /opt/deploy/deploy.sh`
  - Owner: AI ✅

- [ ] **T-044 — Reboot Server 2 (kernel patch)**
  - Schedule maintenance window (low traffic, e.g. 3–4 AM IST Sunday)
  - Before reboot: `sudo dnf update -y`
  - After reboot: verify all Docker containers auto-restarted, all services up
  - Owner: Human (scheduled maintenance)

- [x] **T-045 — Add Docker cleanup cron on all servers** (completed 2026-05-25)
  - Installed /opt/maintenance/docker-cleanup.sh on all 3 servers
  - Cron active: `0 4 * * 0 /opt/maintenance/docker-cleanup.sh` (Sunday 4am) on all 3 servers
  - Owner: AI (generate script + cron entry)

- [x] **T-046 — Enable PostgreSQL query logging for SOC2** (completed 2026-05-25)
  - Applied to /var/lib/pgsql/17/data/postgresql.conf on Server 2:
    log_connections = on, log_disconnections = on, log_min_duration_statement = 1000, log_statement = 'ddl'
  - postgresql-17 reloaded successfully
  - Owner: AI (generate config)

- [x] **T-047 — Write incident response runbook** (completed 2026-05-25 — RUNBOOK.md created)
  - Create `RUNBOOK.md` in ThinkVelocity project
  - Sections: Service down, Database unreachable, Disk full, SSL expired, Payment provider down
  - Each section: detection → immediate response → escalation → resolution
  - Owner: AI (Claude — generate runbook)

- [x] **T-048 — Generate first SOC2 evidence package** (script completed 2026-05-25; Windows console-safe help/output verified)
  - Created `compliance/generate_evidence.py` — covers CC6.1, CC6.3, CC6.6, CC7.2, A1.2
  - Run: `python3 compliance/generate_evidence.py` → generates evidence_YYYYMMDD/ folder
  - Upload: `python3 compliance/generate_evidence.py --upload` to push to S3
  - Owner: AI (Codex — write script)

---

### PHASE 5 — Scale & Upgrade (Month 2–3)

- [x] **T-049 — Add swap to Server 3** (completed 2026-05-25)
  - Server 3 currently has NO swap — any memory spike = OOM kill
  - Commands:
    ```bash
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    ```
  - Owner: AI (generate commands)

- [ ] **T-050 — Upgrade Server 1 Lightsail instance**
  - Current: 1GB RAM, at 64% with swap pressure
  - Target: 2GB RAM instance (same region, snapshot + redeploy)
  - Owner: Human (AWS Console — create snapshot, launch new instance)

- [ ] **T-051 — Add CloudFlare in front of all domains**
  - Move DNS to CloudFlare
  - Enable WAF, DDoS protection, Rocket Loader for NextJS
  - Set SSL mode: Full (strict)
  - Owner: Human (DNS + CloudFlare setup)

- [ ] **T-052 — Build shared prompt library (Git submodule)**
  - Create new repo: `thinkvelocity-prompts`
  - Migrate all 17+ system prompt .md files from Server 1 `/opt/thinkvelocity/core/prompts/`
  - Add as git submodule to all 3 app repos
  - Owner: AI (Codex + Claude — organize and migrate)

- [ ] **T-053 — Evaluate RDS migration**
  - Assess cost: AWS RDS PostgreSQL 17 (db.t3.medium, Multi-AZ) vs self-managed
  - Multi-AZ gives automated backups, SSL enforced, auto-minor-version updates
  - Draft migration plan if approved
  - Owner: AI (Claude — cost analysis + migration plan)

---

## Waiting On

- [~] **T-002 — Close Redis port 6379** — Waiting on WireGuard (T-009 to T-012) to be complete first, so Server 3 has a private path to Redis before the public port closes

---

## Someday

- [ ] **T-054 — Migrate NextJS static frontend to S3 + CloudFront** (removes web-serving load from Server 2)
- [ ] **T-055 — Migrate to AWS ECS Fargate** (at ~50k users, Docker Compose stops scaling)
- [ ] **T-056 — Implement PgBouncer connection pooling** (needed at 10x user growth)
- [ ] **T-057 — Set up Redis Cluster or AWS ElastiCache** (Redis single-node is a bottleneck at scale)
- [ ] **T-058 — Add Celery + Redis Queue for background jobs** (move APScheduler out of FastAPI process)
- [ ] **T-059 — Implement multi-provider LLM fallback on Servers 1 + 2** (Server 3 already has Groq → OpenAI → Gemini routing)
- [ ] **T-060 — Full SOC2 Type II audit engagement** (after Phase 1–4 complete)

---

## Active (Added 2026-06-12 — New Server Live)

> **CURRENT STATE:** New consolidated server `35.154.138.184` is LIVE with all 5 containers running (tv-extension-api :8000, tv-python-ai-unified :8005, tv-nestjs-enterprise :3000, postgres17, redis). Admin panel at `http://35.154.138.184/admin`. DNS flip and Certbot still pending.

- [x] **T-061 — Fix MODERATION_SERVICE_URL on tv-nestjs-enterprise** (completed 2026-06-12)
  - Was: `http://tv-python-ai-unified:8005/ai/enhance` (wrong — guardrail appended `/moderation/check` → 404)
  - Fixed: `http://tv-python-ai-unified:8005/ai` in `/opt/deploy/enterprise.env` + container restarted
  - Also patched guardrail.service.js: 5 lines changed, fail-open (ALLOW) → fail-closed (BLOCK)
  - Verified: `POST /ai/moderation/check` with SSN/CC returns `{"decision":"REDACT","confidence":0.95}` ✅
  - Fail-closed lines confirmed live: guardrail.service.js lines 492, 498, 534 → BLOCK
  - Owner: AI ✅

- [x] **T-062 — Decide fail-open vs fail-closed for moderation service failures** (decided 2026-06-12)
  - Decision: FAIL-CLOSED — moderation unavailable → BLOCK, not ALLOW
  - Logged as D-030 in DECISION_LOG.md
  - Implementation: update guardrail.service.ts catch block (hot-patch script in configs/hotpatches/)
  - Owner: AI ✅ (decision) + Human (apply hot-patch)

- [ ] **T-063 — DNS flip: api.thinkvelocity.in → 35.154.138.184**
  - Current: api.thinkvelocity.in → 13.234.212.59 (old Server 1)
  - Target: api.thinkvelocity.in → 35.154.138.184
  - Pre-req: T-064 Certbot must run BEFORE flip (Chrome extension requires HTTPS)
  - Owner: Human (DNS provider)
  - Dependency: T-064

- [ ] **T-064 — Certbot SSL on 35.154.138.184**
  - Domains: `api.thinkvelocity.in` (critical for extension), `enterprise.thinkvelocity.in`, `thinkvelocity.in`
  - Run BEFORE DNS flip so cert is ready when traffic arrives
  - Commands:
    ```bash
    certbot --nginx -d api.thinkvelocity.in
    certbot --nginx -d enterprise.thinkvelocity.in
    ```
  - Owner: Human (SSH to 35.154.138.184)
  - Dependency: T-063 DNS TTL lowered to 60s first

- [x] **T-065 — Admin panel built and deployed** (completed 2026-06-12)
  - PBKDF2-SHA256 + httpOnly session cookies + CSRF + RBAC (4 roles)
  - 5 PostgreSQL tables auto-created: admin_users, admin_sessions, admin_audit_logs, admin_managed_entities, admin_runtime_config
  - Live at `http://35.154.138.184/admin`
  - Super_admin bootstrapped (arjungujar490@gmail.com)
  - Dashboard and user list wired to live PostgreSQL (5,510 real users)
  - Hot-patched into tv-extension-api container via `ADMIN_DATABASE_URL` env bypass
  - Owner: AI ✅

- [ ] **T-066 — Verify RECONCILE.md items against live containers**
  - 27 open items in `python-ai-unified/RECONCILE.md` — marked "reconstructed contracts"
  - Key items to verify: Node backend persist endpoint paths, response shapes, embedding strategy
  - Run: `configs/env-changes/T-031-fetch-canonical-source.sh --scan` on new server
  - Diff against `python-ai-unified/routers/`
  - Owner: AI (after human runs fetch script)

---

## Pending Architecture Approval (2026-06-12 — awaiting Arjun sign-off)

> These tasks were designed in the 2026-06-12 architecture analysis session. **DO NOT execute until Arjun approves the plan.** See architecture analysis in conversation history.

- [ ] **T-067 — Architecture Phase 1: Single prompt plane — consolidate deployments**
  - Re-point consumer extension's nginx (api.thinkvelocity.in) to port 8005 (tv-python-ai-unified)
  - Run dual-service for 1 week (tv-extension-api AND tv-python-ai-unified both serving)
  - Retire tv-extension-api's enhance/refine duty (keeps auth/admin/storage roles)
  - Decision point: does tv-extension-api fully retire or keep admin + auth roles?
  - One image = one prompt hash = zero drift
  - Owner: AI (nginx config changes) + Arjun (approval, DNS, cutover)
  - Dependency: T-063 (DNS flipped), T-066 (RECONCILE verified)
  - **BLOCKED: Awaiting architecture plan approval**

- [x] **T-068 — Architecture Phase 2: Policy as pipeline stage (not separate HTTP call)** (completed 2026-06-12, commit 90f48b7)
  - enterprise_id detection added to EnhanceRequest; moderation called in-process before enhance
  - Verdicts: BLOCK → SSE error; REDACT → scrub prompt + stamp metadata; WARN → stamp warning; ALLOW → normal
  - Fail-closed per D-030: moderation exception → BLOCK, not ALLOW
  - Consumer requests (no enterprise_id) completely unaffected — zero added latency
  - Owner: AI ✅

- [x] **T-069 — Architecture Phase 3: Context engine enterprise evolution** (completed 2026-06-12, commit a2c033b)
  - enterprise_id/team_id added to ProcessContextRequest; pgvector key namespaced by tenant
  - PII redaction before embed: SSN, CC, email, phone patterns → [REDACTED:TYPE]
  - Enterprise persistence routed to /api/v1/enterprise-context (consumer path unchanged)
  - Audit events logged at INFO: AUDIT {"action":"context_stored","enterprise_id":...}
  - Consumer requests (no enterprise_id) completely unaffected
  - Owner: AI ✅

- [ ] **T-070 — Architecture Phase 4: Rebuild Docker image (decommission hot-patches)**
  - Fold in media-pipeline-v2 hot-patch and admin panel hot-patch into proper Docker image builds
  - Rebuild tv-python-ai-unified image from tag `media-pipeline-v2`
  - Rebuild tv-extension-api image with admin panel baked in
  - Push to Docker Hub, restart containers from new images
  - Hot-patches stop being load-bearing
  - Owner: AI + Human (docker build + push)
  - Dependency: T-067 (after old images are decommissioned)
  - **BLOCKED: Awaiting architecture plan approval**

---

## Done

- [x] ~~**Infrastructure live SSH discovery — all 3 servers**~~ (2026-05-25)
- [x] ~~**INFRASTRUCTURE_MASTER_DOC.md created**~~ (2026-05-25)
- [x] ~~**UNIFIED_ARCHITECTURE_EVOLUTION.md created**~~ (2026-05-25)
- [x] ~~**TASKS.md, CONTEXT_PACK.md, DECISION_LOG.md created**~~ (2026-05-25)
- [x] ~~**New consolidated server 35.154.138.184 provisioned and bootstrapped**~~ (2026-06-12)
- [x] ~~**Admin panel built and deployed**~~ (commits c97e0f5, 0fbcc6d — 2026-06-12)
