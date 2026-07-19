# Account API — HTTP contract

Canonical route list for [`dev/server.py`](dev/server.py) (Flask) and [`worker/src/index.js`](worker/src/index.js) (Cloudflare Worker). **Keep both implementations in sync** when changing behaviour.

Base URL: `http://127.0.0.1:8787` (dev) · `https://api.frogswork.com` (prod).

## Subscribe flow (email-first)

Account creation runs on **frogswork.com** (`marketing_site/account/`). Checkout uses the **Stripe Checkout Sessions API** (`POST /checkout/create-session`) with Cloud monthly/annual price IDs (Local is retired). Sync display prices via `.\scripts\sync-marketing-account-config.ps1`.

1. User creates account at `/account/signup.html` → `POST /auth/signup` → `signup_token` (pending until paid).
2. User chooses monthly or annual Cloud at `/account/subscribe.html` → `POST /checkout/create-session` → Stripe Checkout (`customer_email` prefilled).
3. Stripe redirects to `/account/return.html?session_id=cs_…`.
4. Return page polls `GET /checkout/session-info` until `account_status` is `active`.
5. Webhook `checkout.session.completed` also activates the account (idempotent).
6. Desktop/PWA sign-in: web login with `?next=desktop` or `?next=pwa` → one-time handoff code (`POST /auth/handoff/create` → `app.frogswork.com/?handoff=…` → `POST /auth/handoff/redeem`). Do not put JWTs in the URL.

**Upgrade (logged in):** `/account/subscribe.html?upgrade=1` → sign in → `POST /checkout/create-session` with Bearer token (subscription swap when same interval).

**Legacy payment-first:** `POST /auth/register` after Payment Link checkout (deprecated; kept for in-flight sessions).

**Entitlement:** any Stripe subscription that is `active` or `trialing` unlocks Cloud. The `storage_tier` field is vestigial and always returned as `"cloud"` (Local is no longer a product). App gates check `active` only — do not require price metadata.

Create Stripe prices (metadata `storage_tier: cloud` is optional/legacy):

```powershell
python account_api\dev\setup_stripe_prices.py --grandfather-existing
```

Add printed `STRIPE_PRICE_*` values to `client_app/production.env` and `account_api/worker/wrangler.toml` `[vars]`.

## Routes

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/health` | No | `{ ok, stripe }` connectivity check |
| GET | `/checkout/session-info` | No | Query `session_id=cs_…` → `{ email, paid, subscription_active, storage_tier, account_status }` |
| POST | `/auth/signup` | No | Body: `{ email, password }` → `{ signup_token, email, account_status, resumed? }` |
| POST | `/checkout/create-session` | Bearer signup or access | Body: `{ tier, interval, promotion_code? }` → `{ checkout_url }` or `{ upgraded, storage_tier }` |
| POST | `/auth/register` | No | **Legacy.** Body: `{ password, checkout_session_id, install_id? }` → tokens + `email` |
| POST | `/auth/attach-checkout` | Bearer | Body: `{ checkout_session_id }` → `{ ok: true }` |
| POST | `/auth/login` | No | Body: `{ email, password }` → `{ access_token, refresh_token }` (rate limited) |
| POST | `/auth/handoff/create` | Bearer signup or access | Active/trialing account → `{ code, expires_in }` (single-use, ~60s; opaque code for app handoff) |
| POST | `/auth/handoff/redeem` | No | Body: `{ code }` → `{ access_token, refresh_token }` (rate limited; single-use) |
| GET | `/account/export` | Bearer | ZIP download: `frogswork-export.json` + `pdfs/*.pdf` (rate limited; permanent self-serve copy — not re-importable) |
| POST | `/account/data/delete` | Bearer | Body `{ confirm: "DELETE DATA" }` → purge Cloud docs/PDFs/devices for user; keep login + Stripe |
| POST | `/account/delete` | Bearer | Body `{ confirm: "DELETE ACCOUNT", password }` → cancel Stripe, purge data, delete user |
| POST | `/auth/forgot-password` | No | Body: `{ email }` → generic success (rate limited; sends Resend email if configured) |
| POST | `/auth/reset-password` | No | Body: `{ token, password }` → `{ ok: true }` |
| POST | `/auth/verify-email` | No | Body: `{ token }` → `{ ok: true, verified: true }` |
| POST | `/auth/resend-verification` | Bearer | Resend verification email → `{ ok: true, sent: true }` |
| POST | `/auth/refresh` | No | Body: `{ refresh_token }` → new tokens |
| GET | `/entitlements` | Bearer | Subscription status + `portal_url`, `storage_tier` (always `"cloud"`), `platforms`, `email_verified` |
| POST | `/mobile/v1/session` | No | Body `{ email, password }` → tokens + `account` (PWA v2) |
| GET | `/mobile/v1/account` | Bearer | Slim account: `email`, `active`, `storage_tier` (always `"cloud"`), `portal_url`, `email_verified` |
| GET | `/mobile/v1/bootstrap` | Bearer | Cloud-only snapshot (same as `/documents/bootstrap`) |
| POST | `/mobile/v1/sync` | Bearer | Cloud-only mutation sync |
| GET | `/mobile/v1/invoices/:n/pdf` | Bearer | Cloud-only PDF |
| POST | `/telemetry/heartbeat` | No | Anonymous install heartbeat + usage aggregates |
| POST | `/telemetry/event` | No | Idempotent funnel events (`first_invoice`, `uninstall`, …) |
| GET | `/metrics/summary` | Bearer `METRICS_TOKEN` | Privacy-friendly product aggregates (local dashboard) |
| POST | `/devices/upsert` | Bearer | Register device sighting (`device_id`, `platform`, `coarse_ua`) |
| GET | `/releases/latest` | No | In-app update metadata (see below) |
| POST | `/guest/session` | No (CORS `app.frogswork.com`, localhost:8090) | Guest cloud trial → `{ guest_id, guest_token, expires_at }` |
| POST | `/email/invoices/:n/send` | Bearer access + active subscription | Local-tier relay send — body `{ pdf_b64, customer_email, filename?, subject?, body_text? }`; no D1/R2 persist |
| GET | `/documents/bootstrap` | Bearer access or guest (cloud tier for users) | Full snapshot: businesses, customers, invoices, settings |
| POST | `/documents/migrate` | Bearer access or guest (cloud tier for users) | Import local backup JSON payload (max 5 MB) |
| POST | `/documents/sync` | Bearer access or guest (cloud tier for users) | Body `{ mutations: [...] }` — offline queue replay |
| GET | `/documents/invoices/:n/pdf` | Bearer access or guest | PDF as `{ filename, content_b64 }` |
| POST | `/documents/invoices/:n/generate` | Bearer access or guest | Server PDF generation (pdf-lib) → R2 for users |
| POST | `/documents/invoices/:n/send` | Bearer access (active sub) or guest | Cloud: queue integrated email. Guest: **403** (manual send only in PWA) |
| POST | `/dev/reset-seed` | Bearer `METRICS_TOKEN` + `ALLOW_DEV_RESET=1` | Dev: purge cloud docs + seed from Stripe (non-prod only) |
| POST | `/webhooks/stripe` | Stripe signature | `checkout.session.completed` activates account; idempotent |

### Auth

- Access token: `Authorization: Bearer <access_token>` (12 h).
- Refresh token: 30 d, body field `refresh_token`.
- Passwords: bcrypt only (`$2…` hashes).
- Metrics: `Authorization: Bearer <METRICS_TOKEN>` for `/metrics/summary` (and gated `/dev/reset-seed`).

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
    "gst_registered": true
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
