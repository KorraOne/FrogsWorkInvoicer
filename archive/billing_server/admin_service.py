"""Operator admin queries and actions."""

from datetime import date
from decimal import Decimal

from billing_schedule import (
    BILLING_ANNUAL,
    BILLING_QUARTERLY,
    account_billing_status,
    month_billing_state,
    quarter_bounds,
    year_bounds,
)
from db import get_db
from platform_billing import generate_platform_invoices, preview_platform_invoices


def _row_dict(row):
    return dict(row) if row else None


def _money(value):
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def current_month():
    return date.today().strftime("%Y-%m")


def _attach_billing_status(conn, account_row):
    row = dict(account_row)
    row["billing"] = account_billing_status(row, conn)
    return row


def dashboard_stats():
    month = current_month()
    month_prefix = month + "%"
    with get_db() as conn:
        account_count = conn.execute("SELECT COUNT(*) AS c FROM accounts").fetchone()["c"]
        signups_this_month = conn.execute(
            "SELECT COUNT(*) AS c FROM accounts WHERE created_at LIKE ?",
            (month_prefix,),
        ).fetchone()["c"]
        usage_row = conn.execute(
            """
            SELECT COALESCE(SUM(CAST(total_ex_gst AS REAL)), 0) AS total_usage,
                   COALESCE(SUM(CAST(fee_accrued AS REAL)), 0) AS total_fees
            FROM monthly_summaries WHERE usage_month = ?
            """,
            (month,),
        ).fetchone()
        unpaid_row = conn.execute(
            """
            SELECT COUNT(*) AS c,
                   COALESCE(SUM(CAST(amount_due AS REAL)), 0) AS total_due
            FROM platform_invoices WHERE paid_at IS NULL
            """
        ).fetchone()
        ready_to_bill = 0
        for account in conn.execute("SELECT * FROM accounts").fetchall():
            status = account_billing_status(account, conn)
            if status["status"] in ("ready_to_bill", "awaiting_payment"):
                ready_to_bill += 1
    return {
        "account_count": account_count,
        "signups_this_month": signups_this_month,
        "current_month": month,
        "total_usage_ex_gst": _money(usage_row["total_usage"]),
        "total_fees_ex_gst": _money(usage_row["total_fees"]),
        "unpaid_invoice_count": unpaid_row["c"],
        "unpaid_total_due": _money(unpaid_row["total_due"]),
        "ready_to_bill_count": ready_to_bill,
    }


def list_accounts(usage_month=None):
    usage_month = usage_month or current_month()
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.email, a.created_at, a.billing_cycle,
                   a.cap_enabled, a.cap_amount_ex_gst,
                   COALESCE(ms.total_ex_gst, '0') AS month_total_ex_gst,
                   COALESCE(ms.fee_accrued, '0') AS month_fee_accrued,
                   (
                       SELECT MAX(committed_at) FROM usage_events ue
                       WHERE ue.account_id = a.id
                   ) AS last_commit_at
            FROM accounts a
            LEFT JOIN monthly_summaries ms
                ON ms.account_id = a.id AND ms.usage_month = ?
            ORDER BY a.email
            """,
            (usage_month,),
        ).fetchall()
        return [_attach_billing_status(conn, r) for r in rows]


def get_account(account_id):
    with get_db() as conn:
        account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not account:
            return None
        account = dict(account)
        billing = account_billing_status(account, conn)
        events = conn.execute(
            """
            SELECT invoice_number, amount_ex_gst, usage_month, cap_overridden, committed_at
            FROM usage_events WHERE account_id = ? ORDER BY committed_at DESC
            """,
            (account_id,),
        ).fetchall()
        summaries = conn.execute(
            """
            SELECT usage_month, total_ex_gst, fee_accrued
            FROM monthly_summaries WHERE account_id = ? ORDER BY usage_month DESC
            """,
            (account_id,),
        ).fetchall()
        summary_rows = []
        for s in summaries:
            row = dict(s)
            row["billing_state"] = month_billing_state(
                row["usage_month"], row["fee_accrued"], billing["billed_months"]
            )
            summary_rows.append(row)
        invoices = conn.execute(
            """
            SELECT id, invoice_number, billing_cycle_start, billing_cycle_end,
                   subtotal_ex_gst, gst_amount, amount_due, created_at, paid_at, pdf_filename
            FROM platform_invoices WHERE account_id = ? ORDER BY created_at DESC
            """,
            (account_id,),
        ).fetchall()
    return {
        "account": account,
        "billing": billing,
        "usage_events": [dict(e) for e in events],
        "monthly_summaries": summary_rows,
        "platform_invoices": [dict(i) for i in invoices],
    }


def list_usage_for_month(usage_month):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT a.email, ms.usage_month, ms.total_ex_gst, ms.fee_accrued
            FROM monthly_summaries ms
            JOIN accounts a ON a.id = ms.account_id
            WHERE ms.usage_month = ?
            ORDER BY CAST(ms.total_ex_gst AS REAL) DESC
            """,
            (usage_month,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_platform_invoices(paid_filter=None):
    query = """
        SELECT pi.id, pi.invoice_number, pi.billing_cycle_start, pi.billing_cycle_end,
               pi.subtotal_ex_gst, pi.gst_amount, pi.amount_due, pi.created_at, pi.paid_at,
               pi.pdf_filename, a.email, a.billing_cycle
        FROM platform_invoices pi
        JOIN accounts a ON a.id = pi.account_id
    """
    params = []
    if paid_filter == "paid":
        query += " WHERE pi.paid_at IS NOT NULL"
    elif paid_filter == "unpaid":
        query += " WHERE pi.paid_at IS NULL"
    query += " ORDER BY pi.created_at DESC, pi.id DESC"
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_platform_invoice(invoice_id):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT pi.*, a.email
            FROM platform_invoices pi
            JOIN accounts a ON a.id = pi.account_id
            WHERE pi.id = ?
            """,
            (invoice_id,),
        ).fetchone()
    return _row_dict(row)


def mark_invoice_paid(invoice_id):
    today = date.today().isoformat()
    with get_db() as conn:
        row = conn.execute("SELECT id FROM platform_invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE platform_invoices SET paid_at = ? WHERE id = ?",
            (today, invoice_id),
        )
    return True


def preview_generation(year, quarter=None, billing_mode=BILLING_QUARTERLY):
    if billing_mode == BILLING_ANNUAL:
        cycle_start, cycle_end = year_bounds(year)
        label = f"Year {year}"
    else:
        cycle_start, cycle_end = quarter_bounds(year, quarter)
        label = f"Q{quarter} {year}"
    return {
        "year": year,
        "quarter": quarter,
        "billing_mode": billing_mode,
        "cycle_start": cycle_start,
        "cycle_end": cycle_end,
        "period_label": label,
        "rows": preview_platform_invoices(cycle_start, cycle_end, billing_mode=billing_mode),
    }


def run_generation(year, quarter=None, billing_mode=BILLING_QUARTERLY, regenerate=False):
    if billing_mode == BILLING_ANNUAL:
        cycle_start, cycle_end = year_bounds(year)
    else:
        cycle_start, cycle_end = quarter_bounds(year, quarter)
    return generate_platform_invoices(
        cycle_start=cycle_start,
        cycle_end=cycle_end,
        billing_mode=billing_mode,
        regenerate=regenerate,
    )
