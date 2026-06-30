# Account API (Cloudflare Worker)

Production API for **api.frogswork.com**: auth, Stripe entitlements, webhooks, and client release metadata.

Local development: [`../dev/server.py`](../dev/server.py) (Flask on port 8787).

**Route contract:** [`../ROUTES.md`](../ROUTES.md)

## Setup

```bash
cd account_api/worker
npm install
npx wrangler d1 create frogswork-account
# Paste database_id into wrangler.toml
npx wrangler d1 execute frogswork-account --remote --file=../schema.sql
```

## Secrets (production)

```bash
npx wrangler secret put STRIPE_SECRET_KEY
npx wrangler secret put STRIPE_WEBHOOK_SECRET
npx wrangler secret put JWT_SECRET
```

Optional release vars (or `[vars]` in wrangler.toml):

- `CLIENT_RELEASE_VERSION`
- `CLIENT_RELEASE_URL` — zip URL for in-app updates (`download_url` in API response)
- `CLIENT_RELEASE_SHA256`
- `CLIENT_RELEASE_NOTES`

## Deploy

```bash
npm run deploy
```

## Stripe Dashboard

1. **Products / Prices** — monthly `$12.99`, annual `$129.90` (price IDs on Payment Links).
2. **Payment Links** — desktop app opens these URLs; **After payment** redirect: `http://127.0.0.1:5000/account/stripe/return?session_id={CHECKOUT_SESSION_ID}`.
3. **Customer portal** — enable in Stripe; entitlements endpoint returns `portal_url`.
4. **Webhooks** — endpoint `https://api.frogswork.com/webhooks/stripe`; events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted` (ack only today).

## Routes

See [`../ROUTES.md`](../ROUTES.md) for full request/response shapes.
