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
        ("doc_quotes", "DELETE FROM doc_quotes WHERE user_id = ?"),
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


def _invoice_bucket(inv: dict) -> str:
    if inv.get("deleted_at"):
        return "_deleted"
    status = str(inv.get("status") or "not_sent").lower()
    if status == "paid":
        return "paid"
    if status == "sent":
        return "sent_not_paid"
    return "not_sent"


def _quote_bucket(quote: dict) -> str:
    if quote.get("deleted_at"):
        return "_deleted"
    status = str(quote.get("status") or "not_sent").lower()
    if status == "sent":
        return "sent"
    if status == "closed":
        return "closed"
    if status == "converted":
        return "converted"
    return "not_sent"


def _safe_base(prefix: str, number, date, key: str) -> str:
    num = str(number if number is not None else "unknown")
    date_part = str(date or "nodate")[:10]
    for ch in ("/", "\\", ":", "*", "?", '"', "<", ">", "|", " "):
        num = num.replace(ch, "_")
        date_part = date_part.replace(ch, "_")
    key_suffix = "".join(c if c.isalnum() or c in "._-" else "_" for c in str(key or ""))[:12]
    return f"{prefix}_{num}_{date_part}_{key_suffix}"


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
        "SELECT invoice_key, invoice_number, data_json, pdf_status, pdf_r2_key FROM doc_invoices WHERE user_id = ?",
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
            "_pdf_r2_key": row["pdf_r2_key"] if "pdf_r2_key" in row.keys() else None,
        }

    quotes = {}
    try:
        for row in db.execute(
            "SELECT quote_key, quote_number, data_json, pdf_status, pdf_r2_key FROM doc_quotes WHERE user_id = ?",
            (user_id,),
        ).fetchall():
            try:
                data = json.loads(row["data_json"] or "{}")
            except Exception:
                data = {}
            quotes[row["quote_key"]] = {
                **data,
                "quote_key": row["quote_key"],
                "quote_number": row["quote_number"],
                "pdf_status": row["pdf_status"],
                "_pdf_r2_key": row["pdf_r2_key"] if "pdf_r2_key" in row.keys() else None,
            }
    except Exception:
        quotes = {}

    settings = {}
    row = db.execute(
        "SELECT data_json FROM doc_settings WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row and row["data_json"]:
        try:
            settings = json.loads(row["data_json"])
        except Exception:
            settings = {}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    root = f"frogswork_data_export_{stamp}"
    exported_at = datetime.now(timezone.utc).isoformat()

    readme = "\n".join(
        [
            "FrogsWork Cloud data export",
            "",
            "This archive is for your records. It cannot be re-imported into FrogsWork.",
            "",
            "account.json       — account email / export metadata",
            "businesses.json    — business profiles",
            "customers.json     — customers",
            "settings.json      — app settings",
            "invoices/          — invoices grouped by status",
            "  not_sent/        — draft / send_queued / send_failed",
            "  sent_not_paid/   — sent, awaiting payment",
            "  paid/            — paid",
            "  _deleted/        — soft-deleted invoices",
            "quotes/            — quotes / price estimates grouped by status",
            "  not_sent/        — draft / send_queued / send_failed",
            "  sent/            — sent, awaiting reply",
            "  closed/          — closed (not accepted)",
            "  converted/       — converted to an invoice (see converted_invoice_id)",
            "  _deleted/        — soft-deleted quotes",
            "",
            "Each document folder contains paired .json (and .pdf when available in Cloud export).",
        ]
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{root}/README.txt", readme)
        zf.writestr(
            f"{root}/account.json",
            json.dumps(
                {
                    "exported_at": exported_at,
                    "email": user["email"],
                    "note": "This archive is for your records. FrogsWork cannot restore it into your Cloud account.",
                },
                indent=2,
            ),
        )
        zf.writestr(f"{root}/businesses.json", json.dumps(businesses, indent=2))
        zf.writestr(f"{root}/customers.json", json.dumps(customers, indent=2))
        zf.writestr(f"{root}/settings.json", json.dumps(settings, indent=2))

        for key, inv in invoices.items():
            folder = _invoice_bucket(inv)
            base = _safe_base("Invoice", inv.get("invoice_number"), inv.get("invoice_date"), key)
            payload = {k: v for k, v in inv.items() if k != "_pdf_r2_key"}
            zf.writestr(
                f"{root}/invoices/{folder}/{base}.json",
                json.dumps(payload, indent=2),
            )

        for key, quote in quotes.items():
            folder = _quote_bucket(quote)
            base = _safe_base(
                "Quote",
                quote.get("quote_number"),
                quote.get("quote_date") or quote.get("invoice_date"),
                key,
            )
            payload = {k: v for k, v in quote.items() if k != "_pdf_r2_key"}
            zf.writestr(
                f"{root}/quotes/{folder}/{base}.json",
                json.dumps(payload, indent=2),
            )

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
