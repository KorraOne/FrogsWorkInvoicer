# Account API — HTTP contract

Canonical route list for [`dev/server.py`](dev/server.py) (Flask) and [`worker/src/index.js`](worker/src/index.js) (Cloudflare Worker). **Keep both implementations in sync** when changing behaviour.

Base URL: `http://127.0.0.1:8787` (dev) · `https://api.frogswork.com` (prod).

## Subscribe flow (desktop app)

The app does **not** call the API to start checkout. It opens **Stripe Payment Links** configured in `account_api/dev/.dev.vars` (`STRIPE_PAYMENT_LINK_MONTHLY`, `STRIPE_PAYMENT_LINK_ANNUAL`) and loaded into the desktop app via `start-dev.ps1`.

1. User pays on Stripe Payment Link.
2. Stripe redirects to the app (`http://127.0.0.1:5000/account/stripe/return?session_id=cs_…` in dev) or marketing site in prod.
3. App calls `GET /checkout/session-info?session_id=cs_…`.
4. New user: `POST /auth/register` with `checkout_session_id` + password.
5. Existing user (signed in): `POST /auth/attach-checkout` with `checkout_session_id`.
6. App calls `GET /entitlements` (live Stripe subscription query).

Configure Payment Link redirects for local dev: `.\scripts\configure-payment-links.ps1`

## Routes

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | No | `{ ok, stripe }` connectivity check |
| GET | `/checkout/session-info` | No | Query `session_id=cs_…` → `{ email, paid, subscription_active, account_exists }` |
| POST | `/auth/register` | No | Body: `{ password, checkout_session_id }` → tokens + `email` |
| POST | `/auth/attach-checkout` | Bearer | Body: `{ checkout_session_id }` → `{ ok: true }` |
| POST | `/auth/login` | No | Body: `{ email, password }` → `{ access_token, refresh_token }` |
| POST | `/auth/refresh` | No | Body: `{ refresh_token }` → new tokens |
| GET | `/entitlements` | Bearer | Subscription status from Stripe + `portal_url` |
| GET | `/releases/latest` | No | In-app update metadata (see below) |
| POST | `/webhooks/stripe` | Stripe signature | Ack only — entitlements are live-queried from Stripe |

### Auth

- Access token: `Authorization: Bearer <access_token>` (12 h).
- Refresh token: 30 d, body field `refresh_token`.
- Passwords: bcrypt only (`$2…` hashes).

### `GET /entitlements` response

```json
{
  "active": true,
  "status": "active",
  "canceling": false,
  "access_until": "2026-07-01T00:00:00+00:00",
  "current_period_end": "2026-07-01T00:00:00+00:00",
  "plan_interval": "month",
  "portal_url": "https://billing.stripe.com/..."
}
```

`status` may be `none`, `active`, `trialing`, `canceled`, or `inactive`.

### `GET /releases/latest`

- **204** when no release is configured.
- **200** when configured:

```json
{
  "version": "1.2.0",
  "download_url": "https://downloads.frogswork.com/FrogsWork-1.2.0-win64.zip",
  "sha256": "…",
  "notes": "Release note."
}
```

Worker: set `CLIENT_RELEASE_VERSION`, `CLIENT_RELEASE_URL`, `CLIENT_RELEASE_SHA256`, `CLIENT_RELEASE_NOTES` in wrangler vars/secrets.

Dev: optional same env vars in `.dev.vars`; otherwise returns 204.

### Webhooks

`POST /webhooks/stripe` verifies the Stripe signature and returns `{ received: true }`. Subscription state is **not** cached in the database — `GET /entitlements` queries Stripe on each request. Webhooks are registered for future use and Stripe Dashboard compliance.

Recommended events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`.

## Database

Single table `users`: `id`, `email`, `password_hash`, `stripe_customer_id`, `created_at`. See [`schema.sql`](schema.sql).
