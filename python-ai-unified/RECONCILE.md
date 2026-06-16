# RECONCILE — Unified Python AI Service

This file logs every spot where production source (baked into remote Docker
images, not on disk) could not be reproduced byte-for-byte and a faithful
working implementation was written against the documented contract instead.
Multiple agents append to this file; keep additions in clearly delimited
per-router sections.

## /context/* router

Source service: `context-engine-container-dev` (Server 2, port 8001). Original
mount was `/api/*`; unified app mounts this router at `/context`. Persistence is
via HTTP to the Node.js backend (no direct Postgres). Implemented in
`routers/context.py`.

1. **Node backend persist endpoint paths are assumed.** The real context-engine
   posts essence+embedding to specific Node routes whose exact paths are not in
   the docs. I used `POST /api/context/essence` for both `/process-context` and
   `/process-essence` persistence, and `GET /api/user/{user_id}/contexts` for
   search retrieval, `GET /api/user/{user_id}/profile` for the profile proxy.
   Verify against the Node.js backend's real route table and adjust.

2. **Node response shape for the persisted context id is inferred.** I extract
   `context_id`/`id`/`_id` (and a nested `data.*`) defensively. Confirm the
   actual key the Node backend returns.

3. **Essence schema is a reconstructed contract.** The exact JSON shape the
   production Groq prompt emits is unknown. I defined `EssenceModel`
   (summary, topics, entities, user_intent, preferences, keywords) and a system
   prompt that requests exactly those keys via `response_format={"type":
   "json_object"}`. Tune prompt + fields to match production output.

4. **Essence classification schema is reconstructed.** `EssenceClassification`
   (category, topics, sentiment, importance 0..1) + its system prompt are a
   faithful guess; align with production taxonomy if one exists.

5. **Embedding text selection for `/process-context` is a heuristic.** I embed
   `summary + topics + keywords` (fallback to raw transcript). Production may
   embed the full conversation or a different projection. Confirm.

6. **Semantic search is done in-process (cosine).** The real engine may rely on
   pgvector / a Node-side similarity query. Here we retrieve the user's contexts
   (with stored embeddings) from Node and rank by cosine in Python, filtering by
   `RELEVANCE_THRESHOLD` (0.30, merge-plan §3/§7). If the dataset is large,
   replace with a server-side vector query.

7. **`RELEVANCE_THRESHOLD` / `EMBEDDING_DIMENSION` / `GROQ_MODEL` defaults.**
   Read from `shared.settings` with documented fallbacks (0.30 / 1024 /
   `openai/gpt-oss-120b`) so the router is runnable if those settings fields are
   absent. Confirm the canonical model name.

8. **`groq_pool.async_chat(...)` return shape.** Parsing assumes groq SDK 1.x
   (`completion.choices[0].message.content`) with a dict fallback. Verify the
   shared pool wrapper returns the raw SDK object (or adapt accordingly).

9. **`verify_token` dependency applied to data routes.** Auth is documented as
   disabled (`AUTH_ENABLED=false`); `verify_token` is wired as a FastAPI
   dependency (expected passthrough) on the data-bearing routes and omitted from
   the dev `/test/batch-embedding` and health roots. Adjust if the shared auth
   contract differs.

10. **`/health` actively probes dependencies.** It performs a live embedding
    call, a tiny Groq json_object call, and a Node `GET /health`. The original
    health detail format is unknown; status is `healthy` only when all probes
    pass, else `degraded`. Confirm Node exposes `/health`.

## /ai/* router

Source service: `prompt-enhance` (Server 3, canonical/newer build). Mounted by
the parent app at `/ai`. Implemented in `routers/ai/` (one sub-router per group;
shared helpers in `routers/ai/_common.py`). Patterns mirror the lean app's
`core/llm.py`, `core/contracts.py`, `api/enhance.py`, `api/refine.py`.

### enhance.py
1. **Enhance system prompt(s).** Implemented a complete prompt producing the
   documented `EnhanceResult` JSON shape. Verify the canonical per-mode enhance
   prompts (normal/caveman/research/fast_build/media); the lean app loads these
   from `core/prompts/` + `core/prompt_modes.py` bundles.
2. **Token deduction (`_deduct_tokens`).** Guarded `UPDATE user_tokens SET
   balance = balance - :cost WHERE balance >= :cost`. Verify real table/column
   names, per-call cost (Server 3 may derive cost from `usage.total_tokens`,
   not a flat 1), and pre- vs post-generation timing.
3. **NVIDIA context aggregation (`_aggregate_context`).** Real embedding call
   returning aggregation metadata. Verify the canonical build feeds this into a
   pgvector personalization retrieval and injects snippets into the user message.
4. **Redis cache key/TTL (`/enhance/chat`).** sha256 over prompt/target_ai/mode/
   intent_confirmation, TTL 300s. Verify canonical key schema + TTL.
5. **Rate limits.** 60 req / 60s assumed. Verify real limits/window.

### refine.py
6. **Refine system prompt + fallback.** Produces documented `RefineResult` shape
   with deterministic fallback (mirrors `api/refine.py`). Verify canonical refine
   prompt per mode and any behavioral diff between `/refine`, `/refine/chat`,
   `/refine/chat/stream` beyond transport/rate-limiting.
7. **Token deduction.** Reuses enhance `_deduct_tokens`, cost 1. Verify cost/table.

### clarify.py
8. **`/clarify` + `/clarify/chat/mcq` prompts.** Implemented free-form + MCQ
   question generation, capped at 3. Verify canonical prompt, question schema,
   and max-question count.

### recommendation.py
9. **`/recommendation` prompt.** Ranked (1-3) over `TARGET_AI_VALUES`. Verify
   ranking criteria and whether connectors come from `connectors_catalog`.

### media.py
10. **`/media/enhance`.** Forces `prompt_mode="media"` then delegates to
    `enhance_chat`. Verify Server 3 `is_media=True` media-pipeline differences.
11. **`/transcribe`.** `whisper-large-v3` via a raw AsyncGroq client obtained from
    the shared pool's rotation internals (`_next_key`/`_async_client`). Verify:
    the shared `groq_pool` should expose a public transcription/audio accessor;
    and confirm the canonical whisper model + params.

### quality.py
12. **All `/quality/*` metrics.** Process-local in-memory accumulators (latency
    deques, mode counts, accuracy counters). Verify Server 3 sources these from
    its telemetry pipeline; hooks `record_latency`/`record_mode` exist but are not
    yet called by other routers — wire telemetry.
13. **`/quality/analyze-prompt`.** Real Groq scorer (clarity/specificity/intent/
    depth). Verify canonical rubric/weights.

### moderation.py
14. **Hybrid regex+RAG+LLM.** Regex pre-filter, RAG cosine over a bundled 9-item
    seed knowledge base, LLM adjudication, process-local LRU (1024). Verify: the
    canonical RAG KB (larger/proprietary), RAG threshold (0.92), regex rules, LRU
    size/key schema, and verdict response schema.
15. **`/moderation/document/classify` + `/document/upload`.** Policy-vs-context
    classification via Groq; paragraph chunking on upload. Verify chunking +
    classification schema.

### context_docs.py
16. **pgvector store (`ai_context_documents`).** Best-effort table create + insert
    + cosine (`<=>`) NN retrieval, user-scoped. Verify canonical table name,
    schema/vector dim, indexes (ivfflat/hnsw), and scoping rules.
17. **Chunking.** 1200-char chunks / 150 overlap; only UTF-8 text decoded. Verify
    canonical chunk size and non-text (PDF/docx) parsing.
18. **`/embeddings/generate`.** Thin wrapper over `generate_embeddings_batch`.
    Verify request/response field names (single vs batch).

### prompt_find.py (ENTERPRISE)
19. **`/prompt/find`.** Two HTTP calls via `node_post` to
    `ENTERPRISE_POLICY_ENDPOINT` and `ENTERPRISE_CONTENTS_ENDPOINT`, returning
    `{policy, documents, errors}`, degrading per leg. Verify: exact enterprise
    request/response schemas; whether it should use `ENTERPRISE_BACKEND_BASE_URL`
    with auth headers instead of the Node client; and the combined contract the
    enterprise extension expects.

### diagnostic.py
20. **`/diagnostic/web-search`.** Returns `enabled:false` stub (search providers
    not provisioned). Verify the real web-search service + result schema.
21. **`/diagnostic/rag-strategies`.** Heuristic strategy derivation. Verify the
    canonical vector-KB retrieval + scores.
22. **`/diagnostic/domain|intent|target-ai`.** Real Groq classifiers over the
    `Domain`/`Intent`/`TargetAI` sets. Verify canonical prompts + confidence.
23. **`/diagnostic/complexity`.** Deterministic local formula. Verify canonical
    complexity calculation.

### health.py
24. **`/domain-analyzer`.** Functional HTML page wired to `/ai/diagnostic/all`.
    Verify the canonical Server 3 static HTML asset. (In the documented map but
    not in the task's per-router breakdown; added to fully cover the map.)

### Cross-cutting
25. **Auth.** All routes public (`AUTH_ENABLED=false`); shared `verify_token` not
    applied to `/ai/*`. Decide per-route auth before enabling.
26. **Response metadata envelope.** Lean app attaches `_usage`/`_redactions`/
    `_personalization_used`/`_prompt_files`; this router attaches a subset
    (`_personalization_used`, `_cached`). Verify the full set the
    consumer/enterprise clients expect.
27. **Vendored log scrubber.** `shared/log_scrubber.py` is a self-contained copy
    of `configs/middleware/log_scrubber.py` (so the Docker image scrubs secrets
    without the repo's `configs/` on path). The two MUST stay in sync — any
    redaction-pattern change goes in both, OR replace both with a pip-installable
    shared package (folds into T-052). `logging_config` prefers the vendored copy.

---

## D-019 reconciliation status (2026-05-29) — routers now delegate to local canonical

Per D-019 ("reuse local core as source of truth"), the consumer-core `/ai/*`
routers no longer reconstruct prompt/LLM logic — they import and call this
monorepo's real handlers via `local_app.py` (the same functions the extension
hits through `api/extension_bridge.py`). This **closes** the following items
because there is no longer a reconstructed prompt to diff:

- **enhance.py — items 1, 3, 4 RESOLVED.** `/enhance/stream` + `/enhance/chat`
  call the canonical `api.enhance._generate` (loads real `core/prompts/` +
  `core/prompt_modes` bundles, NVIDIA/personalization + cache owned upstream).
  The router only adapts the native `chunk`/`done` SSE → extension
  `content`/`complete`/`[DONE]`. Item 2 (token deduction) and item 5
  (rate-limit) STILL OPEN — these are unified-service concerns layered on top.
- **refine.py — item 6 RESOLVED.** `/refine`, `/refine/chat`, `/refine/chat/stream`
  call canonical `api.refine.refine`; the endpoint model IS the canonical
  `RefineRequest` (no contract drift). Item 7 (token deduction cost/table) OPEN.
  NEW flag: no canonical *streaming* refine exists — `/refine/chat/stream` frames
  the single canonical result as one `done` SSE event; verify the streaming
  envelope consumer/enterprise clients expect.
- **clarify.py — item 8 RESOLVED.** `/clarify` + `/clarify/chat/mcq` call
  canonical `api.refine.refine_prepare` (questions capped at 3, mapped to MCQ
  shape). Verify only the MCQ field-name mapping if a client mismatch surfaces.
- **media.py — items 10, 11 RESOLVED.** `/media/enhance` runs the canonical
  enhance pipeline with media mode forced; `/transcribe` calls canonical
  `api.cothinker.cothinker_transcribe` (real whisper handler, public accessor —
  the raw-pool-internals concern is gone).
- **quality.py — item 13 RESOLVED (re-aligned).** `/quality/analyze-prompt` now
  mirrors canonical `extension_bridge.ext_quality_analyze` — a deterministic
  keyword domain/intent classifier returning `{status, metadata}`, NOT the
  prior Groq scorer. The reconstructed scorer was a contract mismatch vs the
  proven extension shape. Item 12 (process-local `/quality/*` metrics) STILL
  OPEN — no canonical telemetry source available locally.

STILL fully reconstructed / awaiting external source (unchanged): items 2, 5, 7,
9 (recommendation), 12 (quality metrics), 14–15 (moderation), 16–18
(context_docs), 19 (prompt/find — Node), 20–23 (diagnostic), 24 (health page),
25–26 (cross-cutting auth + metadata envelope). `/context/*` items await the
context-engine source.

## Integration verification (2026-05-29)
- `python -m compileall shared routers main.py` → clean (all 29 modules).
- `import main` → **both routers mount**, 46 API routes live (39 `/ai/*` + 7 `/context/*`), middleware stack = LogScrubber → GZip → CORS, `scrubber=on`.
- Router imports cross-checked against shared `__all__` — no signature drift.
- Fixes applied during integration: added `shared.redis_cache.get_redis()` (main.py health probe referenced it), added `routers/__init__.py` package marker, vendored the log scrubber + wired `LogScrubberMiddleware`.
- STILL BLOCKED on canonical source: run `configs/env-changes/T-031-fetch-canonical-source.sh --pull` on Server 3 + Server 2, then diff `_canonical/` against these routers to close items 1–27 before production cutover.
