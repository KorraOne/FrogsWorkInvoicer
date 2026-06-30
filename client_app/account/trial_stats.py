"""Lifetime trial limits before subscription is required."""

from decimal import Decimal

import storage
from app_config import TRIAL_MAX_EX_GST, TRIAL_MAX_INVOICES


def _invoice_ex_gst(invoice):
    raw = invoice.get("amount_ex_gst")
    if raw is not None and str(raw).strip() != "":
        return Decimal(str(raw))
    return Decimal(str(invoice.get("total_inc_gst", "0")))


def lifetime_totals():
    """Return (invoice_count, total_ex_gst) from active invoices."""
    invoices = storage.load_invoices()
    count = 0
    total = Decimal("0")
    for invoice in invoices.values():
        if storage.is_invoice_deleted(invoice):
            continue
        count += 1
        total += _invoice_ex_gst(invoice)
    return count, total


def trial_gate_reached():
    count, total = lifetime_totals()
    return count >= TRIAL_MAX_INVOICES or total >= TRIAL_MAX_EX_GST


def under_trial_limits():
    return not trial_gate_reached()


def meter_snapshot():
    count, total = lifetime_totals()
    invoices_remaining = max(0, TRIAL_MAX_INVOICES - count)
    amount_remaining = max(Decimal("0"), TRIAL_MAX_EX_GST - total)
    return {
        "lifetime_invoice_count": count,
        "lifetime_ex_gst_total": total,
        "max_invoices": TRIAL_MAX_INVOICES,
        "max_ex_gst": TRIAL_MAX_EX_GST,
        "invoices_remaining": invoices_remaining,
        "amount_remaining_ex_gst": amount_remaining,
        "trial_exhausted": trial_gate_reached(),
    }
