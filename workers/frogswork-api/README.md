# FrogsWork account API (Cloudflare Worker)

Production API for **api.frogswork.com**: auth, Stripe Checkout, subscription entitlements, webhooks, and client release metadata.

For local development, use [`../../frogswork_api/server.py`](../../frogswork_api/server.py) (Flask on port 8787).

## Setup

```bash
cd workers/frogswork-api
npm install
npx wrangler d1 create frogswork-account
# Paste database_id into wrangler.toml
npx wrangler d1 execute frogswork-account --remote --file=./schema.sql
```

## Secrets (production)

```bash
npx wrangler secret put STRIPE_SECRET_KEY
npx wrangler secret put STRIPE_WEBHOOK_SECRET
npx wrangler secret put JWT_SECRET
```

Optional release vars (or `[vars]` in wrangler.toml):

- `CLIENT_RELEASE_VERSION`
- `CLIENT_RELEASE_URL`
- `CLIENT_RELEASE_SHA256`
- `CLIENT_RELEASE_NOTES`

## Deploy

```bash
npm run deploy
```

## Stripe Dashboard

1. **Products / Prices** — monthly `$12.99`, annual `$129.90` (price IDs in `wrangler.toml`).
2. **Checkout** — app creates sessions via `POST /checkout/create`; success URL `https://frogswork.com/subscribe/success.html?session_id={CHECKOUT_SESSION_ID}`.
3. **Customer portal** — enable in Stripe; entitlements endpoint returns `portal_url`.
4. **Webhooks** — endpoint `https://api.frogswork.com/webhooks/stripe`; events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`.
5. **Buy Buttons** (optional on marketing site) — point monthly/annual buttons at the same price IDs; see [`../../docs/commercial/STRIPE_SETUP.md`](../../docs/commercial/STRIPE_SETUP.md).

## Routes

| Method | Path | Auth |
|--------|------|------|
| GET | `/health` | No |
| POST | `/auth/register` | No (requires paid Checkout session) |
| POST | `/auth/login` | No |
| POST | `/auth/refresh` | No |
| GET | `/entitlements` | Bearer access token |
| POST | `/checkout/create` | No |
| GET | `/releases/latest` | No |
| POST | `/webhooks/stripe` | Stripe signature |
