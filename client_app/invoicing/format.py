import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

import storage


def format_money(amount):
    return f"${amount:,.2f}"


def format_invoice_number(number):
    return f"{int(number):08d}"


def parse_invoice_number_input(raw):
    digits = re.sub(r"\D", "", str(raw or "").strip())
    if not digits:
        raise ValueError("Enter an invoice number.")
    number = int(digits)
    if number < 1:
        raise ValueError("Invoice number must be at least 1.")
    return number


def _invoice_business_name(inv):
    from storage.businesses import get_default_business_name, invoice_business_name

    return invoice_business_name(inv) or get_default_business_name()


def suggested_invoice_number(business_name=None, business_profile=None):
    from storage.businesses import resolve_business

    if business_profile is None:
        business_name, business_profile = resolve_business(business_name)
    counter = int((business_profile or {}).get("invoice_counter", 1))
    invoices = storage.load_invoices()
    matching = [
        int(inv.get("invoice_number", 0))
        for inv in invoices.values()
        if _invoice_business_name(inv) == business_name
    ]
    if not matching:
        return counter
    return max(counter, max(matching) + 1)


def persist_invoice_counter(business_name, used_number):
    from storage.businesses import load_businesses, save_businesses

    businesses = load_businesses()
    if business_name not in businesses:
        return
    profile = businesses[business_name]
    profile["invoice_counter"] = max(
        int(profile.get("invoice_counter", 1)),
        int(used_number) + 1,
    )
    save_businesses(businesses)


def format_abn(abn):
    digits = re.sub(r"\D", "", str(abn))
    if len(digits) == 11:
        return f"{digits[0:2]} {digits[2:5]} {digits[5:8]} {digits[8:11]}"
    return abn


def format_account(acc):
    digits = re.sub(r"\D", "", str(acc))
    if len(digits) == 6:
        return f"{digits[0:3]} {digits[3:6]}"
    return acc


def parse_amount(raw):
    cleaned = raw.strip().replace("$", "").replace(",", "")
    if not cleaned:
        raise ValueError("Enter an amount.")
    value = Decimal(cleaned)
    if value < 0:
        raise ValueError("Amount cannot be negative.")
    return value


def compute_gst(amount_ex_gst):
    gst = (amount_ex_gst * Decimal("0.10")).quantize(Decimal("0.01"))
    total = amount_ex_gst + gst
    return gst, total


def parse_quantity(raw):
    cleaned = raw.strip()
    if not cleaned:
        return Decimal("1")
    value = Decimal(cleaned)
    if value <= 0:
        raise ValueError("Quantity must be more than zero.")
    return value


def format_qty(qty):
    q = Decimal(qty)
    if q == q.to_integral_value():
        return str(int(q))
    return format(q, "f").rstrip("0").rstrip(".")


def format_invoice_date(iso_date):
    try:
        parts = iso_date.split("-")
        d = date(int(parts[0]), int(parts[1]), int(parts[2]))
        return d.strftime("%d %B %Y")
    except (ValueError, IndexError):
        return iso_date


def parse_iso_datetime(iso):
    if not iso:
        return None
    try:
        if iso.endswith("Z"):
            iso = iso[:-1] + "+00:00"
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def format_iso_datetime(iso):
    dt = parse_iso_datetime(iso)
    if not dt:
        return (iso or "")[:16]
    return dt.astimezone().strftime("%d %B %Y, %H:%M")


def format_iso_date(iso):
    dt = parse_iso_datetime(iso)
    if not dt:
        return (iso or "")[:10]
    return dt.astimezone().strftime("%d %B %Y")
