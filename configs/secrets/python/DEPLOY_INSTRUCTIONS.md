# AWS Secrets Manager — Python Services Deploy Guide

Services: **python-ai** (port 8005) and **extension-api** (port 8000)  
AWS Region: **ap-south-1**  
SOC2 control: CC6.7 (logical access over secrets)

---

## 1. requirements.txt additions

Add to each service's `requirements.txt`:

```
boto3>=1.26.0
botocore>=1.29.0
pydantic-settings>=2.0.0   # pydantic v2 only; omit for pydantic v1
python-dotenv>=1.0.0       # already present; keep for local dev fallback
```

---

## 2. IAM Policy for the EC2 Instance Role

Attach this inline policy (or a managed policy) to the IAM role used by the
EC2 instances that run the Docker containers.  The role must already exist and
be attached to the instance via an Instance Profile.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadThinkVelocitySecrets",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": [
        "arn:aws:secretsmanager:ap-south-1:*:secret:thinkvelocity/production/python-ai*",
        "arn:aws:secretsmanager:ap-south-1:*:secret:thinkvelocity/production/extension-api*"
      ]
    },
    {
      "Sid": "ListSecretsForAudit",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:ListSecrets"
      ],
      "Resource": "*"
    }
  ]
}
```

**Notes:**
- Replace `*` in the account ID position with your 12-digit AWS account ID for
  stricter least-privilege (e.g. `arn:aws:secretsmanager:ap-south-1:123456789012:secret:...`).
- The trailing `*` after the secret name is required because AWS appends a
  6-character random suffix to secret ARNs.
- No `secretsmanager:PutSecretValue` or `DeleteSecret` — containers are
  read-only.

---

## 3. Create the Secrets in AWS Secrets Manager (aws CLI)

Run once per environment.  Replace placeholder values with real secrets.

### 3a. python-ai secret

```bash
aws secretsmanager create-secret \
  --region ap-south-1 \
  --name "thinkvelocity/production/python-ai" \
  --description "All env vars for the python-ai FastAPI service (port 8005)" \
  --secret-string '{
    "APP_ENV": "production",
    "PORT": "8005",
    "DATABASE_URL": "postgresql://app_consumer:ACTUAL_PASSWORD@127.0.0.1:5432/thinkvelocity_prod",
    "DB_SCHEMA": "consumer",
    "REDIS_URL": "redis://:ACTUAL_REDIS_PASSWORD@127.0.0.1:6379",
    "GROQ_API_KEY": "gsk_ACTUAL_GROQ_KEY",
    "OPENAI_API_KEY": "sk-ACTUAL_OPENAI_KEY",
    "ANTHROPIC_API_KEY": "sk-ant-ACTUAL_ANTHROPIC_KEY",
    "EMBEDDING_MODEL": "all-MiniLM-L6-v2",
    "EMBEDDING_DIM": "1024",
    "EMBEDDING_BATCH_SIZE": "32",
    "MAX_CONTEXT_WINDOW": "10",
    "CONTEXT_SIMILARITY_THRESHOLD": "0.75",
    "MAX_MEMORIES_PER_USER": "500",
    "MAX_REQUESTS_PER_MINUTE": "60",
    "MAX_CONCURRENT_LLM_CALLS": "10",
    "ALLOWED_ORIGINS": "https://thinkvelocity.in,https://www.thinkvelocity.in,https://enterprise.thinkvelocity.in,chrome-extension://",
    "LOG_LEVEL": "info",
    "LOG_FORMAT": "json",
    "SENTRY_DSN": "https://ACTUAL_SENTRY_DSN@sentry.io/PROJECT_ID",
    "AWS_REGION": "ap-south-1"
  }'
```

### 3b. extension-api secret

```bash
aws secretsmanager create-secret \
  --region ap-south-1 \
  --name "thinkvelocity/production/extension-api" \
  --description "All env vars for the extension-api FastAPI service (port 8000)" \
  --secret-string '{
    "APP_ENV": "production",
    "PORT": "8000",
    "DATABASE_URL": "postgresql://app_extension:ACTUAL_PASSWORD@127.0.0.1:5432/thinkvelocity_prod",
    "DB_SCHEMA": "extension",
    "REDIS_URL": "redis://:ACTUAL_REDIS_PASSWORD@127.0.0.1:6379",
    "JWT_SECRET": "ACTUAL_JWT_SECRET_MIN_32_CHARS",
    "GROQ_API_KEY": "gsk_ACTUAL_GROQ_KEY",
    "ALLOWED_ORIGINS": "https://thinkvelocity.in,https://www.thinkvelocity.in,chrome-extension://",
    "RATE_LIMIT_PER_MINUTE": "30",
    "RATE_LIMIT_AUTH_PER_MINUTE": "5",
    "LOG_LEVEL": "info",
    "LOG_FORMAT": "json",
    "AWS_REGION": "ap-south-1"
  }'
```

### Updating an existing secret

```bash
aws secretsmanager put-secret-value \
  --region ap-south-1 \
  --secret-id "thinkvelocity/production/python-ai" \
  --secret-string '{ ... updated JSON ... }'
```

### Verifying a secret

```bash
aws secretsmanager get-secret-value \
  --region ap-south-1 \
  --secret-id "thinkvelocity/production/python-ai" \
  --query SecretString \
  --output text | python3 -m json.tool
```

---

## 4. Integrate into Existing FastAPI Services

### 4a. python-ai — patch main.py

Open `main.py` and add the bootstrap block as the **very first executable
lines**, before any other project import:

```python
# ── Secret bootstrap — MUST be first ──────────────────────────────────────
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from configs.secrets.python.secrets_loader import init_secrets
init_secrets("thinkvelocity/production/python-ai")
# ── End secret bootstrap ───────────────────────────────────────────────────

# Existing imports continue below (load_dotenv is now a harmless no-op for
# keys already set by init_secrets):
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
# ... rest of main.py unchanged
```

### 4b. extension-api — patch its main.py / app.py

```python
# ── Secret bootstrap ───────────────────────────────────────────────────────
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from configs.secrets.python.secrets_loader import init_secrets
init_secrets("thinkvelocity/production/extension-api")
# ── End secret bootstrap ───────────────────────────────────────────────────

from dotenv import load_dotenv
load_dotenv()
# ... rest of app unchanged
```

### 4c. Optional — use the Settings class directly

If you want pydantic validation and IDE autocomplete for all settings:

```python
# main.py (python-ai)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from configs.secrets.python.settings_with_sm import get_python_ai_settings

settings = get_python_ai_settings()   # SM values injected and validated here

from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "secrets_source": settings.secrets_source,
    }
```

---

## 5. Local Development (python-dotenv fallback)

No changes needed for local dev.  When boto3 is not installed, or when AWS
credentials are absent, `secrets_loader.py` silently falls back to
`python-dotenv` and reads `.env` from the project root.

Workflow:

```bash
# 1. Copy the template
cp configs/prod/env-template/python-ai.env .env

# 2. Fill in real local values (never commit this file)
#    DATABASE_URL, GROQ_API_KEY, REDIS_URL, etc.

# 3. Run as normal — SM loader will detect no AWS and use .env
uvicorn main:app --reload --port 8005
```

The log output will tell you which source was used:

```
INFO secrets_loader: boto3 not installed — falling back to env file / os.environ
INFO secrets_loader: loaded .env file via python-dotenv
```

or in production:

```
INFO secrets_loader: loaded 22 secrets from AWS Secrets Manager ('thinkvelocity/production/python-ai')
```

---

## 6. Docker / EC2 Considerations

- The EC2 instance must have the Instance Profile attached **before** the
  container starts.  boto3 uses the IMDSv2 metadata endpoint automatically.
- Do **not** set `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` in the
  container — let the instance role handle credentials.
- Set `AWS_REGION=ap-south-1` in the Docker run command or
  `docker-compose.yml` so boto3 does not need to auto-detect the region:
  ```yaml
  environment:
    - AWS_REGION=ap-south-1
  ```
- The `.env` file should **not** be COPY'd into the production Docker image.
  Add it to `.dockerignore`.

---

## 7. File Reference

| File | Purpose |
|------|---------|
| `configs/secrets/python/secrets_loader.py` | Core SM loader + os.environ merge, caching, fallback |
| `configs/secrets/python/startup_patch_fastapi.py` | Integration pattern + runnable demo |
| `configs/secrets/python/settings_with_sm.py` | Pydantic BaseSettings subclass for both services |
| `configs/secrets/python/DEPLOY_INSTRUCTIONS.md` | This file |
