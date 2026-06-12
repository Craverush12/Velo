# Hot Patches

Scripts for applying fixes to running containers without rebuilding images.
Each patch should be a last resort — rebuild the image when time allows (T-070).

## guardrail-fail-closed

**Fixes:**
1. `MODERATION_SERVICE_URL` wrong path (was `/ai/enhance`, must be `/ai`)
2. Fail-open behavior → fail-closed (ALLOW on error → BLOCK on error)

**Decision reference:** D-030 — enterprise moderation failures must be fail-closed

**Apply:**
```bash
# On server 35.154.138.184:
bash configs/hotpatches/apply-guardrail-fix.sh
```

**Verify:**
```bash
curl -X POST http://127.0.0.1:8005/ai/moderation/check \
  -H 'Content-Type: application/json' \
  -d '{"content":"my ssn is 123-45-6789"}'
# Should return: {"decision": "REDACT", ...}
```

**Permanent fix:** T-070 (rebuild Docker image with corrected `guardrail.service.ts`)

---

**Files:**
- `guardrail-fail-closed.patch` — unified diff showing the TypeScript source change (reference only; compiled JS is what gets patched)
- `apply-guardrail-fix.sh` — shell script to apply the patch to the running container via `docker exec` + `sed`
