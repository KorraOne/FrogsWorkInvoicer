"""Billing calculation helpers — keep FREE_TIER, FEE_RATE, compute_monthly_fee, free_remaining in sync with client_app/billing_core.py."""

from decimal import Decimal

FREE_TIER_EX_GST = Decimal("2000")
FEE_RATE = Decimal("0.0005")
GST_RATE = Decimal("0.10")


def compute_monthly_fee(total_ex_gst):
    total = Decimal(str(total_ex_gst))
    if total <= FREE_TIER_EX_GST:
        return Decimal("0.00")
    return (FEE_RATE * (total - FREE_TIER_EX_GST)).quantize(Decimal("0.01"))


def free_remaining(total_ex_gst):
    total = Decimal(str(total_ex_gst))
    return max(Decimal("0"), FREE_TIER_EX_GST - total)
