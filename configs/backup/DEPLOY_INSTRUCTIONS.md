# PostgreSQL Backup — Deploy Instructions

**Target server:** Server 2 — `ec2-user@13.203.181.76`
**Script install path:** `/opt/backup/pg-backup.sh`
**S3 bucket:** `thinkvelocity-backups` (ap-south-1)

---

## Step 1 — Create the S3 bucket

Run from your local machine (requires AWS CLI configured with admin permissions):

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

# Block all public access
aws s3api put-public-access-block \
  --bucket thinkvelocity-backups \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,\
BlockPublicPolicy=true,RestrictPublicBuckets=true

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

# Add lifecycle rule: transition to Glacier after 30 days, expire after 365 days
aws s3api put-bucket-lifecycle-configuration \
  --bucket thinkvelocity-backups \
  --lifecycle-configuration '{
    "Rules": [{
      "ID": "postgres-backup-lifecycle",
      "Filter": {"Prefix": "postgres/"},
      "Status": "Enabled",
      "Transitions": [{"Days": 30, "StorageClass": "GLACIER"}],
      "Expiration": {"Days": 365}
    }]
  }'
```

---

## Step 2 — Attach an IAM role to Server 2 (recommended) OR create an IAM user

### Option A: IAM Role (recommended — no long-lived credentials)

1. Go to **AWS IAM → Roles → Create role**
2. Select **AWS service → EC2**
3. Attach a custom policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:PutObjectAcl",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::thinkvelocity-backups",
        "arn:aws:s3:::thinkvelocity-backups/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "kms:GenerateDataKey",
        "kms:Decrypt"
      ],
      "Resource": "*"
    }
  ]
}
```

4. Name the role: `thinkvelocity-server2-backup-role`
5. Attach the role to the Server 2 Lightsail/EC2 instance

### Option B: IAM user (simpler, but requires managing credentials)

```bash
# Create IAM user
aws iam create-user --user-name thinkvelocity-backup-bot

# Attach the same policy above
aws iam put-user-policy \
  --user-name thinkvelocity-backup-bot \
  --policy-name S3BackupPolicy \
  --policy-document file://backup-iam-policy.json

# Generate access keys
aws iam create-access-key --user-name thinkvelocity-backup-bot
```

Then on Server 2:
```bash
aws configure  # Enter the access key + secret
```

---

## Step 3 — Configure pg_dump password

The backup script uses `backup_user` to connect. Store the password in `.pgpass`
on Server 2 (never hardcode in the script):

```bash
# As the postgres OS user:
sudo -u postgres bash -c "echo '127.0.0.1:5432:*:backup_user:YOUR_PASSWORD' >> ~/.pgpass"
sudo -u postgres chmod 600 ~/.pgpass
```

---

## Step 4 — Install the backup script on Server 2

```bash
# Copy from local machine:
scp configs/backup/pg-backup.sh ec2-user@13.203.181.76:/tmp/pg-backup.sh

# On Server 2:
sudo mkdir -p /opt/backup
sudo cp /tmp/pg-backup.sh /opt/backup/pg-backup.sh
sudo chmod +x /opt/backup/pg-backup.sh
sudo chown postgres:postgres /opt/backup/pg-backup.sh
```

---

## Step 5 — (Optional) Configure Slack notifications

```bash
# On Server 2, create an env file for the backup script:
sudo bash -c 'cat > /etc/pg-backup.env << EOF
BACKUP_NOTIFY_SLACK=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
EOF'
sudo chmod 600 /etc/pg-backup.env
```

Then add to the top of the crontab line:
```
0 2 * * * env $(cat /etc/pg-backup.env | xargs) /opt/backup/pg-backup.sh >> /var/log/pg-backup.log 2>&1
```

---

## Step 6 — Add the crontab entry

```bash
# As root on Server 2 (runs as postgres's pg_dump permissions via sudo or postgres user):
sudo crontab -e

# Add this line (runs daily at 2:00 AM UTC):
0 2 * * * sudo -u postgres /opt/backup/pg-backup.sh >> /var/log/pg-backup.log 2>&1
```

Or add as the postgres user's crontab:
```bash
sudo -u postgres crontab -e
# Add:
0 2 * * * /opt/backup/pg-backup.sh >> /var/log/pg-backup.log 2>&1
```

---

## Step 7 — Test the backup

```bash
# Dry run (no S3 upload, just verifies pg_dump works):
sudo -u postgres /opt/backup/pg-backup.sh --dry-run

# Full test run (actually uploads to S3):
sudo -u postgres /opt/backup/pg-backup.sh

# Check the log:
tail -50 /var/log/pg-backup.log

# Verify files in S3:
aws s3 ls s3://thinkvelocity-backups/postgres/ --recursive
```

---

## How to Test Restore

```bash
# Download the latest backup for thinkvelocity_prod:
aws s3 cp \
  s3://thinkvelocity-backups/postgres/thinkvelocity_prod/thinkvelocity_prod_LATEST.sql.gz \
  /tmp/restore-test.sql.gz

# Create a test database:
sudo -u postgres createdb thinkvelocity_restore_test

# Restore into the test database:
gunzip -c /tmp/restore-test.sql.gz | sudo -u postgres psql thinkvelocity_restore_test

# Verify row counts match production (spot check):
sudo -u postgres psql -c "SELECT COUNT(*) FROM users;" thinkvelocity_restore_test
sudo -u postgres psql -c "SELECT COUNT(*) FROM users;" thinkvelocity_prod

# Clean up test database:
sudo -u postgres dropdb thinkvelocity_restore_test
rm /tmp/restore-test.sql.gz
```

---

## Log Location

- Backup logs: `/var/log/pg-backup.log`
- Local backup staging: `/var/backups/postgresql/`
- Local backups are retained for 3 days, then automatically deleted by the script
