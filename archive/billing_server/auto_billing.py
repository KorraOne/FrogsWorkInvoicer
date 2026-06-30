"""Automatic platform invoice generation and email delivery."""

import logging
from datetime import date

from billing_schedule import (
    BILLING_ANNUAL,
    BILLING_QUARTERLY,
    _closed_unbilled,
    _invoice_date_for_period,
    get_unbilled_fee_months,
    month_end,
    quarter_bounds,
    quarter_for_month,
    year_bounds,
)
from config import PLATFORM_INVOICE_DIR
from db import get_db
from email_service import mark_invoice_emailed, send_platform_invoice_email
from platform_billing import generate_for_account_period

logger = logging.getLogger(__name__)


def _periods_from_unbilled(unbilled_months, billing_cycle):
    periods = {}
    for entry in unbilled_months:
        usage_month = entry["usage_month"]
        if billing_cycle == BILLING_ANNUAL:
            year = int(usage_month.split("-")[0])
            start, end = year_bounds(year)
            periods[(start, end, BILLING_ANNUAL)] = True
        else:
            year, quarter = quarter_for_month(usage_month)
            start, end = quarter_bounds(year, quarter)
            periods[(start, end, BILLING_QUARTERLY)] = True
    return sorted(periods.keys())


def due_periods_for_account(account, conn, today=None, *, immediate=False):
    """Periods that should be invoiced today (or immediately when immediate=True)."""
    today = today or date.today()
    account = dict(account)
    billing_cycle = account.get("billing_cycle") or BILLING_QUARTERLY
    unbilled = get_unbilled_fee_months(conn, account["id"])
    closed = _closed_unbilled(unbilled, today)
    if not closed:
        return []

    due = []
    for start, end, mode in _periods_from_unbilled(closed, billing_cycle):
        if mode != billing_cycle:
            continue
        period_end = month_end(end)
        invoice_after = _invoice_date_for_period(period_end)
        if immediate or today >= invoice_after:
            due.append((start, end, mode))
    return due


def _email_invoice(conn, account_email, invoice_result):
    row = conn.execute(
        "SELECT * FROM platform_invoices WHERE id = ?",
        (invoice_result["invoice_id"],),
    ).fetchone()
    if not row:
        return False
    if row["emailed_at"]:
        return True
    sent = send_platform_invoice_email(
        account_email,
        dict(row),
        invoice_result["pdf"],
    )
    if sent:
        mark_invoice_emailed(conn, invoice_result["invoice_id"])
    return sent


def bill_periods_for_account(account_id, periods, *, send_email=True):
    created = []
    with get_db() as conn:
        account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not account:
            return created
        account = dict(account)
        for start, end, mode in periods:
            results = generate_for_account_period(account["id"], start, end, mode)
            for result in results:
                created.append(result)
                if send_email:
                    _email_invoice(conn, account["email"], result)
    return created


def bill_quarterly_backlog_for_account(account_id, *, send_email=True):
    """Bill all closed quarters with unbilled fees (annual → quarterly switch)."""
    today = date.today()
    with get_db() as conn:
        account = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if not account:
            return []
        unbilled = get_unbilled_fee_months(conn, account_id)
        closed = _closed_unbilled(unbilled, today)
        periods = {}
        for entry in closed:
            year, quarter = quarter_for_month(entry["usage_month"])
            start, end = quarter_bounds(year, quarter)
            periods[(start, end, BILLING_QUARTERLY)] = True
        period_list = sorted(periods.keys())
    return bill_periods_for_account(account_id, period_list, send_email=send_email)


def run_auto_billing(*, send_email=True):
    """Generate and email platform invoices due today for all accounts."""
    today = date.today()
    summary = {"generated": 0, "emailed": 0, "accounts": 0}
    with get_db() as conn:
        accounts = conn.execute("SELECT * FROM accounts").fetchall()
        for account in accounts:
            periods = due_periods_for_account(account, conn, today)
            if not periods:
                continue
            summary["accounts"] += 1
            created = bill_periods_for_account(account["id"], periods, send_email=send_email)
            summary["generated"] += len(created)
            if send_email:
                for item in created:
                    row = conn.execute(
                        "SELECT emailed_at FROM platform_invoices WHERE id = ?",
                        (item["invoice_id"],),
                    ).fetchone()
                    if row and row["emailed_at"]:
                        summary["emailed"] += 1
    logger.info(
        "Auto billing complete: %s invoice(s), %s emailed, %s account(s)",
        summary["generated"],
        summary["emailed"],
        summary["accounts"],
    )
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_auto_billing()
    print(result)
