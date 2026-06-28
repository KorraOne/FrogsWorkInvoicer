# Billing server

Flask API for FrogsWork account registration, JWT auth, usage commits, cap enforcement, and operator admin UI.

- **Production API:** `https://api.frogswork.com`
- **Local dev:** `http://127.0.0.1:8080`
- **Database:** SQLite `billing.db` (runtime, not committed)
- **Admin UI:** `/admin` (password-protected; **not** exposed publicly in production)
- **Client:** [`../client_app/billing_client.py`](../client_app/billing_client.py) (HTTP only)

## Production deploy

**Follow [`../docs/commercial/DEPLOY.md`](../docs/commercial/DEPLOY.md)** — Pi setup, Cloudflare Tunnel, systemd, first release.

Deploy files: [`deploy/`](deploy/)

## Local dev

Copy `.env.example` to `.env` and edit as needed.

```powershell
cd billing_server
pip install -r requirements.txt
python app.py
```

Or from repo root: `.\scripts\dev-test.ps1 -Action StartServer`

Admin: http://127.0.0.1:8080/admin (`ADMIN_PASSWORD` from `.env`, default `dev-admin`).

## Operator admin (production)

Do **not** browse `/admin` on `api.frogswork.com`. From your laptop:

```bash
ssh -L 8080:127.0.0.1:8080 frogswork@<pi-host>
```

Open http://127.0.0.1:8080/admin

See [`../docs/commercial/operator-admin.md`](../docs/commercial/operator-admin.md).

## Platform fee invoices

```bash
python run_billing_job.py --quarter 1 --year 2026
```

Or **Generate** in admin UI. Automatic daily job: `frogswork-auto-billing.timer` (see deploy/).

## Docs

- [DEPLOY.md](../docs/commercial/DEPLOY.md) — production checklist
- [security-risk-model.md](../docs/commercial/security-risk-model.md) — threat model
- [operator-admin.md](../docs/commercial/operator-admin.md) — admin workflows
