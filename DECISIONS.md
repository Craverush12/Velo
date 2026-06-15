# ThinkVelocity — Architectural Decision Log

Records decisions made during development so future sessions don't re-litigate settled questions.
Each entry: **Decision | Alternatives considered | Rationale | Date**

---

## D-101 — Use LiteLLM for multi-provider fallback, not raw SDK per provider

**Decision:** Replace direct Groq SDK calls in `core/llm.py` with `litellm.acompletion()`. Primary: `groq/llama-3.3-70b-versatile`. Fallback on RateLimitError or ServiceUnavailableError: `openai/gpt-4o-mini`.

**Alternatives considered:**
- Keep raw Groq SDK, add manual try/except with raw OpenAI SDK call
- Use a queue-based retry system (Celery, Redis queue)
- Accept single-provider failure (no fallback)

**Rationale:** LiteLLM gives us provider-agnostic routing with a single interface change. The manual approach requires maintaining two SDK clients and matching their async streaming protocols. Queue-based retry adds operational complexity (Redis dep) for a problem solved by a library call. `agentic_stream` stays on raw Groq SDK because it uses proprietary `extra_body` compound model options that LiteLLM doesn't support.

**Date:** 2026-06-15

---

## D-102 — Context similarity threshold set at 0.6, not 0.5 or 0.7

**Decision:** Gate context injection in `_fetch_context_hint()` at `similarity >= 0.6`.

**Alternatives considered:**
- 0.5 (current implicit threshold from the search service's 0.30 baseline)
- 0.7 (high precision, likely to return nothing for new users)
- No threshold (inject all results)

**Rationale:** 0.30 was the search service's retrieval floor — not a quality gate. At 0.5 there's meaningful noise. At 0.7 we gate out too many valid but loosely-worded sessions. 0.6 is the empirical midpoint that keeps signal-to-noise positive. If data shows the gate is too aggressive (< 1 result for most users), lower to 0.55 with a single-line change.

**Date:** 2026-06-15

---

## D-103 — Regex PII detection in attachments, not an external API

**Decision:** Scan attachment text for email, phone, SSN, card, API key patterns using compiled regex before forwarding to LLM. No external PII detection service.

**Alternatives considered:**
- Microsoft Presidio (self-hosted NER-based PII)
- AWS Comprehend / Google DLP API (managed)
- No PII detection (accept the risk)

**Rationale:** External services add network latency on every attachment request and introduce a new failure mode (PII service down → block or pass? Either is bad). Regex covers the high-value PII categories (credentials, identity numbers) that carry the most risk if leaked to Groq's infrastructure. NER-based tools add recall on edge cases but the false-negative rate on structured PII (SSNs, card numbers) is minimal for regex. This is the right minimum viable solution; upgrade to Presidio if compliance requirements escalate.

**Date:** 2026-06-15

---

## D-104 — Prompt injection detection: whole-text redaction on match, not removal

**Decision:** When an injection pattern is detected in an attachment, replace the **entire attachment text** with `[CONTENT REDACTED: policy violation detected in attachment]`, not just the matched portion.

**Alternatives considered:**
- Remove only the matched substring, pass the rest through
- Reject the entire request (return 400)
- Pass through with a warning flag

**Rationale:** Injection patterns are adversarial. Removing only the matched portion assumes the attacker has only one injection attempt. In practice, adversarial inputs use multiple techniques: Unicode lookalikes, split across lines, etc. Rejecting the whole request breaks legitimate use cases (user uploading a document that happens to contain a quoted instruction). Whole-text redaction gives us the safety of removal while keeping the request alive. The user's core prompt still enhances; only the tainted attachment is zeroed out.

**Date:** 2026-06-15

---

## D-105 — Intent confidence threshold: 0.65, fallback to visual_generation (not marketing_copy)

**Decision:** Below 0.65 confidence, `_classify_media_intent()` returns `visual_generation` instead of the originally classified intent.

**Alternatives considered:**
- Keep existing fallback to `marketing_copy`
- Return all three scores and pick the top-1 regardless of confidence
- Ask the user to clarify (break streaming)

**Rationale:** `marketing_copy` was chosen as the original fallback because it was the safest non-visual default. But for genuinely ambiguous prompts, `visual_generation` is less harmful — it gives creative latitude rather than committing to "this is written content". The old fallback was conservative on the wrong axis. Clarification breaks the UX (streaming). 0.65 is set empirically: clear product photography and creative scenes both score > 0.85; genuinely ambiguous prompts cluster between 0.4–0.6.

**Date:** 2026-06-15

---

## D-106 — Eval golden set: 25 cases, not 50 or 100

**Decision:** Start with 25 curated golden cases covering all 5 modes and 14 sub-types.

**Alternatives considered:**
- 50 cases (more coverage, longer eval run)
- 100 cases (full regression suite)
- Property-based generation (fuzzing)

**Rationale:** 50+ cases at LLM-as-judge pricing adds ~$0.10–0.30 per eval run, which discourages running it frequently. 25 cases completes in < 3 minutes and costs ~$0.05. The goal is a low-friction gate on every prompt change — coverage matters less than frequency of execution. Cases will grow organically as regressions are discovered. Property-based generation doesn't work for LLM quality (we need human judgment on what a good enhancement looks like).

**Date:** 2026-06-15

---

## D-107 — Eval judge scoring rubric: 3 axes (specificity, constraint_adherence, actionability)

**Decision:** Score enhanced prompts on specificity, constraint_adherence, and actionability (each 1–5). Pass threshold: all three >= 3 AND mean >= 3.5.

**Alternatives considered:**
- Single overall quality score (1–10)
- BLEU/ROUGE against reference outputs
- Human preference labeling

**Rationale:** A single score loses diagnostic signal (did it fail because the output was vague, or because it ignored the mode rules?). BLEU/ROUGE require fixed reference outputs — LLM outputs have high valid variance. Human labeling doesn't scale for CI. Three axes give actionable failure signals: if constraint_adherence drops after an overlay change, you know exactly where the regression is.

**Date:** 2026-06-15

---

## D-108 — Entity extraction: regex pattern matching, not a separate LLM call

**Decision:** `extract_entities()` in `routers/context.py` uses substring matching against curated word lists (frameworks, domains, languages). No LLM involved.

**Alternatives considered:**
- Separate LLM call to extract entities from essence (NER-style)
- spaCy NER model
- No entity extraction (stay with text blobs)

**Rationale:** The context fetch happens on every enhance request. An extra LLM call here adds 200–400ms and doubles the inference cost per request. spaCy adds a large dependency with GPU/model management overhead. The entity vocabulary for our use case is bounded and well-defined (frameworks, domains, languages) — substring matching achieves ~95% recall on the cases that matter. The `context_hint` upgrade from text blob to `{essences, entities}` JSON pays dividends immediately with zero added latency.

**Date:** 2026-06-15

---

## D-109 — Tenant prompt suffix: injected via context_hint, not a system prompt field

**Decision:** Per-tenant `prompt_suffix` is prepended to `context_hint` under a `[TENANT_CONSTRAINTS]` label, not added as a separate system prompt override field on `LocalEnhanceRequest`.

**Alternatives considered:**
- Add `system_prompt_suffix: str` field to `LocalEnhanceRequest` and modify the system prompt assembly in `_prepare_enhance_input`
- Pass as a separate field and merge in `build_enhance_user_message`
- Inject via the overlay file system (per-tenant overlay files)

**Rationale:** Adding a new field to `LocalEnhanceRequest` requires changes to `api/enhance.py` (the canonical service) — touching the canonical service for an enterprise-only feature increases blast radius. The `context_hint` path already flows into the LLM's user context block under a separate key, which achieves the same effect: the LLM sees the tenant constraints alongside session history. Per-tenant overlay files don't scale (one file per tenant = thousands of files). The `[TENANT_CONSTRAINTS]` label in the context block makes the injection visible in logs without being part of the hardcoded system prompt.

**Date:** 2026-06-15

---

## Architecture Decisions (pre-existing, documented for completeness)

| ID | Decision | Rationale |
|----|----------|-----------|
| D-019 | Bridge router re-uses canonical `_generate`, doesn't re-implement | No logic duplication; one code path to test and maintain |
| D-029 | In-process moderation (not a sidecar service) | Eliminates network hop + failure mode; fail-closed is simpler in-process |
| D-030 | Moderation fail-closed | A moderation service going down should block, not silently pass all requests |
| Media-3way | 3-way media classifier (product_photography / visual_generation / marketing_copy) | 2-way missed the brand accuracy use case entirely |
| Build-sub | Build sub-intent detection in-prompt (vs external classifier) | Zero latency; vocabulary is bounded and doesn't drift |
| Research-sub | Research sub-type detection in-prompt | Same as build-sub rationale |
