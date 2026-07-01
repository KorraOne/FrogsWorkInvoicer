# Account API — HTTP contract

Canonical route list for [`dev/server.py`](dev/server.py) (Flask) and [`worker/src/index.js`](worker/src/index.js) (Cloudflare Worker). **Keep both implementations in sync** when changing behaviour.

Base URL: `http://127.0.0.1:8787` (dev) · `https://api.frogswork.com` (prod).

## Subscribe flow (desktop app)

The app does **not** call the API to start checkout. It opens **Stripe Payment Links** configured in `account_api/dev/.dev.vars` (`STRIPE_PAYMENT_LINK_MONTHLY`, `STRIPE_PAYMENT_LINK_ANNUAL`) and loaded into the desktop app via `start-dev.ps1`.

1. User pays on Stripe Payment Link.
2. Stripe redirects to the app (`http://127.0.0.1:5000/account/stripe/return?session_id=cs_…` in dev) or marketing site in prod.
3. App calls `GET /checkout/session-info?session_id=cs_…`.
4. New user: `POST /auth/register` with `checkout_session_id` + password (+ optional `install_id`, `signup_snapshot`).
5. Existing user (signed in): `POST /auth/attach-checkout` with `checkout_session_id`.
6. App calls `GET /entitlements` (live Stripe subscription query; updates subscription milestones on linked install).

Configure Payment Link redirects for local dev: `.\scripts\configure-payment-links.ps1`

## Routes

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | No | `{ ok, stripe }` connectivity check |
| GET | `/checkout/session-info` | No | Query `session_id=cs_…` → `{ email, paid, subscription_active, account_exists }` |
| POST | `/auth/register` | No | Body: `{ password, checkout_session_id, install_id?, signup_snapshot? }` → tokens + `email` |
| POST | `/auth/attach-checkout` | Bearer | Body: `{ checkout_session_id }` → `{ ok: true }` |
| POST | `/auth/login` | No | Body: `{ email, password }` → `{ access_token, refresh_token }` |
| POST | `/auth/refresh` | No | Body: `{ refresh_token }` → new tokens |
| GET | `/entitlements` | Bearer | Subscription status from Stripe + `portal_url`; updates install subscription milestones |
| POST | `/telemetry/heartbeat` | No | Anonymous install heartbeat + usage aggregates |
| POST | `/telemetry/event` | No | Idempotent funnel events (`first_invoice`, `uninstall`, …) |
| GET | `/admin` | HTTP Basic (`ADMIN_PASSWORD`) | HTML analytics dashboard |
| GET | `/admin/api/summary` | HTTP Basic | JSON funnel / churn / signup metrics |
| GET | `/releases/latest` | No | In-app update metadata (see below) |
| POST | `/webhooks/stripe` | Stripe signature | Ack only — entitlements are live-queried from Stripe |

### Auth

- Access token: `Authorization: Bearer <access_token>` (12 h).
- Refresh token: 30 d, body field `refresh_token`.
- Passwords: bcrypt only (`$2…` hashes).
- Admin: HTTP Basic — any username, password = `ADMIN_PASSWORD` secret.

### `POST /telemetry/heartbeat`

```json
{
  "install_id": "64-char hex SHA-256 of install secret",
  "app_version": "1.1.0",
  "schema_version": 1,
  "is_packaged": true,
  "usage_snapshot": {
    "gst_registered": true,
    "welcome_complete": true,
    "lifetime_invoice_count": 8,
    "lifetime_ex_gst": "4200.00",
    "customer_count": 3,
    "business_count": 1,
    "invoices_sent": 5,
    "invoices_paid": 2
  }
}
```

Returns `{ ok: true, created: true|false }`. Aggregates only — no customer names, line items, or PDFs.

### `POST /telemetry/event`

```json
{ "install_id": "…", "event": "first_invoice", "app_version": "1.1.0" }
```

Events (idempotent): `first_invoice`, `first_customer`, `first_invoice_sent`, `first_paid_marked`, `backup_export`, `backup_import`, `in_app_update`, `uninstall`.

### `POST /auth/register` optional fields

```json
{
  "install_id": "…",
  "signup_snapshot": {
    "lifetime_invoice_count": 12,
    "lifetime_ex_gst_total": "8500.00",
    "gst_registered": true,
    "trial_gate_hit": "invoices"
  }
}
```

Links install → user; stores signup snapshot on `installs` row.

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

Server updates linked `installs` row: `subscribed_at`, `cancel_scheduled_at`, `unsubscribed_at`, `resubscribed_at`, `subscription_state`.

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

Tables: `users` (`id`, `email`, `password_hash`, `stripe_customer_id`, `install_id`, `created_at`); `installs` (pseudonymous telemetry + funnel milestones). See [`schema.sql`](schema.sql).
