#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://localhost:8000}}"
BASE_URL="${BASE_URL%/}"
RUN_LLM_SMOKE="${RUN_LLM_SMOKE:-0}"
RUN_AUDIO_SMOKE="${RUN_AUDIO_SMOKE:-0}"
RUN_SERVER_TESTS="${RUN_SERVER_TESTS:-0}"
RUN_MCP_SMOKE="${RUN_MCP_SMOKE:-0}"
RUN_PERSONALIZATION_SMOKE="${RUN_PERSONALIZATION_SMOKE:-0}"
RUN_NEURO_SMOKE="${RUN_NEURO_SMOKE:-0}"
AUDIO_FILE="${AUDIO_FILE:-}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

log() {
  printf '[smoke] %s\n' "$1"
}

fail() {
  printf '[smoke] FAILED: %s\n' "$1" >&2
  exit 1
}

curl_get() {
  local path="$1"
  local out="$2"
  curl -fsS "$BASE_URL$path" -o "$out"
}

curl_json() {
  local method="$1"
  local path="$2"
  local payload="$3"
  local out="$4"
  curl -fsS -X "$method" "$BASE_URL$path" \
    -H 'Content-Type: application/json' \
    --data "$payload" \
    -o "$out"
}

assert_json_field() {
  local file="$1"
  local field="$2"
  local expected="$3"
  python3 - "$file" "$field" "$expected" <<'PY'
import json
import sys

path, dotted, expected = sys.argv[1:]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
value = data
for part in dotted.split("."):
    value = value[part]
if str(value).lower() != expected.lower():
    raise SystemExit(f"{dotted} expected {expected!r}, got {value!r}")
PY
}

assert_json_has() {
  local file="$1"
  local field="$2"
  python3 - "$file" "$field" <<'PY'
import json
import sys

path, dotted = sys.argv[1:]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
value = data
for part in dotted.split("."):
    value = value[part]
if value in (None, "", [], {}):
    raise SystemExit(f"{dotted} is empty")
PY
}

USER_ID="smoke-$(date +%s)"

log "Base URL: $BASE_URL"

curl_get "/health" "$TMP_DIR/health.json"
assert_json_field "$TMP_DIR/health.json" "status" "ok"
assert_json_has "$TMP_DIR/health.json" "schema_version"
log "GET /health"

curl_get "/ready" "$TMP_DIR/ready.json"
assert_json_field "$TMP_DIR/ready.json" "status" "ok"
assert_json_field "$TMP_DIR/ready.json" "checks.storage.ok" "true"
log "GET /ready"

curl_get "/config" "$TMP_DIR/config.json"
assert_json_has "$TMP_DIR/config.json" "default_user_id"
log "GET /config"

curl_get "/context/$USER_ID" "$TMP_DIR/context.json"
assert_json_field "$TMP_DIR/context.json" "user_id" "$USER_ID"
log "GET /context/{user_id}"

curl_json PATCH "/context/$USER_ID" '{"preferences":{"output_style":"concise"},"personalization_notes":"Smoke test context note."}' "$TMP_DIR/context_patch.json"
assert_json_field "$TMP_DIR/context_patch.json" "preferences.output_style" "concise"
log "PATCH /context/{user_id}"

curl_get "/history/$USER_ID" "$TMP_DIR/history.json"
log "GET /history/{user_id}"

curl_get "/diagnostics/systems" "$TMP_DIR/systems.json"
assert_json_field "$TMP_DIR/systems.json" "status" "ok"
log "GET /diagnostics/systems"

curl_get "/diagnostics/mcp-tools" "$TMP_DIR/mcp_tools.json"
assert_json_has "$TMP_DIR/mcp_tools.json" "tools"
log "GET /diagnostics/mcp-tools"

curl_get "/diagnostics/sources" "$TMP_DIR/sources.json"
log "GET /diagnostics/sources"

curl_get "/diagnostics/context-smoke/$USER_ID" "$TMP_DIR/context_smoke.json"
assert_json_field "$TMP_DIR/context_smoke.json" "ok" "true"
log "GET /diagnostics/context-smoke/{user_id}"

curl_json POST "/intent/update" '{
  "prompt":"Create a launch email for a new AI writing tool.",
  "target_ai":"chatgpt",
  "prompt_mode":"normal",
  "confirmation":{
    "intent":"marketing",
    "domain":"marketing_growth",
    "interpreted_need":"Create a launch email for a new AI writing tool.",
    "deliverable":"A ready-to-send launch email prompt.",
    "confidence":0.9,
    "confirmation_question":"",
    "suggested_prompt_mode":"normal"
  }
}' "$TMP_DIR/intent_update.json"
assert_json_field "$TMP_DIR/intent_update.json" "_updated" "true"
log "POST /intent/update"

if [[ "$RUN_SERVER_TESTS" == "1" ]]; then
  curl_json POST "/diagnostics/tests" '{"suite":"all"}' "$TMP_DIR/tests.json"
  assert_json_field "$TMP_DIR/tests.json" "ok" "true"
  log "POST /diagnostics/tests"
fi

if [[ "$RUN_PERSONALIZATION_SMOKE" == "1" ]]; then
  curl_json POST "/personalization/$USER_ID/extract" '{
    "notes":"Prefer concise senior implementation checklists with risks and verification steps. Avoid generic advice.",
    "apply":false
  }' "$TMP_DIR/personalization.json"
  assert_json_has "$TMP_DIR/personalization.json" "preferences.output_style"
  log "POST /personalization/{user_id}/extract"
fi

if [[ "$RUN_NEURO_SMOKE" == "1" ]]; then
  curl_json POST "/neuro/score" '{
    "raw_prompt":"write a plan",
    "enhanced_prompt":"Write a concise senior engineering implementation plan with tests, risks, and acceptance criteria.",
    "personalization_context":{"tone":"direct","format_preferences":["implementation checklist"]}
  }' "$TMP_DIR/neuro.json"
  assert_json_has "$TMP_DIR/neuro.json" "overall_score"
  assert_json_has "$TMP_DIR/neuro.json" "dimensions.personal_fit"
  log "POST /neuro/score"
fi

if [[ "$RUN_LLM_SMOKE" == "1" ]]; then
  curl_json POST "/intent/confirm" '{
    "prompt":"Turn rough customer interview notes into a prioritized product roadmap.",
    "user_id":"'"$USER_ID"'",
    "target_ai":"chatgpt",
    "prompt_mode":"normal",
    "incognito":true
  }' "$TMP_DIR/intent_confirm.json"
  assert_json_has "$TMP_DIR/intent_confirm.json" "interpreted_need"
  log "POST /intent/confirm"

  curl_json POST "/enhance/compare" '{
    "prompt":"Write a prompt for analyzing churn risk from SaaS customer notes.",
    "user_id":"'"$USER_ID"'",
    "target_ai":"chatgpt",
    "prompt_mode":"normal",
    "incognito":true,
    "modes":["normal"]
  }' "$TMP_DIR/enhance_compare.json"
  assert_json_has "$TMP_DIR/enhance_compare.json" "results"
  log "POST /enhance/compare"

  curl -fsS -N -X POST "$BASE_URL/enhance" \
    -H 'Content-Type: application/json' \
    --data '{"prompt":"Improve this prompt: summarize a sales call.","user_id":"'"$USER_ID"'","target_ai":"chatgpt","incognito":true}' \
    -o "$TMP_DIR/enhance_stream.txt"
  grep -q '"type": "done"\|"type":"done"' "$TMP_DIR/enhance_stream.txt" || fail "POST /enhance did not finish"
  log "POST /enhance"

  curl_json POST "/refine" '{
    "original_prompt":"Summarize customer feedback.",
    "previous_enhanced_prompt":"Summarize customer feedback into themes, risks, and next actions.",
    "clarification_qa":[{"question":"Who is the audience?","answer":"Product managers"}],
    "target_ai":"chatgpt",
    "prompt_mode":"normal",
    "incognito":true
  }' "$TMP_DIR/refine.json"
  assert_json_has "$TMP_DIR/refine.json" "refined_prompt"
  log "POST /refine"

  curl_json POST "/cothinker/turn" '{"user_message":"I need a prompt that helps me plan a focused product roadmap from messy interview notes."}' "$TMP_DIR/cothinker_turn.json"
  assert_json_has "$TMP_DIR/cothinker_turn.json" "session_id"
  SESSION_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["session_id"])' "$TMP_DIR/cothinker_turn.json")"
  log "POST /cothinker/turn"

  curl_json POST "/cothinker/finalize" '{"session_id":"'"$SESSION_ID"'","target_ai":"chatgpt","prompt_mode":"normal","incognito":true}' "$TMP_DIR/cothinker_finalize.json"
  assert_json_has "$TMP_DIR/cothinker_finalize.json" "enhanced_prompt"
  log "POST /cothinker/finalize"
fi

if [[ "$RUN_AUDIO_SMOKE" == "1" ]]; then
  curl_json POST "/cothinker/speak" '{"text":"ThinkVelocity smoke test."}' "$TMP_DIR/speak.mp3"
  test -s "$TMP_DIR/speak.mp3" || fail "POST /cothinker/speak returned empty audio"
  log "POST /cothinker/speak"
fi

if [[ -n "$AUDIO_FILE" ]]; then
  curl -fsS -X POST "$BASE_URL/cothinker/transcribe" \
    -F "audio=@$AUDIO_FILE" \
    -o "$TMP_DIR/transcribe.json"
  assert_json_has "$TMP_DIR/transcribe.json" "transcript"
  log "POST /cothinker/transcribe"
fi

if [[ "$RUN_MCP_SMOKE" == "1" ]]; then
  set +e
  timeout 5 curl -fsS -N "$BASE_URL/mcp/sse" -o "$TMP_DIR/mcp_sse.txt"
  code=$?
  set -e
  if [[ "$code" != "0" && "$code" != "124" ]]; then
    fail "GET /mcp/sse failed with exit code $code"
  fi
  log "GET /mcp/sse"
fi

log "Smoke tests completed"
