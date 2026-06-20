# ThinkVelocity Backend Hardening & Benchmark Plan
**Date:** 2026-06-18  
**Scope:** python-ai-unified service + context engine + memory system  
**Framework:** DSA Problem-Solving Stack (UNDERSTAND → CLASSIFY → BRUTE FORCE → OPTIMIZE → IMPLEMENT)

---

## Overview

Five problems. All interconnected. Execution order matters:

```
[1] Trace Persistence         ← prerequisite for measuring everything else
[2] Intent Detection Benchmark ← needs test file first (depends on #5)
[3] Context Engine Audit       ← read-only, can run in parallel with #2
[4] Memory Usefulness/Diversity ← builds on #3 findings
[5] IDEAL CASE TEST FILE        ← feeds #2 and #4
```

**Recommended execution order:** 5 → 3 → 2 → 4 → 1 (test file unlocks benchmarks, DB unlocks retention).

---

## Problem 1: Trace Persistence

### UNDERSTAND
`PromptTraceStore` writes to `/tmp/traces/prompt_traces.jsonl`. `/tmp` is tmpfs — wiped on every `docker restart` or recreate. Currently only 4 traces survive after the last rebuild. We have an admin dashboard (`GET /admin/prompt-traces`) that reads this. We lose all enhance telemetry on every deploy.

**Constraints:**
- Trace volume: ~50–500 enhance calls/day (early stage)
- Each trace: ~2–4KB of JSON (prompt before/after, tokens, latency, user_id)
- Must NOT slow down the enhance endpoint (write must be async/fire-and-forget)
- PostgreSQL is already available on `tv-net` as `postgres17`

### CLASSIFY
**Pattern: Append-only log with indexed reads → Write-ahead log / event store**

DSA analog: Insert into sorted structure + range query. The key operations are:
- `O(1)` amortized INSERT (async fire-and-forget)
- `O(log n)` range scan by `(user_id, created_at)`
- `O(1)` point lookup by `trace_id`

### BRUTE FORCE
Keep JSONL but mount a named Docker volume. Solves the wipe problem with zero code change. **Cost:** manual backup management, no indexing, O(n) scans.

### OPTIMIZE → CHOSEN APPROACH
**PostgreSQL append-only table** in existing `thinkvelocity_prod` DB.

```sql
CREATE TABLE IF NOT EXISTS prompt_traces (
    id          SERIAL PRIMARY KEY,
    trace_id    UUID        NOT NULL DEFAULT gen_random_uuid(),
    user_id     TEXT        NOT NULL,
    session_id  TEXT,
    platform    TEXT,
    domain      TEXT,
    intent      TEXT,
    raw_prompt  TEXT,
    enhanced_prompt TEXT,
    context_hint    TEXT,
    persona_hint    TEXT,
    suggested_ai    TEXT,
    model       TEXT,
    tokens_in   INT,
    tokens_out  INT,
    latency_ms  INT,
    quality_score FLOAT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_traces_user_created ON prompt_traces(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_traces_domain ON prompt_traces(domain);
CREATE INDEX IF NOT EXISTS idx_traces_created ON prompt_traces(created_at DESC);
```

**Write path:** `enhance.py` → fire-and-forget `asyncio.create_task(write_trace_to_db(...))`. No await on hot path.

**Read path:** `admin/analytics.py` routes switch from JSONL reader to SQL queries. Keep `PromptTraceStore` as in-memory cache for last 100 traces (fast dashboard refresh), DB as source of truth.

### IMPLEMENT — Step by step

1. **Migration script** (`python-ai-unified/migrations/003_prompt_traces_table.sql`)  
   Run: `psql -h 35.154.138.184 -U postgres -d thinkvelocity_prod < 003_...sql`

2. **`shared/trace_db.py`** — new module  
   Exposes `async def write_trace(pool, trace: dict) -> None` using asyncpg or the existing psycopg3 pool. Single INSERT, fully async, never raises (try/except + log warning).

3. **Update `enhance.py`**  
   After the existing `trace_store.add(...)` call, add:  
   `asyncio.create_task(write_trace(db_pool, trace_record))`  
   No change to response shape.

4. **Update `admin/analytics.py`**  
   `GET /admin/prompt-traces` — queries DB with LIMIT/OFFSET, filters on user_id/domain/intent  
   `GET /admin/prompt-metrics` — SQL aggregates (AVG latency, COUNT by domain, etc.)  
   Keep JSONL path as fallback for local dev (when `DATABASE_URL` is not set).

5. **Retention policy:** Keep all traces. Add a `DELETE FROM prompt_traces WHERE created_at < NOW() - INTERVAL '90 days'` cron (pg_cron or a weekly admin endpoint) when volume warrants it.

### COMPLEXITY
- INSERT: O(log n) with index (acceptable, fire-and-forget)
- Range query: O(log n + k) where k = results returned
- Space: ~3KB/trace × 500 traces/day × 90 days = ~135MB/year — negligible

---

## Problem 2: Intent Detection Benchmark

### UNDERSTAND
The intent classifier runs inside `_extract_context()`. It outputs:
- `PrimaryIntent`: one of 6 macro-intents (`inquiry`, `construction`, `debugging`, `decision`, `operation`, `chat`)
- `SecondaryIntent`: free-form string
- `PrimaryDomain`: one of 20 macro-domains
- `SecondaryDomains`: free-form list

**Current benchmark:** None. We have no ground truth. We don't know if the LLM is picking `construction` vs `debugging` correctly or if domain is accurate.

**Why this matters:** The essence embedding used for context retrieval in enhance depends on intent+domain. Wrong classification = wrong context hint = worse prompts.

### CLASSIFY
**Pattern: Classification with precision/recall evaluation → Multi-label classification benchmark**

This is a **test oracle problem**:
- We need ground truth labels for N conversations
- We need to run the classifier and compare output
- Metrics: per-class precision, recall, F1 for intents; accuracy for domain

### BRUTE FORCE
Manual label 50 conversations by hand. Run classifier. Compare. **Cost:** slow, doesn't scale.

### OPTIMIZE → CHOSEN APPROACH
**LLM-as-judge** + **hand-curated anchor cases**:

1. Build the IDEAL TEST FILE (Problem 5) with known-correct `(intent, domain)` labels
2. Run `_extract_context()` on each test case
3. Score: exact match on intent, exact match on primary domain, semantic similarity on secondary intent
4. Track per-class F1 so we know which classes fail most often

**Red flags to watch for:**
- `inquiry` → `construction` confusion (user asks HOW to do X vs. actually building X)
- `debugging` → `construction` confusion (fixing code vs. writing new code)  
- Domain collapse: everything becomes `software_data_engineering` (the fallback)
- SecondaryIntent is vague/generic ("working on something") vs. specific ("implementing_jwt_auth")

### IMPLEMENT — Step by step

1. **`tests/benchmark_intent_detection.py`**  
   - Loads IDEAL TEST FILE cases that have `expected_intent` + `expected_domain` labels  
   - Calls `_extract_context()` with each conversation  
   - Computes per-class precision/recall/F1  
   - Prints confusion matrix  
   - Passes if overall intent accuracy ≥ 85% and domain accuracy ≥ 75%

2. **Baseline run on current system**  
   Record current scores as v0 baseline. Commit scores to `tests/benchmarks/intent_v0_scores.json`.

3. **Failure-driven improvement loop:**  
   - If `debugging`/`construction` confusion ≥ 20%: add distinction examples to `_ESSENCE_EXTRACTION_PROMPT`  
   - If domain collapses to `software_data_engineering` > 30% of non-tech cases: reorder domain list in prompt  
   - Re-run benchmark, compare v1 vs v0

4. **SecondaryIntent quality metric:**  
   Score specificity as: `len(secondary_intent.split("_")) >= 2` (compound phrase = specific). Flag cases where secondary is just one word.

### THRESHOLDS (initial targets)
| Metric | Target v1 |
|--------|-----------|
| PrimaryIntent accuracy | ≥ 85% |
| PrimaryDomain accuracy | ≥ 75% |
| SecondaryIntent specificity rate | ≥ 70% |
| Domain fallback rate (sw_data_eng on non-tech) | ≤ 15% |

---

## Problem 3: Context Engine Audit

### UNDERSTAND
The context engine produces a MASTER+FLOW essence stored in pgvector and Supermemory. This essence is retrieved in `_fetch_context_hint()` during enhance calls. The product has evolved — we need to audit whether the MASTER/FLOW structure is producing high-signal context or low-signal noise.

**Key question:** Is MASTER capturing real long-term trajectory, or is it a restatement of the first conversation?

### CLASSIFY
**Pattern: State machine audit → Graph traversal + entropy analysis**

The essence pipeline is a state machine:
```
[no context] → FULL extraction → MASTER only
[has context] → INCREMENTAL → MASTER + FLOW (≤2 bullets)
[domain shift] → FULL (reset MASTER)
[version limit 5] → FULL (force reset)
```

Audit each transition: does it produce the right output for the right input?

### FINDINGS FROM CODE REVIEW

**Strengths:**
- MASTER stability rule is well-encoded in the prompt — only rewritten on macro-goal shift
- FLOW compression is deterministic (no LLM needed, pure regex + word frequency)
- PII redaction for enterprise is solid
- Cost gate `_MAX_COST_PER_SESSION = 5.0` prevents runaway LLM calls
- Version limit of 5 forces periodic full refresh (prevents semantic drift)

**Gaps identified:**
1. **MASTER quality is unverifiable** — we never check if MASTER is actually stable across incremental updates. A hallucinating LLM could rewrite MASTER on every call.
2. **FLOW compression is keyword-based, not semantic** — `_compress_flow_to_limit()` extracts keywords from bullets using stopwords, builds "refining context for X and Y" — this loses specificity when bullets are complex.
3. **Domain shift detection is binary** — a user going from `software_data_engineering` → `business_marketing` resets the entire MASTER. But a SaaS founder switching between these IS their stable context — they shouldn't lose continuity.
4. **Supermemory and pgvector can diverge** — pgvector gets the embedding, Supermemory gets the text. Retrieval in `_fetch_context_hint()` uses local-wins logic. If they diverge, the returned hint may be from different versions.
5. **No feedback loop** — we never know if a retrieved context hint actually improved the enhance output. The context is consumed silently.
6. **SecondaryDomains are stored as a list but the node backend payload shape doesn't include them as a top-level field** — they're folded into the `domains` array. Retrieval just uses primary domain for pgvector namespace.

### RECOMMENDED EVOLUTION (preserve all request/response shapes)

**Zero-breaking-change improvements:**
- Add MASTER drift detection: compare cosine similarity of new MASTER embedding vs old MASTER embedding. If > 0.85 similarity → MASTER is stable (good). If < 0.5 → LLM rewrote MASTER when it shouldn't have. Log a warning.
- Improve FLOW compression: instead of keyword frequency, use the **most recent bullet verbatim** + summarize the rest as "previously: [topic]" — higher specificity, same character budget.
- Multi-domain users: add a "composite domain" concept where if `new_primary` not in previous BUT previous IS in `new_domains` secondary list → stay incremental instead of forcing full reset.
- Add context utilization tracking to trace: record whether `context_hint` was non-empty when enhance was called (already partially in the trace, but not surfaced in admin metrics).

**Implementation order:** MASTER drift detection first (observability before change). Then FLOW compression improvement. Then multi-domain fix.

---

## Problem 4: Memory Usefulness & Diversity

### UNDERSTAND
Supermemory stores essence text (the MASTER+FLOW string) tagged by `user_id`. Retrieval is semantic search over these. The question: are memories useful (high-signal, enhance-relevant) and diverse (not all the same)?

### CLASSIFY
**Pattern: Information entropy / coverage measurement**

Think of it as a **bloom filter health check**: is every user's memory bucket containing distinct information, or are we storing near-duplicates?

Also a **set cover problem**: do the stored memories across a user's history cover their full working context, or does recency bias mean only recent conversations are retrievable?

### MEASUREMENTS TO RUN

1. **Uniqueness ratio:** For each user, compute pairwise cosine similarity of all stored essences. If avg similarity > 0.85 → near-duplicate storage (memory isn't diverse).
2. **Domain coverage:** Given a user has N memories, how many distinct `PrimaryDomain` values are represented? A power user should have ≥ 3 domains in memory.
3. **Recency bias check:** Sort by `created_at`. Does semantic search always return the most recent? If yes → we're not benefiting from historical context.
4. **Retrieval relevance:** When `_fetch_context_hint()` is called with a specific query (the current prompt), does the returned memory have semantic overlap with the query domain?

### GAPS TO FIX

**Gap 1: Only essences are stored, not the secondary_intent trail**
Supermemory entries contain the full essence string, but `SecondaryIntent` (e.g., "implementing_oauth_flow") is not stored separately. This means semantic search can retrieve on MASTER but can't surface "last time user was doing X" specifically.
- **Fix:** Add `secondary_intent` as a tag on the Supermemory entry alongside `containerTags`

**Gap 2: No deduplication**
If a user has 50 `software_data_engineering` + `construction` sessions, all essences look similar. Semantic search always returns the highest-similarity one, which is the most recent. Historical context is lost.
- **Fix:** Before writing to Supermemory, check if existing memory cosine similarity > 0.9 → skip write (it's a near-duplicate). This caps memory at ~10–20 distinct conceptual states per user.

**Gap 3: Memory has no "freshness weight"**
A 6-month-old memory about JavaScript is less useful than a 3-day-old memory about the same topic. Current retrieval is pure semantic similarity with no time decay.
- **Fix (simple):** Pass `created_at` into the memory body text (Supermemory's search is semantic, not filtered). The enhancement context builder can prefer recent memories if multiple are returned.
- **Fix (proper):** Use Supermemory's search + manual filter: retrieve top 5, then re-rank by `0.7 * semantic_score + 0.3 * recency_score`.

### IMPLEMENTATION ORDER
1. Add `secondary_intent` as a tag/field in Supermemory add calls (1 line change in `context.py`)
2. Add near-duplicate skip in `_save_to_node()` / pre-Supermemory write (requires embedding similarity check)
3. Add recency re-ranking in `_fetch_context_hint()` (requires returning metadata from Supermemory)

---

## Problem 5: IDEAL CASE TEST FILE

### UNDERSTAND
We need a ground truth test suite that covers the full space of users, domains, and modes the system handles. This is the reference benchmark for everything else (intent detection, context quality, memory diversity, enhance quality).

### CLASSIFY
**Pattern: Set cover over a multi-dimensional space**

Dimensions:
- **ICP type** (4 primary ICPs): Developer, Knowledge Worker, Creator, Student
- **Domain** (20 macro-domains): prioritize top 8 by usage
- **Mode** (3): First-time user (no context), returning user (has MASTER), power user (MASTER + FLOW)
- **Context richness** (3): zero context, sparse context, rich context
- **Intent** (6): all macro-intents

Minimum set cover = 4 × 8 × 3 × 3 × 6 = 1,728 combinations.
Realistic test file = ~60 hand-curated cases covering the critical paths.

**Set cover insight:** We don't need all 1,728. We need every *dimension value* to appear at least twice. With 60 cases we can cover all 20 domains, all 6 intents, all 4 ICPs, all 3 modes.

### STRUCTURE

Each test case in `tests/ideal_cases/ideal_test_cases.json`:
```json
{
  "id": "dev-001",
  "icp": "developer",
  "domain": "software_data_engineering",
  "intent": "debugging",
  "mode": "returning",
  "context_richness": "rich",
  "conversation": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "user_profile": {
    "llm_platform": "claude",
    "primary_domain": "software_development"
  },
  "existing_essence": "MASTER:\nSenior engineer building distributed systems on Kubernetes.\n\nFLOW:\n- debugging pod networking issues",
  "expected_intent": "debugging",
  "expected_domain": "software_data_engineering",
  "expected_essence_keywords": ["distributed", "infrastructure", "kubernetes"],
  "expected_suggested_ai": "claude",
  "enhance_quality_criteria": {
    "min_length_ratio": 1.3,
    "must_contain_context": true,
    "must_not_be_generic": true
  }
}
```

### THE 60 CASES — Dimensional Coverage Plan

| ICP | Domain | Intent | Mode | Count |
|-----|--------|--------|------|-------|
| Developer | software_data_engineering | debugging | returning | 3 |
| Developer | software_data_engineering | construction | returning+rich | 3 |
| Developer | software_data_engineering | inquiry | first-time | 2 |
| Developer | software_data_engineering | operation | returning | 2 |
| Developer | logic_mathematics | construction | returning | 2 |
| Knowledge Worker | business_marketing | decision | returning | 3 |
| Knowledge Worker | productivity_planning | construction | first-time | 2 |
| Knowledge Worker | finance_legal | inquiry | first-time | 2 |
| Knowledge Worker | operations_hr_support | construction | returning | 2 |
| Knowledge Worker | education_research | inquiry | returning | 2 |
| Creator | creative_arts_media | construction | first-time | 3 |
| Creator | creative_arts_media | decision | returning | 2 |
| Creator | social_casual | chat | first-time | 2 |
| Creator | lifestyle_relationships | inquiry | first-time | 2 |
| Student | education_research | inquiry | first-time | 3 |
| Student | logic_mathematics | debugging | returning | 2 |
| Student | software_data_engineering | inquiry | first-time | 2 |
| Student | philosophy_religion | inquiry | first-time | 2 |
| **Edge Cases** | | | | |
| Developer | system_ai_meta | construction | power | 2 |
| Knowledge Worker | healthcare_medical | inquiry | returning | 2 |
| Any | news_current_events | decision | first-time | 2 |
| Any | food_nutrition | construction | first-time | 2 |
| Any | travel_hospitality | operation | first-time | 2 |
| Any | gov_nonprofit | inquiry | returning | 2 |
| **Domain shift test** | sw → business | decision | returning | 3 |
| **Multi-turn compression** | sw_data_eng | construction | power+10msgs | 3 |
| **MASTER stability** | sw_data_eng | (flip: inquiry→debug→construct) | power | 3 |
| **Zero context baseline** | any | any | first-time | 2 |
| **Enterprise ICP** | finance_legal | operation | returning | 2 |

**Total: ~62 cases.**

### ICP PROFILES (used in `user_profile` field)

```json
{
  "developer": {"llm_platform": "claude", "primary_domain": "software_development", "icp": "developer"},
  "knowledge_worker": {"llm_platform": "chatgpt", "primary_domain": "business_operations", "icp": "business"},
  "creator": {"llm_platform": "gemini", "primary_domain": "creative_arts", "icp": "creator"},
  "student": {"llm_platform": "chatgpt", "primary_domain": "education", "icp": "student"}
}
```

### IMPLEMENTATION STEPS

1. Create `tests/ideal_cases/` directory
2. Write `tests/ideal_cases/ideal_test_cases.json` with all 62 cases (conversation text must be realistic — not "please help me", actual technical/domain-specific exchanges)
3. Write `tests/benchmark_ideal_cases.py` — loads test file, runs `_extract_context()` + `_resolve_suggested_ai()` on each case, reports pass/fail per case
4. Write `tests/benchmark_enhance_quality.py` — for selected cases, calls enhance endpoint locally, checks `enhance_quality_criteria`

---

## Execution Roadmap

### Sprint 1 — Foundation (Days 1–3)
- [ ] Write IDEAL CASE TEST FILE (Problem 5) — 62 cases, realistic conversations
- [ ] Run baseline intent benchmark on current system with test file (Problem 2 v0)
- [ ] Commit `tests/benchmarks/intent_v0_scores.json`

### Sprint 2 — Persistence (Days 4–5)
- [ ] DB migration: `prompt_traces` table on prod
- [ ] `shared/trace_db.py` — async write module
- [ ] Update `enhance.py` — add DB write (fire-and-forget)
- [ ] Update `admin/analytics.py` — switch reads to DB
- [ ] Deploy + verify traces accumulating

### Sprint 3 — Context Engine Improvements (Days 6–8)
- [ ] Add MASTER drift detection (cosine similarity check on incremental updates)
- [ ] Improve FLOW compression (verbatim last bullet, abstract summary for prior)
- [ ] Multi-domain users: incremental if secondary overlap (not binary domain reset)
- [ ] Add `secondary_intent` as tag in Supermemory writes

### Sprint 4 — Memory Deduplication & Re-ranking (Days 9–10)
- [ ] Near-duplicate skip in Supermemory write path (cosine sim > 0.9 → skip)
- [ ] Recency re-ranking in `_fetch_context_hint()` (top 5 → re-rank by 0.7 semantic + 0.3 recency)
- [ ] Run memory diversity audit on real user data (print report to logs)

### Sprint 5 — Benchmark v1 (Day 11)
- [ ] Re-run intent benchmark with Sprint 3 prompt changes
- [ ] Compare v0 vs v1 scores
- [ ] Commit `tests/benchmarks/intent_v1_scores.json`
- [ ] Ship if: intent ≥ 85%, domain ≥ 75%

---

## Key Invariants (Do Not Break)

These are hard constraints throughout all work:

1. `POST /context/process-context` request/response shape — **DO NOT CHANGE** camelCase fields
2. `POST /ai/enhance/chat` response shape — **DO NOT CHANGE** (only additions allowed)
3. Node backend callback payload fields (`sessionId`, `essence`, `intent`, `secondaryIntent`, `domains`, `embedding`, `embeddingModel`, `embeddingVersion`, `messageCount`, `platform`, `version`, `updateType`, `usageCost`, `userId`) — **DO NOT CHANGE**
4. Supermemory `containerTags: [user_id]` — **DO NOT REMOVE** (this was the cross-user leakage fix)
5. All DB writes to prompt_traces are fire-and-forget — **NEVER await on hot path**

---

## Success Criteria

| Area | Metric | Target |
|------|--------|--------|
| Trace persistence | Traces survive container restart | 100% |
| Trace persistence | Write latency impact on enhance | < 5ms added |
| Intent detection | PrimaryIntent accuracy on test file | ≥ 85% |
| Intent detection | PrimaryDomain accuracy | ≥ 75% |
| Context engine | MASTER stability across 5 incremental updates | ≥ 90% cases |
| Memory diversity | Avg pairwise similarity for power user | ≤ 0.75 |
| Test file | Coverage of all 6 intents | ✓ |
| Test file | Coverage of all 4 ICPs | ✓ |
| Test file | Coverage of ≥ 12 distinct domains | ✓ |
