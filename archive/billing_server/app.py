"""KorraOne billing API server."""

import logging
import os
import sqlite3
from datetime import date
from functools import wraps

from flask import Flask, g, jsonify, request

import auth_service
from admin_routes import register_admin_routes
from auth_service import CapBlockedError, decode_access_token
from config import FLASK_SECRET_KEY
from db import check_db_writable, init_db
from rate_limit import auth_rate_limited

log = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
init_db()
register_admin_routes(app)


def current_month():
    return date.today().strftime("%Y-%m")


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "Authentication required"}), 401
        try:
            account_id, email = decode_access_token(header[7:])
            g.account_id = account_id
            g.email = email
        except Exception:
            return jsonify({"error": "Invalid or expired token"}), 401
        return fn(*args, **kwargs)

    return wrapper


@app.post("/auth/register")
def register():
    if auth_rate_limited():
        return jsonify({"error": "Too many attempts. Try again later."}), 429
    data = request.get_json(force=True)
    email = data.get("email", "").strip()
    password = data.get("password", "")
    if not email or not password:
        return jsonify({"error": "Email and password required."}), 400
    try:
        account_id, access, refresh = auth_service.register_account(
            email,
            password,
            data.get("cap_enabled", False),
            data.get("cap_amount_ex_gst"),
            data.get("billing_cycle", "quarterly"),
            data.get("initial_usage"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except sqlite3.OperationalError:
        log.exception("register failed: database not writable")
        return jsonify({"error": "Account service is temporarily unavailable."}), 503
    except Exception:
        log.exception("register failed")
        return jsonify({"error": "Account service is temporarily unavailable."}), 500
    return jsonify({"access_token": access, "refresh_token": refresh, "email": email})


@app.post("/auth/login")
def login():
    if auth_rate_limited():
        return jsonify({"error": "Too many attempts. Try again later."}), 429
    data = request.get_json(force=True)
    try:
        _, access, refresh, email = auth_service.login_account(
            data.get("email", ""), data.get("password", "")
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 401
    except sqlite3.OperationalError:
        log.exception("login failed: database not writable")
        return jsonify({"error": "Account service is temporarily unavailable."}), 503
    except Exception:
        log.exception("login failed")
        return jsonify({"error": "Account service is temporarily unavailable."}), 500
    return jsonify({"access_token": access, "refresh_token": refresh, "email": email})


@app.post("/auth/refresh")
def refresh():
    data = request.get_json(force=True)
    try:
        access, email = auth_service.refresh_access_token(data.get("refresh_token", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 401
    return jsonify({"access_token": access, "email": email})


@app.get("/usage")
@require_auth
def get_usage():
    snap = auth_service.usage_snapshot(g.account_id, current_month())
    return jsonify(snap)


@app.post("/usage/preview")
@require_auth
def preview_usage():
    data = request.get_json(force=True)
    amount = float(data.get("amount_ex_gst", 0))
    snap = auth_service.usage_snapshot(g.account_id, current_month(), additional=amount)
    return jsonify(snap)


@app.post("/usage/commit")
@require_auth
def commit_usage():
    data = request.get_json(force=True)
    try:
        result = auth_service.commit_usage(
            g.account_id,
            data["invoice_number"],
            data["amount_ex_gst"],
            data.get("usage_month", current_month()),
            cap_bypassed=bool(data.get("cap_bypassed")),
        )
    except CapBlockedError as exc:
        return jsonify({"error": "Cap exceeded", "preview": exc.preview}), 409
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.post("/usage/revert")
@require_auth
def revert_usage():
    data = request.get_json(force=True)
    try:
        result = auth_service.revert_usage(
            g.account_id,
            data["invoice_number"],
            data.get("usage_month", current_month()),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result)


@app.patch("/account/cap")
@require_auth
def patch_cap():
    data = request.get_json(force=True)
    auth_service.update_cap(
        g.account_id,
        data.get("cap_enabled", False),
        data.get("cap_amount_ex_gst"),
    )
    return jsonify({"ok": True})


@app.get("/account/billing")
@require_auth
def get_account_billing():
    import user_billing_service

    return jsonify(user_billing_service.get_user_billing_overview(g.account_id))


@app.patch("/account/billing-cycle")
@require_auth
def patch_billing_cycle():
    import user_billing_service

    data = request.get_json(force=True)
    try:
        overview = user_billing_service.update_billing_cycle(
            g.account_id,
            data.get("billing_cycle", "quarterly"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(overview)


@app.get("/health")
def health():
    from config import CLIENT_RELEASE_VERSION

    db_error = check_db_writable()
    payload = {"status": "ok" if db_error is None else "degraded"}
    if db_error:
        payload["db_error"] = db_error
    if CLIENT_RELEASE_VERSION:
        payload["client_release_version"] = CLIENT_RELEASE_VERSION
    code = 200 if db_error is None else 503
    return jsonify(payload), code


@app.get("/releases/latest")
def releases_latest():
    from config import (
        CLIENT_RELEASE_NOTES,
        CLIENT_RELEASE_SHA256,
        CLIENT_RELEASE_URL,
        CLIENT_RELEASE_VERSION,
    )

    if not CLIENT_RELEASE_VERSION or not CLIENT_RELEASE_URL:
        return "", 204
    return jsonify(
        {
            "version": CLIENT_RELEASE_VERSION,
            "download_url": CLIENT_RELEASE_URL,
            "sha256": CLIENT_RELEASE_SHA256,
            "notes": CLIENT_RELEASE_NOTES,
        }
    )


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8080"))
    app.run(host=host, port=port)


if __name__ == "__main__":
    main()
