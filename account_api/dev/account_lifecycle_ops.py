"""Account export / wipe / delete (dev Flask parity)."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone


def purge_user_cloud_data(db, user_id: int) -> dict:
    counts = {}
    for label, sql in [
        ("doc_invoices", "DELETE FROM doc_invoices WHERE user_id = ?"),
        ("doc_businesses", "DELETE FROM doc_businesses WHERE user_id = ?"),
        ("doc_customers", "DELETE FROM doc_customers WHERE user_id = ?"),
        ("doc_settings", "DELETE FROM doc_settings WHERE user_id = ?"),
        ("email_outbox", "DELETE FROM email_outbox WHERE user_id = ?"),
        ("account_devices", "DELETE FROM account_devices WHERE user_id = ?"),
        ("auth_handoff_codes", "DELETE FROM auth_handoff_codes WHERE user_id = ?"),
        ("password_reset_tokens", "DELETE FROM password_reset_tokens WHERE user_id = ?"),
        ("email_verification_tokens", "DELETE FROM email_verification_tokens WHERE user_id = ?"),
    ]:
        try:
            cur = db.execute(sql, (user_id,))
            counts[label] = cur.rowcount if cur.rowcount is not None else 0
        except Exception:
            counts[label] = 0
    counts["r2_deleted"] = 0
    db.commit()
    return counts


def build_export_zip(db, user) -> bytes:
    user_id = user["id"]
    businesses = {}
    for row in db.execute(
        "SELECT name, data_json FROM doc_businesses WHERE user_id = ?", (user_id,)
    ).fetchall():
        try:
            businesses[row["name"]] = json.loads(row["data_json"] or "{}")
        except Exception:
            businesses[row["name"]] = {}

    customers = {}
    for row in db.execute(
        "SELECT name, data_json FROM doc_customers WHERE user_id = ?", (user_id,)
    ).fetchall():
        try:
            customers[row["name"]] = json.loads(row["data_json"] or "{}")
        except Exception:
            customers[row["name"]] = {}

    invoices = {}
    for row in db.execute(
        "SELECT invoice_key, invoice_number, data_json, pdf_status FROM doc_invoices WHERE user_id = ?",
        (user_id,),
    ).fetchall():
        try:
            data = json.loads(row["data_json"] or "{}")
        except Exception:
            data = {}
        invoices[row["invoice_key"]] = {
            **data,
            "invoice_key": row["invoice_key"],
            "invoice_number": row["invoice_number"],
            "pdf_status": row["pdf_status"],
        }

    settings = {}
    row = db.execute(
        "SELECT data_json FROM doc_settings WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row and row["data_json"]:
        try:
            settings = json.loads(row["data_json"])
        except Exception:
            settings = {}

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "email": user["email"],
        "businesses": businesses,
        "customers": customers,
        "invoices": invoices,
        "settings": settings,
        "note": "This file is for your records. FrogsWork cannot restore it into your Cloud account.",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("frogswork-export.json", json.dumps(payload, indent=2))
    return buf.getvalue()


def cancel_stripe_subscriptions(stripe_mod, customer_id: str) -> dict:
    if not customer_id:
        return {"cancelled": 0}
    subs = stripe_mod.Subscription.list(customer=customer_id, status="all", limit=20)
    cancelled = 0
    for sub in subs.data:
        if sub.status in ("active", "trialing", "past_due"):
            try:
                stripe_mod.Subscription.cancel(sub.id)
            except Exception:
                stripe_mod.Subscription.delete(sub.id)
            cancelled += 1
    return {"cancelled": cancelled}
