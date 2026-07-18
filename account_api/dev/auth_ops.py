"""Auth email and rate-limit helpers for Flask dev API."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

RATE_LIMIT = 10
RATE_WINDOW = timedelta(minutes=15)
RESET_TTL = timedelta(hours=1)
VERIFY_TTL = timedelta(days=7)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _marketing_base() -> str:
    return os.environ.get("CHECKOUT_RETURN_BASE", "http://127.0.0.1:8080").rstrip("/")


def check_rate_limit(db, bucket_key: str) -> bool:
    now = datetime.now(timezone.utc)
    window_start = (now - RATE_WINDOW).isoformat()
    row = db.execute(
        "SELECT window_start, count FROM rate_limit_buckets WHERE bucket_key = ?",
        (bucket_key,),
    ).fetchone()
    if not row or row["window_start"] < window_start:
        db.execute(
            """INSERT INTO rate_limit_buckets (bucket_key, window_start, count)
               VALUES (?, ?, 1)
               ON CONFLICT(bucket_key) DO UPDATE SET window_start = excluded.window_start, count = 1""",
            (bucket_key, now.isoformat()),
        )
        db.commit()
        return True
    if row["count"] >= RATE_LIMIT:
        return False
    db.execute(
        "UPDATE rate_limit_buckets SET count = count + 1 WHERE bucket_key = ?",
        (bucket_key,),
    )
    db.commit()
    return True


def is_email_verified(user) -> bool:
    return bool(user.get("email_verified_at"))


def send_verification_email(db, user):
    token = secrets.token_hex(32)
    token_hash = _hash_token(token)
    now = datetime.now(timezone.utc)
    expires = (now + VERIFY_TTL).isoformat()
    db.execute(
        """INSERT INTO email_verification_tokens (user_id, token_hash, expires_at, created_at)
           VALUES (?, ?, ?, ?)""",
        (user["id"], token_hash, expires, now.isoformat()),
    )
    db.commit()
    link = f"{_marketing_base()}/account/verify-email.html?token={token}"
    print(f"[dev] verification email to {user['email']}: {link}")


def forgot_password(db, email: str, user_by_email):
    generic = {"ok": True, "message": "If that email is registered, we sent reset instructions."}
    if not email or "@" not in email:
        return generic, 200
    user = user_by_email(email)
    if not user:
        return generic, 200
    token = secrets.token_hex(32)
    token_hash = _hash_token(token)
    now = datetime.now(timezone.utc)
    expires = (now + RESET_TTL).isoformat()
    db.execute(
        """INSERT INTO password_reset_tokens (user_id, token_hash, expires_at, created_at)
           VALUES (?, ?, ?, ?)""",
        (user["id"], token_hash, expires, now.isoformat()),
    )
    db.commit()
    link = f"{_marketing_base()}/account/reset-password.html?token={token}"
    print(f"[dev] password reset for {email}: {link}")
    return generic, 200


def reset_password(db, token: str, password: str, hash_password):
    if not token:
        return {"error": "Reset token is required."}, 400
    if len(password) < 8:
        return {"error": "Password must be at least 8 characters."}, 400
    token_hash = _hash_token(token)
    row = db.execute(
        """SELECT * FROM password_reset_tokens
           WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?""",
        (token_hash, datetime.now(timezone.utc).isoformat()),
    ).fetchone()
    if not row:
        return {"error": "Invalid or expired reset link."}, 400
    used_at = datetime.now(timezone.utc).isoformat()
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(password), row["user_id"]),
    )
    db.execute(
        "UPDATE password_reset_tokens SET used_at = ? WHERE id = ?",
        (used_at, row["id"]),
    )
    db.commit()
    return {"ok": True}, 200


def verify_email(db, token: str):
    if not token:
        return {"error": "Verification token is required."}, 400
    token_hash = _hash_token(token)
    row = db.execute(
        """SELECT * FROM email_verification_tokens
           WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?""",
        (token_hash, datetime.now(timezone.utc).isoformat()),
    ).fetchone()
    if not row:
        return {"error": "Invalid or expired verification link."}, 400
    used_at = datetime.now(timezone.utc).isoformat()
    db.execute(
        "UPDATE users SET email_verified_at = ? WHERE id = ?",
        (used_at, row["user_id"]),
    )
    db.execute(
        "UPDATE email_verification_tokens SET used_at = ? WHERE id = ?",
        (used_at, row["id"]),
    )
    db.commit()
    return {"ok": True, "verified": True}, 200
