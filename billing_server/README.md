# Billing server

Flask API for FrogsWork accounts, usage, and operator admin.

| Environment | URL |
|-------------|-----|
| **Production API** | `https://api.frogswork.com` |
| **Production admin** | SSH tunnel → `http://127.0.0.1:8008/admin` (not public) |
| **Local dev** | `http://127.0.0.1:8080` |

- **Database:** SQLite `billing.db` (runtime, not committed)
- **Client:** [`../client_app/billing_client.py`](../client_app/billing_client.py) (HTTP only)

## Production (Pi)

**Setup:** [PI-SETUP.md](deploy/PI-SETUP.md) · [DEPLOY.md](../docs/commercial/DEPLOY.md)

**Deploy files:** [deploy/](deploy/)

## Local dev

Copy `.env.example` to `.env`. From `billing_server/`:

```powershell
pip install -r requirements.txt
python app.py
```

Admin: http://127.0.0.1:8080/admin

Or from repo root: `.\scripts\dev-test.ps1 -Action StartServer`

## Operator admin (production)

SSH as **`pi`**, forward port **8008**:

```powershell
ssh -L 8008:127.0.0.1:8008 pi@<pi-ip>
```

http://127.0.0.1:8008/admin

See [operator-admin.md](../docs/commercial/operator-admin.md).

## Platform fee invoices

```bash
python run_billing_job.py --quarter 1 --year 2026
```

Automatic daily job: `frogswork-auto-billing.timer` (see deploy/).
