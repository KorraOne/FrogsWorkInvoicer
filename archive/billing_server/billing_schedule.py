"""Platform invoice schedule: quarters, years, per-month billed state, next due dates."""

import json
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from config import KORRAONE_BUSINESS

BILLING_QUARTERLY = "quarterly"
BILLING_ANNUAL = "annual"


def quarter_bounds(year, quarter):
    starts = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}
    sm, em = starts[quarter]
    return f"{year:04d}-{sm:02d}", f"{year:04d}-{em:02d}"


def year_bounds(year):
    return f"{year:04d}-01", f"{year:04d}-12"


def quarter_for_month(usage_month):
    year, month = map(int, usage_month.split("-"))
    return year, (month - 1) // 3 + 1


def month_range(cycle_start, cycle_end):
    months = []
    y, m = map(int, cycle_start.split("-"))
    ey, em = map(int, cycle_end.split("-"))
    while (y, m) <= (ey, em):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def month_end(usage_month):
    y, m = map(int, usage_month.split("-"))
    return date(y, m, monthrange(y, m)[1])


def parse_payment_terms_days(terms=None):
    terms = (terms or KORRAONE_BUSINESS.get("payment_terms") or "14 days").strip().lower()
    if terms.endswith(" days"):
        try:
            return int(terms.split()[0])
        except ValueError:
            pass
    return 14


def invoice_number_prefix(cycle_start, cycle_end, billing_cycle):
    year = cycle_start.split("-")[0]
    if billing_cycle == BILLING_ANNUAL:
        return f"PF-{year}-Y"
    quarter = quarter_for_month(cycle_start)[1]
    return f"PF-{year}-Q{quarter}"


def get_billed_months(conn, account_id):
    """Map usage_month -> invoice metadata for months already on a platform invoice."""
    rows = conn.execute(
        """
        SELECT id, invoice_number, line_items_json, paid_at,
               billing_cycle_start, billing_cycle_end, created_at
        FROM platform_invoices WHERE account_id = ?
        """,
        (account_id,),
    ).fetchall()
    billed = {}
    for row in rows:
        try:
            items = json.loads(row["line_items_json"])
        except (json.JSONDecodeError, TypeError):
            items = []
        for item in items:
            usage_month = item.get("usage_month")
            if not usage_month:
                continue
            billed[usage_month] = {
                "invoice_id": row["id"],
                "invoice_number": row["invoice_number"],
                "paid": row["paid_at"] is not None,
                "paid_at": row["paid_at"],
                "period_start": row["billing_cycle_start"],
                "period_end": row["billing_cycle_end"],
                "invoice_created_at": row["created_at"],
            }
    return billed


def get_unbilled_fee_months(conn, account_id, billed=None):
    """Usage months with fee > 0 not yet on any platform invoice."""
    billed = billed if billed is not None else get_billed_months(conn, account_id)
    rows = conn.execute(
        """
        SELECT usage_month, fee_accrued, total_ex_gst
        FROM monthly_summaries
        WHERE account_id = ? AND CAST(fee_accrued AS REAL) > 0
        ORDER BY usage_month
        """,
        (account_id,),
    ).fetchall()
    unbilled = []
    for row in rows:
        usage_month = row["usage_month"]
        if usage_month in billed:
            continue
        unbilled.append(
            {
                "usage_month": usage_month,
                "fee_ex_gst": Decimal(str(row["fee_accrued"])),
                "total_ex_gst": Decimal(str(row["total_ex_gst"])),
            }
        )
    return unbilled


def _period_end_date(cycle_start, cycle_end):
    return month_end(cycle_end)


def _invoice_date_for_period(period_end):
    """Operator generates on the first day after the billing period closes."""
    return period_end + timedelta(days=1)


def _payment_due(invoice_date, terms_days=None):
    days = terms_days if terms_days is not None else parse_payment_terms_days()
    return invoice_date + timedelta(days=days)


def _unbilled_in_period(unbilled_months, cycle_start, cycle_end):
    period_months = set(month_range(cycle_start, cycle_end))
    return [m for m in unbilled_months if m["usage_month"] in period_months]


def _closed_unbilled(unbilled_months, today):
    """Unbilled months whose calendar month has fully ended."""
    return [m for m in unbilled_months if month_end(m["usage_month"]) < today]


def account_billing_status(account, conn, today=None):
    """
    Billing snapshot for admin display.

    Uses per-month billed tracking from platform invoice line items so cycle
    changes only bill months not yet invoiced (no double-billing).
    """
    if not isinstance(account, dict):
        account = dict(account)
    today = today or date.today()
    account_id = account["id"]
    billing_cycle = account.get("billing_cycle") or BILLING_QUARTERLY
    terms_days = parse_payment_terms_days()

    billed = get_billed_months(conn, account_id)
    unbilled = get_unbilled_fee_months(conn, account_id, billed)
    unbilled_total = sum((m["fee_ex_gst"] for m in unbilled), Decimal("0"))

    unpaid_rows = conn.execute(
        """
        SELECT id, invoice_number, amount_due, created_at, billing_cycle_start, billing_cycle_end
        FROM platform_invoices
        WHERE account_id = ? AND paid_at IS NULL
        ORDER BY created_at
        """,
        (account_id,),
    ).fetchall()

    oldest_unpaid_due = None
    if unpaid_rows:
        for row in unpaid_rows:
            try:
                created = date.fromisoformat(str(row["created_at"])[:10])
            except ValueError:
                created = today
            due = _payment_due(created, terms_days)
            if oldest_unpaid_due is None or due < oldest_unpaid_due:
                oldest_unpaid_due = due

    closed_unbilled = _closed_unbilled(unbilled, today)
    closed_unbilled_total = sum((m["fee_ex_gst"] for m in closed_unbilled), Decimal("0"))

    if billing_cycle == BILLING_ANNUAL:
        period_label = str(today.year if today.month > 1 or unbilled else today.year - 1)
        # Current accrual period is the calendar year in progress
        accrual_year = today.year
        cycle_start, cycle_end = year_bounds(accrual_year)
        period_end = _period_end_date(cycle_start, cycle_end)
        invoice_after = _invoice_date_for_period(period_end)
        payment_due = _payment_due(invoice_after, terms_days)
        period_name = f"Year {accrual_year}"
        generate_mode = "annual"
    else:
        q = (today.month - 1) // 3 + 1
        cycle_start, cycle_end = quarter_bounds(today.year, q)
        period_end = _period_end_date(cycle_start, cycle_end)
        invoice_after = _invoice_date_for_period(period_end)
        payment_due = _payment_due(invoice_after, terms_days)
        period_name = f"Q{q} {today.year}"
        generate_mode = "quarterly"

    # If there are closed months with fees not yet invoiced, operator should bill now
    if closed_unbilled:
        status = "ready_to_bill"
        status_label = "Ready to bill"
        next_action = "Generate invoice for unbilled months"
        payment_due = _payment_due(today, terms_days)
    elif unpaid_rows:
        status = "awaiting_payment"
        status_label = "Awaiting payment"
        next_action = f"Unpaid invoice ({unpaid_rows[0]['invoice_number'] or unpaid_rows[0]['id']})"
        payment_due = oldest_unpaid_due
    elif today < invoice_after:
        status = "accruing"
        status_label = "Accruing"
        next_action = f"Invoice after {invoice_after.isoformat()}"
    else:
        status = "ready_to_bill"
        status_label = "Ready to bill"
        next_action = "Generate invoice for this period"
        payment_due = _payment_due(today, terms_days)

    outside_current = [
        m
        for m in closed_unbilled
        if m["usage_month"] not in set(month_range(cycle_start, cycle_end))
    ]

    return {
        "billing_cycle": billing_cycle,
        "generate_mode": generate_mode,
        "current_period": period_name,
        "period_start": cycle_start,
        "period_end": cycle_end,
        "period_ends_on": period_end.isoformat(),
        "invoice_after": invoice_after.isoformat(),
        "payment_due": payment_due.isoformat() if payment_due else None,
        "status": status,
        "status_label": status_label,
        "next_action": next_action,
        "unbilled_months_count": len(unbilled),
        "unbilled_fee_ex_gst": str(unbilled_total.quantize(Decimal("0.01"))),
        "closed_unbilled_count": len(closed_unbilled),
        "closed_unbilled_fee_ex_gst": str(closed_unbilled_total.quantize(Decimal("0.01"))),
        "outside_current_period_count": len(outside_current),
        "unpaid_invoice_count": len(unpaid_rows),
        "billed_months": billed,
        "unbilled_months": unbilled,
    }


def month_billing_state(usage_month, fee_accrued, billed_map):
    """Per-row status for monthly summary tables."""
    fee = Decimal(str(fee_accrued))
    if fee <= 0:
        return {"state": "no_fee", "label": "No fee"}
    info = billed_map.get(usage_month)
    if not info:
        if month_end(usage_month) < date.today():
            return {"state": "unbilled", "label": "Unbilled"}
        return {"state": "accruing", "label": "Accruing"}
    if info["paid"]:
        return {
            "state": "paid",
            "label": f"Paid ({info['paid_at']})",
            "invoice_number": info["invoice_number"],
        }
    return {
        "state": "invoiced_unpaid",
        "label": "Invoiced, unpaid",
        "invoice_number": info["invoice_number"],
    }
