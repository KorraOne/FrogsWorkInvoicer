"""Create FrogsWork Stripe products/prices with storage_tier metadata.

Usage (from repo root, with STRIPE_SECRET_KEY in env or production.env):
  python account_api/dev/setup_stripe_prices.py
  python account_api/dev/setup_stripe_prices.py --grandfather-existing

Prints price IDs to add to client_app/production.env and Worker vars.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import stripe

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_ENV = ROOT / "client_app" / "production.env"

PLANS = [
    ("local", "month", "FrogsWork Local (monthly)", 999, "aud"),
    ("local", "year", "FrogsWork Local (annual)", 9900, "aud"),
    ("cloud", "month", "FrogsWork Cloud (monthly)", 1499, "aud"),
    ("cloud", "year", "FrogsWork Cloud (annual)", 14900, "aud"),
]

LEGACY_AMOUNTS = {
    ("local", "month"): 1299,
    ("local", "year"): 12990,
}


def load_stripe_key() -> str:
    key = os.environ.get("STRIPE_SECRET_KEY", "").strip()
    if key:
        return key
    if PRODUCTION_ENV.is_file():
        for line in PRODUCTION_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("STRIPE_SECRET_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def env_key(tier: str, interval: str) -> str:
    i = "ANNUAL" if interval == "year" else "MONTHLY"
    return f"STRIPE_PRICE_{tier.upper()}_{i}"


def _meta_get(meta, key: str):
    if meta is None:
        return None
    try:
        return meta[key]
    except (KeyError, TypeError):
        return None


def _frogswork_price_ids():
    ids = []
    for tier, interval, _name, amount, _currency in PLANS:
        key = env_key(tier, interval)
        from_env = os.environ.get(key, "").strip()
        if from_env:
            ids.append(from_env)
            continue
        if PRODUCTION_ENV.is_file():
            for line in PRODUCTION_ENV.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith(f"{key}="):
                    val = line.split("=", 1)[1].strip()
                    if val:
                        ids.append(val)
                    break
    return ids


def list_catalog():
    """Print FrogsWork subscription products/prices for coupon product restrictions."""
    price_ids = _frogswork_price_ids()
    if not price_ids:
        print("No STRIPE_PRICE_* in production.env — run without --list-catalog after setup.")
        price_ids = []
        for tier, interval, _n, amount, _c in PLANS:
            pid = find_existing_price(tier, interval, amount)
            if pid:
                price_ids.append(pid)

    seen_products = {}
    print("FrogsWork subscription catalog (use prod_ IDs when limiting coupons):\n")
    for price_id in price_ids:
        try:
            price = stripe.Price.retrieve(price_id, expand=["product"])
        except stripe.error.StripeError as exc:
            print(f"  {price_id}: error — {exc}")
            continue
        product = price.product
        prod_id = product if isinstance(product, str) else product.id
        if not isinstance(product, str):
            seen_products[prod_id] = product.name
        tier = _meta_get(price.metadata, "storage_tier") or "?"
        interval = price.recurring.interval if price.recurring else "?"
        amount = (price.unit_amount or 0) / 100
        prod_name = seen_products.get(prod_id, prod_id)
        print(
            f"  {price_id}  ${amount:.2f}/{interval}  tier={tier}  "
            f"product={prod_id} ({prod_name})"
        )

    if seen_products:
        print("\nCoupon -> Apply to specific products -> select:")
        for prod_id, name in sorted(seen_products.items(), key=lambda x: x[1]):
            print(f"  - {name}  ({prod_id})")


def find_existing_price(tier: str, interval: str, amount: int):
    for product in stripe.Product.list(limit=100).auto_paging_iter():
        for price in stripe.Price.list(product=product.id, limit=100).auto_paging_iter():
            if not price.recurring:
                continue
            if price.recurring.interval != interval:
                continue
            if price.unit_amount != amount:
                continue
            meta = price.metadata or {}
            st = (_meta_get(meta, "storage_tier") or _meta_get(meta, "tier") or "").lower()
            if st == tier:
                return price.id
    return None


def ensure_price(tier: str, interval: str, name: str, amount: int, currency: str):
    existing = find_existing_price(tier, interval, amount)
    if existing:
        print(f"  exists: {env_key(tier, interval)}={existing}")
        return existing

    product = stripe.Product.create(
        name=name.rsplit(" (", 1)[0],
        metadata={"storage_tier": tier},
    )
    price = stripe.Price.create(
        product=product.id,
        unit_amount=amount,
        currency=currency,
        recurring={"interval": interval},
        metadata={"storage_tier": tier},
    )
    print(f"  created: {env_key(tier, interval)}={price.id}")
    return price.id


def tag_legacy_prices():
    """Add storage_tier=local to legacy $12.99 / $129.90 prices if found."""
    for (tier, interval), amount in LEGACY_AMOUNTS.items():
        for product in stripe.Product.list(limit=100).auto_paging_iter():
            for price in stripe.Price.list(product=product.id, limit=100).auto_paging_iter():
                if not price.recurring or price.recurring.interval != interval:
                    continue
                if price.unit_amount != amount:
                    continue
                meta = price.metadata or {}
                if _meta_get(meta, "storage_tier") or _meta_get(meta, "tier"):
                    continue
                stripe.Price.modify(
                    price.id,
                    metadata={"storage_tier": tier},
                )
                print(f"  tagged legacy price {price.id} as storage_tier={tier}")


def lookup_promo_beta80():
    codes = stripe.PromotionCode.list(code="BETA80", active=True, limit=1)
    if not codes.data:
        print("No active BETA80 promotion code found in Stripe.")
        return
    promo = codes.data[0]
    print(f"STRIPE_PROMO_BETA80={promo.id}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--grandfather-existing",
        action="store_true",
        help="Tag existing $12.99/$129.90 prices with storage_tier=local",
    )
    parser.add_argument(
        "--list-catalog",
        action="store_true",
        help="List FrogsWork price/product IDs for Stripe coupon restrictions",
    )
    parser.add_argument(
        "--lookup-promo-beta80",
        action="store_true",
        help="Print STRIPE_PROMO_BETA80 promo_ ID for admin auto-apply toggle",
    )
    args = parser.parse_args()

    key = load_stripe_key()
    if not key:
        print("STRIPE_SECRET_KEY required.", file=sys.stderr)
        sys.exit(1)
    stripe.api_key = key

    if args.lookup_promo_beta80:
        lookup_promo_beta80()
        return

    if args.list_catalog:
        list_catalog()
        return

    print("FrogsWork Stripe prices:")
    ids = {}
    for tier, interval, name, amount, currency in PLANS:
        ids[env_key(tier, interval)] = ensure_price(
            tier, interval, name, amount, currency
        )

    if args.grandfather_existing:
        print("Grandfathering legacy prices:")
        tag_legacy_prices()

    print("\nAdd to client_app/production.env:")
    for k, v in ids.items():
        print(f"{k}={v}")
    print("\nAdd to account_api/worker/wrangler.toml [vars] (non-secret):")


if __name__ == "__main__":
    main()
