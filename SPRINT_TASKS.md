# ThinkVelocity — Exhaustive Sprint Task List
**Version:** 2026-05-30 | **For agents:** Read AGENT_CONTEXT.md first.
**Chrome Store:** Already published → update review = 1–3 days
**New server:** thinkvelocity-prod-v2 (8GB Lightsail) being provisioned NOW
**Launch target:** 8–10 days from today

---

## LEGEND
```
🔴 LAUNCH BLOCKER    — cannot ship without this
🟡 LAUNCH QUALITY    — ships broken = bad user experience
🟢 POST-LAUNCH       — do during Chrome Store review window or after

[AGENT]  = AI agent executes (Claude, Grok, Codex, Gemini, OpenCode)
[ARJUN]  = Human action required (AWS Console, SSH, DNS, CMS)
[ANIKET] = Extension UI + context/memory wiring
[AAKASH] = Analytics, paywall, events
[ANANYA] = Extension UX, output actions, landing
[PRADEEP]= Enterprise delivery

Status: [ ] TODO | [~] IN PROGRESS | [x] DONE | [!] BLOCKED
```

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## TRACK A — CONSOLIDATION (Agent + Arjun)
## Build the new system. Team keeps current live.
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

---

### BLOCK A0 — CODE COMPLETION (Today, all parallel)
*Complete python-ai-unified so it's deployment-ready*

---

**A0-1** | Remove `notifications` from manifest.json | [AGENT] | 🔴
```
File: FullCodebase/ThinkVelocity/Sidebar_extension/manifest.json
Action: Remove "notifications" from permissions array
Why: Unused permission — flags in Chrome review, potential rejection
Acceptance: manifest.json has no "notifications" in permissions
Time: 5 min
Depends: nothing
```

**A0-2** | Rewrite `/context/*` router using real ContextEngine source | [AGENT] | 🔴
```
Source: FullCodebase/ThinkVelocity/ContextEngine/src/api/context_router.py
        FullCodebase/ThinkVelocity/ContextEngine/src/api/schemas.py
        FullCodebase/ThinkVelocity/ContextEngine/src/api/extension_schemas.py
        FullCodebase/ThinkVelocity/ContextEngine/src/infrastructure/http_repository.py
Target: python-ai-unified/routers/context.py
Routes to implement:
  POST /context/process-context    → ExtensionAdapterService → ContextProcessorService
  POST /context/process-essence    → processor.process_manual_essence()
  GET  /context/user/{user_id}/profile → proxies to NODE_BACKEND_URL/api/v1/user-profile
  POST /context/search/contexts    → ContextSearchService (NVIDIA 1024-dim embeddings)
  POST /context/test/batch-embedding → embedding_service.generate_embeddings(texts)
  GET  /health                     → health check
Node callback payload (exact): {sessionId, essence, intent, secondaryIntent, domains,
  embedding, embeddingModel, embeddingVersion, messageCount, platform, version,
  updateType, usageCost, userId}
Acceptance: All 6 routes mount, process-context returns ProcessContextResponse shape
Time: 3–4 hrs
Depends: nothing (source available)
```

**A0-3** | Rebuild `/ai/moderation/*` routes | [AGENT] | 🔴
```
Source: FullCodebase/ThinkVelocity/PromptEnhancement/src/api/
        Look for: moderation router files in src/api/ and src/application/
Target: python-ai-unified/routers/ai/moderation.py
Routes: POST /ai/moderation/check, /ai/moderation/document/classify,
        /ai/moderation/document/upload, /ai/moderation/cache,
        /ai/moderation/stats, /ai/moderation/health + 1 more
Why: Enterprise guardrail depends on this. VYGR launch blocked without it.
Acceptance: 7 moderation routes mount and return correct response shapes
Time: 2–3 hrs
Depends: nothing (source available)
```

**A0-4** | Wire `/ai/prompt/find` to Node backend | [AGENT] | 🔴
```
File: python-ai-unified/routers/ai/prompt_find.py
Action: Replace stub with real HTTP calls to:
  NODE_BACKEND_URL + /api/v1/processed-context/public/user/{userId}
  NODE_BACKEND_URL + /api/v1/processed-context/public/search
Uses: shared/node_client.py (node_get, node_post)
Returns: {policy, documents, errors} — enterprise policy + context docs
Acceptance: /ai/prompt/find returns 200 with correct shape when Node is reachable
Time: 1–2 hrs
Depends: nothing
```

**A0-5** | Mode mapping end-to-end (Fast/Best/Media/Saver) | [AGENT] | 🔴
```
Files to update:
  python-ai-unified/local_app.py — EXT_MODE_TO_INTERNAL dict
  FullCodebase/ThinkVelocity/Sidebar_extension/features/consumer-enhance-flow.js
    → confirm mode labels sent match: 'flash', 'research', 'media', 'caveman'
Mapping:
  Fast   → 'flash'   (→ internal: 'normal')
  Best   → 'research'
  Media  → 'media'
  Saver  → 'caveman'
Acceptance: Extension sends correct mode string, unified service maps to correct
  system prompt overlay, verify in enhance response metadata
Time: 1 hr
Depends: nothing
```

**A0-6** | Generate DB migrations script (rini 015–019) | [AGENT] | 🔴
```
Target file: configs/env-changes/run-rini-migrations.sh
Migrations (in order):
  015: engagement_reward_tracking
  016: consumer_partner_cohort
  017: prompt_library_catalog + seed data (FullCodebase/.../migrations/017_*.sql)
  018: annotated_segments (adds column to save_enhance_prompt)
  019: auth_sessions + client_id + magic_links
Script requirements:
  - Dry-run mode first (--dry-run flag, just prints SQL)
  - Transaction per migration (rollback on failure)
  - Row count verification before and after 017 (seed data = 315+ rows)
  - Idempotent (check if already applied)
  - Prints: [OK] / [SKIP] / [FAIL] per migration
Acceptance: ./run-rini-migrations.sh --dry-run prints all steps with no errors
Time: 1 hr
Depends: nothing
```

**A0-7** | Define mode nudge spec + output view integration | [AGENT] | 🟡
```
Context: 4+ modes tried = 35.7% Pro conversion vs 0.6% for 1 mode (60x lift)
         83.2% of users never leave first mode passively
Spec to write (for Aniket/Ananya to implement):
  - After enhance completes, read `intent` + `domain` from enhance response
  - Map to suggested mode:
      software_development → suggest Build (if current mode != Build)
      creative_writing → suggest Media (if current mode != Media)
      research_analysis → suggest Best (if current mode != Best)
      Any → suggest Saver if user has < 3 token credits remaining
  - Show nudge chip: "This looks like [domain] — try [Mode] for [benefit]"
  - Fire PostHog: mode_nudge_shown {suggested_mode, trigger_domain, trigger_intent}
  - On click: fire mode_nudge_clicked, switch mode, re-enhance automatically
File to create: FullCodebase/ThinkVelocity/Sidebar_extension/docs/mode-nudge-spec.md
Acceptance: Spec is clear enough for Aniket to implement without asking questions
Time: 45 min
Depends: A0-5 mode mapping
```

**A0-8** | Analytics event spec (win/loss + all events) | [AGENT] | 🟡
```
File to create: FullCodebase/ThinkVelocity/Sidebar_extension/docs/analytics-events-spec.md
Events (exact names, properties, where to fire):
  enhance_started      {mode, platform, prompt_length_chars, user_id, session_prompt_count}
  enhance_completed    {mode, platform, intent, domain, tokens_used, processing_ms, success}
  enhance_failed       {mode, platform, error_type, error_message}
  output_copied        {mode, platform, session_prompt_count}   ← WIN SIGNAL
  refine_triggered     {from_mode, session_prompt_count}        ← STRONG WIN
  mode_nudge_shown     {suggested_mode, trigger_domain, trigger_intent, current_mode}
  mode_nudge_clicked   {suggested_mode, accepted: bool}
  mode_switched        {from_mode, to_mode, via_nudge: bool}    ← CONVERSION PREDICTOR
  platform_added       {new_platform, total_platforms_ever}     ← 130x engagement signal
  paywall_hit          {session_prompt_count, current_mode, plan_type}
  session_win          {prompts_count, modes_tried, copied: true}
  session_loss         {prompts_count, last_action, paywall_hit: bool}
Win definition: output_copied fires within 60s of enhance_completed
Loss definition: enhance_completed + no output_copied within 60s
Time: 45 min
Depends: nothing
```

**A0-9** | python-ai-unified full compile + smoke test | [AGENT] | 🔴
```
Commands:
  cd python-ai-unified
  python -m compileall -q routers local_app.py shared 2>&1
  python -c "import main; routes=[r.path for r in main.app.routes]; print(f'{len(routes)} routes')"
Expected: 50+ routes, 0 compile errors, scrubber=on in startup log
Acceptance: All routes mount, no import errors, 46+ routes confirmed
Time: 30 min
Depends: A0-2, A0-3, A0-4 completed
```

---

### BLOCK A1 — SERVER SETUP (Arjun, today in AWS Console)
*Provision and baseline-harden the new server*

---

**A1-1** | Provision thinkvelocity-prod-v2 | [ARJUN] | 🔴
```
AWS Lightsail → Create instance
  Region: ap-south-1a (Mumbai)
  OS: Ubuntu 24.04 LTS
  Plan: 8GB RAM / 4 vCPU / 160GB SSD ($40/mo)
  Name: thinkvelocity-prod-v2
Acceptance: Instance shows "Running" in Lightsail console
Time: 10 min
```

**A1-2** | Assign Elastic IP to new server | [ARJUN] | 🔴
```
AWS Lightsail → Networking → Create static IP
→ Attach to thinkvelocity-prod-v2
→ Send IP to Claude
Acceptance: Static IP visible, ping from local returns response
Time: 5 min
Depends: A1-1
```

**A1-3** | Set firewall rules on new server | [ARJUN] | 🔴
```
Lightsail console → thinkvelocity-prod-v2 → Networking
ALLOW: TCP 22, TCP 80, TCP 443
BLOCK: everything else (especially 5432, 6379, 3005, 8005, 3000, 8000)
Acceptance: nmap from outside shows only 22/80/443 open
Time: 5 min
Depends: A1-1
```

**A1-4** | Publish privacy policy | [ARJUN] | 🔴
```
Source: PRIVACY_POLICY_COPY.md (complete copy ready)
Target: thinkvelocity.in/privacypolicy/ (page exists, needs content update)
Action: Copy content from PRIVACY_POLICY_COPY.md into the CMS/page editor
Verify: https://thinkvelocity.in/privacypolicy/ loads with real content
  Check: Groq and NVIDIA listed as data processors
  Check: Voice input disclaimer present (no background recording)
  Check: Brevo listed as email processor (NOT SendGrid)
  Check: Last updated date = 2026-05-30
Acceptance: Page accessible publicly, content matches PRIVACY_POLICY_COPY.md
Time: 15 min
Depends: nothing
```

**A1-5** | Confirm contact emails exist | [ARJUN] | 🔴
```
Verify these email addresses work (forward to your real inbox):
  privacy@thinkvelocity.in
  security@thinkvelocity.in
  support@thinkvelocity.in
If they don't exist: create forwarders in your email/DNS provider
Acceptance: Test email to privacy@thinkvelocity.in lands in Arjun's inbox
Time: 10 min
```

---

### BLOCK A2 — SERVER BOOTSTRAP (Agent, after A1-2 IP received)
*Generate complete setup script for Arjun to run on new server*

---

**A2-1** | Generate server bootstrap script | [AGENT] | 🔴
```
Output file: configs/prod/bootstrap-new-server.sh
Script must do (in order):
  1. SSH hardening (PasswordAuthentication no, PermitRootLogin no)
  2. fail2ban install + configure (5 jails: sshd, nginx-auth, nginx-badbots)
  3. unattended-upgrades (security patches)
  4. Docker + Docker Compose plugin install
  5. Nginx + Certbot install
  6. PostgreSQL 17 (Docker container, 127.0.0.1:5432)
     - Create databases: thinkvelocity_prod, enterprise
     - Run schema creation scripts
     - Create per-service users (app_consumer, app_enterprise, app_python_ai, app_readonly)
  7. Redis 7 (Docker container, 127.0.0.1:6379)
  8. AWS CLI install + Secrets Manager access verify
  9. Create /opt/deploy/, /opt/backup/, /opt/observability/ directories
  10. Install backup cron (pg-backup.sh at 02:00 IST daily)
  11. Install cleanup cron (docker-cleanup.sh at 04:00 Sunday)
Each step: prints [STEP N/11], verifies success, exits on failure
Acceptance: Script runs on fresh Ubuntu 24.04 from top to bottom without manual intervention
Time: 2 hrs
Depends: A1-2 (IP needed for any server-specific configs)
```

**A2-2** | Generate production docker-compose.yml | [AGENT] | 🔴
```
Output file: configs/prod/docker-compose-new-server.yml
Services:
  node-backend:
    image: thinkvelocity24/thinkvelocity-backend:latest
    ports: ["127.0.0.1:3005:3005"]
    env_file: configs/prod/env-template/node.env
    security_opt: [no-new-privileges:true]
    restart: unless-stopped
    healthcheck: curl -f http://localhost:3005/health

  python-ai-unified:
    build: .  (build context = repo root, uses python-ai-unified/Dockerfile)
    ports: ["127.0.0.1:8005:8005"]
    security_opt: [no-new-privileges:true]
    read_only: true
    tmpfs: [/tmp]
    restart: unless-stopped
    healthcheck: curl -f http://localhost:8005/health

  nestjs-enterprise:
    image: enterprise-backend:latest
    ports: ["127.0.0.1:3000:3000"]
    security_opt: [no-new-privileges:true]
    restart: unless-stopped

  extension-api:
    image: thinkvelocity-backend:local (built from this repo)
    ports: ["127.0.0.1:8000:8000"]
    security_opt: [no-new-privileges:true]
    restart: unless-stopped

  postgres:
    image: pgvector/pgvector:pg17
    ports: ["127.0.0.1:5432:5432"]
    volumes: [postgres-data:/var/lib/postgresql/data]
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports: ["127.0.0.1:6379:6379"]
    command: redis-server --requirepass ${REDIS_PASSWORD}
    restart: unless-stopped

All with resource limits (memory + cpu)
Acceptance: docker-compose config validates, all healthchecks defined
Time: 1.5 hrs
Depends: A2-1
```

**A2-3** | Generate Nginx vhost configs for all 4 domains | [AGENT] | 🔴
```
Output files: configs/prod/nginx/
  thinkvelocity.in.conf:
    - Serve /var/www/velocity/ (NextJS static) for root
    - proxy_pass /backend/* → http://127.0.0.1:3005/
    - proxy_pass /ai/* → http://127.0.0.1:8005/ai/
    - proxy_pass /context/* → http://127.0.0.1:8005/context/
    - proxy_buffering off for /ai/enhance/stream (SSE)
    - proxy_read_timeout 300s
    - Security headers: HSTS, X-Frame-Options, X-Content-Type-Options

  api.thinkvelocity.in.conf:
    - proxy_pass → http://127.0.0.1:8000/
    - proxy_buffering off (SSE streaming)
    - proxy_read_timeout 300s
    - client_max_body_size 25m

  enterprise.thinkvelocity.in.conf:
    - Serve /var/www/enterprise/ (React static) for root + /frontend/
    - proxy_pass /backend/* → http://127.0.0.1:3000/
    - proxy_pass /ai/* → http://127.0.0.1:8005/ai/ (enterprise uses same AI)
    - proxy_buffering off for streaming

  grafana.thinkvelocity.in.conf:
    - proxy_pass → http://127.0.0.1:3200/ (Grafana)
    - IP allowlist: team IPs only

Acceptance: nginx -t passes, all vhosts load
Time: 1.5 hrs
Depends: nothing
```

---

### BLOCK A3 — DEPLOY (Arjun SSH, Day 2–3)
*Run the scripts, get containers live*

---

**A3-1** | Run bootstrap script on new server | [ARJUN] | 🔴
```
Commands:
  scp -i lightsail-key.pem configs/prod/bootstrap-new-server.sh ubuntu@<NEW_IP>:~
  ssh -i lightsail-key.pem ubuntu@<NEW_IP>
  chmod +x bootstrap-new-server.sh && sudo ./bootstrap-new-server.sh
Verify: All 11 steps print [OK]
Time: ~45 min to run
Depends: A1-2 (IP), A2-1 (script ready)
```

**A3-2** | Run DB migrations (rini 015–019) on production Server 2 | [ARJUN] | 🔴
```
IMPORTANT: Run on current Server 2 (not new server) while it's still live
Commands:
  scp configs/env-changes/run-rini-migrations.sh ec2-user@13.203.181.76:~
  ssh ec2-user@13.203.181.76
  ./run-rini-migrations.sh --dry-run  (review output first)
  ./run-rini-migrations.sh            (run for real)
Verify: All 5 migrations print [OK], table counts correct for migration 017
Time: 30 min
Depends: A0-6 (script ready)
```

**A3-3** | Deploy all containers on new server | [ARJUN] | 🔴
```
Commands (Agent will generate exact sequence):
  1. Pull Docker images from Docker Hub
  2. docker compose -f configs/prod/docker-compose-new-server.yml up -d
  3. docker ps — verify all containers healthy
  4. Smoke test each service:
       curl http://localhost:3005/health
       curl http://localhost:8005/health
       curl http://localhost:3000/api/health
       curl http://localhost:8000/health
Time: 30 min
Depends: A3-1 (server bootstrapped), A3-2 (DB has correct schema), A0-9 (code smoke tested)
```

**A3-4** | PostgreSQL SSL enable on new server | [ARJUN] | 🔴
```
File: configs/postgresql/01_enable_ssl.sh
Run on new server (not Server 2 — too risky mid-flight)
Acceptance: psql connection shows SSL active, openssl s_client confirms
Time: 20 min
Depends: A3-1
```

**A3-5** | Create per-service PostgreSQL users | [ARJUN] | 🔴
```
File: configs/postgresql/03_create_db_users.sql
Run: psql -U postgres -f 03_create_db_users.sql
Creates: app_consumer (thinkvelocity_prod), app_enterprise (enterprise),
         app_python_ai (read on both), app_readonly (read-only), backup_user
Acceptance: \du shows all 5 users, each with correct grants only
Time: 15 min
Depends: A3-1
```

**A3-6** | Data migration from Server 2 → new server | [ARJUN] | 🔴
```
Agent will generate exact commands. Sequence:
  1. pg_dump on Server 2: localpgvelocity + enterprise DBs
  2. Transfer dump file to new server
  3. pg_restore on new server
  4. Verify row counts match (Agent generates verification query)
  5. Run rini migrations 015–019 on new server DB (same script as A3-2)
Downtime: Zero for this step (Server 2 still live, new server is shadow)
Time: 45 min
Depends: A3-1, A3-2
```

**A3-7** | SSL certificates via Certbot | [ARJUN] | 🔴
```
DO ONLY AFTER DNS is pointed to new server (A3-9)
Commands:
  certbot --nginx -d thinkvelocity.in -d www.thinkvelocity.in
  certbot --nginx -d api.thinkvelocity.in
  certbot --nginx -d enterprise.thinkvelocity.in
Verify: HTTPS on all 4 domains, no mixed content warnings
Time: 15 min
Depends: A3-8 (DNS pointed)
```

**A3-8** | Lower DNS TTL (do 24h before cutover) | [ARJUN] | 🔴
```
In DNS provider: Set TTL = 60 seconds for:
  thinkvelocity.in
  www.thinkvelocity.in
  api.thinkvelocity.in
  enterprise.thinkvelocity.in
Why: Enables rapid rollback if cutover fails
Time: 5 min
WHEN: 24h before you plan to flip DNS
```

**A3-9** | DNS flip — point all domains to new server | [ARJUN] | 🔴
```
Update A records simultaneously:
  thinkvelocity.in          → <NEW_ELASTIC_IP>
  www.thinkvelocity.in      → <NEW_ELASTIC_IP>
  api.thinkvelocity.in      → <NEW_ELASTIC_IP>
  enterprise.thinkvelocity.in → <NEW_ELASTIC_IP>
Immediate verification:
  curl -sk https://thinkvelocity.in/health → 200
  curl -sk https://api.thinkvelocity.in/health → 200
  curl -sk https://enterprise.thinkvelocity.in/backend/health → 200
ROLLBACK TRIGGER: any endpoint returns non-200 in first 15 minutes
  Rollback: flip DNS back (TTL=60s, effect in 1 min)
Time: 5 min to flip, 15 min monitoring
Depends: A3-6, A3-7, QA pass
```

---

### BLOCK A4 — QA (Day 5–6, all owners)
*Full validation on consolidated system*

---

**A4-1** | Consumer end-to-end QA | [ARJUN + ANIKET] | 🔴
```
Test on new server (via /etc/hosts override before DNS flip):
  <NEW_IP> thinkvelocity.in
  <NEW_IP> api.thinkvelocity.in

Test cases:
  [ ] Extension: login → enhance (Fast mode) → output appears via SSE
  [ ] Extension: enhance (Best mode) → different output, more detailed
  [ ] Extension: enhance (Media mode) → correct system prompt applied
  [ ] Extension: enhance (Saver mode) → minimal output
  [ ] Extension: mode nudge appears on technical prompt in Fast mode
  [ ] Extension: mode nudge click → re-enhances in suggested mode
  [ ] Extension: refine from output screen → clarify questions appear
  [ ] Extension: copy button fires output_copied PostHog event
  [ ] Extension: paywall hits at correct prompt count (5–7)
  [ ] Web: thinkvelocity.in loads (NextJS static)
  [ ] Web: enhance works via web UI
  [ ] Memory panel: shows user's essences from processed_contexts
  [ ] Context panel: shows user's domains and intents
Acceptance: All checkboxes pass, no console errors, no 500s in logs
```

**A4-2** | Enterprise end-to-end QA | [ANIKET + PRADEEP] | 🔴
```
Test cases:
  [ ] Enterprise extension: enterprise login form appears in-panel
  [ ] Enterprise login: valid credentials → enterprise workspace loads
  [ ] Guardrail check: clean prompt → ALLOW → enhance streams
  [ ] Guardrail check: WARN prompt → warning banner + Proceed/Cancel
  [ ] Guardrail check: BLOCK prompt → hard block, no enhance path
  [ ] Enterprise enhance: output streams via SSE from python-ai-unified
  [ ] Enterprise admin: NestJS dashboard loads
  [ ] Consumer mode: enterprise user can switch to consumer mode
  [ ] Mode switcher visible only when both sessions active
Acceptance: All checkboxes pass
```

**A4-3** | Release checklist sign-off | [ARJUN] | 🔴
```
Before Chrome Store submission, verify:
  [ ] All health endpoints return 200
  [ ] All Docker containers healthy (docker ps)
  [ ] DB row counts match pre-migration counts
  [ ] Backups running (S3 has at least 1 file)
  [ ] SSL valid on all domains
  [ ] No secrets in logs (grep for API key patterns in docker logs)
  [ ] Privacy policy live at thinkvelocity.in/privacypolicy/
  [ ] notifications removed from extension manifest
  [ ] Extension version bumped (3.9.1 → 3.9.2 or 4.0.0)
Acceptance: All items checked
```

**A4-4** | Extension update submission | [ARJUN] | 🔴
```
Steps:
  1. Build extension zip from Sidebar_extension/ folder
  2. Go to Chrome Developer Console
  3. Upload new zip (auto-increments version)
  4. Confirm privacy policy URL is correct
  5. Submit for review
Expected review time: 1–3 days
Depends: A4-1, A4-2, A4-3, A1-4 (privacy policy live)
```

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## TRACK B — KEEP PRODUCT LIVE (Team)
## Work on current system. Code merges to consolidated on cutover.
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

---

### BLOCK B0 — EXTENSION UX (Aniket + Ananya, Days 1–3)

**B0-1** | Implement mode nudge in output view | [ANIKET/ANANYA] | 🟡
```
Spec: docs/mode-nudge-spec.md (generated by Agent in A0-7)
File: Sidebar_extension/panel/consumer/output-view.js
Logic:
  - Read intent + domain from enhance response metadata
  - Map to suggested mode (see A0-7 spec)
  - Show chip: "This looks like [domain] — try [Mode]"
  - On click: fire mode_nudge_clicked, switch mode, re-enhance
Fire PostHog: mode_nudge_shown, mode_nudge_clicked
Acceptance: Nudge appears on technical prompt in Fast mode, clicking re-enhances
Depends: A0-5 (mode mapping done), A0-7 (spec ready)
```

**B0-2** | Output actions (copy + use in AI) | [ANANYA] | 🟡
```
File: Sidebar_extension/panel/consumer/output-view.js
Actions:
  Copy button: copies enhanced prompt to clipboard, fires output_copied PostHog event
  "Use in [Platform]" button: injects enhanced prompt into current AI platform input
Fire PostHog: output_copied {mode, platform, session_prompt_count}
Acceptance: Copy fires event, inject puts text in ChatGPT/Claude input
```

**B0-3** | Refine flow from output screen | [ANIKET] | 🟡
```
File: Sidebar_extension/panel/consumer/output-view.js
Action: Refine button opens clarify/refine flow without losing current output
Current output must be preserved as previous_enhanced_prompt in refine request
Fire PostHog: refine_triggered {from_mode, session_prompt_count}
Acceptance: Output → Refine → questions appear → user answers → refined output appears
```

**B0-4** | Mode buttons wired to correct API mode strings | [ANANYA] | 🔴
```
Files: Sidebar_extension/panel/consumer/composer-bar.js (or similar)
Current state: Unknown if mode buttons send correct internal strings
Required: Fast → 'flash', Best → 'research', Media → 'media', Saver → 'caveman'
Check context: context.mode in enhance request body
Acceptance: Each mode button sends correct string, verify in network tab
```

**B0-5** | Fix Claude.ai injection (53% enhancement rate = broken) | [ANIKET] | 🟡
```
File: Sidebar_extension/content/claude-extractor.js
Problem: 46% of Claude users don't complete enhance (input selector wrong or timing issue)
Debug: Open Claude.ai, open panel, try enhance, check console for injection errors
Fix: Update input field selector or fix injection timing
Acceptance: Enhancement rate on Claude.ai reaches >85%
```

**B0-6** | Fix Gemini injection (62% enhancement rate) | [ANIKET] | 🟡
```
File: Sidebar_extension/content/gemini-extractor.js
Same approach as B0-5
Acceptance: Enhancement rate on Gemini reaches >80%
```

**B0-7** | Version history navigation | [ANANYA] | 🟢
```
File: Sidebar_extension/panel/consumer/versions-view.js
Action: Show previous enhanced versions, user can restore
Acceptance: User sees list of previous enhancements, clicking one restores it
```

---

### BLOCK B1 — ANALYTICS + PAYWALL (Aakash, Days 1–4)

**B1-1** | Wire PostHog events in extension | [AAKASH] | 🔴
```
Source: docs/analytics-events-spec.md (generated by Agent in A0-8)
Add PostHog.capture() calls at the correct locations in:
  Sidebar_extension/features/consumer-enhance-flow.js
  Sidebar_extension/panel/consumer/output-view.js
  Sidebar_extension/panel/consumer/composer-bar.js
Required first: enhance_started, enhance_completed, output_copied, paywall_hit
Acceptance: Open PostHog dashboard, trigger actions, events appear within 30s
```

**B1-2** | Paywall: move limit from 3 to 5–7 prompts | [AAKASH] | 🔴
```
Context (D-023): Data proves 3-prompt wall kills habit before it forms.
  At 3 prompts: 44% of users drop off
  At 5 prompts: 29% of users remain (better habit formation window)
Backend: Node.js backend-V1 token/limit logic
Extension: paywall UI display
Change: Free tier gets 5 prompts (not 3) before paywall
Fire PostHog: paywall_hit {session_prompt_count, mode, plan_type}
Acceptance: User can run 5 enhances before seeing paywall, event fires correctly
```

**B1-3** | Paywall UI: display clear upgrade prompt | [AAKASH] | 🟡
```
When paywall hit: show modal/banner with:
  - How many prompts they've used
  - What they get with Pro
  - CTA to upgrade → opens thinkvelocity.in/pricing
Acceptance: Modal appears on 5th enhance, CTA works
```

**B1-4** | Win/loss computation in analytics | [AAKASH] | 🟡
```
In extension: start 60s timer on enhance_completed
If output_copied fires within 60s: session_win event
If timer expires without copy: session_loss event
In analytics dashboard: add win_rate metric to main page
  win_rate = session_wins / (session_wins + session_losses)
Target: visible on Dashboard-nextjs main page
Acceptance: Win rate visible in dashboard, tracking correctly
```

**B1-5** | Mode performance comparison in dashboard | [AAKASH] | 🟢
```
File: analytics/Dashboard-nextjs/src/app/prompts/page.jsx
Add: breakdown of win rate per mode (Fast vs Best vs Media vs Saver)
Data source: save_enhance_prompt.mode + has output_copied signal
Acceptance: Chart shows which modes have highest win rates
```

**B1-6** | Ritual users identification query | [AAKASH] | 🟢
```
Pull list of 81 ritual users (same-hour usage 3+ days/week for 3+ weeks)
SQL query: analytics/Dashboard-nextjs/src/lib/db.js (add getRitualUsers function)
Output: CSV of user_id, email, ritual_pattern, total_prompts
Send to Arjun for personal outreach
Acceptance: List generated, exported as CSV
```

---

### BLOCK B2 — CONTEXT + MEMORY UI (Aniket, Days 2–5)

**B2-1** | Context Engine visible in panel | [ANIKET] | 🟡
```
File: Sidebar_extension/panel/consumer/context-view.js
Data source: GET /api/v1/processed-context/public/user/{userId} (Node backend)
Show: User's top domains, recent intents, last active platform
Purpose: User sees "Velocity knows you work in [domain], [intent]"
Acceptance: Context view loads real data, not placeholder
Depends: Context engine processing conversations (already happening in background)
```

**B2-2** | Memory panel wired to live processed_contexts | [ANIKET] | 🟡
```
File: Sidebar_extension/panel/consumer/collection-memory-views.js
Data source: GET /api/v1/processed-context/public/user/{userId}
Show: List of essences (memories), each with domain, intent, date
Allow: Edit essence (PATCH /session/:sessionId/essence), soft delete
Acceptance: Memory panel shows real user memories, edit/delete work
```

---

### BLOCK B3 — ENTERPRISE DELIVERY (Pradeep + Aniket, Days 2–5)

**B3-1** | VYGR team access and onboarding | [PRADEEP] | 🟡
```
Steps:
  Collect all VYGR team email IDs
  Create enterprise accounts in NestJS admin
  Set up company policy (what prompts are allowed)
  Create admin fallback account
  Test: VYGR user can log in, enhance, see guardrail check working
Acceptance: VYGR team of N users can all log in and use enterprise features
```

**B3-2** | Enterprise extension end-to-end flow | [ANIKET + PRADEEP] | 🟡
```
Test the full flow on current enterprise.thinkvelocity.in (before new server):
  Login → guardrail check → enhance streams → context saved → admin sees usage
Document any failures for QA phase
```

---

### BLOCK B4 — CONTENT + LEGAL (Arjun + Ananya)

**B4-1** | Landing page | [ANANYA] | 🟢
```
Location: thinkvelocity.in (Vel-Next-Live-working, probably pages/ or app/)
Minimum required sections:
  Hero: headline + CTA (Add to Chrome)
  What it does: 3 bullets
  Modes: Fast/Best/Media/Saver cards
  Social proof: user count, testimonials if any
  Footer: Privacy Policy link, Contact, Enterprise link
Acceptance: Page loads, CTA links to Chrome Web Store extension page
```

**B4-2** | Pro user outreach | [AAKASH] | 🟢
```
Pull email list from analytics: pro users + high-usage free users
Write 3 variants of outreach email (warm, inform about new features, launch)
Send via Brevo (not SendGrid — migrated in rini)
Track: opens, clicks, upgrades
Acceptance: Campaign sent to list, tracked in Brevo dashboard
```

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## DURING CHROME STORE REVIEW (Block C)
## Do while review is pending (1–3 days)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**C1** | Deploy observability stack | [ARJUN] | 🟡
```
Command: cd /opt/observability && docker compose -f configs/observability/docker-compose.yml up -d
Verify: Grafana loads at grafana.thinkvelocity.in (IP allowlisted)
Acceptance: Prometheus scraping all 5 services, Loki receiving logs, alerts configured
```

**C2** | S3 backup deployment | [ARJUN] | 🟡
```
Create S3 bucket: thinkvelocity-backups (ap-south-1)
Deploy: sudo cp configs/backup/pg-backup.sh /opt/backup/ && chmod 750
Crontab: 0 2 * * * /opt/backup/pg-backup.sh (daily 2am IST)
Test: /opt/backup/pg-backup.sh (manual run, verify S3 object created)
Acceptance: S3 bucket has at least 1 backup file
```

**C3** | WireGuard private networking | [ARJUN] | 🟡
```
After new server is live, install WireGuard mesh (10.100.0.0/24)
Configs: configs/wireguard/
Why: Enables closing public PostgreSQL/Redis ports on old servers during decommission
Acceptance: ping 10.100.0.1 from new server works
```

**C4** | Old server cleanup | [ARJUN] | 🟢
```
After DNS flip confirmed clean for 48h:
  Stop all containers on old servers (do NOT terminate yet)
  Wait 48h
  Terminate Server 1, Server 2, Server 3 instances
  Close AWS Security Groups
  Release old Elastic IPs if any
Estimated cost saving: ~$55/mo
```

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## TRACK E — SERVER EVOLUTION (Agent + Arjun)
## New server 35.154.138.184 is LIVE. DNS flip pending.
## Updated: 2026-06-12
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

---

### BLOCK E0 — COMPLETED (as of 2026-06-12)

**E0-1** | New consolidated server provisioned and bootstrapped | [DONE] | ✅
```
Server: 35.154.138.184
Running: tv-extension-api :8000, tv-python-ai-unified :8005, tv-nestjs-enterprise :3000, postgres17, redis
Nginx: catch-all on port 80 → proxies to 127.0.0.1:8000
```

**E0-2** | Admin panel built and deployed | [DONE] | ✅
```
Live at: http://35.154.138.184/admin
Auth: PBKDF2-SHA256, httpOnly sessions, CSRF
Roles: super_admin, admin, support_ops, read_only
DB: 5 admin tables in thinkvelocity_prod via app_admin user
Dashboard: live metrics (5,510 users, active subscriptions)
User list: paginated, search, subscription status from real usertable
Commits: c97e0f5 (admin panel), 0fbcc6d (wire to PostgreSQL)
```

**E0-3** | Media pipeline v2 deployed to tv-python-ai-unified | [DONE] | ✅
```
Hot-patched into running container
Note: Must rebuild Docker image (T-070) to make this non-hot-patch
```

---

### BLOCK E1 — IMMEDIATE (do now, no approval needed)

**E1-1** | Fix MODERATION_SERVICE_URL + fail-closed — DONE (2026-06-12) | [AI] | ✅
```
Fixed /opt/deploy/enterprise.env: ai/enhance → ai
Patched guardrail.service.js (5 lines): fail-open ALLOW → fail-closed BLOCK
Container restarted. Verified: POST /ai/moderation/check → {"decision":"REDACT","confidence":0.95}
```

**E1-2** | Fail-closed decision made + implementation in progress | [DONE] | ✅
Decision: fail-closed — moderation unavailable → BLOCK. Logged D-030. Hot-patch script generated (configs/hotpatches/guardrail-fail-closed.sh).
```
Current behavior: if moderation service unreachable → default to ALLOW
Recommended: fail-closed → BLOCK with error code "moderation_unavailable"
  This is appropriate for an enterprise compliance product.

File to update (after decision): guardrail.service.js callModerationService() catch block
  Current: return { decision: 'ALLOW', confidence: 0, reason: 'moderation service error' }
  Proposed: throw new ModerationUnavailableError() → caller handles as BLOCK

Depends: E1-1 (fix URL first, then decide policy)
Acceptance: explicit decision logged in DECISION_LOG.md as D-030
```

**E1-3** | Certbot SSL on 35.154.138.184 | [ARJUN] | 🔴
```
Run BEFORE DNS flip — Chrome extension requires HTTPS and will break on DNS flip
if cert is not ready.

Pre-req: Lower DNS TTL to 60s for all domains 24h before flip.

Commands (SSH to 35.154.138.184):
  sudo certbot --nginx -d api.thinkvelocity.in
  sudo certbot --nginx -d enterprise.thinkvelocity.in
  sudo certbot --nginx -d thinkvelocity.in -d www.thinkvelocity.in

Note: Certbot needs DNS to point to this server to complete ACME challenge.
Sequence: Lower TTL → wait 24h → DNS flip → Certbot runs → verify HTTPS

Depends: nothing code-wise; requires DNS control
Acceptance: https://api.thinkvelocity.in returns valid Let's Encrypt cert
```

**E1-4** | DNS flip: all domains → 35.154.138.184 | [ARJUN] | 🔴
```
Update A records simultaneously:
  api.thinkvelocity.in          → 35.154.138.184
  thinkvelocity.in              → 35.154.138.184
  www.thinkvelocity.in          → 35.154.138.184
  enterprise.thinkvelocity.in   → 35.154.138.184

Immediate verification (run within 2 min of flip):
  curl -sk https://api.thinkvelocity.in/health      → 200
  curl -sk https://enterprise.thinkvelocity.in/backend/health → 200

Rollback trigger: any endpoint non-200 for >5 min
  Rollback: flip DNS back (TTL=60s, effect in 1 min)

Depends: E1-3 (SSL certs ready)
Acceptance: All domains resolve to 35.154.138.184 with valid HTTPS
```

---

### BLOCK E2 — ARCHITECTURE UNIFICATION (Pending Arjun approval)

> Design delivered in 2026-06-12 session. Tasks created. **DO NOT execute until Arjun approves plan.**
> See session conversation for full architecture reasoning and decision points.

**E2-1** | Phase 1: Single prompt plane — re-point consumer to tv-python-ai-unified | [AGENT+ARJUN] | 🟡
```
Action: Update nginx on 35.154.138.184 so api.thinkvelocity.in/dev/test/* routes
to port 8005 instead of 8000 for enhance/refine paths.
Run dual (both ports) for 1 week, monitor for differences.
Decision: does tv-extension-api keep auth+admin+storage only, or fully retire?

Files: nginx catch-all conf on 35.154.138.184
Depends: E1-4 (DNS flipped), T-066 (RECONCILE.md verified)
BLOCKED: Awaiting architecture plan approval
```

**E2-2** | Phase 2: Policy as pipeline stage — DONE (commit 90f48b7) | [AGENT] | ✅
```
File: python-ai-unified/routers/ai/enhance.py
enterprise_id detection + in-process moderation before enhance
BLOCK→SSE error, REDACT→scrub prompt, WARN→stamp metadata, ALLOW→normal
Fail-closed D-030: moderation exception → BLOCK
Consumer requests completely unaffected
```

**E2-3** | Phase 3: Context engine enterprise evolution — DONE (commit a2c033b) | [AGENT] | ✅
```
File: python-ai-unified/routers/context.py
enterprise_id/team_id partition keys in pgvector
PII redaction before embed (SSN, CC, email, phone → [REDACTED:TYPE])
Enterprise persistence → /api/v1/enterprise-context
Audit events at INFO level
Consumer requests completely unaffected
```

**E2-4** | Phase 4: Rebuild Docker images (decommission hot-patches) | [AGENT+ARJUN] | 🟢
```
Build tv-python-ai-unified image from current codebase (folds in media-pipeline-v2)
Build tv-extension-api image (folds in admin panel)
Push to Docker Hub, update containers from proper images
Hot-patches stop being load-bearing

Depends: E2-1, E2-2, E2-3
BLOCKED: Awaiting architecture plan approval
```

---

## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## POST-LAUNCH (Block D)
## ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| ID | Task | Owner | Notes |
|---|---|---|---|
| D1 | SOC2 Type 1 audit prep | Arjun | Subscribe to Vanta/Drata, engage auditor |
| D2 | Full personalization system | Arjun | Park until post-launch |
| D3 | Button expansion + injection modal | Aniket | Extension enhancement |
| D4 | Autocorrect / SLM layer | Aakash | Quality improvement |
| D5 | Profile page redesign | Ananya | Blocked on design |
| D6 | CloudFront evaluation | Arjun | Revisit at 50k users |
| D7 | RDS migration evaluation | Arjun | Revisit at 10x user growth |
| D8 | PgBouncer connection pooling | Agent | Needed at scale |
| D9 | Multi-provider LLM fallback on all services | Aakash | Server 3 already has it |
| D10| Ritual users personal outreach | Arjun | 81 users, highest conversion |

---

## OWNER SUMMARY

### AGENT (Claude/Grok/Codex/Gemini) — Code tasks
```
TODAY:
  A0-1: Remove notifications from manifest.json         (5 min)
  A0-2: /context/* router rewrite                       (4 hrs)
  A0-3: /ai/moderation/* routes                         (3 hrs)
  A0-4: /ai/prompt/find wiring                          (2 hrs)
  A0-5: Mode mapping Fast/Best/Media/Saver              (1 hr)
  A0-6: DB migrations script 015–019                    (1 hr)
  A0-7: Mode nudge spec                                 (45 min)
  A0-8: Analytics event spec                            (45 min)
DAY 2:
  A0-9: Smoke test unified service
  A2-1: Server bootstrap script
  A2-2: Production docker-compose.yml
  A2-3: Nginx vhost configs (all 4 domains)
```

### ARJUN — AWS + Deploy + Legal
```
TODAY:
  A1-1: Provision Lightsail instance (10 min)
  A1-2: Assign Elastic IP, send to Claude (5 min)
  A1-3: Set firewall rules (5 min)
  A1-4: Publish privacy policy (15 min) ← CRITICAL PATH
  A1-5: Confirm contact emails (10 min)
DAY 2:
  A3-1: Run bootstrap script on new server
  A3-2: Run DB migrations on Server 2
DAY 3-4:
  A3-3: Deploy all containers
  A3-4: PostgreSQL SSL enable
  A3-5: Create per-service DB users
  A3-6: Data migration
  A3-8: Lower DNS TTL (24h before flip)
DAY 5:
  A3-7: Certbot SSL (after DNS pointed)
  A3-9: DNS flip
DAY 6-7:
  A4-3: Release checklist
  A4-4: Chrome Store submission
```

### ANIKET — Extension UI + Context + Enterprise
```
Days 1–3: B0-1 (mode nudge), B0-3 (refine flow), B0-5 (Claude fix), B0-6 (Gemini fix)
Days 2–4: B2-1 (context visible), B2-2 (memory wired)
Days 3–5: B3-1 (VYGR access), B3-2 (enterprise E2E)
```

### AAKASH — Analytics + Paywall
```
Days 1–2: B1-1 (PostHog events), B1-2 (paywall 3→5 prompts)
Days 2–3: B1-3 (paywall UI), B1-4 (win/loss computation)
Post-launch: B1-5 (mode analytics), B1-6 (ritual users)
```

### ANANYA — Extension UX + Landing
```
Days 1–3: B0-2 (output actions), B0-4 (mode buttons)
Post-launch: B0-7 (version history), B4-1 (landing page)
```

### PRADEEP — Enterprise
```
Days 2–5: B3-1 (VYGR onboarding), B3-2 (enterprise E2E)
```

---

## CRITICAL PATH DIAGRAM

```
TODAY         DAY 2       DAY 3       DAY 4-5     DAY 6       DAY 7-10
  │             │           │            │           │            │
  │ A1-4 ─────────────────────────────────────────► A4-4 ──►  Review
  │ Privacy                                         Store Sub   (1-3d)
  │ Policy                                                        │
  │                                                               │
  │ A0-2 ─────► A0-9 ─────► A3-3 ─────► A4-1 ─────► A4-3       │
  │ context/*   smoke        deploy       QA          checklist   │
  │ router      test                                              │
  │                                                               │
  │ A1-1 ─► A1-2 ─► A3-1 ─► A3-6 ─► A3-8/9                     │
  │ Provision  IP    Boot     Data    DNS flip                    │
  │                                                               ▼
  │                                                           LAUNCH
  │
  └── Team track (parallel, no blocking):
      B0-1 (nudge), B1-1 (events), B1-2 (paywall), B2-1 (context UI)

Minimum launch: Day 8–10 if A0 completes today
```

---

## DECISIONS REFERENCE (quick lookup)

| Decision | What | Why |
|---|---|---|
| D-019 | python-ai-unified reuses local core | Source IS this repo — no SSH needed |
| D-021 | Keep Node.js + NestJS separate | SOC2 auth isolation |
| D-022 | No CloudFront, no Lambda | Wrong scale, breaks SSE |
| D-023 | Move paywall 3→5-7 prompts | Behavioral data: wall kills habit |
| D-024 | Active mode nudges in output | 60x conversion lift at 4+ modes |
| D-025 | Single 8GB Lightsail | All services on localhost |
| D-026 | S3 for uploads + backups only | No CloudFront at this scale |

Full decision log: DECISION_LOG.md (D-001 to D-026)
Full context: AGENT_CONTEXT.md
