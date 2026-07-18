# Stripe coupons and promotion codes (FrogsWork checkout)

FrogsWork checkout uses **dynamic Checkout Sessions** with `allow_promotion_codes: true`. Customers enter a code on the Stripe-hosted payment page (not on frogswork.com).

## Scoping coupons to FrogsWork subscriptions only

Stripe applies a promotion code only if the coupon is **allowed for the products in the cart**. FrogsWork checkout always contains exactly one of these four subscription prices:

| Plan | Env var |
|------|---------|
| Local monthly | `STRIPE_PRICE_LOCAL_MONTHLY` |
| Local annual | `STRIPE_PRICE_LOCAL_ANNUAL` |
| Cloud monthly | `STRIPE_PRICE_CLOUD_MONTHLY` |
| Cloud annual | `STRIPE_PRICE_CLOUD_ANNUAL` |

To stop a code working on unrelated Stripe products (other businesses, one-off items, old payment links):

1. In **Stripe Dashboard → Product catalog → Coupons → Create coupon**
2. Under **Apply to specific products**, select only:
   - **FrogsWork Local**
   - **FrogsWork Cloud**  
   (and legacy FrogsWork subscription products if you still sell them)
3. Do **not** select products used for other ventures.

If you use other checkouts without promotion codes enabled, codes restricted to FrogsWork products will not apply there anyway.

List product and price IDs from your account:

```powershell
python account_api\dev\setup_stripe_prices.py --list-catalog
```

Use the printed `prod_...` IDs when creating coupons in the Dashboard.

## Recommended coupon setup

### Dev (100% off)

| Setting | Suggestion |
|---------|------------|
| Type | Percent off → **100%** |
| Duration | **Forever** (or **Repeating** if you only want free for N months) |
| Products | FrogsWork Local + FrogsWork Cloud only |
| Promotion code | e.g. `DEV100` |
| Redemptions | Limit total uses; restrict to your email domain if needed |
| Mode | Prefer **test mode** for internal dev; use live only with tight limits |

100% off still creates a real subscription (status `active` / `trialing`) so entitlements and `storage_tier` work normally.

### Beta testers (heavy discount)

| Setting | Suggestion |
|---------|------------|
| Type | e.g. **80% off** or fixed amount |
| Duration | **Repeating** → e.g. 3 or 6 months, then full price |
| Products | Same FrogsWork Local + Cloud only |
| Promotion code | e.g. `BETA80` (one code per cohort, or unique codes per tester) |
| Redemptions | Max redemptions = number of beta invites |

Create **separate coupons** for dev vs beta vs future campaigns. Each gets its own promotion code(s).

## What FrogsWork does not do (by design)

- No coupon field on frogswork.com (Stripe Checkout handles it).
- Optional URL: `subscribe.html?promo=BETA80` passes `promotion_code` to checkout.
- Coupons on **subscription upgrade** (swap price via API) are separate from Checkout; use Portal or a dedicated flow if needed.
- Auto-apply of a default promo from the old admin panel was removed — manage discounts in Stripe.

## Verify

1. Signup → subscribe → Stripe Checkout.
2. Click **Add promotion code** (wording may vary).
3. Enter `DEV100` (test) — total should reflect discount.
4. Complete payment; account activates with correct `storage_tier`.

## Deploy note

`allow_promotion_codes` is set in `account_api/worker/src/billing.js`. Redeploy the API worker after changing checkout options.
