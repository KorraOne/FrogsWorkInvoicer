# FrogsWork account API

Production deployment uses the Cloudflare Worker in [`../workers/frogswork-api/`](../workers/frogswork-api/). This Flask app mirrors the same routes for local development.

## Local development

```powershell
cd frogswork_api
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .dev.vars.example .dev.vars
# Edit .dev.vars with your Stripe test keys and price IDs
python server.py
```

API listens on `http://127.0.0.1:8787`.

Point the desktop app at it:

```powershell
$env:FROGSWORK_ACCOUNT_API_URL = "http://127.0.0.1:8787"
```

## Stripe CLI (webhooks)

```powershell
stripe listen --forward-to http://127.0.0.1:8787/webhooks/stripe
```

Copy the printed `whsec_…` into `.dev.vars` as `STRIPE_WEBHOOK_SECRET`.

## Test checkout

Use card `4242 4242 4242 4242`, any future expiry, any CVC.
