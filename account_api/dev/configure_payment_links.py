"""Point Stripe Payment Links at the marketing site return URL."""

import os
import sys

import stripe

from dev_vars import load_dev_vars

RETURN_URL = os.environ.get(
    "STRIPE_CHECKOUT_RETURN_URL",
    "http://127.0.0.1:8080/account/return.html?session_id={CHECKOUT_SESSION_ID}",
)


def _payment_link_urls():
    monthly = os.environ.get("STRIPE_PAYMENT_LINK_MONTHLY", "").strip()
    annual = os.environ.get("STRIPE_PAYMENT_LINK_ANNUAL", "").strip()
    if not monthly or not annual:
        print("Set STRIPE_PAYMENT_LINK_MONTHLY and STRIPE_PAYMENT_LINK_ANNUAL in .dev.vars")
        sys.exit(1)
    return monthly, annual


def main():
    load_dev_vars()
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe.api_key:
        print("STRIPE_SECRET_KEY missing in .dev.vars")
        sys.exit(1)

    targets = set(_payment_link_urls())
    updated = 0
    for pl in stripe.PaymentLink.list(limit=20, active=True).auto_paging_iter():
        if pl.url.rstrip("/") not in targets:
            continue
        stripe.PaymentLink.modify(
            pl.id,
            after_completion={
                "type": "redirect",
                "redirect": {"url": RETURN_URL},
            },
        )
        print(f"Updated {pl.id} ({pl.url})")
        print(f"  redirect -> {RETURN_URL}")
        updated += 1

    if updated == 0:
        print("No matching payment links found. Check URLs in .dev.vars")
        sys.exit(1)
    print(f"Done. Updated {updated} link(s).")


if __name__ == "__main__":
    main()
