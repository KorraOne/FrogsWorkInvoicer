# Deploy files (Raspberry Pi)

**Start here:** [PI-SETUP.md](PI-SETUP.md) · [DEPLOY.md](../../docs/commercial/DEPLOY.md)

| File | Purpose |
|------|---------|
| `pi-bootstrap.sh` | First-time setup: user, clone, venv, env, systemd, backup cron |
| `PI-SETUP.md` | Step-by-step Pi guide |
| `production.env.example` | Template → `/etc/frogswork/billing.env` |
| `frogswork-billing.service` | Billing API on `127.0.0.1:8008` |
| `cloudflared-frogswork.service` | Tunnel `frogswork-api` → `api.frogswork.com` (separate from `pi` tunnel) |
| `cloudflared-config.yml.example` | Ingress → `http://127.0.0.1:8008` |
| `frogswork-auto-billing.service` + `.timer` | Daily platform invoice job |
| `backup.sh` | Nightly `billing.db` + PDF backup |

Paths assume clone at `/home/frogswork/frogswork/` and Linux user `frogswork`.
