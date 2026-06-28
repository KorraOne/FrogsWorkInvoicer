"""Shared billing calculation constants and helpers."""

from datetime import date
from decimal import Decimal

FREE_TIER_EX_GST = Decimal("2000")
FEE_RATE = Decimal("0.0005")
GST_RATE = Decimal("0.10")


def current_usage_month():
    return date.today().strftime("%Y-%m")


def compute_monthly_fee(total_ex_gst):
    total = Decimal(str(total_ex_gst))
    if total <= FREE_TIER_EX_GST:
        return Decimal("0.00")
    return (FEE_RATE * (total - FREE_TIER_EX_GST)).quantize(Decimal("0.01"))


def max_fee_at_cap(cap_ex_gst):
    cap = Decimal(str(cap_ex_gst))
    return compute_monthly_fee(cap)


def invoice_cap_from_max_fee(max_fee):
    fee = Decimal(str(max_fee))
    if fee <= 0:
        return FREE_TIER_EX_GST
    cap = FREE_TIER_EX_GST + (fee / FEE_RATE)
    return cap.quantize(Decimal("0.01"))


def free_remaining(total_ex_gst):
    total = Decimal(str(total_ex_gst))
    remaining = FREE_TIER_EX_GST - total
    return max(Decimal("0"), remaining)


def cap_room(cap_ex_gst, total_ex_gst):
    cap = Decimal(str(cap_ex_gst))
    total = Decimal(str(total_ex_gst))
    return max(Decimal("0"), cap - total)
