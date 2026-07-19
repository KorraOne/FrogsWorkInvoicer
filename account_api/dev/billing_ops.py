"""Billing helpers for Flask dev API (parity with worker billing.js)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import jwt
import stripe

from telemetry_ops import update_subscription_milestones

SIGNUP_TTL = timedelta(hours=24)
PENDING_TTL_DAYS = 7


def _price_id(tier: str, interval: str) -> str:
    t = "cloud" if tier == "cloud" else "local"
    i = "ANNUAL" if interval == "year" else "MONTHLY"
    key = f"STRIPE_PRICE_{t.upper()}_{i}"
    value = (os.environ.get(key) or "").strip()
    if not value:
        raise ValueError(f"Stripe price not configured for {t} {interval}.")
    return value


def _storage_tier_from_subscription(sub) -> str:
    """Local tier is retired — every FrogsWork subscription is Cloud."""
    return "cloud"


def _checkout_email(checkout) -> str:
    details = getattr(checkout, "customer_details", None)
    if details and getattr(details, "email", None):
        return details.email.strip().lower()
    return (getattr(checkout, "customer_email", None) or "").strip().lower()


def issue_signup_token(user_id: int, email: str, jwt_secret: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user_id),
            "email": email,
            "type": "signup",
            "exp": now + SIGNUP_TTL,
            "iat": now,
        },
        jwt_secret,
        algorithm="HS256",
    )


def decode_signup_token(token: str, jwt_secret: str) -> dict:
    payload = jwt.decode(token, jwt_secret, algorithms=["HS256"])
    if payload.get("type") != "signup":
        raise jwt.PyJWTError("wrong token type")
    return payload


def auth_signup(db, body, hash_password, check_password, user_by_email, jwt_secret):
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    if not email or "@" not in email:
        return {"error": "A valid email is required."}, 400
    if len(password) < 8:
        return {"error": "Password must be at least 8 characters."}, 400

    existing = user_by_email(email)
    if existing:
        status = (existing.get("account_status") or "active").strip()
        if status == "pending_payment":
            if not check_password(password, existing["password_hash"]):
                return {
                    "error": "Could not create account. Check your details or sign in."
                }, 400
            token = issue_signup_token(existing["id"], email, jwt_secret)
            return {
                "signup_token": token,
                "email": email,
                "account_status": "pending_payment",
                "resumed": True,
            }, 200
        return {
            "error": "An account with this email already exists. Sign in instead."
        }, 409

    cur = db.execute(
        """INSERT INTO users (email, password_hash, stripe_customer_id, storage_tier, account_status, created_at)
           VALUES (?, ?, NULL, 'local', 'pending_payment', ?)""",
        (
            email,
            hash_password(password),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db.commit()
    user_id = cur.lastrowid
    token = issue_signup_token(user_id, email, jwt_secret)
    return {
        "signup_token": token,
        "email": email,
        "account_status": "pending_payment",
        "resumed": False,
    }, 200


def _active_subscription(customer_id):
    if not customer_id:
        return None
    subs = stripe.Subscription.list(customer=customer_id, status="all", limit=5)
    for sub in subs.data:
        if sub.status in ("active", "trialing"):
            return sub
    return None


def create_checkout_session(db, user, body, jwt_secret, decode_access_token):
    tier = "cloud" if (body.get("tier") or "").lower() == "cloud" else "local"
    interval = "year" if (body.get("interval") or "").lower() == "year" else "month"
    try:
        price_id = _price_id(tier, interval)
    except ValueError as exc:
        return {"error": str(exc)}, 503

    origin = os.environ.get("CHECKOUT_RETURN_BASE", "http://127.0.0.1:8080").rstrip("/")
    success_url = f"{origin}/account/return.html?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/account/subscribe.html"

    existing_sub = _active_subscription(user.get("stripe_customer_id"))
    status = (user.get("account_status") or "active").strip()
    if existing_sub and status == "active":
        current_interval = (
            existing_sub.items.data[0].price.recurring.interval
            if existing_sub.items.data
            else ""
        )
        if current_interval == interval:
            item_id = existing_sub.items.data[0].id
            updated = stripe.Subscription.modify(
                existing_sub.id,
                items=[{"id": item_id, "price": price_id}],
                proration_behavior="create_prorations",
                metadata={"storage_tier": tier},
            )
            db.execute(
                "UPDATE users SET storage_tier = ? WHERE id = ?",
                (tier, user["id"]),
            )
            db.commit()
            return {"upgraded": True, "storage_tier": tier, "subscription_id": updated.id}, 200

    session_kwargs = {
        "mode": "subscription",
        "customer_email": user["email"],
        "line_items": [{"price": price_id, "quantity": 1}],
        "allow_promotion_codes": True,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(user["id"]),
        "metadata": {"user_id": str(user["id"]), "storage_tier": tier},
        "subscription_data": {
            "metadata": {"storage_tier": tier},
            "trial_period_days": 14,
        },
    }

    promo_code = (body.get("promotion_code") or "").strip()
    if promo_code:
        codes = stripe.PromotionCode.list(code=promo_code, active=True, limit=1)
        if codes.data:
            session_kwargs["discounts"] = [{"promotion_code": codes.data[0].id}]

    session = stripe.checkout.Session.create(**session_kwargs)
    return {"checkout_url": session.url, "session_id": session.id}, 200


def activate_from_checkout(db, checkout, user_by_id, subscription_status_fn):
    user_id = int(
        (checkout.metadata or {}).get("user_id")
        or checkout.client_reference_id
        or 0
    )
    user = user_by_id(user_id)
    if not user:
        raise ValueError("User not found for checkout.")

    email = _checkout_email(checkout)
    if email and email != user["email"].strip().lower():
        raise ValueError("Checkout email does not match account.")

    customer_id = checkout.customer
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    if not customer_id:
        raise ValueError("Checkout missing customer.")

    sub = checkout.subscription
    if isinstance(sub, str):
        sub = stripe.Subscription.retrieve(sub)
    if not sub or sub.status not in ("active", "trialing"):
        raise ValueError("No active subscription on checkout.")

    tier = _storage_tier_from_subscription(sub)
    db.execute(
        """UPDATE users SET stripe_customer_id = ?, account_status = 'active', storage_tier = ?
           WHERE id = ?""",
        (customer_id, tier, user_id),
    )
    db.commit()
    updated = user_by_id(user_id)
    sub_status = subscription_status_fn(customer_id)
    update_subscription_milestones(db, updated, sub_status)
    db.commit()
    return updated, tier


def checkout_session_info(db, session_id, user_by_id, subscription_status_fn):
    checkout = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
    paid = checkout.payment_status == "paid" or checkout.status == "complete"

    user_id = int(
        (checkout.metadata or {}).get("user_id")
        or checkout.client_reference_id
        or 0
    )
    user = user_by_id(user_id) if user_id else None
    email = _checkout_email(checkout) or (user["email"] if user else "")
    account_status = user.get("account_status") if user else None
    storage_tier = "cloud"

    sub = checkout.subscription
    if isinstance(sub, str) and sub:
        sub = stripe.Subscription.retrieve(sub)
    subscription_active = bool(sub and sub.status in ("active", "trialing"))

    if not paid:
        return {
            "paid": False,
            "email": email or None,
            "subscription_active": False,
            "storage_tier": storage_tier,
            "account_status": account_status,
        }, 200

    if not subscription_active:
        return {"error": "No active subscription on this checkout."}, 400

    try:
        activate_from_checkout(db, checkout, user_by_id, subscription_status_fn)
    except ValueError:
        pass

    user = user_by_id(user_id) if user_id else None
    return {
        "email": email,
        "paid": True,
        "subscription_active": True,
        "storage_tier": user.get("storage_tier", storage_tier) if user else storage_tier,
        "account_status": "active",
    }, 200


def cleanup_pending_users(db) -> int:
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=PENDING_TTL_DAYS)
    ).isoformat()
    cur = db.execute(
        """DELETE FROM users
           WHERE account_status = 'pending_payment'
             AND stripe_customer_id IS NULL
             AND created_at < ?""",
        (cutoff,),
    )
    db.commit()
    return cur.rowcount


def resolve_storage_tier_dev(user) -> str:
    """Local tier is retired — always Cloud."""
    return "cloud"
