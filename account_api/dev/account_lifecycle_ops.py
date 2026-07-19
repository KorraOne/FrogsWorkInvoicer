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


def parse_au_financial_year(fy_raw: str | None = None):
    from datetime import date

    raw = (fy_raw or "").strip()
    if not raw:
        today = date.today()
        start_year = today.year if today.month >= 7 else today.year - 1
        raw = f"{start_year}-{(start_year + 1) % 100:02d}"
    m = __import__("re").match(r"^(\d{4})[-/](\d{2})$", raw)
    if not m:
        return None
    start_year = int(m.group(1))
    end_yy = int(m.group(2))
    if end_yy != (start_year + 1) % 100:
        return None
    end_year = start_year + 1
    return {
        "token": f"{start_year}-{end_yy:02d}",
        "start": f"{start_year}-07-01",
        "end": f"{end_year}-06-30",
        "display": f"{start_year}–{str(end_year)[2:]}",
        "file_slug": f"FY{str(start_year)[2:]}_{str(end_year)[2:]}",
    }


def _iso_in_range(iso, start: str, end: str) -> bool:
    d = str(iso or "")[:10]
    if len(d) != 10:
        return False
    return start <= d <= end


def _pad_invoice_num(n) -> str:
    try:
        return f"{max(0, int(n)):08d}"
    except Exception:
        return "00000000"


def _format_au_date(iso) -> str:
    d = str(iso or "")[:10]
    if len(d) != 10:
        return ""
    return f"{d[8:10]}/{d[5:7]}/{d[0:4]}"


def _include_tax_invoice(inv: dict, fy: dict, business_filter: str) -> bool:
    if inv.get("deleted_at"):
        return False
    if business_filter and str(inv.get("business_name") or "") != business_filter:
        return False
    status = str(inv.get("status") or "not_sent")
    if status == "paid":
        if inv.get("paid_date") and _iso_in_range(inv.get("paid_date"), fy["start"], fy["end"]):
            return True
        if not inv.get("paid_date") and _iso_in_range(inv.get("invoice_date"), fy["start"], fy["end"]):
            return True
        return False
    if status in ("not_sent", "send_queued", "send_failed", "sent"):
        return _iso_in_range(inv.get("invoice_date"), fy["start"], fy["end"])
    return False


def build_tax_export_zip(db, user, fy_raw: str | None = None, business: str | None = None) -> bytes:
    fy = parse_au_financial_year(fy_raw)
    if not fy:
        raise ValueError("Invalid financial year")
    business_filter = (business or "").strip()
    user_id = user["id"]

    businesses = {}
    for row in db.execute(
        "SELECT name, data_json FROM doc_businesses WHERE user_id = ?", (user_id,)
    ).fetchall():
        try:
            businesses[row["name"]] = json.loads(row["data_json"] or "{}")
        except Exception:
            businesses[row["name"]] = {}
    if business_filter and business_filter not in businesses:
        raise ValueError("Business not found")

    invoices = {}
    for row in db.execute(
        "SELECT invoice_key, invoice_number, data_json FROM doc_invoices WHERE user_id = ?",
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
        }

    rows = [
        (key, inv)
        for key, inv in invoices.items()
        if _include_tax_invoice(inv, fy, business_filter)
    ]
    rows.sort(
        key=lambda item: (
            str(item[1].get("invoice_date") or ""),
            int(item[1].get("invoice_number") or 0),
        )
    )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    root = f"frogswork_tax_export_{fy['file_slug']}_{stamp}"
    ledger_name = f"income_ledger_{fy['file_slug']}.csv"

    def esc(v):
        s = str(v if v is not None else "")
        if any(c in s for c in '",\n\r'):
            return '"' + s.replace('"', '""') + '"'
        return s

    header = [
        "Invoice Date",
        "Invoice Number",
        "Business Name",
        "Customer Name",
        "Customer ABN",
        "Gross Amount (Inc. GST)",
        "GST Amount",
        "Net Amount (Ex. GST)",
        "Status",
        "Date Paid",
    ]
    csv_lines = [",".join(esc(h) for h in header)]
    total_ex = total_gst = total_inc = 0.0
    paid_count = unpaid_count = 0
    for _key, inv in rows:
        status = "Paid" if str(inv.get("status") or "") == "paid" else "Unpaid"
        if status == "Paid":
            paid_count += 1
        else:
            unpaid_count += 1
        ex = float(inv.get("amount_ex_gst") or 0) or 0.0
        gst = float(inv.get("gst_amount") or 0) or 0.0
        inc = float(inv.get("total_inc_gst") or 0) or 0.0
        total_ex += ex
        total_gst += gst
        total_inc += inc
        csv_lines.append(
            ",".join(
                esc(x)
                for x in [
                    _format_au_date(inv.get("invoice_date")),
                    _pad_invoice_num(inv.get("invoice_number")),
                    inv.get("business_name") or "",
                    inv.get("customer_name") or "",
                    inv.get("customer_abn") or "",
                    f"{inc:.2f}",
                    f"{gst:.2f}",
                    f"{ex:.2f}",
                    status,
                    _format_au_date(inv.get("paid_date")),
                ]
            )
        )

    biz_names = (
        [business_filter]
        if business_filter
        else sorted(
            {
                str(inv.get("business_name") or "").strip()
                for _k, inv in rows
                if str(inv.get("business_name") or "").strip()
            }
            or businesses.keys()
        )
    )
    biz_lines = []
    for name in biz_names:
        b = businesses.get(name) or {}
        abn = str(b.get("business_abn") or b.get("abn") or "").strip()
        biz_lines.append(f"{name} (ABN {abn})" if abn else (name or "(unnamed business)"))

    readme = "\n".join(
        [
            "FrogsWork tax-time export",
            "",
            f"Business: {'; '.join(biz_lines) or '(none)'}",
            f"Financial year: {fy['display']} ({_format_au_date(fy['start'])} to {_format_au_date(fy['end'])})",
            f"Generated: {stamp}",
            "",
            "Generated via FrogsWork Invoicing. This package contains a complete income ledger.",
            "(Local/dev export may omit PDFs; production Cloud export includes invoice_pdfs/.)",
        ]
    )
    summary = "\n".join(
        [
            "FrogsWork tax-time summary",
            "",
            f"Financial year: {fy['display']}",
            f"Invoice rows: {len(rows)} ({paid_count} paid, {unpaid_count} unpaid)",
            f"Total Revenue (Ex. GST): ${total_ex:.2f}",
            f"Total GST Collected: ${total_gst:.2f}",
            f"Total Gross Revenue: ${total_inc:.2f}",
        ]
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{root}/README.txt", readme)
        zf.writestr(f"{root}/summary.txt", summary)
        zf.writestr(f"{root}/{ledger_name}", "\r\n".join(csv_lines) + "\r\n")
        zf.writestr(f"{root}/invoice_pdfs/.keep", "")
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
