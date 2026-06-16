# PostgreSQL Hardening — Deploy Instructions

**Target server:** Server 2 — `ec2-user@13.203.181.76`
**PostgreSQL version:** 17
**Data directory:** `/var/lib/pgsql/17/data/`
**Service name:** `postgresql-17`

> Complete these steps in order. Do not skip steps or reorder them.
> Prerequisite: WireGuard VPN must be active (T-009 to T-012) before Step 6 —
> otherwise app services on Server 1 and Server 3 will lose database access.

---

## Step 1 — Generate strong passwords for each DB user

Run this command **five times** (once per user) and record each output securely
in your password manager or AWS Secrets Manager (T-018):

```bash
openssl rand -base64 32
```

Users requiring passwords:
- `app_consumer`
- `app_enterprise`
- `app_extension`
- `app_readonly`
- `backup_user`

---

## Step 2 — Replace password placeholders in the SQL script

Edit `03_create_db_users.sql` and replace every instance of:

```
REPLACE_WITH_STRONG_32CHAR_PASSWORD
```

with the corresponding password generated in Step 1.

There are **5 placeholders** — one per user. Verify with:

```bash
grep -c 'REPLACE_WITH_STRONG_32CHAR_PASSWORD' 03_create_db_users.sql
# Expected output: 0 (after replacement)
```

---

## Step 3 — Copy scripts to Server 2

```bash
# From your local machine:
scp configs/postgresql/*.sh configs/postgresql/*.sql configs/postgresql/pg_hba.conf \
    ec2-user@13.203.181.76:/tmp/pg-hardening/
```

On Server 2:
```bash
chmod +x /tmp/pg-hardening/01_enable_ssl.sh
chmod +x /tmp/pg-hardening/02_postgresql_conf_changes.sh
```

---

## Step 4 — Apply SSL certificate generation

```bash
ssh ec2-user@13.203.181.76
sudo bash /tmp/pg-hardening/01_enable_ssl.sh
```

Expected output ends with:
```
SSL cert generated. Now apply pg_hba.conf changes before restarting PostgreSQL.
```

Do NOT restart PostgreSQL yet.

---

## Step 5 — Apply postgresql.conf changes

```bash
sudo bash /tmp/pg-hardening/02_postgresql_conf_changes.sh
```

This will:
- Backup the original: `postgresql.conf.bak.YYYYMMDD`
- Set `listen_addresses = '127.0.0.1,10.100.0.1'`
- Enable SSL
- Add connection and audit logging
- Set `max_connections = 200` and `shared_buffers = 512MB`

Review the diff output before proceeding.

---

## Step 6 — Replace pg_hba.conf

> **WARNING:** This step restricts who can connect to PostgreSQL.
> Ensure WireGuard is active (T-010 to T-012) before applying,
> or app services on other servers will be locked out.

```bash
sudo cp /tmp/pg-hardening/pg_hba.conf /var/lib/pgsql/17/data/pg_hba.conf
sudo chown postgres:postgres /var/lib/pgsql/17/data/pg_hba.conf
sudo chmod 600 /var/lib/pgsql/17/data/pg_hba.conf
```

Verify the file looks correct:
```bash
sudo cat /var/lib/pgsql/17/data/pg_hba.conf
```

---

## Step 7 — Restart PostgreSQL

```bash
sudo systemctl restart postgresql-17
```

Verify it started cleanly:
```bash
sudo systemctl status postgresql-17
# Should show: Active: active (running)

# Check for errors:
sudo journalctl -u postgresql-17 --since "5 minutes ago"
```

---

## Step 8 — Create per-service database users

```bash
sudo -u postgres psql -f /tmp/pg-hardening/03_create_db_users.sql
```

Review the verification output at the end of the script. All 5 users should
appear and all database CONNECT privileges should show `t` (true).

---

## Step 9 — Verify connectivity from each server

### From Server 2 (local):
```bash
psql -h 127.0.0.1 -U app_consumer -d thinkvelocity_prod -c "SELECT current_user, current_database();"
psql -h 127.0.0.1 -U app_enterprise -d enterprise -c "SELECT current_user, current_database();"
psql -h 127.0.0.1 -U app_extension -d thinkvelocity_ext -c "SELECT current_user, current_database();"
```

### From Server 1 (via WireGuard):
```bash
psql "host=10.100.0.1 user=app_extension dbname=thinkvelocity_ext sslmode=require" \
  -c "SELECT current_user, current_database();"
```

### From Server 3 (via WireGuard):
```bash
psql "host=10.100.0.1 user=app_enterprise dbname=enterprise sslmode=require" \
  -c "SELECT current_user, current_database();"
psql "host=10.100.0.1 user=app_consumer dbname=thinkvelocity_prod sslmode=require" \
  -c "SELECT current_user, current_database();"
```

---

## Step 10 — Update app .env files to use new credentials (T-017)

After verifying connectivity, update each service's environment file:

| Server | Service | DB User | Database |
|--------|---------|---------|----------|
| Server 2 | Node.js backend | `app_consumer` | `thinkvelocity_prod` |
| Server 2 | Python AI | `app_consumer` | `thinkvelocity_prod` |
| Server 3 | NestJS enterprise | `app_enterprise` | `enterprise` |
| Server 3 | Prompt Enhance | `app_consumer` | `thinkvelocity_prod` |
| Server 1 | FastAPI extension | `app_extension` | `thinkvelocity_ext` |

Restart each service after updating its `.env`.

---

## Rollback Procedure

If anything goes wrong and PostgreSQL is inaccessible:

```bash
# Restore original postgresql.conf:
sudo cp /var/lib/pgsql/17/data/postgresql.conf.bak.$(date +%Y%m%d) \
        /var/lib/pgsql/17/data/postgresql.conf

# Restore a known-working pg_hba.conf (keep a backup before applying):
sudo cp /var/lib/pgsql/17/data/pg_hba.conf.ORIGINAL \
        /var/lib/pgsql/17/data/pg_hba.conf

sudo systemctl restart postgresql-17
```

> **Tip:** Before Step 6, back up the existing pg_hba.conf:
> ```bash
> sudo cp /var/lib/pgsql/17/data/pg_hba.conf \
>         /var/lib/pgsql/17/data/pg_hba.conf.ORIGINAL
> ```
