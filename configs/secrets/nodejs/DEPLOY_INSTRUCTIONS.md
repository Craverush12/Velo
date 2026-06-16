# AWS Secrets Manager — Node.js Services Deploy Instructions

**Covers:** `consumer-backend` (Express, port 3005) and `enterprise-backend` (NestJS, port 3000)
**AWS Region:** `ap-south-1`
**Secret namespaces:**
- `thinkvelocity/production/consumer-backend`
- `thinkvelocity/production/enterprise-backend`

---

## Step 1 — Attach the IAM policy to the EC2 instance role

The EC2 instance that runs the Docker containers must have an IAM role with the
following policy attached.  No access keys or credentials are ever stored on disk.

**Policy name to create:** `ThinkVelocitySecretsManagerReadOnly`

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowReadThinkVelocitySecrets",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:ap-south-1:*:secret:thinkvelocity/production/consumer-backend*",
        "arn:aws:secretsmanager:ap-south-1:*:secret:thinkvelocity/production/enterprise-backend*"
      ]
    },
    {
      "Sid": "AllowDecryptWithDefaultKey",
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "secretsmanager.ap-south-1.amazonaws.com"
        }
      }
    }
  ]
}
```

### Attach the policy to the instance role

```bash
# 1. Create the policy (run once from your local machine with admin credentials)
aws iam create-policy \
  --policy-name ThinkVelocitySecretsManagerReadOnly \
  --policy-document file://thinkvelocity-sm-policy.json \
  --region ap-south-1

# 2. Find the role currently attached to the EC2 instance
#    Replace i-0123456789abcdef0 with your actual instance ID
aws ec2 describe-iam-instance-profile-associations \
  --filters "Name=instance-id,Values=i-0123456789abcdef0" \
  --region ap-south-1

# 3. Attach the policy to that role (replace ROLE_NAME)
aws iam attach-role-policy \
  --role-name ROLE_NAME \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/ThinkVelocitySecretsManagerReadOnly
```

---

## Step 2 — Populate secrets in AWS Secrets Manager

Run these commands once from your local machine.  Replace every `REPLACE_WITH_*`
placeholder with the real value before running.

### consumer-backend secret

```bash
aws secretsmanager create-secret \
  --name "thinkvelocity/production/consumer-backend" \
  --description "All env vars for the ThinkVelocity consumer-backend Express service" \
  --region ap-south-1 \
  --secret-string '{
    "DATABASE_URL":              "postgresql://app_consumer:REPLACE_WITH_CONSUMER_DB_PASS@127.0.0.1:5432/thinkvelocity_prod",
    "DB_SCHEMA":                 "consumer",
    "REDIS_URL":                 "redis://:REPLACE_WITH_REDIS_PASS@127.0.0.1:6379",
    "JWT_SECRET":                "REPLACE_WITH_JWT_SECRET_64CHARS",
    "JWT_REFRESH_SECRET":        "REPLACE_WITH_JWT_REFRESH_SECRET_64CHARS",
    "JWT_EXPIRY":                "15m",
    "REFRESH_TOKEN_EXPIRY":      "30d",
    "GROQ_API_KEY":              "REPLACE_WITH_GROQ_API_KEY",
    "RAZORPAY_KEY_ID":           "REPLACE_WITH_RAZORPAY_KEY_ID",
    "RAZORPAY_KEY_SECRET":       "REPLACE_WITH_RAZORPAY_KEY_SECRET",
    "RAZORPAY_WEBHOOK_SECRET":   "REPLACE_WITH_RAZORPAY_WEBHOOK_SECRET",
    "SENDGRID_API_KEY":          "REPLACE_WITH_SENDGRID_API_KEY",
    "EMAIL_FROM":                "noreply@thinkvelocity.in",
    "ALLOWED_ORIGINS":           "https://thinkvelocity.in,https://www.thinkvelocity.in",
    "LOG_LEVEL":                 "info",
    "LOG_FORMAT":                "json",
    "SENTRY_DSN":                "REPLACE_WITH_CONSUMER_SENTRY_DSN",
    "AWS_S3_BUCKET":             "thinkvelocity-backups",
    "TRUST_PROXY":               "1",
    "REQUEST_TIMEOUT_MS":        "60000"
  }'
```

To update an existing secret (after initial creation):

```bash
aws secretsmanager put-secret-value \
  --secret-id "thinkvelocity/production/consumer-backend" \
  --region ap-south-1 \
  --secret-string '{ ... updated JSON ... }'
```

### enterprise-backend secret

```bash
aws secretsmanager create-secret \
  --name "thinkvelocity/production/enterprise-backend" \
  --description "All env vars for the ThinkVelocity enterprise-backend NestJS service" \
  --region ap-south-1 \
  --secret-string '{
    "DATABASE_URL":      "postgresql://app_enterprise:REPLACE_WITH_ENTERPRISE_DB_PASS@127.0.0.1:5432/thinkvelocity_prod?schema=enterprise",
    "REDIS_URL":         "redis://:REPLACE_WITH_REDIS_PASS@127.0.0.1:6379",
    "JWT_SECRET":        "REPLACE_WITH_ENTERPRISE_JWT_SECRET_64CHARS",
    "JWT_EXPIRY":        "8h",
    "GROQ_API_KEY":      "REPLACE_WITH_GROQ_API_KEY",
    "OPENAI_API_KEY":    "REPLACE_WITH_OPENAI_API_KEY",
    "SENDGRID_API_KEY":  "REPLACE_WITH_SENDGRID_API_KEY",
    "ALLOWED_ORIGINS":   "https://enterprise.thinkvelocity.in",
    "LOG_LEVEL":         "info",
    "LOG_FORMAT":        "json",
    "SENTRY_DSN":        "REPLACE_WITH_ENTERPRISE_SENTRY_DSN"
  }'
```

---

## Step 3 — Install the shared secrets loader in each service

### 3a. Install the AWS SDK dependency

In both `consumer-backend/` and `enterprise-backend/`:

```bash
npm install @aws-sdk/client-secrets-manager
```

Add to `package.json` as a production dependency (not devDependency).

### 3b. Copy the loader module

```bash
# For consumer-backend (Express)
cp configs/secrets/nodejs/secrets-loader.js consumer-backend/secrets-loader.js

# For enterprise-backend (NestJS)
cp configs/secrets/nodejs/secrets-loader.js enterprise-backend/src/secrets-loader.js
```

### 3c. Integrate the startup patch

**consumer-backend (Express)**

```bash
cp configs/secrets/nodejs/consumer-backend-startup.js consumer-backend/startup.js
```

Edit `startup.js` and update the `require('./server')` line to match your actual
entry point filename (e.g. `./src/index`, `./app`, etc.).

Update `package.json`:
```json
{
  "scripts": {
    "start": "node startup.js",
    "start:dev": "node startup.js"
  }
}
```

Update `Dockerfile` CMD:
```dockerfile
CMD ["node", "startup.js"]
```

---

**enterprise-backend (NestJS)**

```bash
cp configs/secrets/nodejs/enterprise-backend-startup.ts enterprise-backend/src/main.ts
```

This replaces `src/main.ts`.  If your existing `main.ts` has custom global
middleware, pipes, or interceptors, merge them into the new file in the
section marked "Optional: global prefix, CORS, pipes".

The `nest-cli.json` `entryFile` (default: `"main"`) requires no change.

Update `Dockerfile` CMD for production:
```dockerfile
CMD ["node", "dist/main.js"]
```

---

## Step 4 — Set AWS_REGION in the container environment

`secrets-loader.js` uses `AWS_REGION` to detect whether to call Secrets Manager.
Ensure it is present in the Docker environment block (it is non-sensitive):

In `configs/prod/docker-compose.yml`, the environment blocks for both services
already include `AWS_REGION: ap-south-1`.  Verify it is present; add if missing:

```yaml
services:
  consumer-backend:
    environment:
      AWS_REGION: ap-south-1
      NODE_ENV: production
      PORT: 3005
      # All other secrets are fetched from SM at startup — no plaintext values here

  enterprise-backend:
    environment:
      AWS_REGION: ap-south-1
      NODE_ENV: production
      PORT: 3000
```

Remove all plaintext secret values from the `environment:` blocks in docker-compose
once the SM integration is verified working (keep only non-secret vars like
`NODE_ENV`, `PORT`, `AWS_REGION`, `LOG_LEVEL`).

---

## Step 5 — Local development (no AWS required)

For local dev, secrets-loader falls back to `process.env` when `AWS_REGION` is
not set.  Use a `.env` file in each service's project root with real dev values:

```bash
# consumer-backend/.env  (gitignored — never commit this file)
DATABASE_URL=postgresql://app_consumer:devpassword@127.0.0.1:5432/thinkvelocity_dev
REDIS_URL=redis://127.0.0.1:6379
JWT_SECRET=local-dev-jwt-secret-at-least-32-chars
JWT_REFRESH_SECRET=local-dev-refresh-secret-at-least-32-chars
GROQ_API_KEY=gsk_...
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...
SENDGRID_API_KEY=SG....
```

The startup files call `require('dotenv').config()` before `initSecrets()`, so
`.env` is loaded first.  Because `AWS_REGION` is absent, Secrets Manager is
never contacted.  The service boots purely from `.env` values.

Ensure `.env` is in `.gitignore`:
```
# .gitignore
.env
.env.*
!.env.example
```

---

## Step 6 — Verify the integration

After deploying, confirm secrets are being fetched:

```bash
# Tail the container logs immediately after startup
docker logs tv-consumer-backend --tail 30

# You should see a line like:
# [secrets-loader] Loaded secret "thinkvelocity/production/consumer-backend"
#   from AWS Secrets Manager (14 vars injected into process.env, 3 already present/skipped)

docker logs tv-enterprise-backend --tail 30
# [secrets-loader] Loaded secret "thinkvelocity/production/enterprise-backend"
#   from AWS Secrets Manager (10 vars injected into process.env, 2 already present/skipped)
```

If you see the warning line instead:
```
[secrets-loader] WARNING: Failed to fetch secret "..." from AWS Secrets Manager.
```
Check:
1. The EC2 instance role has `ThinkVelocitySecretsManagerReadOnly` attached.
2. `AWS_REGION=ap-south-1` is in the container environment.
3. The secret name exactly matches (case-sensitive).
4. Run `aws secretsmanager get-secret-value --secret-id thinkvelocity/production/consumer-backend --region ap-south-1`
   from the EC2 instance to confirm IAM access.

---

## Summary — What changes in production

| Before (SOC2 gap)                        | After (SOC2 CC6.7 compliant)                  |
|------------------------------------------|-----------------------------------------------|
| Secrets in `.env` files on disk          | Secrets in AWS Secrets Manager (encrypted)    |
| Plaintext values in docker-compose.yml   | Only non-secret vars in docker-compose.yml    |
| Secrets in CI/CD env vars                | CI/CD has no secret values — SM is authoritative |
| Rotation requires container rebuild      | Rotation only requires container restart       |
| No audit trail for secret access         | CloudTrail logs every `GetSecretValue` call   |
