"""FrogsWork account API — auth, Stripe checkout, entitlements."""

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import jwt
import stripe
from flask import Flask, g, jsonify, request

try:
    import bcrypt
except ImportError:
    bcrypt = None
from werkzeug.security import check_password_hash, generate_password_hash

APP_DIR = Path(__file__).resolve().parent


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


_load_dev_vars()

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-insecure-jwt-secret")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PRICE_MONTHLY = os.environ.get("STRIPE_PRICE_MONTHLY_ID", "")
PRICE_ANNUAL = os.environ.get("STRIPE_PRICE_ANNUAL_ID", "")
ACCESS_TTL = timedelta(hours=12)
REFRESH_TTL = timedelta(days=30)

app = Flask(__name__)


def _db_path():
    return APP_DIR / "account_api.db"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(_db_path())
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _hash_password(password):
    if bcrypt:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    return generate_password_hash(password)


def _check_password(password, password_hash):
    if bcrypt and password_hash.startswith("$2"):
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    return check_password_hash(password_hash, password)


def init_db():
    db = sqlite3.connect(_db_path())
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            stripe_customer_id TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    db.commit()
    db.close()


def _price_for_plan(plan):
    if plan == "annual":
        return PRICE_ANNUAL
    if plan == "monthly":
        return PRICE_MONTHLY
    return None


def _issue_tokens(user_id, email):
    now = datetime.now(timezone.utc)
    access = jwt.encode(
        {
            "sub": str(user_id),
            "email": email,
            "type": "access",
            "exp": now + ACCESS_TTL,
            "iat": now,
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    refresh = jwt.encode(
        {
            "sub": str(user_id),
            "email": email,
            "type": "refresh",
            "exp": now + REFRESH_TTL,
            "iat": now,
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    return access, refresh


def _decode_token(token, expected_type):
    payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def _user_by_email(email):
    row = get_db().execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    return row


def _user_by_id(user_id):
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return row


def _iso_from_timestamp(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _period_end_from_subscription(sub):
    ts = getattr(sub, "current_period_end", None)
    if not ts:
        ts = getattr(sub, "cancel_at", None)
    items = getattr(sub, "items", None)
    if not ts and items and items.data:
        ts = getattr(items.data[0], "current_period_end", None)
    return _iso_from_timestamp(ts)


def _subscription_is_canceling(sub):
    if getattr(sub, "cancel_at_period_end", False):
        return True
    if getattr(sub, "cancel_at", None):
        return True
    if getattr(sub, "canceled_at", None) and sub.status in ("active", "trialing"):
        return True
    return False


def _plan_interval_from_subscription(sub):
    items = getattr(sub, "items", None)
    if not items or not items.data:
        return ""
    price = items.data[0].price
    if price and price.recurring:
        return price.recurring.interval or ""
    return ""


def _subscription_status(customer_id):
    if not customer_id:
        return {
            "active": False,
            "status": "none",
            "canceling": False,
            "access_until": None,
            "current_period_end": None,
            "plan_interval": "",
        }
    subs = stripe.Subscription.list(customer=customer_id, status="all", limit=5)
    for sub in subs.data:
        if sub.status in ("active", "trialing"):
            access_until = _period_end_from_subscription(sub)
            return {
                "active": True,
                "status": sub.status,
                "canceling": _subscription_is_canceling(sub),
                "access_until": access_until,
                "current_period_end": access_until,
                "plan_interval": _plan_interval_from_subscription(sub),
            }
    for sub in subs.data:
        if sub.status == "canceled":
            ended = _iso_from_timestamp(getattr(sub, "ended_at", None))
            return {
                "active": False,
                "status": "canceled",
                "canceling": False,
                "access_until": ended,
                "current_period_end": ended,
                "plan_interval": _plan_interval_from_subscription(sub),
            }
    return {
        "active": False,
        "status": "inactive",
        "canceling": False,
        "access_until": None,
        "current_period_end": None,
        "plan_interval": "",
    }


def _portal_url(customer_id):
    if not customer_id:
        return None
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url="https://frogswork.com/support.html",
    )
    return session.url


def require_auth(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        token = header[7:]
        try:
            payload = _decode_token(token, "access")
            user = _user_by_id(int(payload["sub"]))
            if not user:
                return jsonify({"error": "Unauthorized"}), 401
            g.current_user = user
        except jwt.PyJWTError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)

    return wrapped


@app.get("/health")
def health():
    return jsonify({"ok": True, "stripe": bool(stripe.api_key)})


def _checkout_session_email(checkout):
    details = getattr(checkout, "customer_details", None)
    if details is not None:
        email = getattr(details, "email", None)
        if email:
            return email
    return getattr(checkout, "customer_email", None)


def _validated_checkout_session(session_id):
    """Return (email, stripe_customer_id) for a paid subscription checkout."""
    checkout = stripe.checkout.Session.retrieve(session_id, expand=["subscription"])
    if checkout.payment_status != "paid" and checkout.status != "complete":
        raise ValueError("Checkout is not complete. Finish payment first.")
    email = _checkout_session_email(checkout)
    if not email:
        raise ValueError("No email on this checkout session.")
    sub = checkout.subscription
    if isinstance(sub, str):
        sub = stripe.Subscription.retrieve(sub)
    if not sub or sub.status not in ("active", "trialing"):
        raise ValueError("No active subscription on this checkout.")
    customer_id = checkout.customer
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    return email.strip().lower(), customer_id


@app.get("/checkout/session-info")
def checkout_session_info():
    session_id = (request.args.get("session_id") or "").strip()
    if not session_id.startswith("cs_"):
        return jsonify({"error": "Invalid checkout session."}), 400
    try:
        email, _customer_id = _validated_checkout_session(session_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(
        {
            "email": email,
            "paid": True,
            "subscription_active": True,
            "account_exists": _user_by_email(email) is not None,
        }
    )


@app.post("/auth/register")
def auth_register():
    body = request.get_json(force=True, silent=True) or {}
    password = body.get("password") or ""
    session_id = (body.get("checkout_session_id") or "").strip()
    if not password:
        return jsonify({"error": "Password is required."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    if not session_id:
        return jsonify({"error": "Checkout session is required to register."}), 400

    try:
        email, stripe_customer_id = _validated_checkout_session(session_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if _user_by_email(email):
        return jsonify({"error": "An account with this email is already registered. Try signing in."}), 409

    db = get_db()
    cur = db.execute(
        "INSERT INTO users (email, password_hash, stripe_customer_id, created_at) VALUES (?, ?, ?, ?)",
        (
            email,
            _hash_password(password),
            stripe_customer_id,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db.commit()
    access, refresh = _issue_tokens(cur.lastrowid, email)
    return jsonify({"access_token": access, "refresh_token": refresh, "email": email})


@app.post("/auth/attach-checkout")
@require_auth
def auth_attach_checkout():
    """Link a paid checkout to an existing account (same email as Stripe)."""
    body = request.get_json(force=True, silent=True) or {}
    session_id = (body.get("checkout_session_id") or "").strip()
    if not session_id:
        return jsonify({"error": "Checkout session is required."}), 400
    try:
        email, stripe_customer_id = _validated_checkout_session(session_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    user = g.current_user
    if email != user["email"].strip().lower():
        return jsonify({"error": "Checkout email does not match your account."}), 400

    db = get_db()
    db.execute(
        "UPDATE users SET stripe_customer_id = ? WHERE id = ?",
        (stripe_customer_id, user["id"]),
    )
    db.commit()
    return jsonify({"ok": True})


@app.post("/auth/login")
def auth_login():
    body = request.get_json(force=True, silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    user = _user_by_email(email)
    if not user or not _check_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid email or password."}), 401
    access, refresh = _issue_tokens(user["id"], user["email"])
    return jsonify({"access_token": access, "refresh_token": refresh})


@app.post("/auth/refresh")
def auth_refresh():
    body = request.get_json(force=True, silent=True) or {}
    token = body.get("refresh_token") or ""
    try:
        payload = _decode_token(token, "refresh")
        user = _user_by_id(int(payload["sub"]))
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        access, refresh = _issue_tokens(user["id"], user["email"])
        return jsonify({"access_token": access, "refresh_token": refresh})
    except jwt.PyJWTError:
        return jsonify({"error": "Invalid refresh token."}), 401


@app.get("/entitlements")
@require_auth
def entitlements():
    user = g.current_user
    sub = _subscription_status(user["stripe_customer_id"])
    sub["portal_url"] = _portal_url(user["stripe_customer_id"])
    return jsonify(sub)


@app.post("/checkout/create")
def checkout_create():
    body = request.get_json(force=True, silent=True) or {}
    plan = (body.get("plan") or "monthly").strip().lower()
    price_id = _price_for_plan(plan)
    if not price_id:
        return jsonify({"error": "Unknown plan."}), 400
    email = (body.get("email") or "").strip()
    success_url = body.get("success_url") or "https://frogswork.com/subscribe/success.html?session_id={CHECKOUT_SESSION_ID}"
    cancel_url = body.get("cancel_url") or "https://frogswork.com/pricing.html"
    params = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    if email:
        params["customer_email"] = email
    session = stripe.checkout.Session.create(**params)
    return jsonify({"checkout_url": session.url, "session_id": session.id})


@app.get("/releases/latest")
def releases_latest():
    return ("", 204)


@app.post("/webhooks/stripe")
def stripe_webhook():
    payload = request.get_data()
    sig = request.headers.get("Stripe-Signature", "")
    if not WEBHOOK_SECRET:
        return jsonify({"error": "Webhook secret not configured."}), 500
    try:
        event = stripe.Webhook.construct_event(payload, sig, WEBHOOK_SECRET)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    if event["type"] in (
        "checkout.session.completed",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        return jsonify({"received": True})
    return jsonify({"received": True})


def main():
    init_db()
    port = int(os.environ.get("FLASK_PORT", "8787"))
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
