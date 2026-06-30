# Stripe setup (FrogsWork subscription)

Operator checklist for the subscription model. Test mode first, then live keys on the Worker.

## Products and prices

| Plan | Amount | Stripe price ID (test) |
|------|--------|-------------------------|
| Monthly | $12.99 AUD | `price_1TntfOIQSiAlmwTlzqPJayus` |
| Annual | $129.90 AUD (2 months free) | `price_1TnthTIQSiAlmwTlfcvD95h5` |

Create matching **live** prices before go-live and update `account_api/worker/wrangler.toml` `[vars]`.

## Payment links (recommended)

Use **Stripe Payment Links** for checkout in the **desktop app**. No API call needed when the user pays.

### Create links

1. Stripe Dashboard → **Payment links** → **New**
2. Product: monthly ($12.99) or annual ($129.90) subscription price
3. **After payment** must **redirect** (not Stripe’s hosted confirmation page) to:  
   `http://127.0.0.1:5000/account/stripe/return?session_id={CHECKOUT_SESSION_ID}`  
   For production packaged app, use the same URL pattern — the app serves `127.0.0.1:5000` locally.
4. Copy each link (`https://buy.stripe.com/…`) into `account_api/dev/.dev.vars`

Or run (updates links via API from `.dev.vars`):

```powershell
.\scripts\configure-payment-links.ps1
```

### Configure desktop app

Add to `account_api/dev/.dev.vars` (loaded by `scripts/start-dev.ps1`):

```env
STRIPE_PAYMENT_LINK_MONTHLY=https://buy.stripe.com/test_...
STRIPE_PAYMENT_LINK_ANNUAL=https://buy.stripe.com/test_...
```

Payment link **After payment** URL must be exactly:

`http://127.0.0.1:5000/account/stripe/return?session_id={CHECKOUT_SESSION_ID}`

(Shown at the bottom of the in-app subscribe page.)

### Marketing site

Subscription checkout runs **in the app**, not on [pricing.html](../../marketing_site/pricing.html). The marketing site describes pricing only.

---

## Checkout flow (payment links)

**Pay first, then password** — Stripe is the source of truth for email.

| Step | Where | What |
|------|--------|------|
| 1 | App — Subscribe | Choose monthly or annual |
| 2 | Browser — Stripe | Pay; enter the email you want on your account |
| 3 | App — Create password | Email shown from checkout (read-only); set password |
| 4 | App — Done | Signed in with active subscription |

Business details and customers stay in **Welcome** or **Settings** — not in the subscribe wizard.

1. User clicks **Pay monthly / Pay annually** → browser opens Payment Link
2. User pays on Stripe (email collected there)
3. Stripe redirects to `http://127.0.0.1:5000/account/stripe/return?session_id=…`; app polls and continues
4. User sets password → API registers using checkout session email → full access

See also [`account_api/ROUTES.md`](../../account_api/ROUTES.md).

## Customer portal

Enable **Customer portal** in Stripe Dashboard → Settings → Billing → Customer portal. Users open it from **Settings → Your account** (`portal_url` from `/entitlements`).

## Webhooks

| Setting | Value |
|---------|--------|
| URL | `https://api.frogswork.com/webhooks/stripe` |
| Secret | Store as `STRIPE_WEBHOOK_SECRET` on the Worker |

Subscribe to:

- `checkout.session.completed`
- `customer.subscription.updated`
- `customer.subscription.deleted`

Entitlements are checked live on `/entitlements`; webhooks acknowledge events for future automation.

## Local development

```powershell
.\scripts\start-dev.ps1 -DevBrowser
```

Copy `account_api/dev/.dev.vars.example` → `.dev.vars` with Stripe keys, price IDs, and payment links.

Point the desktop app at `http://127.0.0.1:8787` automatically via the start scripts.

## Security

- Never commit `sk_test_` / `sk_live_` keys or webhook secrets.
- Rotate keys if exposed in chat or logs.
- Use restricted keys only where appropriate (e.g. read-only analytics); the Worker needs full secret key for Checkout and portal.
