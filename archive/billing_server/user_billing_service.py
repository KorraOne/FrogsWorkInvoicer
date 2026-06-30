"""User-facing platform billing overview and cycle changes."""

from datetime import date

from auth_service import get_account
from billing_schedule import (
    BILLING_ANNUAL,
    BILLING_QUARTERLY,
    _payment_due,
    account_billing_status,
    month_billing_state,
    parse_payment_terms_days,
)
from db import get_db


def _user_status_label(status):
    labels = {
        "accruing": "Fees accruing this period",
        "awaiting_payment": "Payment due",
        "ready_to_bill": "Invoice pending",
    }
    return labels.get(status, status.replace("_", " ").title())


def _serialize_invoice(row, terms_days):
    row = dict(row)
    try:
        created = date.fromisoformat(str(row["created_at"])[:10])
    except ValueError:
        created = date.today()
    payment_due = _payment_due(created, terms_days)
    return {
        "id": row["id"],
        "invoice_number": row.get("invoice_number"),
        "billing_cycle_start": row["billing_cycle_start"],
        "billing_cycle_end": row["billing_cycle_end"],
        "subtotal_ex_gst": row["subtotal_ex_gst"],
        "gst_amount": row["gst_amount"],
        "amount_due": row["amount_due"],
        "created_at": row["created_at"],
        "paid_at": row.get("paid_at"),
        "emailed_at": row.get("emailed_at"),
        "payment_due": payment_due.isoformat(),
    }


def get_user_billing_overview(account_id):
    account = get_account(account_id)
    terms_days = parse_payment_terms_days()
    with get_db() as conn:
        status = account_billing_status(account, conn)
        summaries = conn.execute(
            """
            SELECT usage_month, total_ex_gst, fee_accrued
            FROM monthly_summaries
            WHERE account_id = ?
            ORDER BY usage_month DESC
            """,
            (account_id,),
        ).fetchall()
        history = []
        for row in summaries:
            row_dict = dict(row)
            billing_state = month_billing_state(
                row_dict["usage_month"],
                row_dict["fee_accrued"],
                status["billed_months"],
            )
            history.append(
                {
                    "usage_month": row_dict["usage_month"],
                    "total_ex_gst": row_dict["total_ex_gst"],
                    "fee_accrued": row_dict["fee_accrued"],
                    "billing_state": billing_state["state"],
                    "billing_label": billing_state["label"],
                    "invoice_number": billing_state.get("invoice_number"),
                }
            )
        invoices = conn.execute(
            """
            SELECT id, invoice_number, billing_cycle_start, billing_cycle_end,
                   subtotal_ex_gst, gst_amount, amount_due, created_at, paid_at, emailed_at
            FROM platform_invoices
            WHERE account_id = ?
            ORDER BY created_at DESC
            """,
            (account_id,),
        ).fetchall()

    return {
        "billing_cycle": status["billing_cycle"],
        "current_period": status["current_period"],
        "period_ends_on": status["period_ends_on"],
        "next_invoice_date": status["invoice_after"],
        "next_payment_due": status["payment_due"],
        "status": status["status"],
        "status_label": _user_status_label(status["status"]),
        "unbilled_fee_ex_gst": status["unbilled_fee_ex_gst"],
        "unbilled_months_count": status["unbilled_months_count"],
        "monthly_history": history,
        "platform_invoices": [_serialize_invoice(row, terms_days) for row in invoices],
    }


def update_billing_cycle(account_id, new_cycle):
    if new_cycle not in (BILLING_QUARTERLY, BILLING_ANNUAL):
        raise ValueError("billing_cycle must be quarterly or annual.")

    account = get_account(account_id)
    old_cycle = account.get("billing_cycle") or BILLING_QUARTERLY
    if old_cycle == new_cycle:
        return get_user_billing_overview(account_id)

    with get_db() as conn:
        conn.execute(
            "UPDATE accounts SET billing_cycle = ? WHERE id = ?",
            (new_cycle, account_id),
        )

    backlog_invoices = []
    if old_cycle == BILLING_ANNUAL and new_cycle == BILLING_QUARTERLY:
        from auto_billing import bill_quarterly_backlog_for_account

        backlog_invoices = bill_quarterly_backlog_for_account(account_id, send_email=True)

    overview = get_user_billing_overview(account_id)
    overview["backlog_invoices_sent"] = len(backlog_invoices)
    return overview
