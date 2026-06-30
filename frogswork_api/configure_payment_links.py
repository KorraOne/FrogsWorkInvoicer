"""Point Stripe Payment Links at the desktop app return URL (local dev)."""

import os
import sys
from pathlib import Path

import stripe

APP_DIR = Path(__file__).resolve().parent
RETURN_URL = os.environ.get(
    "STRIPE_CHECKOUT_RETURN_URL",
    "http://127.0.0.1:5000/account/stripe/return?session_id={CHECKOUT_SESSION_ID}",
)


def _load_dev_vars():
    path = APP_DIR / ".dev.vars"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _payment_link_urls():
    monthly = os.environ.get("STRIPE_PAYMENT_LINK_MONTHLY", "").strip()
    annual = os.environ.get("STRIPE_PAYMENT_LINK_ANNUAL", "").strip()
    if not monthly or not annual:
        print("Set STRIPE_PAYMENT_LINK_MONTHLY and STRIPE_PAYMENT_LINK_ANNUAL in .dev.vars")
        sys.exit(1)
    return monthly, annual


def main():
    _load_dev_vars()
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
