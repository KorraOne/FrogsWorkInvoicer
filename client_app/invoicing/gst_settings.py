"""GST registration rules for Australian invoices."""

from decimal import Decimal

ATO_GST_REGISTER_URL = (
    "https://www.ato.gov.au/businesses-and-organisations/"
    "gst-excise-and-indirect-taxes/gst/registering-for-gst"
)


def is_gst_registered(settings):
    return bool((settings or {}).get("gst_registered"))


def parse_gst_registered_form(value):
    return str(value or "").strip().lower() in ("yes", "true", "1", "on")


def apply_gst_registered_to_settings(settings, form):
    settings["gst_registered"] = parse_gst_registered_form(form.get("gst_registered"))


def validate_business_gst_settings(settings):
    if is_gst_registered(settings) and not (settings.get("business_abn") or "").strip():
        return "ABN required when registered for GST."
    return None


def invoice_uses_tax_invoice(invoice_data, settings=None):
    if invoice_data.get("gst_registered") is not None:
        return bool(invoice_data.get("gst_registered"))
    if settings is not None:
        return is_gst_registered(settings)
    try:
        return Decimal(str(invoice_data.get("gst_amount", "0"))) > 0
    except Exception:
        return False


def apply_registration_to_parsed_items(items, subtotal, gst_registered):
    """Return totals with GST stripped when the business is not GST-registered."""
    if gst_registered:
        taxable_ex_gst = sum(item["amount_ex_gst"] for item in items if item["gst_applicable"])
        gst_free_ex_gst = sum(item["amount_ex_gst"] for item in items if not item["gst_applicable"])
        gst_amount = (taxable_ex_gst * Decimal("0.10")).quantize(Decimal("0.01"))
        total_inc_gst = taxable_ex_gst + gst_free_ex_gst + gst_amount
        return items, subtotal, gst_amount, total_inc_gst, taxable_ex_gst, gst_free_ex_gst

    for item in items:
        item["gst_applicable"] = False
    return items, subtotal, Decimal("0"), subtotal, Decimal("0"), subtotal
