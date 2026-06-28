# Pi deploy files

Systemd units, Cloudflare Tunnel example, production env template, and backup script for the billing server.

**Follow the numbered checklist in [`docs/commercial/DEPLOY.md`](../../docs/commercial/DEPLOY.md)** — that is the canonical deploy order.

| File | Purpose |
|------|---------|
| `production.env.example` | Copy to `/etc/frogswork/billing.env` on the Pi |
| `frogswork-billing.service` | systemd unit for `python app.py` |
| `frogswork-auto-billing.service` + `.timer` | Daily platform invoice job |
| `cloudflared-config.yml.example` | `api.frogswork.com` → `127.0.0.1:8080` |
| `backup.sh` | Cron backup for `billing.db` + PDFs |

Paths assume repo clone at `/home/frogswork/frogswork/` and Linux user `frogswork`. Adjust before installing.
