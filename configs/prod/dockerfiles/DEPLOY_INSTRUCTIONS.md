# ThinkVelocity — Docker Build & Deploy Instructions

## Prerequisites

- Docker Engine 24+ with BuildKit enabled (default on 24+)
- `docker compose` v2 plugin (`docker compose version`)
- Sufficient disk: ~8 GB for all images (python-ai is largest at ~3-4 GB due to torch)
- AWS credentials to pull secrets from Secrets Manager (or a pre-populated `.env`)

---

## 1. Build all images locally (development / staging smoke-test)

Run from the repo root (where `configs/prod/docker-compose.yml` lives):

```bash
# Build every service image in parallel with BuildKit
DOCKER_BUILDKIT=1 docker compose \
  -f configs/prod/docker-compose.yml \
  build --parallel
```

To build a single service:

```bash
DOCKER_BUILDKIT=1 docker compose \
  -f configs/prod/docker-compose.yml \
  build python-ai
```

> **Note:** `python-ai` build downloads `all-MiniLM-L6-v2` (~90 MB) from HuggingFace
> during the builder stage. This is cached in the layer; subsequent builds skip it.

---

## 2. Tag images for a versioned release

```bash
VERSION=1.2.0   # or $(git rev-parse --short HEAD)

docker tag thinkvelocity/consumer-backend:latest  thinkvelocity/consumer-backend:${VERSION}
docker tag thinkvelocity/python-ai:latest          thinkvelocity/python-ai:${VERSION}
docker tag thinkvelocity/enterprise-backend:latest thinkvelocity/enterprise-backend:${VERSION}
docker tag thinkvelocity/extension-api:latest      thinkvelocity/extension-api:${VERSION}
```

---

## 3. Push to your container registry

Replace `<REGISTRY>` with your ECR endpoint or Docker Hub org.

```bash
REGISTRY=123456789.dkr.ecr.ap-south-1.amazonaws.com
VERSION=1.2.0

# ECR login (AWS)
aws ecr get-login-password --region ap-south-1 \
  | docker login --username AWS --password-stdin ${REGISTRY}

for svc in consumer-backend python-ai enterprise-backend extension-api; do
  docker tag  thinkvelocity/${svc}:${VERSION} ${REGISTRY}/thinkvelocity/${svc}:${VERSION}
  docker tag  thinkvelocity/${svc}:${VERSION} ${REGISTRY}/thinkvelocity/${svc}:latest
  docker push ${REGISTRY}/thinkvelocity/${svc}:${VERSION}
  docker push ${REGISTRY}/thinkvelocity/${svc}:latest
done
```

---

## 4. Reference pre-built registry images in docker-compose.yml

When deploying from a registry (no source code on the server), the `build:` blocks
are ignored and the `image:` field is used directly. Set `VERSION` in your `.env`
or pass it on the command line:

```bash
# .env on the server
VERSION=1.2.0

# Pull latest images
VERSION=1.2.0 docker compose -f configs/prod/docker-compose.yml pull

# Start all services
VERSION=1.2.0 docker compose -f configs/prod/docker-compose.yml up -d
```

Docker Compose resolves `image: thinkvelocity/consumer-backend:${VERSION:-latest}`
from the registry. If `VERSION` is unset it falls back to `latest`.

---

## 5. Deploy to production server (Lightsail)

```bash
# 1. SSH into the server
ssh ubuntu@<server-ip>

# 2. Create deployment directory
sudo mkdir -p /var/www/thinkvelocity
cd /var/www/thinkvelocity

# 3. Copy docker-compose.yml (scp or git pull)
# 4. Populate .env from AWS Secrets Manager — never commit real values
aws secretsmanager get-secret-value \
    --secret-id thinkvelocity/prod/env \
    --query SecretString \
    --output text > .env

# 5. Pull images from ECR
VERSION=1.2.0 docker compose pull

# 6. Start all services
VERSION=1.2.0 docker compose up -d

# 7. Verify all containers healthy (all must show "healthy")
docker compose ps

# 8. Check logs for errors
docker compose logs --tail=50
```

---

## 6. Rolling update (zero downtime via depends_on health gates)

```bash
VERSION=1.3.0 docker compose pull
VERSION=1.3.0 docker compose up -d --no-deps --wait consumer-backend
VERSION=1.3.0 docker compose up -d --no-deps --wait python-ai
VERSION=1.3.0 docker compose up -d --no-deps --wait enterprise-backend
VERSION=1.3.0 docker compose up -d --no-deps --wait extension-api
```

---

## 7. Security notes (SOC2 CC6.6)

- Every app container runs as UID 10001 (`nonroot`) — never root.
- `no-new-privileges:true` prevents privilege escalation via setuid binaries.
- `read_only: true` + `tmpfs: [/tmp]` ensures the container filesystem is immutable at runtime.
- All secrets are injected via environment variables at runtime; no `.env` is baked into any image.
- Postgres and Redis are bound to `127.0.0.1` only — never exposed to `0.0.0.0`.
