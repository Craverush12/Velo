# =============================================================================
# Dockerfile — ThinkVelocity AI Unified service
# Python 3.11-slim, multi-stage. Port: 8005.
# Merges prompt-enhance (/ai/*) + context-engine (/context/*).
# Hardening mirrors configs/prod/dockerfiles/Dockerfile.python-ai:
#   - multi-stage build (builder pre-downloads the HF embedding model)
#   - non-root user UID 10001 (SOC2 CC6.6 P2-T06)
#   - TORCH_HOME / HF cache writable under /tmp for read-only root FS + tmpfs
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: builder — install deps and pre-download the sentence-transformers
#                    model so production starts fast on a read-only FS.
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS builder

# Build tools for native extensions (psycopg, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Create the non-root user here too, so the model cache lands in its home dir
# with the correct ownership before we copy it into the runtime stage.
RUN groupadd -g 10001 nonroot && \
    useradd -u 10001 -g nonroot -m -s /sbin/nologin nonroot

# Install Python deps into a relocatable prefix (cleaner copy into runtime).
# Use python-ai-unified/requirements.txt (build context is the repo root).
COPY python-ai-unified/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# Pre-download all-MiniLM-L6-v2 (local embedding fallback). Runs as nonroot so
# the cache materializes under /home/nonroot/.cache/huggingface.
USER nonroot
ENV HF_HOME=/home/nonroot/.cache/huggingface
RUN PYTHONPATH=/install/lib/python3.11/site-packages \
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# -----------------------------------------------------------------------------
# Stage 2: production — slim runtime image.
# -----------------------------------------------------------------------------
FROM python:3.11-slim AS production

# Runtime system deps (libpq for psycopg, curl for the healthcheck).
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user/group (SOC2 CC6.6 P2-T06).
RUN groupadd -g 10001 nonroot && \
    useradd -u 10001 -g nonroot -m -s /sbin/nologin nonroot

# Installed Python packages from the builder.
COPY --from=builder /install /usr/local

# Pre-downloaded HuggingFace model cache from the builder.
COPY --from=builder --chown=nonroot:nonroot \
    /home/nonroot/.cache/huggingface \
    /home/nonroot/.cache/huggingface

WORKDIR /app

# Application source.
COPY --chown=nonroot:nonroot . .

USER nonroot

EXPOSE 8005

ENV APP_ENV=production \
    APP_PORT=8005 \
    HF_HOME=/home/nonroot/.cache/huggingface \
    TRANSFORMERS_CACHE=/home/nonroot/.cache/huggingface \
    TORCH_HOME=/tmp/torch \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # python-ai-unified imports 'shared.*' as top-level; root api/core also top-level
    PYTHONPATH=/app/python-ai-unified:/app

# Healthcheck hits the root /health (returns {"status": "ok"|"degraded", ...}).
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=60s \
  CMD curl -sf http://127.0.0.1:8005/health | grep -q '"status"'

# uvicorn handles signals natively; no wrapper needed.
CMD ["uvicorn", "python-ai-unified.main:app", "--host", "0.0.0.0", "--port", "8005", \
     "--workers", "2", "--loop", "uvloop", "--log-level", "info"]
