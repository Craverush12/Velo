# ThinkVelocity AI Unified

A single FastAPI service that merges three previously separate Python services
into one app with router namespaces. See `docs/python-ai-merge-plan.md` and
`docs/python-ai-endpoint-map.md` for the full audit and rationale.

| Namespace    | Source service (old)                          | Old port |
|--------------|-----------------------------------------------|----------|
| `/ai/*`      | `prompt-enhance` (Server 3) — **canonical**   | 3002     |
| `/context/*` | `context-engine-container-dev` (Server 2)     | 8001     |

> The Server 2 `python-backend-container` is a **stale** build of the same code
> as `prompt-enhance`; it is ignored. Server 3 is the source of truth for `/ai/*`.

---

## Run locally

```bash
cd python-ai-unified
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill in keys (or leave blank — app boots degraded)
uvicorn main:app --reload --port 8005
```

Then:

```bash
curl http://localhost:8005/health
```

The app is **boot-tolerant**: if Groq keys, PostgreSQL, Redis, or even a whole
router are missing, startup logs a warning and continues. `/health` reports the
status of each router and shared resource (`ok` when everything is up,
`degraded` otherwise).

`python main.py` also works (reads `APP_PORT`, default 8005; reloads when
`DEV_MODE=true`).

---

## Layout

```
python-ai-unified/
├── main.py              # app: lifespan (groq/db/redis), CORS, GZip, router mounts, /health
├── requirements.txt     # union of all three services' deps
├── Dockerfile           # multi-stage; non-root UID 10001; HF model pre-baked
├── .env.example         # full env superset (merge-plan §3)
├── routers/
│   ├── ai/              # /ai/* — enhance, refine, clarify, moderation, … (41 routes)
│   └── context.py       # /context/* — process-context, process-essence, … (7 routes)
└── shared/
    ├── settings.py      # pydantic-settings: merged env superset  -> `settings`, `get_settings`
    ├── groq_client.py   # Groq key-pool rotation                  -> `groq_pool`
    ├── db.py            # SQLAlchemy async engine (PG_CONNECTION)  -> `engine`, `get_session`
    ├── redis_cache.py   # Redis client + cache helpers             -> `get_redis`
    ├── embedding_client.py  # NVIDIA API + local HF fallback
    ├── node_client.py   # HTTP client for the Node.js backend (/context/* persistence)
    └── logging_config.py    # `configure_logging(level)`
```

`main.py` mounts the routers with `include_router(ai_router, prefix="/ai")` and
`include_router(context_router, prefix="/context")`. Both mounts are wrapped in
`try/except ImportError` so the app boots even while routers are still being
built in parallel.

---

## Reconciliation workflow

Before trusting the hand-ported routers, diff them against the **canonical
source baked into the live containers** (the host source trees may be stale).

1. **Fetch canonical source** — run on each server (read-only on containers):
   ```bash
   # Server 3 (prompt-enhance) and Server 2 (context-engine)
   ./configs/env-changes/T-031-fetch-canonical-source.sh --scan   # dry run
   ./configs/env-changes/T-031-fetch-canonical-source.sh --pull   # docker cp + tarball
   # scp the tarball back, then: tar -xzf canonical-source-*.tar.gz  -> ./_canonical/
   ```
2. **Diff** `./_canonical/*` against the implemented routers:
   ```bash
   diff -ru ./_canonical/prompt-enhance/app/src   ./python-ai-unified/routers/ai
   diff -ru ./_canonical/context-engine/app/src   ./python-ai-unified/routers
   ```
3. **Resolve** each discrepancy as a checklist item in `RECONCILE.md` — confirm
   every canonical route from `docs/python-ai-endpoint-map.md` (41 under `/ai/*`,
   7 under `/context/*`) is present and behaves identically.

---

## Deploy / cutover (merge-plan §8)

1. **Build & ship** the unified image (`Dockerfile`, port 8005). The builder
   pre-downloads `all-MiniLM-L6-v2`; runtime runs as non-root UID 10001 with
   `TORCH_HOME=/tmp/torch` so it works on a read-only root FS + tmpfs.
2. **Configure** `.env` from `.env.example` (or wire AWS Secrets Manager by
   setting `AWS_REGION` + `SM_SECRET_NAME` — `shared/settings.py` injects SM
   values at boot). Note `CONTEXT_ENGINE_URL` is gone: the context engine is now
   an in-process router, not an HTTP hop.
3. **Route at nginx / load balancer:**
   - `/ai/*`      → `unified:8005`
   - `/context/*` → `unified:8005`
   Update internal callers of the old `:8001` context engine with
   `configs/env-changes/T-032-context-endpoint-migration.sh`.
4. **Verify** `/health`, `/ai/health`, `/context/health` all return healthy.
5. **Decommission** the three old containers (`prompt-enhance`,
   `python-backend-container`, `context-engine-container-dev`) once traffic is
   confirmed flowing through the unified service.
