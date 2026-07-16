from datetime import date
from decimal import Decimal, InvalidOperation

import storage
from .due_dates import (
    due_rule_from_form_data,
    invoice_due_summary,
    sent_invoice_sort_key,
)
from .gst_settings import (
    apply_registration_to_parsed_items,
    is_gst_registered,
)
from .format import (
    parse_amount,
    parse_quantity,
)


def _is_gst_free_flag(raw):
    return str(raw).strip().lower() in ("1", "on", "true", "yes")


def parse_line_items(descriptions, amounts, quantities=None, gst_free_flags=None, gst_registered=True):
    """Parse parallel description/amount/qty lists into validated line items."""
    if quantities is None:
        quantities = []
    if gst_free_flags is None:
        gst_free_flags = []
    items = []
    row_num = 0
    for i, (desc_raw, amt_raw) in enumerate(zip(descriptions, amounts)):
        desc = desc_raw.strip()
        amt = amt_raw.strip()
        qty_raw = quantities[i] if i < len(quantities) else ""
        gst_flag = gst_free_flags[i] if i < len(gst_free_flags) else ""
        if not desc and not amt and not qty_raw.strip():
            continue
        row_num += 1
        if not desc:
            raise ValueError(f"Item {row_num}: add a description.")
        try:
            unit_amount_ex_gst = parse_amount(amt)
        except (ValueError, InvalidOperation):
            raise ValueError(
                f"Item {row_num}: enter a valid amount (e.g. 4500.00)."
            )
        try:
            qty = parse_quantity(qty_raw)
        except (ValueError, InvalidOperation):
            raise ValueError(f"Item {row_num}: enter a valid quantity (e.g. 1).")
        line_total = (qty * unit_amount_ex_gst).quantize(Decimal("0.01"))
        gst_applicable = not _is_gst_free_flag(gst_flag)
        items.append(
            {
                "description": desc,
                "quantity": qty,
                "unit_amount_ex_gst": unit_amount_ex_gst,
                "amount_ex_gst": line_total,
                "gst_applicable": gst_applicable,
            }
        )

    if not items:
        raise ValueError("Add at least one line item with a description and amount.")

    subtotal = sum(item["amount_ex_gst"] for item in items)
    return apply_registration_to_parsed_items(items, subtotal, gst_registered)


def line_items_from_request(form, gst_registered=None):
    if gst_registered is None:
        _, profile = storage.resolve_business(form.get("business"))
        gst_registered = is_gst_registered(profile)
    return parse_line_items(
        form.getlist("item_description"),
        form.getlist("item_amount"),
        form.getlist("item_quantity"),
        form.getlist("item_gst_free"),
        gst_registered=gst_registered,
    )


def invoice_summary_description(items):
    if len(items) == 1:
        return items[0]["description"]
    return f"{items[0]['description']} (+{len(items) - 1} more)"


def line_items_from_form_dict(form, gst_registered=None):
    if gst_registered is None:
        _, profile = storage.resolve_business(form.get("business"))
        gst_registered = is_gst_registered(profile)
    descriptions = [item["description"] for item in form["line_items"]]
    amounts = [item["amount"] for item in form["line_items"]]
    quantities = [item["qty"] for item in form["line_items"]]
    gst_free_flags = ["on" if item.get("gst_free") else "" for item in form["line_items"]]
    return parse_line_items(
        descriptions, amounts, quantities, gst_free_flags, gst_registered=gst_registered
    )


def due_context_from_form(form, invoice_date=None):
    settings = storage.load_settings()
    invoice_date = invoice_date or date.today()
    rule = due_rule_from_form_data(form, settings)
    return invoice_due_summary(
        invoice_date,
        rule["due_rule_type"],
        rule["due_net_days"],
        rule["due_fixed_date"],
    )


def invoices_by_status(invoices):
    groups = {"not_sent": [], "sent": [], "paid": []}
    for invoice in invoices.values():
        if storage.is_invoice_deleted(invoice):
            continue
        status = invoice.get("status", "not_sent")
        if status in ("send_queued", "send_failed"):
            groups["not_sent"].append(invoice)
        elif status in groups:
            groups[status].append(invoice)

    def sort_key(inv):
        return (inv.get("invoice_date", ""), inv.get("invoice_number", 0))

    settings = storage.load_settings()
    for status in groups:
        if status == "sent":
            groups[status].sort(key=lambda inv: sent_invoice_sort_key(inv, settings))
        else:
            groups[status].sort(key=sort_key, reverse=True)

    sent_total = sum(
        Decimal(inv.get("total_inc_gst", "0")) for inv in groups["sent"]
    )
    return groups, sent_total


def _invoice_money(invoice, key):
    try:
        return Decimal(str(invoice.get(key, "0") or "0"))
    except Exception:
        return Decimal("0")


def _invoice_in_month(invoice, year, month):
    raw = str(invoice.get("invoice_date") or "")
    if len(raw) < 7:
        return False
    try:
        return int(raw[0:4]) == year and int(raw[5:7]) == month
    except ValueError:
        return False


def dashboard_totals(invoices, *, today=None):
    """Sales totals for the dashboard (inc GST primary, ex GST secondary)."""
    if today is None:
        today = date.today()
    groups, _ = invoices_by_status(invoices)

    def bucket_sums(items):
        return {
            "inc_gst": sum((_invoice_money(inv, "total_inc_gst") for inv in items), Decimal("0")),
            "ex_gst": sum((_invoice_money(inv, "amount_ex_gst") for inv in items), Decimal("0")),
            "count": len(items),
        }

    month_items = [
        inv
        for inv in invoices.values()
        if not storage.is_invoice_deleted(inv) and _invoice_in_month(inv, today.year, today.month)
    ]
    return {
        "month": bucket_sums(month_items),
        "outstanding": bucket_sums(groups["sent"]),
        "paid": bucket_sums(groups["paid"]),
    }
