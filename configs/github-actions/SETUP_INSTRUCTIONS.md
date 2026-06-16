# GitHub Actions Setup Instructions

## Required GitHub Secrets

Go to: **Settings → Secrets and variables → Actions → New repository secret**

| Secret Name        | Value                                              |
|--------------------|----------------------------------------------------|
| `DOCKER_USERNAME`  | `thinkvelocity24`                                  |
| `DOCKER_PASSWORD`  | Docker Hub access token (not your login password) |
| `SERVER1_SSH_KEY`  | Full contents of `velo-python.pem`                |
| `SERVER2_SSH_KEY`  | Full contents of `velo-large-main-server-key.pem` |
| `SERVER3_SSH_KEY`  | Full contents of `fr-img-tes-ap-south.pem`        |
| `SLACK_WEBHOOK_URL`| Slack incoming webhook URL                        |

### Creating a Docker Hub Access Token

1. Log in to hub.docker.com as `thinkvelocity24`
2. Account Settings → Security → New Access Token
3. Name: `github-actions-deploy`
4. Permissions: Read & Write
5. Copy the token — it is only shown once

### Copying SSH Key Contents

On Windows, open PowerShell and run:
```powershell
Get-Content "C:\Users\Arjun\Downloads\velo-python.pem" | Set-Clipboard
```
Then paste into the GitHub secret field.

---

## Required GitHub Environments

Go to: **Settings → Environments → New environment**

| Environment Name | Required Reviewers         |
|------------------|----------------------------|
| `production`     | Add Arjun (arjungujar490@gmail.com) |

With a required reviewer set, every push to `main` that reaches the `deploy` job will pause and wait for manual approval in the GitHub Actions UI before SSHing into production.

---

## Workflow File Placement

These workflow files must be placed in `.github/workflows/` in each respective repository:

- `deploy-nodejs-backend.yml` — Node.js backend repo
- `deploy-python-ai.yml` — Python AI / ThinkVelocity FastAPI repo
- `deploy-enterprise-backend.yml` — NestJS enterprise repo

If all services live in a monorepo, all three files go in the same `.github/workflows/` directory. The `paths:` filter in each workflow ensures only the relevant files trigger each pipeline.

---

## Deploy Script Setup (on each server)

The workflows call `/opt/deploy/deploy.sh` on the target server. This script must be present before the workflow runs.

See `configs/deploy/deploy.sh` (T-043, already generated).

```bash
# Run on each server as root or via sudo:
sudo mkdir -p /opt/deploy
sudo cp deploy.sh /opt/deploy/deploy.sh
sudo chmod +x /opt/deploy/deploy.sh
```

### Signature expected by workflows

```bash
/opt/deploy/deploy.sh <service-name> <image:tag> <health-url>
```

Example:
```bash
/opt/deploy/deploy.sh nodejs-backend thinkvelocity24/thinkvelocity-backend:abc1234 http://localhost:3005/health
```

---

## Security Notes

- The `security-scan` job uploads SARIF results to the GitHub Security tab (requires `security-events: write` permission — already set in the workflow).
- Trivy will block the pipeline with `exit-code: 1` on any CRITICAL or HIGH CVE in either the filesystem or the final Docker image.
- `npm audit --audit-level=high` and `pip-audit` block the pipeline before the image is even built.
- The `production` environment gate means no code reaches production without a human approving it in GitHub.
