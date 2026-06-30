# Billing rules (subscription model)

## Free trial

- **20 invoices** lifetime, **or**
- **$20,000 ex GST** invoiced lifetime (whichever comes first)
- No account required during trial
- Works fully offline
- Totals derive from `invoices.json` on the local PC

Configurable in `client_app/app_config.py`: `TRIAL_MAX_INVOICES`, `TRIAL_MAX_EX_GST`.

## After trial

1. User creates a KorraOne account (email + password).
2. User subscribes via Stripe Checkout (**$12.99/month** or **$129.90/year**).
3. Registration links the paid Checkout session to the account.

## Subscribed use

- **Unlimited** sales invoice generation
- Invoice PDFs and customer data remain local (`%APPDATA%\FrogsWork\`)
- Subscription status cached in `entitlement_cache.json`

## Offline grace

| Days since last verify | Behaviour |
|------------------------|-----------|
| 0–6 | Full access |
| 7–13 | Soft reminder banner; generate still allowed |
| 14+ | Generate blocked until online verify |

Verify via **Settings → Your account** (calls `GET /entitlements` on api.frogswork.com).

## Related docs

- [STRIPE_SETUP.md](STRIPE_SETUP.md) — Stripe Dashboard, webhooks, Buy Buttons
- [security-risk-model.md](security-risk-model.md) — offline entitlement cache
- [DEPLOY.md](DEPLOY.md) — api.frogswork.com Worker deploy
