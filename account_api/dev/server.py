"""FrogsWork account API — auth, Stripe checkout, entitlements."""

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

import bcrypt
import jwt
import stripe
from flask import Flask, Response, g, jsonify, request

from auth_ops import (
    check_rate_limit,
    forgot_password,
    is_default_beta80_enabled,
    is_email_verified,
    reset_password,
    send_verification_email,
    set_default_beta80_enabled,
    verify_email,
)
from billing_ops import (
    auth_signup,
    checkout_session_info,
    cleanup_pending_users,
    create_checkout_session,
    decode_signup_token,
    activate_from_checkout,
    resolve_storage_tier_dev,
)
from dev_vars import load_dev_vars
from telemetry_ops import (
    is_valid_install_id,
    link_install_on_register,
    record_event,
    update_subscription_milestones,
    upsert_heartbeat,
)

load_dev_vars()

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-insecure-jwt-secret")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ACCESS_TTL = timedelta(hours=12)
REFRESH_TTL = timedelta(days=30)

app = Flask(__name__)
APP_DIR = Path(__file__).resolve().parent


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
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _check_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def init_db():
    schema_path = APP_DIR.parent / "schema.sql"
    db = sqlite3.connect(_db_path())
    _migrate_db(db)
    db.executescript(schema_path.read_text(encoding="utf-8"))
    db.commit()
    db.close()


def _migrate_db(db):
    """Apply additive migrations for existing dev databases."""
    cols = {row[1] for row in db.execute("PRAGMA table_info(users)").fetchall()}
    if "install_id" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN install_id TEXT")
    if "storage_tier" not in cols:
        db.execute(
            "ALTER TABLE users ADD COLUMN storage_tier TEXT NOT NULL DEFAULT 'local'"
        )
    if "account_status" not in cols:
        db.execute(
            "ALTER TABLE users ADD COLUMN account_status TEXT NOT NULL DEFAULT 'active'"
        )
    if "email_verified_at" not in cols:
        db.execute("ALTER TABLE users ADD COLUMN email_verified_at TEXT")


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


def require_admin(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not ADMIN_PASSWORD:
            return jsonify({"error": "Admin not configured."}), 503
        auth = request.authorization
        if not auth or auth.password != ADMIN_PASSWORD:
            return Response(
                "Unauthorized",
                401,
                {"WWW-Authenticate": 'Basic realm="FrogsWork Admin"'},
            )
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
def checkout_session_info_route():
    session_id = (request.args.get("session_id") or "").strip()
    if not session_id.startswith("cs_"):
        return jsonify({"error": "Invalid checkout session."}), 400
    try:
        payload, status = checkout_session_info(
            get_db(),
            session_id,
            _user_by_id,
            _subscription_status,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(payload), status


@app.post("/auth/signup")
def auth_signup_route():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
    if not check_rate_limit(get_db(), f"auth_signup:{ip}"):
        return jsonify({"error": "Too many requests. Try again later."}), 429
    body = request.get_json(force=True, silent=True) or {}
    payload, status = auth_signup(
        get_db(),
        body,
        _hash_password,
        _check_password,
        _user_by_email,
        JWT_SECRET,
    )
    if status == 200 and not payload.get("resumed"):
        user = _user_by_email(payload.get("email", ""))
        if user:
            send_verification_email(get_db(), dict(user))
    return jsonify(payload), status


def _auth_user_from_request():
    header = request.headers.get("Authorization") or ""
    if not header.startswith("Bearer "):
        return None, None
    token = header[7:]
    try:
        payload = decode_signup_token(token, JWT_SECRET)
        user = _user_by_id(int(payload["sub"]))
        if user and user["email"] == (payload.get("email") or "").strip().lower():
            return user, "signup"
    except jwt.PyJWTError:
        pass
    try:
        payload = _decode_token(token, "access")
        user = _user_by_id(int(payload["sub"]))
        if user:
            return user, "access"
    except jwt.PyJWTError:
        pass
    return None, None


@app.post("/checkout/create-session")
def checkout_create_session():
    user, _kind = _auth_user_from_request()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    body = request.get_json(force=True, silent=True) or {}
    try:
        payload, status = create_checkout_session(
            get_db(), user, body, JWT_SECRET, _decode_token
        )
    except stripe.error.StripeError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(payload), status


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
        "INSERT INTO users (email, password_hash, stripe_customer_id, account_status, created_at) VALUES (?, ?, ?, 'active', ?)",
        (
            email,
            _hash_password(password),
            stripe_customer_id,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db.commit()
    access, refresh = _issue_tokens(cur.lastrowid, email)

    install_id = (body.get("install_id") or "").strip().lower()
    if is_valid_install_id(install_id):
        link_install_on_register(db, install_id, cur.lastrowid, body.get("signup_snapshot"))
        user = _user_by_id(cur.lastrowid)
        sub = _subscription_status(stripe_customer_id)
        update_subscription_milestones(db, user, sub)
        db.commit()

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
        "UPDATE users SET stripe_customer_id = ?, account_status = 'active' WHERE id = ?",
        (stripe_customer_id, user["id"]),
    )
    db.commit()
    tier = resolve_storage_tier_dev(
        {**user, "stripe_customer_id": stripe_customer_id}
    )
    return jsonify({"ok": True, "storage_tier": tier})


@app.post("/auth/login")
def auth_login():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
    if not check_rate_limit(get_db(), f"auth_login:{ip}"):
        return jsonify({"error": "Too many requests. Try again later."}), 429
    body = request.get_json(force=True, silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""
    user = _user_by_email(email)
    if not user or not _check_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid email or password."}), 401
    if (user.get("account_status") or "active").strip() == "pending_payment":
        return jsonify(
            {
                "error": "Your account is not active yet. Finish checkout on the subscribe page."
            }
        ), 403
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


@app.post("/auth/forgot-password")
def auth_forgot_password():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
    if not check_rate_limit(get_db(), f"auth_forgot:{ip}"):
        return jsonify({"error": "Too many requests. Try again later."}), 429
    body = request.get_json(force=True, silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    payload, status = forgot_password(get_db(), email, _user_by_email)
    return jsonify(payload), status


@app.post("/auth/reset-password")
def auth_reset_password():
    body = request.get_json(force=True, silent=True) or {}
    payload, status = reset_password(
        get_db(),
        (body.get("token") or "").strip(),
        body.get("password") or "",
        _hash_password,
    )
    return jsonify(payload), status


@app.post("/auth/verify-email")
def auth_verify_email():
    body = request.get_json(force=True, silent=True) or {}
    payload, status = verify_email(get_db(), (body.get("token") or "").strip())
    return jsonify(payload), status


@app.post("/auth/resend-verification")
@require_auth
def auth_resend_verification():
    user = g.current_user
    if is_email_verified(user):
        return jsonify({"ok": True, "already_verified": True})
    send_verification_email(get_db(), dict(user))
    return jsonify({"ok": True, "sent": True})


@app.get("/entitlements")
@require_auth
def entitlements():
    user = g.current_user
    sub = _subscription_status(user["stripe_customer_id"])
    sub["portal_url"] = _portal_url(user["stripe_customer_id"])
    tier = resolve_storage_tier_dev(user)
    sub["storage_tier"] = tier
    sub["platforms"] = {"desktop": True, "mobile": tier == "cloud"}
    sub["email_verified"] = is_email_verified(user)
    sub["email"] = user["email"]
    db = get_db()
    update_subscription_milestones(db, user, sub)
    db.commit()
    return jsonify(sub)


@app.post("/telemetry/heartbeat")
def telemetry_heartbeat():
    body = request.get_json(force=True, silent=True) or {}
    try:
        result = upsert_heartbeat(get_db(), body)
        get_db().commit()
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/telemetry/event")
def telemetry_event():
    body = request.get_json(force=True, silent=True) or {}
    try:
        result = record_event(get_db(), body)
        get_db().commit()
        return jsonify({"ok": True, **result})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.get("/admin/api/accounts")
@require_admin
def admin_api_accounts():
    return jsonify({"accounts": list_admin_accounts(get_db())})


@app.get("/admin/api/summary")
@require_admin
def admin_api_summary():
    return jsonify(build_admin_summary(get_db()))


@app.post("/admin/api/checkout/default-beta80")
@require_admin
def admin_checkout_beta80():
    body = request.get_json(force=True, silent=True) or {}
    enabled = set_default_beta80_enabled(get_db(), bool(body.get("enabled")))
    return jsonify({"ok": True, "enabled": enabled})


@app.get("/admin")
@require_admin
def admin_dashboard():
    summary = build_admin_summary(get_db())
    promo = {"default_beta80_enabled": is_default_beta80_enabled(get_db())}
    html = render_admin_html(summary, promo_context=promo)
    return Response(html, mimetype="text/html; charset=utf-8")


@app.get("/releases/latest")
def releases_latest():
    version = (os.environ.get("CLIENT_RELEASE_VERSION") or "").strip()
    if not version:
        return ("", 204)
    return jsonify(
        {
            "version": version,
            "download_url": (os.environ.get("CLIENT_RELEASE_URL") or "").strip(),
            "sha256": (os.environ.get("CLIENT_RELEASE_SHA256") or "").strip(),
            "notes": (os.environ.get("CLIENT_RELEASE_NOTES") or "").strip(),
        }
    )


@app.post("/admin/api/cleanup-pending")
@require_admin
def admin_cleanup_pending():
    deleted = cleanup_pending_users(get_db())
    return jsonify({"ok": True, "deleted": deleted})


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
    if event.type == "checkout.session.completed":
        checkout = event.data.object
        if checkout.mode == "subscription":
            try:
                activate_from_checkout(
                    get_db(), checkout, _user_by_id, _subscription_status
                )
            except ValueError:
                pass
    return jsonify({"received": True})


def main():
    init_db()
    port = int(os.environ.get("FLASK_PORT", "8787"))
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
