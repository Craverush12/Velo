# PostgreSQL Backup System — Deploy Guide

**Target server:** Server 2 — `ec2-user@13.203.181.76` (AlmaLinux)
**Database:** `thinkvelocity_prod` (fallback: `localpgvelocity` during rename)
**S3 bucket:** `thinkvelocity-backups` (ap-south-1)
**Backup user:** `backup_user` (PostgreSQL role with `pg_read_all_data`)
**SOC2 control:** A1.2 — Backup and recovery procedures

---

## Prerequisites

- AWS CLI configured locally with admin-level IAM credentials
- SSH access to Server 2 (`ec2-user@13.203.181.76`)
- PostgreSQL 17 running with `backup_user` already created (see `configs/postgresql/`)

---

## Step 1 — Create the S3 Bucket

Run from your local machine:

```bash
# Create the bucket in ap-south-1 (same region as servers)
aws s3api create-bucket \
  --bucket thinkvelocity-backups \
  --region ap-south-1 \
  --create-bucket-configuration LocationConstraint=ap-south-1

# Enable versioning (allows recovery of accidentally deleted backups)
aws s3api put-bucket-versioning \
  --bucket thinkvelocity-backups \
  --versioning-configuration Status=Enabled

# Block ALL public access
aws s3api put-public-access-block \
  --bucket thinkvelocity-backups \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Enable server-side encryption with KMS by default
aws s3api put-bucket-encryption \
  --bucket thinkvelocity-backups \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms"
      },
      "BucketKeyEnabled": true
    }]
  }'
```

---

## Step 2 — S3 Lifecycle Policy

Transition backups to Glacier after 90 days; expire after 400 days (covers 30 daily + 12 monthly).

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket thinkvelocity-backups \
  --lifecycle-configuration '{
    "Rules": [
      {
        "ID": "postgres-daily-lifecycle",
        "Filter": {"Prefix": "postgres/"},
        "Status": "Enabled",
        "Transitions": [
          {"Days": 90, "StorageClass": "GLACIER"}
        ],
        "Expiration": {"Days": 400}
      }
    ]
  }'
```

Note: The backup scripts also enforce retention by actively deleting objects (daily after 30 days, monthly after 365 days). The lifecycle policy is a safety net.

---

## Step 3 — S3 Bucket Policy

Deny all access except the backup IAM role. Replace `ACCOUNT_ID` and role name as needed.

```bash
aws s3api put-bucket-policy \
  --bucket thinkvelocity-backups \
  --policy '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Sid": "DenyPublicAccess",
        "Effect": "Deny",
        "Principal": "*",
        "Action": "s3:*",
        "Resource": [
          "arn:aws:s3:::thinkvelocity-backups",
          "arn:aws:s3:::thinkvelocity-backups/*"
        ],
        "Condition": {
          "Bool": {
            "aws:SecureTransport": "false"
          }
        }
      },
      {
        "Sid": "AllowBackupRole",
        "Effect": "Allow",
        "Principal": {
          "AWS": "arn:aws:iam::ACCOUNT_ID:role/thinkvelocity-server2-backup-role"
        },
        "Action": [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:DeleteObject"
        ],
        "Resource": [
          "arn:aws:s3:::thinkvelocity-backups",
          "arn:aws:s3:::thinkvelocity-backups/*"
        ]
      }
    ]
  }'
```

---

## Step 4 — IAM Role for Server 2

Create an IAM role and attach it to the Server 2 EC2 instance.

### 4a. Create the IAM policy

Save as `backup-iam-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3BackupAccess",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::thinkvelocity-backups",
        "arn:aws:s3:::thinkvelocity-backups/*"
      ]
    },
    {
      "Sid": "SecretsManagerReadBackupSecrets",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "arn:aws:secretsmanager:ap-south-1:ACCOUNT_ID:secret:thinkvelocity/production/*"
      ]
    }
  ]
}
```

```bash
# Create the policy
aws iam create-policy \
  --policy-name ThinkVelocityBackupPolicy \
  --policy-document file://backup-iam-policy.json

# Create the role (trust relationship for EC2)
aws iam create-role \
  --role-name thinkvelocity-server2-backup-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ec2.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach the policy to the role
aws iam attach-role-policy \
  --role-name thinkvelocity-server2-backup-role \
  --policy-arn arn:aws:iam::ACCOUNT_ID:policy/ThinkVelocityBackupPolicy

# Create an instance profile and attach the role
aws iam create-instance-profile \
  --instance-profile-name thinkvelocity-server2-backup-profile

aws iam add-role-to-instance-profile \
  --instance-profile-name thinkvelocity-server2-backup-profile \
  --role-name thinkvelocity-server2-backup-role

# Attach to the EC2 instance (replace INSTANCE_ID)
aws ec2 associate-iam-instance-profile \
  --instance-id INSTANCE_ID \
  --iam-instance-profile Name=thinkvelocity-server2-backup-profile \
  --region ap-south-1
```

---

## Step 5 — Store Secrets in AWS Secrets Manager

Store all three secrets. The backup scripts fetch them automatically at runtime.

```bash
# GPG passphrase — generate a strong random one
GPG_PASSPHRASE=$(openssl rand -base64 48)
echo "Save this somewhere safe: ${GPG_PASSPHRASE}"

aws secretsmanager create-secret \
  --name "thinkvelocity/production/backup-gpg-passphrase" \
  --description "GPG symmetric passphrase for PostgreSQL backup encryption" \
  --secret-string "${GPG_PASSPHRASE}" \
  --region ap-south-1

# PostgreSQL backup_user password (must match what's in pg_hba / backup_user role)
aws secretsmanager create-secret \
  --name "thinkvelocity/production/pg-backup-password" \
  --description "PGPASSWORD for backup_user PostgreSQL role" \
  --secret-string "YOUR_BACKUP_USER_PG_PASSWORD" \
  --region ap-south-1

# Slack webhook URL
aws secretsmanager create-secret \
  --name "thinkvelocity/production/slack-webhook" \
  --description "Slack incoming webhook for backup notifications" \
  --secret-string "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK" \
  --region ap-south-1
```

To rotate or update a secret later:

```bash
aws secretsmanager put-secret-value \
  --secret-id "thinkvelocity/production/backup-gpg-passphrase" \
  --secret-string "NEW_PASSPHRASE" \
  --region ap-south-1
```

---

## Step 6 — Deploy Scripts to Server 2

From your local machine:

```bash
# Copy scripts to server
scp configs/backup/pg-backup.sh \
    configs/backup/pg-restore-test.sh \
    configs/backup/setup-backup.sh \
    ec2-user@13.203.181.76:/tmp/

# SSH into the server
ssh ec2-user@13.203.181.76

# Run setup as root
sudo bash /tmp/setup-backup.sh
```

The setup script will:
- Install awscli v2 and gnupg2 if missing
- Copy scripts to `/opt/backup/` with mode 700
- Create log files at `/var/log/pg-backup.log` and `/var/log/pg-restore-test.log`
- Add crontab entries for `backup_user`

---

## Step 7 — Verify Installation

```bash
# On Server 2 — dry run (no actual S3 upload, confirms pg_dump works)
sudo -u backup_user /opt/backup/pg-backup.sh --dry-run

# Full live run (uploads to S3, sends Slack notification)
sudo -u backup_user /opt/backup/pg-backup.sh

# Check log output
tail -80 /var/log/pg-backup.log

# Verify objects in S3
aws s3 ls s3://thinkvelocity-backups/postgres/ --recursive --region ap-south-1
```

---

## How to Manually Trigger Backups

```bash
# Backup (as root, delegating to backup_user)
sudo -u backup_user /opt/backup/pg-backup.sh

# Restore verification test
sudo -u backup_user /opt/backup/pg-restore-test.sh
```

---

## How to Manually Restore to Production (Disaster Recovery)

> This is a destructive operation. Confirm with the team before proceeding.

```bash
# 1. Download the target backup from S3
aws s3 cp \
  s3://thinkvelocity-backups/postgres/YYYY/MM/daily_YYYYMMDD.sql.gz.gpg \
  /tmp/restore.sql.gz.gpg \
  --region ap-south-1

# 2. Decrypt (requires GPG passphrase from AWS SM)
GPG_PASS=$(aws secretsmanager get-secret-value \
  --secret-id "thinkvelocity/production/backup-gpg-passphrase" \
  --region ap-south-1 \
  --query SecretString --output text)

gpg --batch --yes \
    --passphrase "${GPG_PASS}" \
    --decrypt \
    --output /tmp/restore.sql.gz \
    /tmp/restore.sql.gz.gpg

# 3. Decompress
gunzip /tmp/restore.sql.gz

# 4. Stop application traffic (take the app offline)

# 5. Restore (as postgres superuser — drops and recreates schemas)
sudo -u postgres psql -d thinkvelocity_prod -f /tmp/restore.sql

# 6. Verify row counts and bring the app back online

# 7. Clean up
rm -f /tmp/restore.sql.gz.gpg /tmp/restore.sql
```

---

## Crontab Entries (Reference)

These are installed automatically by `setup-backup.sh` for `backup_user`:

```
# Daily backup at 02:00 IST (UTC+5:30)
0 2 * * * /opt/backup/pg-backup.sh >> /var/log/pg-backup.log 2>&1

# Monthly restore verification at 03:00 IST on the 1st of each month
0 3 1 * * /opt/backup/pg-restore-test.sh >> /var/log/pg-restore-test.log 2>&1
```

---

## S3 Object Path Structure

```
s3://thinkvelocity-backups/
  postgres/
    YYYY/
      MM/
        daily_YYYYMMDD.sql.gz.gpg       ← uploaded every day
        monthly_YYYYMM.sql.gz.gpg       ← uploaded on 1st of month only
```

---

## Log Locations

| Log | Path |
|-----|------|
| Daily backup | `/var/log/pg-backup.log` |
| Restore verification | `/var/log/pg-restore-test.log` |
| Local staging (temp) | `/var/backups/postgresql/` |

---

## Troubleshooting

**Backup fails with "database not found"**
The script tries `thinkvelocity_prod` first, then `localpgvelocity`. If both fail, the PostgreSQL user `backup_user` may not have `pg_read_all_data` or the DB may be named differently. Check: `sudo -u backup_user psql -h 127.0.0.1 -U backup_user -l`

**GPG encryption fails**
Verify the secret exists in SM: `aws secretsmanager get-secret-value --secret-id thinkvelocity/production/backup-gpg-passphrase --region ap-south-1`

**S3 upload fails**
Check IAM role is attached to the instance: `curl -s http://169.254.169.254/latest/meta-data/iam/security-credentials/`

**No Slack notification received**
Check the webhook secret in SM. The backup script logs "Slack notification failed (non-fatal)" if the webhook call fails — this will appear in `/var/log/pg-backup.log`.
