# ThinkVelocity Docker + AWS Runtime

## Local Docker

Build and run with Docker Compose:

```bash
docker compose up --build
```

The API listens on:

```text
http://localhost:8000
```

The container stores JSON data at `/data`. The compose file mounts that path to the named volume `thinkvelocity-data`.

Required environment:

```text
GROQ_API_KEY=...
LLM_MODEL=llama-3.3-70b-versatile
APP_ENV=production
STORAGE_PATH=/data
ENABLE_REMOTE_TEST_RUNNER=false
```

## AWS Recommendation

Lightest AWS path for this backend:

1. Build the Docker image.
2. Push it to Amazon ECR.
3. Run it on ECS Fargate or AWS App Runner.
4. Set secrets through AWS Secrets Manager or the service's managed environment secret integration.

For the current JSON-file store, use persistent storage:

- ECS Fargate: mount EFS at `/data`.
- App Runner: treat the filesystem as ephemeral; use it only for stateless demo mode unless you move storage to S3 or Postgres.

Pragmatic production path:

- Short-lived demo: App Runner + no durable context.
- Portable MVP with durable JSON context: ECS Fargate + EFS mounted at `/data`.
- Serious multi-user or enterprise mode: ECS/App Runner + RDS Postgres.

## Build And Push To ECR

```bash
aws ecr create-repository --repository-name thinkvelocity-backend
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
docker build -t thinkvelocity-backend .
docker tag thinkvelocity-backend:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/thinkvelocity-backend:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/thinkvelocity-backend:latest
```

## Runtime Contract

The container expects:

- `PORT`: port for Uvicorn, default `8000`
- `GROQ_API_KEY`: required for LLM calls
- `LLM_MODEL`: Groq chat model
- `APP_ENV`: `development` or `production`
- `STORAGE_PATH`: persistent storage directory, default `/data`

Health check:

```text
GET /health
GET /ready
```
