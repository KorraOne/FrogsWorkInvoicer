"""Generate quarterly/annual platform fee invoices."""

import json
import os
from calendar import month_name
from datetime import date
from decimal import Decimal

import billing_core
from billing_schedule import (
    BILLING_ANNUAL,
    BILLING_QUARTERLY,
    get_billed_months,
    get_unbilled_fee_months,
    invoice_number_prefix,
    month_range,
    quarter_bounds,
    year_bounds,
)
from config import PLATFORM_INVOICE_DIR
from db import get_db
from pdf_layout import generate_platform_invoice_pdf


def _label_month(usage_month):
    y, m = usage_month.split("-")
    return f"{month_name[int(m)]} {y}"


def _next_invoice_sequence(conn, prefix):
    row = conn.execute(
        """
        SELECT COUNT(*) AS cnt FROM platform_invoices
        WHERE invoice_number LIKE ?
        """,
        (f"{prefix}-%",),
    ).fetchone()
    return int(row["cnt"]) + 1


def _build_line_items(unbilled_in_period, conn, account_id):
    """Line items for unbilled months only (fee > 0 already filtered)."""
    line_items = []
    subtotal = Decimal("0")
    for entry in unbilled_in_period:
        usage_month = entry["usage_month"]
        row = conn.execute(
            """
            SELECT total_ex_gst, fee_accrued FROM monthly_summaries
            WHERE account_id = ? AND usage_month = ?
            """,
            (account_id, usage_month),
        ).fetchone()
        total_ex = Decimal(row["total_ex_gst"]) if row else entry.get("total_ex_gst", Decimal("0"))
        fee = Decimal(row["fee_accrued"]) if row else entry["fee_ex_gst"]
        line_items.append(
            {
                "usage_month": usage_month,
                "label": _label_month(usage_month),
                "invoiced_ex_gst": str(total_ex),
                "fee_ex_gst": str(fee),
            }
        )
        subtotal += fee
    return line_items, subtotal


def _accounts_for_mode(conn, billing_mode, account_id=None):
    if account_id is not None:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return [row] if row else []
    if billing_mode == BILLING_ANNUAL:
        return conn.execute(
            "SELECT * FROM accounts WHERE billing_cycle = ? ORDER BY email",
            (BILLING_ANNUAL,),
        ).fetchall()
    return conn.execute(
        """
        SELECT * FROM accounts
        WHERE COALESCE(billing_cycle, 'quarterly') != ?
        ORDER BY email
        """,
        (BILLING_ANNUAL,),
    ).fetchall()


def _preview_row(conn, account, cycle_start, cycle_end, billing_mode):
    billed = get_billed_months(conn, account["id"])
    unbilled = get_unbilled_fee_months(conn, account["id"], billed)
    period_months = set(month_range(cycle_start, cycle_end))
    unbilled_in_period = [m for m in unbilled if m["usage_month"] in period_months]
    if not unbilled_in_period:
        return None

    line_items, subtotal = _build_line_items(unbilled_in_period, conn, account["id"])
    if subtotal <= 0:
        return None

    gst = (subtotal * billing_core.GST_RATE).quantize(Decimal("0.01"))
    total_due = subtotal + gst
    actual_start = unbilled_in_period[0]["usage_month"]
    actual_end = unbilled_in_period[-1]["usage_month"]
    months_label = ", ".join(m["usage_month"] for m in unbilled_in_period)

    existing = conn.execute(
        """
        SELECT id, invoice_number FROM platform_invoices
        WHERE account_id = ? AND billing_cycle_start = ? AND billing_cycle_end = ?
        """,
        (account["id"], actual_start, actual_end),
    ).fetchone()

    return {
        "account_id": account["id"],
        "email": account["email"],
        "billing_cycle": account["billing_cycle"],
        "subtotal_ex_gst": str(subtotal),
        "gst_amount": str(gst),
        "amount_due": str(total_due),
        "months_label": months_label,
        "month_count": len(unbilled_in_period),
        "cycle_start": actual_start,
        "cycle_end": actual_end,
        "already_billed": existing is not None,
        "existing_invoice_id": existing["id"] if existing else None,
        "existing_invoice_number": existing["invoice_number"] if existing else None,
        "billing_mode": billing_mode,
    }


def preview_platform_invoices(cycle_start, cycle_end, billing_mode=BILLING_QUARTERLY, account_id=None):
    """Return per-account preview rows for a billing period."""
    rows = []
    with get_db() as conn:
        for account in _accounts_for_mode(conn, billing_mode, account_id):
            account = dict(account)
            if billing_mode == BILLING_ANNUAL and account.get("billing_cycle") != BILLING_ANNUAL:
                continue
            if billing_mode == BILLING_QUARTERLY and account.get("billing_cycle") == BILLING_ANNUAL:
                continue
            row = _preview_row(conn, account, cycle_start, cycle_end, billing_mode)
            if row:
                rows.append(row)
    return rows


def _generate_from_preview(conn, account, preview, billing_mode, output_dir, regenerate):
    if preview["already_billed"] and not regenerate:
        return None

    actual_start = preview["cycle_start"]
    actual_end = preview["cycle_end"]
    billed = get_billed_months(conn, account["id"])
    unbilled = get_unbilled_fee_months(conn, account["id"], billed)
    period_months = set(month_range(actual_start, actual_end))
    unbilled_in_period = [m for m in unbilled if m["usage_month"] in period_months]
    line_items, subtotal = _build_line_items(unbilled_in_period, conn, account["id"])
    gst = (subtotal * billing_core.GST_RATE).quantize(Decimal("0.01"))
    total_due = subtotal + gst

    prefix = invoice_number_prefix(actual_start, actual_end, billing_mode)
    seq = _next_invoice_sequence(conn, prefix)
    invoice_number = f"{prefix}-{seq:05d}"
    pdf_name = (
        f"PlatformInvoice_{account['email'].replace('@', '_at_')}_{actual_start}_{actual_end}.pdf"
    )
    pdf_path = os.path.join(output_dir, pdf_name)

    if preview["already_billed"] and regenerate:
        conn.execute(
            "DELETE FROM platform_invoices WHERE id = ?",
            (preview["existing_invoice_id"],),
        )
        if os.path.isfile(pdf_path):
            os.remove(pdf_path)

    generate_platform_invoice_pdf(
        pdf_path,
        invoice_number=invoice_number,
        bill_to_email=account["email"],
        cycle_start=actual_start,
        cycle_end=actual_end,
        line_items=line_items,
        subtotal=subtotal,
        gst=gst,
        total_due=total_due,
    )
    cursor = conn.execute(
        """
        INSERT INTO platform_invoices (
            account_id, billing_cycle_start, billing_cycle_end, line_items_json,
            subtotal_ex_gst, gst_amount, amount_due, pdf_filename, invoice_number, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account["id"],
            actual_start,
            actual_end,
            json.dumps(line_items),
            str(subtotal),
            str(gst),
            str(total_due),
            pdf_name,
            invoice_number,
            date.today().isoformat(),
        ),
    )
    return {
        "account_id": account["id"],
        "email": account["email"],
        "invoice_id": cursor.lastrowid,
        "pdf": pdf_path,
        "pdf_filename": pdf_name,
        "total": str(total_due),
        "invoice_number": invoice_number,
        "months": preview["months_label"],
        "amount_due": str(total_due),
        "created_at": date.today().isoformat(),
    }


def generate_platform_invoices(
    output_dir=None,
    cycle_start=None,
    cycle_end=None,
    *,
    billing_mode=BILLING_QUARTERLY,
    regenerate=False,
    account_id=None,
):
    """Create platform invoices for accounts matching billing_mode with unbilled fees in period."""
    output_dir = output_dir or PLATFORM_INVOICE_DIR
    os.makedirs(output_dir, exist_ok=True)
    created = []
    with get_db() as conn:
        for account in _accounts_for_mode(conn, billing_mode, account_id):
            account = dict(account)
            if billing_mode == BILLING_ANNUAL and account.get("billing_cycle") != BILLING_ANNUAL:
                continue
            if billing_mode == BILLING_QUARTERLY and account.get("billing_cycle") == BILLING_ANNUAL:
                continue
            preview = _preview_row(conn, account, cycle_start, cycle_end, billing_mode)
            if not preview:
                continue
            result = _generate_from_preview(
                conn, account, preview, billing_mode, output_dir, regenerate
            )
            if result:
                created.append(result)
    return created


def generate_for_account_period(account_id, cycle_start, cycle_end, billing_mode, regenerate=False):
    """Generate a single platform invoice for one account and period window."""
    return generate_platform_invoices(
        cycle_start=cycle_start,
        cycle_end=cycle_end,
        billing_mode=billing_mode,
        regenerate=regenerate,
        account_id=account_id,
    )
