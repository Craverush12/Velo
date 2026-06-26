# ThinkVelocity — Antigravity Briefing Document
**Version:** 2026-06-26 | **Agent:** Antigravity (Gemini Pro) | **Authored by:** Claude Sonnet 4.6 + Arjun

> This document is the COMPLETE operational briefing for Antigravity. It supersedes AGENT_CONTEXT.md where they conflict (AGENT_CONTEXT.md is from 2026-06-12; this reflects the live state as of 2026-06-26).

---

## MISSION

ThinkVelocity is a prompt-engineering SaaS at **thinkvelocity.in**. ~5,150 registered users, live payments, Chrome extension with ~2,400 monthly active users. We are **pre-launch** on a new consolidated server and preparing for a growth push.

**Arjun (founder) runs this project.** You are Antigravity — Arjun's autonomous engineering co-pilot powered by Gemini Pro. Claude handles integration, testing, and server deployment. You handle everything else: feature code, analysis, planning, strategic tasks.

**The two of you coordinate via this repo.** Claude reads files you write here; you read files Claude writes.

---

## REPO AND LOCAL PATHS

```
C:\Users\Arjun\Desktop\ThinkVelocity\           ← PRIMARY MONOREPO (always here)
├── api/enhance.py                                ← CANONICAL enhance pipeline
├── core/llm.py                                   ← Groq client (complete, stream_completion)
├── core/contracts.py                             ← Shared types
├── core/prompts/enhance_system.md                ← System prompt (LIVE, recently updated)
├── python-ai-unified/
│   ├── routers/ai/enhance.py                     ← The main AI service router (HEAVILY modified 2026-06-26)
│   └── configs/prod/docker-compose-new-server.yml
├── FullCodebase/ThinkVelocity/
│   ├── backend-V1/                               ← Node.js Express API (live, :3005)
│   ├── Vel-Next-Live-working-ai/                 ← Next.js 15 frontend
│   │   └── src/utils/userProperties.js           ← BUG: subscription_status always 'inactive'
│   ├── Sidebar_extension/                        ← Chrome extension v3.9.1
│   │   ├── features/consumer-enhance-flow.js
│   │   ├── features/enterprise-enhance-flow.js
│   │   └── panel/consumer/output-view.js         ← Mode nudge goes here
│   └── backend-V1-ai/lib/posthog.js              ← PostHog client for Node backend
└── ANTIGRAVITY_CONTEXT.md                        ← THIS FILE
```

---

## SERVER ACCESS

**Production server:** `35.154.138.184` (AWS Lightsail, Ubuntu 24.04, 8GB)
**SSH key:** `C:/Users/Arjun/Downloads/new_velo_key.pem`

```bash
# SSH command
ssh -i "C:/Users/Arjun/Downloads/new_velo_key.pem" -o StrictHostKeyChecking=no ubuntu@35.154.138.184

# Key locations on server
/opt/deploy/thinkvelocity/        ← Git repo (branch: reconcile/quality-engine-on-prod)
/opt/deploy/python-ai.env         ← Python AI service env vars
/opt/deploy/node.env              ← Node backend env vars
/opt/deploy/enterprise.env        ← NestJS enterprise env vars
/opt/deploy/extension-api.env     ← Extension API (port 8000) env vars
```

**Running containers (as of 2026-06-26):**
| Container | Port | Status |
|---|---|---|
| tv-python-ai-unified | 127.0.0.1:8005 | HEALTHY — rebuilt today with all new changes |
| tv-extension-api | 127.0.0.1:8000 | HEALTHY — OLD service, no PostHog instrumentation |
| nodejs-pg-backend-container | 0.0.0.0:3005 | HEALTHY — **BUG: NODE_ENV=development in container** |
| tv-nestjs-enterprise | 127.0.0.1:3000 | RUNNING — BUG: MODERATION_SERVICE_URL wrong |
| tv-velocity-frontend | 127.0.0.1:8081 | RUNNING |
| postgres17 | 127.0.0.1:5432 | HEALTHY |
| redis7 | 127.0.0.1:6379 | HEALTHY |

**Key docker commands:**
```bash
# Rebuild and restart python-ai-unified
cd /opt/deploy/thinkvelocity
docker compose -f python-ai-unified/configs/prod/docker-compose-new-server.yml build python-ai-unified
docker stop tv-python-ai-unified && docker rm tv-python-ai-unified
docker compose -f python-ai-unified/configs/prod/docker-compose-new-server.yml up -d python-ai-unified

# Check logs
docker logs tv-python-ai-unified --tail 50
docker logs nodejs-pg-backend-container --tail 50

# Quick health test
curl -s http://localhost:8005/health
curl -s -X POST http://localhost:8005/ai/enhance/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"write a python function to sort a list","user_id":"smoke-test"}'
```

---

## LIVE ARCHITECTURE (2026-06-26)

### Traffic Flow
```
Internet → Nginx (:80/:443)
  thinkvelocity.ai/chat      → OLD tv-extension-api :8000  ← NO PostHog, NO quality tracing
  thinkvelocity.ai/ai/*      → tv-python-ai-unified :8005  ← FULL PostHog, quality tracing, model routing
  thinkvelocity.ai/backend/* → nodejs-pg-backend-container :3005
  Extension → /ai/enhance/chat → :8005                     ← FULL instrumentation
```

### Python AI Service (port 8005) — Current Capabilities (deployed 2026-06-26)
- **Context similarity threshold:** 0.85 (was 0.6 — reduces leakage)
- **Topic-continuity guard:** In system prompt — discards off-topic session_context
- **Pre-classifier:** `_pre_classify()` runs in parallel (zero latency overhead) using `llama-3.3-70b-versatile`
- **Intent-driven model routing:**
  - CODE intents (code_generation, debugging, code_review, testing_qa, code_conversion) → `meta-llama/llama-4-scout-17b-16e-instruct`
  - REASONING intents (architecture, research, business_strategy, financial_analysis) → `meta-llama/llama-4-scout-17b-16e-instruct`
  - CREATIVE intents (creative_writing, copywriting, marketing) → `llama-3.3-70b-versatile`
  - DEFAULT → `llama-3.3-70b-versatile`
- **Quality signals traced:** `prompt_quality_score`, `framework_used`, `pe_techniques_applied`, `expansion_ratio`
- **PostHog $ai_generation:** Fires with full quality + classification metadata
- **enterprise_citations, SSE negotiation, legacy_compat:** All preserved from production branch

### Key Env Vars (python-ai.env)
```
GROQ_API_KEY=<see /opt/deploy/python-ai.env on server>
LLM_MODEL=llama-3.3-70b-versatile
PRE_CLASSIFY_MODEL=llama-3.3-70b-versatile
MODEL_CODE=meta-llama/llama-4-scout-17b-16e-instruct
MODEL_REASONING=meta-llama/llama-4-scout-17b-16e-instruct
MODEL_CREATIVE=llama-3.3-70b-versatile
POSTHOG_CONSUMER_KEY=phc_rpm6NQqQUVxSHOq7ST2xHsPo0LZVOgp7s6FVRRZ0jTb
PROMPT_TRACE_ENABLED=true
PROMPT_TRACE_CAPTURE_FULL_TEXT=true
PROMPT_ANALYTICS_API_TOKEN=34fd368e18e0e0cfa46da8b6992b9c8f192757f500ae69f11b8ab08e5a5be836
```

---

## PRODUCT — WHAT USERS EXPERIENCE

**Core flow:** paste rough prompt → select mode → enhanced prompt in 2-4s → copy/inject into AI platform

**Four modes:**
| User Label | Internal | System Prompt | Use Case |
|---|---|---|---|
| Fast | `normal` | enhance_system.md | Quick standard |
| Best | `research` | + enhance_research_overlay.md | Deep evidence-aware |
| Media | `media` | + enhance_media_overlay.md | Images/video/design |
| Saver | `caveman` | + enhance_caveman_overlay.md | Minimal tokens |

**Additional features:** Refine (guided Q&A), CoThinker (voice via Groq Whisper), Memory (context essences stored as pgvector embeddings), Personalization, Platform injection (ChatGPT, Claude, Gemini, Cursor, etc.)

**Chrome Extension:** ID `ggiecgdncaiedmdnbmgjhpfniflebfpa`, v3.9.1, MV3 side-panel, live on Chrome Web Store. Updates take 1-3 days review (NOT 3 weeks — that's new submissions only).

---

## BEHAVIORAL DATA (the source of truth for product decisions)

### Core finding
Churners vs returners are **statistically identical** in behavior. The only difference is 2.86 vs 1.97 prompts on day 1. **Churn is caused by the 3-prompt paywall, not product quality.**

### Conversion funnel
| Modes tried | Pro conversion |
|---|---|
| 1 mode | 0.6% |
| 2 modes | 1.1% |
| 3 modes | 6.2% |
| 4+ modes | **35.7% (60x lift)** |

83.2% of users NEVER switch from their first mode. Mode nudge is the highest-leverage conversion feature.

### Platform enhancement rates (extension injection health)
| Platform | Rate | Status |
|---|---|---|
| Extension self | 95.9% | ✅ |
| ChatGPT | 84.9% | ✅ |
| Gemini | 62.3% | ❌ |
| Claude | 53.4% | ❌ |

### Retention
D1: 13.9% (benchmark 25-40%). Fix the day-1 experience = fix retention.

### Analytics win/loss
- **Win:** `output_copied` fires within 60s of enhance completion
- **Loss:** enhance_completed with no copy within 60s
- **Conversion signal:** `mode_switched` event

---

## ANALYTICS — POSTHOG (the only analytics stack)

**Project:** 296904 | **Consumer key:** `phc_rpm6NQqQUVxSHOq7ST2xHsPo0LZVOgp7s6FVRRZ0jTb`

PostHog is the ONLY analytics source. Mixpanel is dead/deprecated.

### What's instrumented (working)
- Extension → `/ai/enhance/chat` (port 8005): `$ai_generation` fires with full quality + classification metadata
- Node backend: PostHog key set, fires subscription events

### What's broken/missing
- **Web chat** → port 8000 (old service): no `$ai_generation`, no quality tracing
- **Pro identity:** `buildUserTraits()` always sets `subscription_status: 'inactive'` on every page load (localStorage doesn't store subscription_status, falls to default)
- **Surveys:** 3 surveys exist as drafts, never activated
- **Feature flags:** `paywall-copy-ab` and `mode-nudge-placement` exist but not wired to frontend

### Required events not yet firing
```
enhance_started        { mode, platform, prompt_length, user_id }
enhance_completed      { mode, platform, intent, domain, tokens, processing_ms }
output_copied          { mode, platform, session_prompt_count }   ← WIN signal
mode_nudge_shown       { suggested_mode, trigger_domain }
mode_nudge_clicked     { suggested_mode, accepted: bool }
mode_switched          { from_mode, to_mode }
paywall_hit            { prompts_in_session, mode, plan }
```

---

## OPEN BUGS AND GAPS

### P0 — User-facing, blocking launch

| # | Gap | File/Location | Confirmed? |
|---|---|---|---|
| G-01 | Pro identity broken: every page load overwrites PostHog `subscription_status` to `'inactive'` | `Vel-Next-Live-working-ai/src/utils/userProperties.js:65` — `getLocalTraits()` doesn't read subscription_status | ✅ Code verified |
| G-02 | Node backend container runs `NODE_ENV=development` despite node.env having `production` | Docker container startup | ✅ Live-verified |
| G-03 | Web chat observability dead: `/chat` calls port 8000 which has zero PostHog instrumentation | `tv-extension-api` has no `$ai_generation` | ✅ Architecture confirmed |
| G-04 | Platform injection failing: Claude 53.4%, Gemini 62.3% enhancement rate | `Sidebar_extension/content/claude-extractor.js`, `gemini-extractor.js` | ✅ Behavioral data confirmed |
| G-05 | Mode nudge missing: 83.2% users never switch mode, 60x conversion lift at 4+ modes | `Sidebar_extension/panel/consumer/output-view.js` | ✅ Behavioral data |
| G-06 | Paywall at 3 prompts causing churn (D-023) | Node.js token limit middleware | ✅ Behavioral data |

### P1 — Broken infrastructure, high risk

| # | Gap | Fix |
|---|---|---|
| G-07 | T-061: MODERATION_SERVICE_URL wrong on NestJS enterprise → guardrail silently fails open | Fix `ENTERPRISE_BACKEND_BASE_URL`/`MODERATION_SERVICE_URL` in enterprise.env, restart |
| G-08 | No SSL on 35.154.138.184 (T-064) | Run Certbot before DNS flip |
| G-09 | DNS not yet flipped — old server still receiving traffic (T-063) | Flip after Certbot |
| G-10 | PostHog surveys (3 drafts) never activated with event triggers | Wire `enhance_completed`, `output_copied`, `paywall_hit` as triggers |
| G-11 | Feature flags `paywall-copy-ab`, `mode-nudge-placement` not wired in extension/web | Frontend integration |

### P2 — Quality and observability

| # | Gap | Fix |
|---|---|---|
| G-12 | Context threshold raised to 0.85 (just deployed) — need monitoring for zero-context rate | Add logging to `_fetch_context_hint` |
| G-13 | Model routing new (just deployed) — need monitoring for which intents hit which models | Already in PostHog via `classified_intent`, `model_used` |
| G-14 | Quality score `prompt_quality_score` from enhance response — no baseline established | Build PostHog insight after 1 week of data |

---

## COORDINATION PROTOCOL WITH CLAUDE

Claude Code (running locally for Arjun) handles:
- Integration work that requires testing against the live server
- Docker build/restart (SSH deployment)
- Final verification before marking tasks done
- Any work requiring real-time debugging

Antigravity (you) handles:
- Feature code (complete, runnable files)
- Analysis and planning documents
- Extension JS fixes
- Frontend fixes
- Research and specification

**Handoff mechanism:**
1. Antigravity writes complete code to the repo
2. Antigravity writes a `HANDOFF_FOR_CLAUDE.md` describing what to deploy and test
3. Claude picks up the file, deploys, tests, reports back

**Never both work on the same file at the same time.** If you're working on `enhance.py`, say so in `HANDOFF_FOR_CLAUDE.md`. If Claude is working on something, it will note it there.

---

## HARD CONSTRAINTS (never violate)

1. **No placeholder code.** Every file must be complete and immediately runnable.
2. **No CloudFront or Lambda** (breaks SSE streaming).
3. **No merging Node.js and NestJS backends** (SOC2 isolation requirement — different JWT secrets).
4. **NEVER touch `/ai/enhance/stream`** — it's deprecated but live; breaking it kills extension users.
5. **`python-ai-unified` must import from `local_app.py`** — never re-implement LLM logic.
6. **System prompts live in `core/prompts/*.md`** — not inline in Python files.
7. **Load prompt files with `encoding='utf-8'`** explicitly.
8. **Always `response_format={"type": "json_object"}` on Groq calls.**
9. **Extension storage keys:** consumer = camelCase, enterprise = `ent_*` prefix — never mix.
10. **Production branch on server is `reconcile/quality-engine-on-prod`**, NOT `codex/prompt-trace-backend`. Always patch surgically; never do a full checkout of enhance.py on server.

---

## PAYMENT / BILLING

- **Razorpay:** India payments. Keys in `/opt/deploy/node.env`.
- **Monthly plan ID:** `sub_RZJG8f81ImHopI`
- **Yearly plan ID:** `sub_RZJFmCNj2Vk87C`
- Payment webhook → Node backend → updates `subscriptions` table → Node should fire `subscription_changed` PostHog event

---

## QUICK DECISION REFERENCE

| Decision | What | Why |
|---|---|---|
| D-019 | python-ai-unified reuses `local_app.py` as bridge to canonical code | Don't re-implement LLM logic |
| D-021 | Node.js and NestJS stay separate | SOC2 auth isolation (different JWT secrets/lifetimes) |
| D-022 | No CloudFront/Lambda | Wrong scale + Lambda breaks SSE streaming |
| D-023 | Move paywall from 3 → 5-7 prompts | Behavioral data: churn caused by early wall |
| D-024 | Build active mode nudge | 60x conversion lift at 4+ modes vs 1 mode |
| D-025 | Single 8GB Lightsail server | All services on 127.0.0.1, ~$65/mo |

---

## WHAT TO DO FIRST

When you start a session, run this mental checklist:
1. Read `HANDOFF_FOR_CLAUDE.md` — are there tasks in progress from Claude?
2. Read this file (done).
3. Check `ANTIGRAVITY_TASKS.md` (if it exists) for your current task queue.
4. Always write to `HANDOFF_FOR_CLAUDE.md` when your code is ready for deployment.
