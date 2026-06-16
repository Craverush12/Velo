# WireGuard Deployment Instructions — ThinkVelocity Mesh Network

## Network Map

| Server | Public IP | WireGuard IP | OS | Role |
|--------|-----------|--------------|-----|------|
| Server 2 (velocity-prod-large) | 13.203.181.76 | 10.100.0.1 | AlmaLinux | HUB — PostgreSQL + Redis |
| Server 1 (python-velocity-v1) | 13.234.212.59 | 10.100.0.2 | Ubuntu | Spoke |
| Server 3 (enterprise) | 13.233.86.137 | 10.100.0.3 | Ubuntu | Spoke |

## Prerequisites

- T-007 must be done first: Server 3 needs a static Elastic IP before WireGuard is configured.
- You need local WireGuard tools installed to run the key generation script.
  - macOS: `brew install wireguard-tools`
  - Ubuntu/Debian: `sudo apt install -y wireguard-tools`
  - Windows: Install WireGuard from https://www.wireguard.com/install/

---

## Step 1 — Generate Keys (Run Once Locally)

```bash
cd configs/wireguard/
chmod +x 00_generate_keys.sh
./00_generate_keys.sh
```

This creates 6 files: `server1_private`, `server1_public`, `server2_private`, `server2_public`, `server3_private`, `server3_public`.

**IMPORTANT:** Do not commit the `*_private` files to git. Add them to `.gitignore`.

---

## Step 2 — Fill In Key Placeholders

Open each config file and replace the placeholder strings with actual key values.

### server1_wg0.conf
- `REPLACE_WITH_SERVER1_PRIVATE_KEY` → paste contents of `server1_private`
- `REPLACE_WITH_SERVER2_PUBLIC_KEY` → paste contents of `server2_public`

### server2_wg0.conf
- `REPLACE_WITH_SERVER2_PRIVATE_KEY` → paste contents of `server2_private`
- `REPLACE_WITH_SERVER1_PUBLIC_KEY` → paste contents of `server1_public`
- `REPLACE_WITH_SERVER3_PUBLIC_KEY` → paste contents of `server3_public`

### server3_wg0.conf
- `REPLACE_WITH_SERVER3_PRIVATE_KEY` → paste contents of `server3_private`
- `REPLACE_WITH_SERVER2_PUBLIC_KEY` → paste contents of `server2_public`

---

## Step 3 — Open Port 51820/UDP on Server 2 (AWS Lightsail Console)

1. Go to AWS Lightsail Console → **velocity-prod-large** → **Networking** tab
2. Under **IPv4 Firewall**, click **Add rule**
3. Set: Protocol = **UDP**, Port = **51820**, Source = **Any IPv4** (0.0.0.0/0)
4. Save the rule

Only Server 2 needs this inbound rule. Servers 1 and 3 initiate outbound connections to Server 2.

---

## Step 4 — Install WireGuard on Each Server

### Server 2 — AlmaLinux (ec2-user@13.203.181.76)

```bash
sudo dnf install -y wireguard-tools
sudo modprobe wireguard
# Enable at boot:
echo "wireguard" | sudo tee /etc/modules-load.d/wireguard.conf
```

### Server 1 — Ubuntu (ubuntu@13.234.212.59)

```bash
sudo apt update
sudo apt install -y wireguard
```

### Server 3 — Ubuntu (ubuntu@13.233.86.137)

```bash
sudo apt update
sudo apt install -y wireguard
```

---

## Step 5 — Deploy Config Files to Each Server

### Server 2

```bash
scp configs/wireguard/server2_wg0.conf ec2-user@13.203.181.76:/tmp/wg0.conf
ssh ec2-user@13.203.181.76 "sudo cp /tmp/wg0.conf /etc/wireguard/wg0.conf && sudo chmod 600 /etc/wireguard/wg0.conf"
```

### Server 1

```bash
scp configs/wireguard/server1_wg0.conf ubuntu@13.234.212.59:/tmp/wg0.conf
ssh ubuntu@13.234.212.59 "sudo cp /tmp/wg0.conf /etc/wireguard/wg0.conf && sudo chmod 600 /etc/wireguard/wg0.conf"
```

### Server 3

```bash
scp configs/wireguard/server3_wg0.conf ubuntu@13.233.86.137:/tmp/wg0.conf
ssh ubuntu@13.233.86.137 "sudo cp /tmp/wg0.conf /etc/wireguard/wg0.conf && sudo chmod 600 /etc/wireguard/wg0.conf"
```

---

## Step 6 — Set Permissions

Run on each server after copying the config:

```bash
sudo chmod 600 /etc/wireguard/wg0.conf
```

This is already covered in Step 5 above. Double-check with:

```bash
ls -la /etc/wireguard/wg0.conf
# Expected: -rw------- 1 root root ...
```

---

## Step 7 — Enable and Start WireGuard

Start on **Server 2 first** (hub must be listening before spokes connect):

```bash
# Server 2
ssh ec2-user@13.203.181.76 "sudo systemctl enable --now wg-quick@wg0"

# Server 1
ssh ubuntu@13.234.212.59 "sudo systemctl enable --now wg-quick@wg0"

# Server 3
ssh ubuntu@13.233.86.137 "sudo systemctl enable --now wg-quick@wg0"
```

---

## Step 8 — Verify Connectivity

### From Server 1 — should reach hub

```bash
ssh ubuntu@13.234.212.59 "ping -c 3 10.100.0.1"
```

### From Server 3 — should reach hub

```bash
ssh ubuntu@13.233.86.137 "ping -c 3 10.100.0.1"
```

### From Server 2 — should reach both spokes

```bash
ssh ec2-user@13.203.181.76 "ping -c 3 10.100.0.2 && ping -c 3 10.100.0.3"
```

### Check WireGuard status on any server

```bash
sudo wg show
# Should show peer(s) with a recent handshake timestamp
```

---

## Step 9 — After WireGuard is Running: Update Connection Strings

Once the tunnel is verified, update Server 3 to use private IPs instead of public IPs.

### Server 3 NestJS (.env)

```
# Change from:
DATABASE_URL=postgresql://user:pass@13.203.181.76:5432/thinkvelocity_prod
# Change to:
DATABASE_URL=postgresql://user:pass@10.100.0.1:5432/thinkvelocity_prod
```

### Server 3 Prompt Enhance service (.env)

```
# Change from:
REDIS_URL=redis://13.203.181.76:6379
# Change to:
REDIS_URL=redis://10.100.0.1:6379
```

Restart affected containers after updating env files:

```bash
docker compose up -d
```

---

## Step 10 — Lock Down PostgreSQL and Redis on Server 2

After connection strings are updated and verified:

**PostgreSQL** — edit `/var/lib/pgsql/17/data/postgresql.conf`:
```
listen_addresses = '127.0.0.1,10.100.0.1'
```

**Redis** — edit `/etc/redis/redis.conf` (or `/etc/redis.conf`):
```
bind 127.0.0.1 10.100.0.1
```

Restart services:
```bash
sudo systemctl restart postgresql-17
sudo systemctl restart redis
```

Then close the public ports in AWS Lightsail Console (T-001 and T-002).

---

## Troubleshooting

### Handshake never completes
- Confirm port 51820/UDP is open in Lightsail firewall on Server 2
- Run `sudo wg show` on both ends — check "latest handshake" field
- Ensure Server 2's public IP in Endpoint lines matches actual current IP

### wg-quick fails to start
- Check config file permissions: `sudo chmod 600 /etc/wireguard/wg0.conf`
- Verify key values have no extra whitespace or newlines
- Check for syntax errors: `sudo wg-quick up wg0` (run manually for verbose output)

### AlmaLinux — wireguard module not loading
```bash
sudo modprobe wireguard
# If error: kernel-headers may be needed
sudo dnf install -y kernel-devel-$(uname -r) kernel-headers-$(uname -r)
```
