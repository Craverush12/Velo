# Fail2ban Deployment Instructions — Server 2

## Target Server

Server 2 — velocity-prod-large (ec2-user@13.203.181.76, AlmaLinux)

## Prerequisites

Fail2ban must be installed. If not already present:

```bash
sudo dnf install -y fail2ban
sudo systemctl enable fail2ban
```

---

## Step 1 — Copy jail.local to Server 2

From your local machine:

```bash
scp configs/fail2ban/jail.local ec2-user@13.203.181.76:/tmp/jail.local
ssh ec2-user@13.203.181.76 "sudo cp /tmp/jail.local /etc/fail2ban/jail.local"
```

Or copy the contents manually via SSH:

```bash
ssh ec2-user@13.203.181.76
sudo nano /etc/fail2ban/jail.local
# Paste the contents of jail.local, save and exit
```

---

## Step 2 — Restart Fail2ban

```bash
ssh ec2-user@13.203.181.76 "sudo systemctl restart fail2ban"
```

---

## Step 3 — Verify Active Jails

```bash
ssh ec2-user@13.203.181.76 "sudo fail2ban-client status"
```

Expected output should list these active jails:
- sshd
- apache-auth
- apache-badbots
- apache-noscript
- apache-overflows

---

## Step 4 — Verify SSH Jail Specifically

```bash
ssh ec2-user@13.203.181.76 "sudo fail2ban-client status sshd"
```

Expected output includes:
- `Status for the jail: sshd`
- `Currently banned: 0` (or more if bans are in effect)
- `Total banned: <number>`
- `Banned IP list: ...`

---

## Useful Commands

### Check fail2ban service status
```bash
sudo systemctl status fail2ban
```

### View fail2ban logs
```bash
sudo journalctl -u fail2ban -f
# or
sudo tail -f /var/log/fail2ban.log
```

### Manually unban an IP
```bash
sudo fail2ban-client set sshd unbanip <IP_ADDRESS>
```

### Test that a jail is working (dry run)
```bash
sudo fail2ban-regex /var/log/secure /etc/fail2ban/filter.d/sshd.conf
```

### Reload config without restart
```bash
sudo fail2ban-client reload
```

---

## Notes on AlmaLinux / RHEL

- SSH log path on AlmaLinux is `/var/log/secure` (not `/var/log/auth.log`)
  The `%(sshd_log)s` variable in jail.local resolves correctly via the systemd backend.
- Apache logs are at `/var/log/httpd/error_log` and `/var/log/httpd/access_log`
  The `%(apache_error_log)s` and `%(apache_access_log)s` variables resolve these automatically.
- The `backend = systemd` setting is the correct backend for AlmaLinux systems using journald.
