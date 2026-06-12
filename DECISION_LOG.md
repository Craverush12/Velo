# ThinkVelocity — Decision Log

> **For AI Agents:** Every architectural or implementation decision that is non-obvious must be logged here.
> Format: `## D-NNN — [Short title]` with date, context, decision, rationale, and trade-offs.
> This log is append-only. Never delete or edit past entries.

---

## D-001 — Keep Three Separate Servers (Not Consolidate to Two)

**Date:** 2026-05-25  
**Made by:** Architecture analysis (Claude)  
**Status:** ACCEPTED

**Context:** Three AWS servers exist. Server 1 (1GB) runs only the extension API. Could be merged into Server 2 (4GB) to save cost.

**Decision:** Keep 3 separate servers. Upgrade Server 1 RAM (T-050) rather than consolidating.

**Rationale:**
- Extension API has different users (Chrome extension), different auth model, different deployment cadence from the consumer web app
- Consolidating Server 1 into Server 2 would mix concerns and make the deployment surface larger
- At $10-20/month for a 2GB Lightsail instance, the cost of a separate server is negligible vs. the operational complexity of merging

**Trade-off accepted:** Slightly higher monthly cost. Eliminated by the isolation benefit.

---

## D-002 — localpgvelocity Is the Canonical Database (Not localVelo)

**Date:** 2026-05-25  
**Made by:** Architecture analysis (Claude)  
**Status:** ACCEPTED

**Context:** Two nearly identical databases exist on Server 2:
- `localpgvelocity` — 89MB, 52 tables, has the user data (5,150 users)
- `localVelo` — 24MB, 53 tables, 2 extra tables, less data

**Decision:** `localpgvelocity` is canonical. Add its 2 missing tables (`inactive_email_sent`, `referral_relations`) from `localVelo`, then rename to `thinkvelocity_prod` and drop `localVelo`.

**Rationale:**
- `localpgvelocity` has 4x more data → has been in use longer → is the active database
- `localVelo` only has 2 tables that `localpgvelocity` lacks → easier to add those than to migrate the full 89MB
- Rename to `thinkvelocity_prod` gives it a clear canonical identity

**Trade-off accepted:** If `localVelo` has active writes from a service we haven't identified, we may miss data. Mitigation: do a 48h comparison of row counts in each DB before dropping `localVelo`.

---

## D-003 — WireGuard (Not SSH Tunnel or VPC Peering) for Private Networking

**Date:** 2026-05-25  
**Made by:** Architecture analysis (Claude)  
**Status:** ACCEPTED

**Context:** Server 3 connects to Server 2's PostgreSQL over the public internet. Needs a private networking solution. Options:
1. SSH tunnel (port forwarding)
2. WireGuard VPN
3. AWS VPC Peering (Lightsail ↔ EC2)
4. AWS PrivateLink

**Decision:** WireGuard VPN mesh between all 3 servers.

**Rationale:**
- SSH tunnels are fragile — they drop on connection reset and need a process manager to stay up
- AWS VPC Peering between Lightsail and EC2 requires Lightsail VPC peering feature which has limitations and is more complex to set up correctly
- WireGuard is kernel-native on Ubuntu 24.04 and AlmaLinux 9, zero-overhead once running, extremely stable
- WireGuard gives us a permanent private network (10.100.0.0/24) that all future servers can join

**Trade-off accepted:** WireGuard adds a new operational surface (key management). Mitigated by the simplicity of WireGuard key rotation.

---

## D-004 — Merge Context Engine Into Python AI (Not Keep Separate)

**Date:** 2026-05-25  
**Made by:** Architecture analysis (Claude)  
**Status:** ACCEPTED

**Context:** The Context Engine is a separate Docker container (port 8001) running a FastAPI service that does one thing: convert chat conversations into user context objects. It currently calls the Node.js DEV backend for callbacks.

**Decision:** Merge context extraction endpoint into the Python AI service (port 8005). Remove the separate container.

**Rationale:**
- Context extraction is a natural concern of the AI backend, not a separate service
- Running a separate container for a single endpoint adds operational overhead (another container to monitor, restart, update)
- The current implementation calls the Node.js DEV backend — this is wrong in production; merge gives us the opportunity to fix the callback to point to prod
- Reduces Server 2 from 5 containers to 3 containers (after also removing dev containers)

**Trade-off accepted:** Slightly larger Python AI container. Acceptable — Python AI already has LangChain; context extraction is lightweight.

---

## D-005 — AWS Secrets Manager (Not HashiCorp Vault or Doppler) for Secrets

**Date:** 2026-05-25  
**Made by:** Architecture analysis (Claude)  
**Status:** ACCEPTED

**Context:** Secrets currently live in `.env` files on disk and in Docker container environment variables in plaintext. Need a secrets management solution.

**Decision:** AWS Secrets Manager.

**Rationale:**
- Already on AWS — Secrets Manager is available without additional tooling or accounts
- EC2/Lightsail instances can use IAM roles for credential-free access to Secrets Manager
- Native SDK support in both Python (boto3) and Node.js (@aws-sdk/client-secrets-manager)
- Audit trail: every secret access is logged to CloudTrail
- Automatic rotation support (can automate DB password rotation later)

**Trade-off accepted:** Adds AWS SDK dependency to all services. Mitigated by keeping `.env` fallback for local development. Vault would give more control but requires running and maintaining a Vault server — not worth it at current scale.

---

## D-006 — Docker Compose (Not ECS/Kubernetes) for Current Scale

**Date:** 2026-05-25  
**Made by:** Architecture analysis (Claude)  
**Status:** ACCEPTED

**Context:** At 5,150 users, with manual deployments and Docker Compose on 3 servers. Options for container orchestration:
1. Stay with Docker Compose
2. Migrate to AWS ECS (Fargate)
3. Migrate to Kubernetes (EKS or self-managed)

**Decision:** Stay with Docker Compose now. Add ECS evaluation to Someday list (T-055) at ~50k users.

**Rationale:**
- Team is small; Kubernetes operational overhead is not justified at current scale
- ECS adds ~$50-100/month per service in Fargate costs vs. existing Lightsail instances
- Docker Compose is already working; migrations introduce risk and time cost
- At 10x users (50k), revisit this decision — ECS Fargate auto-scaling becomes valuable

**Trade-off accepted:** Cannot auto-scale. Manual scaling required if traffic spikes. Mitigated by: upgrading instance sizes when needed, monitoring (T-036), and clear runbook for emergency scaling.

---

## D-007 — Apache on Server 2, Nginx on Servers 1 and 3 (Not Unified)

**Date:** 2026-05-25  
**Made by:** Architecture analysis (Claude)  
**Status:** ACCEPTED (leave as-is, no migration)

**Context:** Server 2 uses Apache 2.4; Servers 1 and 3 use Nginx 1.24. Inconsistency but not a critical problem.

**Decision:** Do not migrate Server 2 from Apache to Nginx. Too much risk for no functional gain.

**Rationale:**
- Apache on Server 2 is running and working with a complex vhost configuration
- Migration would require recreating all proxy rules, WebSocket upgrade handling, SSL config in Nginx format
- Risk of production outage is high; benefit is only consistency
- Both Apache and Nginx are production-grade; consistency is nice but not required

**Trade-off accepted:** Inconsistency in web server config. Engineers need to know which syntax applies where.

---

## D-008 — Assign Elastic IP to Server 3 Before WireGuard Setup

**Date:** 2026-05-25  
**Made by:** Architecture analysis (Claude)  
**Status:** ACCEPTED

**Context:** Server 3 has a dynamic public IP. WireGuard configuration uses the Endpoint (public IP) of Server 2 as the hub. If Server 3's IP changes, WireGuard still works (Server 3 initiates all connections). However, DNS for the enterprise domain (`velocityenterprise.toteminteractive.in`) points to Server 3's IP — if Server 3 reboots, the domain breaks.

**Decision:** Assign Elastic IP to Server 3 (T-007) before doing anything else, as it's a prerequisite for WireGuard and domain migration work.

**Rationale:** All subsequent work on Server 3 assumes a stable IP. SSL cert issuance (T-038), WireGuard peer config, and DNS all require IP stability.

---

## D-009 — Close Port 6379 (Redis) AFTER WireGuard, Not Before

**Date:** 2026-05-25  
**Made by:** Architecture analysis (Claude)  
**Status:** ACCEPTED

**Context:** Redis port 6379 is currently accessible on Server 2's public IP. Server 3's Prompt Enhance service connects to Redis at `13.203.181.76:6379`. If we close the port before WireGuard is up, Server 3 loses Redis access and the Prompt Enhance service breaks.

**Decision:** T-002 (close Redis port) is blocked on WireGuard completion (T-009 to T-013). T-002 is listed in "Waiting On" in TASKS.md.

**Exception:** As an interim measure, can temporarily add Server 3's public IP to a firewall allowlist, then close the public rule once WireGuard is running.

---

## D-010 — Rename DB to thinkvelocity_prod (Not Keep localpgvelocity)

**Date:** 2026-05-25  
**Made by:** Architecture analysis (Claude)  
**Status:** ACCEPTED

**Context:** The canonical consumer database is named `localpgvelocity` — a name that reveals it was meant to be "local" temporary storage, not a production database name.

**Decision:** Rename to `thinkvelocity_prod` after merging with `localVelo`.

**Rationale:**
- `thinkvelocity_prod` makes the database's identity, product, and environment explicit
- Consistent naming convention: `thinkvelocity_prod`, `thinkvelocity_ext`, `enterprise`
- The rename is a single `ALTER DATABASE` statement; it's low-risk once connections are tested

---

## D-011 — Enterprise Domain Migration to thinkvelocity.in Namespace

**Date:** 2026-05-25  
**Made by:** Architecture analysis (Claude)  
**Status:** ACCEPTED

**Context:** Enterprise product is hosted at `velocityenterprise.toteminteractive.in` — a completely different root domain from `thinkvelocity.in`.

**Decision:** Migrate to `enterprise.thinkvelocity.in`. Keep the old domain as a 301 redirect for 6 months, then let it expire.

**Rationale:**
- Brand consistency: enterprise product should be under the same root domain as the main product
- `toteminteractive.in` appears to be an agency/holding company domain — not the right home for a branded product
- `enterprise.thinkvelocity.in` is clear and matches the product hierarchy

**Risk:** Users with the old domain bookmarked will follow the redirect. NestJS `ALLOWED_ORIGINS` must be updated to include the new domain.

---

*All future decisions should be added below this line in the same format.*

---

## D-012 — Use Documented Enterprise Guardrail Endpoint

**Date:** 2026-05-25  
**Made by:** Codex  
**Status:** ACCEPTED

**Context:** Phase 2 verification found the extension enterprise enhance flow calling `/backend/guardrail/check`, while the handoff, design spec, and Postman collection define `/backend/guardrail/check-prompt` with `enterpriseId` in the request body.

**Decision:** Update `IMPORTANT/Sidebar_extension/features/enterprise-enhance-flow.js` to call `/backend/guardrail/check-prompt` and include the stored enterprise id.

**Rationale:** The guardrail check is mandatory before enterprise enhancement, so the extension must match the documented backend contract rather than relying on an undocumented route alias.

**Trade-off accepted:** If the backend temporarily supports only the shorter alias, that backend should be corrected or aliased server-side; the extension now follows the canonical contract.

---

## D-013 — Fail Closed on Deploy Pre-Promotion Health Checks

**Date:** 2026-05-25  
**Made by:** Codex  
**Status:** ACCEPTED

**Context:** The generated zero-downtime deploy script started a `_new` container without production port bindings, then health-checked the normal `localhost` production URL. That could validate the old container instead of the new image.

**Decision:** Update `configs/deploy/deploy.sh` to map the localhost health port to the current container's internal port, health-check the `_new` container by Docker network IP, and fail before promotion if the mapping or IP cannot be resolved.

**Rationale:** A deployment script must prove the candidate container is healthy before stopping the old one. Failing closed is safer than a false-positive health check.

**Trade-off accepted:** The script now requires local health URLs with explicit ports and Docker networking that exposes a container IP; unusual host-network deployments need a separate explicit path before use.

---

## D-014 — Single Database With 4 Schemas (Not 3 Separate Databases)

**Date:** 2026-05-28
**Made by:** Architecture analysis (Claude)
**Status:** ACCEPTED — supersedes the 3-database target in CONTEXT_PACK.md v1.0

**Context:** The earlier consolidation plan targeted 3 databases (`thinkvelocity_ext`, `thinkvelocity_prod`, `enterprise`). On building the actual schema (`schema/v2/`), a single database `thinkvelocity_prod` with 4 schemas (`shared`, `consumer`, `enterprise`, `extension`) proved cleaner.

**Decision:** One database, four schemas. Cross-schema FKs from `consumer`/`extension` tables reference `shared.users`. Per-service DB users get `USAGE` only on the schemas they need (`schema/v2/006_users_db.sql`).

**Rationale:**
- A single database allows FK integrity across `shared` ↔ `consumer`/`extension` (impossible across separate databases)
- Schema-level `GRANT`/`REVOKE` gives the same least-privilege isolation as separate databases (SOC2 CC6.3) without losing referential integrity
- One connection pool, one backup target (`pg-backup.sh` dumps all 4 schemas in one pass), one SSL config

**Trade-off accepted:** A compromise of the `postgres` superuser exposes all 4 schemas at once. Mitigated by never using `postgres` from app code — only the scoped `app_*` users connect.

---

## D-015 — enterprise.User Is NOT Linked to shared.users

**Date:** 2026-05-28
**Made by:** Architecture analysis (Claude)
**Status:** ACCEPTED

**Context:** During schema design, the question arose whether the enterprise `User` table (NestJS/Prisma, TEXT cuid PKs) should FK into `shared.users` (INTEGER serial PKs, the consumer identity table).

**Decision:** Keep them entirely separate. `enterprise."User"` stays in the `enterprise` schema with its own auth domain, PK type (cuid/uuid TEXT), and JWT secret. No FK to `shared.users`.

**Rationale:**
- Enterprise and consumer are distinct auth domains with different login flows, token lifetimes (8h enterprise vs 15m consumer), and even different JWT secrets (SOC2 CC6.2 isolation)
- PK types are incompatible (TEXT cuid vs INTEGER serial) — forcing a link would require a fragile mapping table
- A consumer user and an enterprise user are conceptually different principals; conflating them risks privilege leakage across products

**Trade-off accepted:** A person who is both a consumer user and an enterprise user has two unrelated identities. Acceptable — that is the actual security boundary we want.

---

## D-016 — Python AI Merge Uses Server 3 (prompt-enhance) As Canonical Source

**Date:** 2026-05-28
**Made by:** SSH endpoint audit (Claude, T-031)
**Status:** ACCEPTED

**Context:** Three Python services exist: `python-backend` (Server 2 :8005), `context-engine` (Server 2 :8001), and `prompt-enhance` (Server 3 :3002). The audit (`docs/python-ai-merge-plan.md`) found that Server 2's `python-backend` (28 routes) is a **stale image** of Server 3's `prompt-enhance` (38 routes) — Server 3 has 10 newer routes (moderation, transcribe, prompt/find, refine/stream).

**Decision:** When merging into the unified Python AI service, use **Server 3's `prompt-enhance` source** as canonical for the `/ai/*` router. Port `context-engine` separately for `/context/*`. Do NOT port Server 2's code.

**Rationale:**
- Server 3 is the most mature, current build — porting the stale Server 2 code would regress 10 endpoints
- `context-engine` is independent (proxies persistence through Node.js, no direct DB) so it ports cleanly as its own router
- The Groq SDK version gap (0.22.0 in A/C vs 1.0.0 in context-engine) must be resolved by standardizing on `groq>=1.0.0`

**Trade-off accepted:** Must SSH to Server 3 to pull the canonical source rather than working from the (closer) Server 2 image. Worth it to avoid shipping stale code.

---

## D-017 — Consolidated Server Uses Nginx (Not Apache)

**Date:** 2026-05-28
**Made by:** Architecture analysis (Claude)
**Status:** ACCEPTED — supersedes D-007 for the consolidated server

**Context:** D-007 decided to leave Apache on Server 2 to avoid migration risk. But the consolidation plan builds a *new* consolidated server from scratch (`configs/prod/docker-compose.yml`), so there is no in-place migration risk — it is greenfield config.

**Decision:** The consolidated production server uses Nginx for all vhosts (`configs/prod/nginx/`). Apache is retired with the old Server 2.

**Rationale:**
- Greenfield config means no risk of breaking a running Apache setup — D-007's risk concern does not apply
- Nginx unifies the stack with Servers 1 and 3 (already Nginx); one syntax, one set of security-header/rate-limit patterns
- Nginx `limit_req`, `proxy_cookie_flags`, and streaming config (for LLM responses) are already written and SOC2-aligned

**Trade-off accepted:** The old Apache vhost rules must be fully re-expressed in Nginx (done in `configs/prod/nginx/`). Verified against all proxy paths before cutover.

---

## D-018 — Non-Root, Read-Only Containers For All Services

**Date:** 2026-05-28
**Made by:** Architecture analysis (Claude, SOC2 CC6.6 P2-T06)
**Status:** ACCEPTED

**Context:** SOC2 CC6.6 requires containers not run as root. The audit found container user privilege was unverified.

**Decision:** All 4 app Dockerfiles (`configs/prod/dockerfiles/`) create a `nonroot` user (UID 10001) and `USER nonroot` before CMD. The compose file adds `security_opt: ["no-new-privileges:true"]` to every service and `read_only: true` + `tmpfs: /tmp` to the 4 app containers.

**Rationale:**
- A non-root container limits blast radius if an app is compromised (no root in the container, no privilege escalation, no writable root FS)
- Read-only root FS prevents an attacker from writing webshells/persisting; legitimate writes go to `/tmp` (tmpfs) or named volumes
- `no-new-privileges` blocks setuid escalation even if a setuid binary exists in the image

**Trade-off accepted:** The Python AI container must pre-download the `all-MiniLM-L6-v2` model at build time (read-only FS at runtime can't write the HF cache) and route torch's compiled-kernel cache to `/tmp` via `TORCH_HOME`. Handled in `Dockerfile.python-ai`.

---

## D-019 — Unified Python AI Reuses This Repo's Local `core/` As Canonical (Refines D-016)

**Date:** 2026-05-29
**Made by:** Source-location finding + owner decision (Claude + Arjun, T-031)
**Status:** ACCEPTED — refines D-016

**Context:** D-016 assumed the canonical `/ai/*` source had to be pulled off the remote Server 3 `prompt-enhance` container via SSH/`docker cp`. While building `python-ai-unified/`, the owner confirmed — and inspection verified — that the canonical prompt-enhance logic already lives **in this repo**: `api/extension_bridge.py` (the `/dev/test/*` adapter the extension calls) delegates to the real handlers in `api/enhance.py` (`_generate`), `api/refine.py` (`_refine`, `_refine_prepare`), `api/cothinker.py` (transcribe), and `core/` (prompts, contracts, `llm.py`). The deployed Server 3 container is a packaging of this codebase, not a separate source of truth.

**Decision:** The unified service's `/ai/*` routers REUSE this repo's `core/` + `api/` logic as the single source of truth (thin adapters mapping the documented unified contracts onto the existing functions), rather than re-implementing Groq/prompt logic or porting from the remote container. `python-ai-unified/` is therefore a **façade within this monorepo**, not a standalone island: its Docker build context is the repo root, with `core/` + `api/` copied in and the repo root on `PYTHONPATH`.

**Rationale:**
- One implementation of enhance/refine/clarify — no prompt-logic drift between the local app and the unified service
- The real logic is fully readable here; no SSH/`docker cp` needed for the `/ai/*` overlap (closes most RECONCILE items immediately)
- Matches the existing, proven `extension_bridge.py` adapter pattern

**Scope / what still needs external source:**
- `/context/*` (7 routes) → the **context-engine** source (owner providing)
- `/ai/prompt/find` + `/context/*` Node persistence → the **Node backend** code (owner providing)
- `/ai/moderation/*` (7 routes) → no local equivalent; needs the deployed Server 3 source + moderation knowledge base

**Trade-off accepted:** The unified container is coupled to this repo's `core/` package (can't build it from its own subdir alone). Acceptable — it is the same monorepo and avoids maintaining two copies of the enhancement pipeline. D-016's "SSH to pull canonical" is now only needed for moderation + context-engine + node, not the core `/ai/*` routes.

---

## D-027 — MODERATION_SERVICE_URL Must Point to Base URL, Not Enhance Endpoint

**Date:** 2026-06-12
**Made by:** Architecture audit (Claude)
**Status:** ACCEPTED — Fix pending human action (T-061)

**Context:** `tv-nestjs-enterprise` had `MODERATION_SERVICE_URL=http://tv-python-ai-unified:8005/ai/enhance` in its env. The guardrail service (`guardrail.service.js`) builds the moderation URL as `${MODERATION_SERVICE_URL}/moderation/check`, producing `…/ai/enhance/moderation/check` → 404. On failure, the code falls back to ALLOW. Effect: enterprise policy checking, PII redaction, and blocking were silently disabled in production.

**Decision:** `MODERATION_SERVICE_URL` must be the base URL of the python-ai-unified service: `http://tv-python-ai-unified:8005/ai`. The guardrail service correctly appends `/moderation/check`.

**Rationale:** The root of the enterprise security model (guardrail check before every enhance) was broken and failing silently. This is the #1 production security gap.

**Trade-off accepted:** After the fix, a moderation service outage will cause failures. The fail-open vs fail-closed behavior must be explicitly decided (T-062). Recommend fail-closed for an enterprise compliance product.

---

## D-028 — Admin Panel Uses ADMIN_DATABASE_URL to Bypass STORAGE_BACKEND=local

**Date:** 2026-06-12
**Made by:** Implementation (Claude)
**Status:** ACCEPTED

**Context:** The tv-extension-api container had `STORAGE_BACKEND=local` in env, causing the admin store to fall back to JSON files instead of PostgreSQL. The admin panel needed to read live user data (5,510 users) from PostgreSQL without changing the consumer storage configuration.

**Decision:** Add a dedicated `ADMIN_DATABASE_URL` env var checked first in `storage/admin_store.py:get_default_store()`. When set, it bypasses `STORAGE_BACKEND` entirely and connects directly to PostgreSQL with a dedicated `app_admin` DB user.

**Rationale:** The cleanest solution that doesn't touch the consumer storage path, avoids the risk of inadvertently enabling PostgreSQL for consumer paths that rely on local JSON behavior, and uses least-privilege DB access (app_admin has only admin table grants, not full thinkvelocity_prod access).

**Trade-off accepted:** Admin panel DB connection is not managed by the same pool as consumer queries. Acceptable — admin traffic is low-volume and the separation is a security feature, not a bug.

---

## D-029 — tv-python-ai-unified Is the Single Prompt Brain for Both Consumer and Enterprise

**Date:** 2026-06-12
**Made by:** Architecture analysis (Claude)
**Status:** ACCEPTED — implementation plan pending Arjun approval

**Context:** Analysis of the live 35.154.138.184 server revealed that `tv-python-ai-unified` (port 8005) already serves enterprise enhance requests via nginx proxy from `enterprise.thinkvelocity.in/ai/*`. The consumer extension still routes to `tv-extension-api` (port 8000) for its enhance calls. Two separate services, one LLM brain.

**Decision:** Treat `tv-python-ai-unified` as the single prompt brain. Enterprise already uses it. Consumer will be re-pointed to it (T-067). tv-extension-api retains auth, admin, storage roles. No new prompt logic should ever be added to tv-extension-api.

**Rationale:** One prompt image = one prompt hash = no drift (the media-pipeline hot-patch divergence was the direct cost of having two images). Eliminates the class of bug where a feature ships to enterprise but not consumer or vice versa.

**Trade-off accepted:** tv-extension-api's auth/session code will need to remain maintained as a separate container. This is acceptable — auth and prompt enhancement have different scaling and deployment cadences.

---

## D-030 — Moderation Service Failures Are Fail-Closed (BLOCK, Not ALLOW)

**Date:** 2026-06-12
**Made by:** Arjun (product decision)
**Status:** ACCEPTED

**Context:** The moderation service (`tv-python-ai-unified /ai/moderation/check`) is called by the NestJS enterprise guardrail before every enhance request. The prior behavior in `guardrail.service.js` caught errors and returned `{ decision: 'ALLOW', confidence: 0, reason: 'moderation service error' }` — silently allowing all requests through when the moderation service was unreachable or returned an error.

**Decision:** Fail-closed. When the moderation service is unreachable or returns an unexpected error, the guardrail must return `{ decision: 'BLOCK', confidence: 1, reason: 'moderation_service_unavailable', guardrail: 'moderation_unavailable' }`. No enhance request may proceed without a successful moderation verdict.

**Rationale:** ThinkVelocity Enterprise is sold as a compliance product to teams with policy requirements. A moderation outage that silently permits all requests defeats the entire value proposition and creates compliance liability. Fail-open is only acceptable for consumer products; enterprise requires fail-closed.

**Trade-off accepted:** If the moderation service goes down, enterprise enhance requests will fail with a clear error. Mitigation: (1) robust health monitoring on tv-python-ai-unified, (2) the error message to the user explains it is a service issue, not a content issue, so users know to retry.

---

## TEMPLATE FOR NEW DECISIONS

```
## D-NNN — [Short decision title]

**Date:** YYYY-MM-DD  
**Made by:** [Who decided — human name, Claude, Codex]  
**Status:** ACCEPTED | REJECTED | UNDER REVIEW

**Context:** [What problem or choice prompted this]

**Decision:** [What was decided, in one sentence]

**Rationale:** [Why this is the right choice]

**Trade-off accepted:** [What downside you're living with]
```
