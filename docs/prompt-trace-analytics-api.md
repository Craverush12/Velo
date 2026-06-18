# Prompt Trace Analytics API

This spec describes how an external analytics dashboard can consume ThinkVelocity prompt observability data. It is intentionally API-only: the dashboard may render the data however it wants.

## Base URL

Use the ThinkVelocity backend URL:

```text
http://localhost:8000
```

Production should use the deployed backend origin.

## Authentication

Dashboard server-side code should send a bearer token:

```http
Authorization: Bearer <PROMPT_ANALYTICS_API_TOKEN>
```

Set the same token in the ThinkVelocity backend environment:

```text
PROMPT_ANALYTICS_API_TOKEN=<shared-server-token>
```

Browser clients should not call these endpoints directly. Keep the token on the dashboard server and proxy or fetch from server components/API routes.

Admin users can also access these endpoints with the existing `/admin/api/login` session cookie.

## Runtime Environment

Optional backend environment variables:

```text
PROMPT_TRACE_ENABLED=true
PROMPT_TRACE_STORAGE_PATH=storage/traces
PROMPT_TRACE_CAPTURE_FULL_TEXT=true
PROMPT_ANALYTICS_API_TOKEN=<shared-server-token>
```

`PROMPT_TRACE_CAPTURE_FULL_TEXT=false` keeps hashes and previews but omits full assembled prompt/message text from trace records. Incognito prompt runs do not write traces.

## Endpoints

### List Prompt Traces

```http
GET /admin/api/prompt-traces
```

Query parameters:

```text
flow=enhance|refine
status=completed|failed
user_id=<id>
prompt_mode=normal|research|fast_build|media|caveman
search=<text>
page=1
page_size=25
include_payload=false
```

Response:

```json
{
  "items": [
    {
      "trace_id": "uuid",
      "created_at": "2026-06-17T10:00:00+00:00",
      "flow": "enhance",
      "status": "completed",
      "user_id": "user_123",
      "session_id": "session_123",
      "prompt_mode": "research",
      "target_ai": "claude",
      "model": "llama-3.3-70b-versatile",
      "prompt_version": "sha256",
      "prompt_files": ["enhance_system.md", "enhance_research_overlay.md"],
      "raw_prompt_preview": "Write a launch plan...",
      "output_preview": "You are a growth strategist...",
      "quality_score": 0.82,
      "tokens": 530,
      "latency_ms": 1400,
      "changed": true,
      "similarity": 0.43
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 25,
  "pages": 1
}
```

Use this for trace tables, filters, top-level drilldowns, and recent activity.

### Get Prompt Trace Detail

```http
GET /admin/api/prompt-traces/{trace_id}
```

Response:

```json
{
  "trace": {
    "trace_id": "uuid",
    "flow": "enhance",
    "status": "completed",
    "user_id": "user_123",
    "prompt_mode": "research",
    "target_ai": "claude",
    "model": "llama-3.3-70b-versatile",
    "prompt_version": "sha256",
    "prompt_files": ["enhance_system.md"],
    "input": {
      "raw_prompt": "Write a launch plan",
      "raw_prompt_hash": "sha256",
      "redacted_prompt": "Write a launch plan",
      "redactions_count": 0,
      "attachments_count": 0,
      "context_hint_used": false,
      "persona_hint_used": false
    },
    "messages": {
      "system_prompt": "...",
      "system_prompt_hash": "sha256",
      "system_prompt_preview": "...",
      "user_message": "...",
      "user_message_hash": "sha256",
      "user_message_preview": "..."
    },
    "output": {
      "raw_model_output": "{...}",
      "raw_model_output_hash": "sha256",
      "raw_model_output_preview": "{...}",
      "final_text": "Enhanced prompt...",
      "quality_score": 0.82,
      "framework_used": "RTF",
      "summary": "..."
    },
    "usage": {
      "prompt_tokens": 200,
      "completion_tokens": 330,
      "total_tokens": 530
    },
    "timings": {
      "total_ms": 1400
    },
    "validation": {
      "status": "valid",
      "repair_status": "not_needed",
      "schema_version": "2026-05-14.prompt-contracts.v3",
      "error": ""
    },
    "before_after": {
      "before": "Write a launch plan",
      "after": "Enhanced prompt...",
      "changed": true,
      "similarity": 0.43,
      "before_hash": "sha256",
      "after_hash": "sha256"
    }
  }
}
```

Use this for a trace detail drawer/page. Treat full prompt/message fields as sensitive.

### Get Prompt Trace Diff

```http
GET /admin/api/prompt-traces/{trace_id}/diff
```

Response:

```json
{
  "trace_id": "uuid",
  "before": "Write a launch plan",
  "after": "Enhanced prompt...",
  "unified_diff": "--- before\n+++ after\n@@ ...",
  "similarity": 0.43
}
```

Use this for before/after viewers. The `unified_diff` field is plain text.

### Get Prompt Metrics

```http
GET /admin/api/prompt-metrics
```

Query parameters:

```text
days=7
```

Response:

```json
{
  "metrics": {
    "generated_at": "2026-06-17T10:00:00+00:00",
    "totals": {
      "traces": 120,
      "completed": 116,
      "failed": 4,
      "tokens": 84200
    },
    "quality": {
      "average_score": 0.78,
      "samples": 116
    },
    "latency": {
      "average_ms": 1530.4,
      "samples": 120
    },
    "by_flow": {
      "enhance": {"count": 90, "tokens": 64000},
      "refine": {"count": 30, "tokens": 20200}
    },
    "by_status": {
      "completed": {"count": 116, "tokens": 83000},
      "failed": {"count": 4, "tokens": 1200}
    },
    "by_prompt_mode": {
      "research": {"count": 50, "tokens": 31000}
    },
    "by_model": {
      "llama-3.3-70b-versatile": {"count": 120, "tokens": 84200}
    }
  }
}
```

Use this for KPI cards, trend inputs, and grouped charts.

## Expected Dashboard Integration

1. Store `THINKVELOCITY_API_URL` and `THINKVELOCITY_PROMPT_ANALYTICS_TOKEN` in the analytics dashboard server environment.
2. Fetch `/admin/api/prompt-metrics` server-side for summary cards.
3. Fetch `/admin/api/prompt-traces` server-side for table data.
4. Fetch `/admin/api/prompt-traces/{trace_id}` only when a user opens a detail view.
5. Fetch `/admin/api/prompt-traces/{trace_id}/diff` only when rendering a before/after comparison.
6. Never expose the bearer token or full trace payloads to unauthenticated browser code.

## Error Cases

```json
{"detail": "Admin login required"}
```

Returned with HTTP 401 when no valid admin session or bearer token is supplied.

```json
{"detail": "Prompt trace not found"}
```

Returned with HTTP 404 for unknown trace IDs.
