# Account API (local dev)

Flask mirror of the production Worker for local development.

Production deployment: [`../worker/`](../worker/) (Cloudflare Worker at `api.frogswork.com`).

## Local development

```powershell
cd account_api/dev
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .dev.vars.example .dev.vars
# Edit .dev.vars with your Stripe test keys and price IDs
python server.py
```

Or from repo root: `.\scripts\start-dev.ps1` (starts API + desktop app).

API listens on `http://127.0.0.1:8787`.

Route reference: [`../ROUTES.md`](../ROUTES.md).

## Stripe CLI (webhooks)

```powershell
stripe listen --forward-to http://127.0.0.1:8787/webhooks/stripe
```

Copy the printed `whsec_…` into `.dev.vars` as `STRIPE_WEBHOOK_SECRET`.

## Payment link redirects (dev)

```powershell
.\scripts\configure-payment-links.ps1
```

## Test checkout

Use card `4242 4242 4242 4242`, any future expiry, any CVC.
