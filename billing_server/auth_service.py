import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import jwt
from werkzeug.security import check_password_hash, generate_password_hash

import billing_core
from config import JWT_ACCESS_MINUTES, JWT_REFRESH_DAYS, JWT_SECRET
from db import get_db

MIN_PASSWORD_LENGTH = 8
AMOUNT_TOLERANCE = Decimal("0.01")


def _utcnow():
    return datetime.now(timezone.utc)


def hash_password(password):
    return generate_password_hash(password)


def verify_password(password_hash, password):
    return check_password_hash(password_hash, password)


def validate_password(password):
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


def validate_initial_usage(initial_usage):
    if not initial_usage:
        return
    if not initial_usage.get("ledger_hmac"):
        raise ValueError("Usage history is not signed.")
    try:
        total = Decimal(str(initial_usage.get("total_ex_gst", "0")))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Invalid usage history.") from exc
    if total < 0:
        raise ValueError("Invalid usage history.")
    event_sum = Decimal("0")
    for event in initial_usage.get("events", []):
        try:
            amount = Decimal(str(event["amount_ex_gst"]))
        except (InvalidOperation, TypeError, KeyError) as exc:
            raise ValueError("Invalid usage history.") from exc
        if amount < 0:
            raise ValueError("Invalid usage history.")
        event_sum += amount
    if abs(total - event_sum) > AMOUNT_TOLERANCE:
        raise ValueError("Usage history does not match event totals.")


def create_tokens(account_id, email):
    now = int(datetime.now(timezone.utc).timestamp())
    access = jwt.encode(
        {
            "sub": str(account_id),
            "email": email,
            "type": "access",
            "exp": now + JWT_ACCESS_MINUTES * 60,
            "iat": now,
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    refresh_raw = secrets.token_urlsafe(32)
    refresh_hash = hashlib.sha256(refresh_raw.encode()).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_DAYS)
    expires_iso = expires.isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO refresh_tokens (account_id, token_hash, expires_at) VALUES (?, ?, ?)",
            (account_id, refresh_hash, expires_iso),
        )
    return access, refresh_raw


def refresh_access_token(refresh_raw):
    refresh_hash = hashlib.sha256(refresh_raw.encode()).hexdigest()
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT rt.account_id, a.email, rt.expires_at
            FROM refresh_tokens rt
            JOIN accounts a ON a.id = rt.account_id
            WHERE rt.token_hash = ?
            """,
            (refresh_hash,),
        ).fetchone()
        if not row:
            raise ValueError("Invalid refresh token")
        if row["expires_at"] < _utcnow().isoformat():
            raise ValueError("Refresh token expired")
        access, _ = create_tokens(row["account_id"], row["email"])
        return access, row["email"]


def decode_access_token(token):
    payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    if payload.get("type") != "access":
        raise ValueError("Invalid token type")
    return int(payload["sub"]), payload["email"]


def register_account(email, password, cap_enabled, cap_amount, billing_cycle, initial_usage):
    validate_password(password)
    validate_initial_usage(initial_usage)
    now = _utcnow().isoformat()
    with get_db() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO accounts (email, password_hash, cap_enabled, cap_amount_ex_gst, billing_cycle, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    email.lower().strip(),
                    hash_password(password),
                    1 if cap_enabled else 0,
                    str(cap_amount) if cap_amount else None,
                    billing_cycle,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("An account with this email already exists.") from exc
        account_id = cur.lastrowid
        if initial_usage:
            _import_initial_usage(conn, account_id, initial_usage)
    access, refresh = create_tokens(account_id, email.lower().strip())
    return account_id, access, refresh


def _import_initial_usage(conn, account_id, initial_usage):
    month = initial_usage.get("usage_month")
    for event in initial_usage.get("events", []):
        try:
            conn.execute(
                """
                INSERT INTO usage_events (account_id, invoice_number, amount_ex_gst, usage_month, committed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    int(event["invoice_number"]),
                    str(event["amount_ex_gst"]),
                    event.get("usage_month", month),
                    _utcnow().isoformat(),
                ),
            )
        except sqlite3.IntegrityError:
            pass
    _recompute_month(conn, account_id, month)


def login_account(email, password):
    if not password:
        raise ValueError("Invalid email or password.")
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash FROM accounts WHERE email = ?",
            (email.lower().strip(),),
        ).fetchone()
        if not row or not verify_password(row["password_hash"], password):
            raise ValueError("Invalid email or password.")
        access, refresh = create_tokens(row["id"], row["email"])
        return row["id"], access, refresh, row["email"]


def get_account(account_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return dict(row) if row else None


def _month_total(conn, account_id, usage_month):
    row = conn.execute(
        """
        SELECT COALESCE(SUM(CAST(amount_ex_gst AS REAL)), 0) AS total
        FROM usage_events WHERE account_id = ? AND usage_month = ?
        """,
        (account_id, usage_month),
    ).fetchone()
    return row["total"]


def _recompute_month(conn, account_id, usage_month):
    total = _month_total(conn, account_id, usage_month)
    fee = billing_core.compute_monthly_fee(total)
    conn.execute(
        """
        INSERT INTO monthly_summaries (account_id, usage_month, total_ex_gst, fee_accrued)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(account_id, usage_month) DO UPDATE SET
            total_ex_gst = excluded.total_ex_gst,
            fee_accrued = excluded.fee_accrued
        """,
        (account_id, usage_month, str(total), str(fee)),
    )
    return total, fee


def usage_snapshot(account_id, usage_month, additional=0):
    account = get_account(account_id)
    with get_db() as conn:
        total = _month_total(conn, account_id, usage_month)
    projected = float(total) + float(additional)
    fee_now = billing_core.compute_monthly_fee(total)
    projected_fee = billing_core.compute_monthly_fee(projected)
    cap_enabled = bool(account["cap_enabled"])
    cap_amount = account["cap_amount_ex_gst"]
    cap_blocked = False
    over_by = 0
    if cap_enabled and cap_amount and projected > float(cap_amount):
        cap_blocked = True
        over_by = projected - float(cap_amount)
    return {
        "usage_month": usage_month,
        "month_total_ex_gst": projected,
        "fee_so_far": float(fee_now),
        "projected_fee": float(projected_fee),
        "fee_delta": float(projected_fee - fee_now),
        "free_remaining": float(billing_core.free_remaining(projected)),
        "cap_enabled": cap_enabled,
        "cap_amount_ex_gst": cap_amount,
        "cap_blocked": cap_blocked,
        "over_by": over_by,
        "account_required": False,
        "account_authenticated": True,
        "server_required": True,
    }


def commit_usage(account_id, invoice_number, amount_ex_gst, usage_month, cap_bypassed=False):
    account = get_account(account_id)
    preview = usage_snapshot(account_id, usage_month, additional=amount_ex_gst)
    if preview["cap_blocked"] and not cap_bypassed:
        raise CapBlockedError(preview)
    with get_db() as conn:
        try:
            conn.execute(
                """
                INSERT INTO usage_events (account_id, invoice_number, amount_ex_gst, usage_month, cap_overridden, committed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    int(invoice_number),
                    str(amount_ex_gst),
                    usage_month,
                    1 if cap_bypassed else 0,
                    _utcnow().isoformat(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Invoice already committed.") from exc
        total, fee = _recompute_month(conn, account_id, usage_month)
    return {"ok": True, "month_total_ex_gst": total, "fee_accrued": float(fee)}


def update_cap(account_id, cap_enabled, cap_amount_ex_gst):
    with get_db() as conn:
        conn.execute(
            """
            UPDATE accounts SET cap_enabled = ?, cap_amount_ex_gst = ? WHERE id = ?
            """,
            (1 if cap_enabled else 0, str(cap_amount_ex_gst) if cap_amount_ex_gst else None, account_id),
        )


class CapBlockedError(Exception):
    def __init__(self, preview):
        self.preview = preview
        super().__init__("Cap exceeded")
