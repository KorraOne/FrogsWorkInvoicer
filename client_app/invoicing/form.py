from datetime import date
from decimal import Decimal, InvalidOperation

import os
import re
import shutil

from flask import render_template, session

from account import entitlement_guard
import storage
from invoicing.address import format_address_multiline
from .due_dates import (
    due_rule_from_form_data,
    due_rule_template_context,
    invoice_due_summary,
    merge_due_rule_into_form,
    sent_invoice_sort_key,
)
from .gst_settings import (
    apply_registration_to_parsed_items,
    is_gst_registered,
    validate_business_gst_settings,
)
from .format import (
    format_abn,
    format_account,
    format_invoice_number,
    format_money,
    format_qty,
    parse_amount,
    parse_invoice_number_input,
    parse_quantity,
    suggested_invoice_number,
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


def create_form_from_request(req):
    if req.method == "POST":
        descriptions = req.form.getlist("item_description")
        amounts = req.form.getlist("item_amount")
        quantities = req.form.getlist("item_quantity")
        gst_free_flags = req.form.getlist("item_gst_free")
        customer = req.form.get("customer", "").strip()
        business = req.form.get("business", "").strip()
        comment = req.form.get("comment", "").strip()
        due_rule_type = req.form.get("due_rule_type", "").strip()
        due_net_days = req.form.get("due_net_days", "").strip()
        due_fixed_date = req.form.get("due_fixed_date", "").strip()
        invoice_number = req.form.get("invoice_number", "").strip()
    else:
        descriptions = req.args.getlist("item_description")
        amounts = req.args.getlist("item_amount")
        quantities = req.args.getlist("item_quantity")
        gst_free_flags = req.args.getlist("item_gst_free")
        customer = req.args.get("customer", "")
        business = req.args.get("business", "")
        comment = req.args.get("comment", "")
        due_rule_type = req.args.get("due_rule_type", "")
        due_net_days = req.args.get("due_net_days", "")
        due_fixed_date = req.args.get("due_fixed_date", "")
        invoice_number = req.args.get("invoice_number", "")

    items = []
    for i, (desc, amt) in enumerate(zip(descriptions, amounts)):
        qty = quantities[i] if i < len(quantities) else "1"
        gst_free = _is_gst_free_flag(gst_free_flags[i] if i < len(gst_free_flags) else "")
        items.append({"description": desc, "amount": amt, "qty": qty or "1", "gst_free": gst_free})
    if not items:
        items = [{"description": "", "amount": "", "qty": "1", "gst_free": False}]
    return {
        "customer": customer,
        "business": business,
        "comment": comment,
        "line_items": items,
        "due_rule_type": due_rule_type,
        "due_net_days": due_net_days,
        "due_fixed_date": due_fixed_date,
        "invoice_number": invoice_number,
    }


def save_invoice_draft(form):
    session["invoice_draft"] = form
    session.modified = True


def get_invoice_draft():
    return session.get("invoice_draft")


def clear_invoice_draft():
    draft = session.get("invoice_draft") or {}
    token = (draft.get("work_photos_token") or "").strip()
    if re.fullmatch(r"[a-f0-9]{32}", token or ""):
        staging_dir = os.path.join(storage.get_data_path(), "staging", "invoice_attachments", token)
        if os.path.isdir(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)
    session.pop("invoice_draft", None)
    session.modified = True


def has_invoice_draft():
    return bool(session.get("invoice_draft"))


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


def create_invoice_template_context(form, error=None):
    settings = storage.load_settings()
    customers = storage.load_customers()
    businesses = storage.load_businesses()
    business_count = len(businesses)
    default_business = storage.get_default_business_name()
    selected_business = (form.get("business") or "").strip() or default_business
    if business_count == 1:
        selected_business = default_business
    elif business_count > 1 and selected_business not in businesses:
        selected_business = default_business

    if business_count == 0:
        business_error = "Set up your business details before creating an invoice."
        error = error or business_error

    _, business_profile = storage.resolve_business(selected_business)
    merge_due_rule_into_form(form, settings)
    due_ctx = due_rule_template_context(date.today(), settings, form)
    try:
        invoice_number_raw = parse_invoice_number_input(
            form.get("invoice_number")
            or suggested_invoice_number(selected_business, business_profile)
        )
    except ValueError:
        invoice_number_raw = suggested_invoice_number(selected_business, business_profile)
    return {
        "customers": customers,
        "businesses": businesses,
        "business_count": business_count,
        "selected_business": selected_business,
        "default_business": default_business,
        "form": form,
        "error": error,
        "gst_registered": is_gst_registered(business_profile),
        "invoice_number_raw": invoice_number_raw,
        "invoice_number_display": format_invoice_number(invoice_number_raw),
        **due_ctx,
    }


def render_create_invoice(form, error=None):
    ctx = create_invoice_template_context(form, error=error)
    return render_template("create_invoice.html", **ctx)


def render_preview_from_form(form):
    settings = storage.load_settings()
    customers = storage.load_customers()
    businesses = storage.load_businesses()
    customer_name = form["customer"]
    comment = form["comment"]

    if not businesses:
        return render_create_invoice(form, error="Set up your business details before creating an invoice.")

    business_name, business_profile = storage.resolve_business(form.get("business"))
    if not business_name:
        return render_create_invoice(form, error="Select which business to invoice from.")

    if not customer_name or customer_name not in customers:
        return render_create_invoice(form, error="Select a customer.")

    gst_err = validate_business_gst_settings(business_profile)
    if gst_err:
        return render_create_invoice(form, error=gst_err)

    gst_registered = is_gst_registered(business_profile)
    try:
        items, subtotal, gst_amount, total_inc_gst, taxable_ex_gst, gst_free_ex_gst = line_items_from_form_dict(
            form, gst_registered=gst_registered
        )
    except ValueError as exc:
        return render_create_invoice(form, error=str(exc))

    save_invoice_draft({**form, "business": business_name})
    customer = customers[customer_name]
    invoice_date = date.today()
    due = due_context_from_form(form, invoice_date)
    try:
        invoice_number_int = parse_invoice_number_input(form.get("invoice_number"))
    except ValueError as exc:
        return render_create_invoice(form, error=str(exc))
    invoice_number_fmt = format_invoice_number(invoice_number_int)
    preview_items = [
        {
            "description": item["description"],
            "qty": format_qty(item["quantity"]),
            "qty_raw": str(item["quantity"]),
            "unit_amount_fmt": format_money(item["unit_amount_ex_gst"]),
            "unit_amount_raw": str(item["unit_amount_ex_gst"]),
            "amount_fmt": format_money(item["amount_ex_gst"]),
            "amount_raw": str(item["unit_amount_ex_gst"]),
            "gst_applicable": item["gst_applicable"],
            "gst_free": not item["gst_applicable"],
        }
        for item in items
    ]

    sender = storage.business_invoice_fields(business_name, business_profile)
    return render_template(
        "preview_invoice.html",
        business_name=sender["business_name"],
        business_address=sender["business_address"],
        business_abn=format_abn(sender["business_abn"]),
        account_name=sender["account_name"],
        bsb=sender["bsb"],
        acc=format_account(sender["acc"]),
        due_date_fmt=due["due_date_fmt"],
        due_rule_label=due["due_rule_label"],
        due_rule_type=due["due_rule_type"],
        due_net_days=due["due_net_days"],
        due_fixed_date=due.get("due_fixed_date") or "",
        customer_name=customer_name,
        selected_business=business_name,
        customer_address=format_address_multiline(customer) or customer.get("address", ""),
        customer_abn=format_abn(customer.get("abn", "")),
        items=preview_items,
        comment=comment,
        amount_ex_gst_fmt=format_money(subtotal),
        taxable_ex_gst_fmt=format_money(taxable_ex_gst),
        gst_free_ex_gst_fmt=format_money(gst_free_ex_gst),
        gst_amount_fmt=format_money(gst_amount),
        total_inc_gst_fmt=format_money(total_inc_gst),
        gst_registered=gst_registered,
        invoice_title="Tax Invoice" if gst_registered else "Invoice",
        has_mixed_gst=gst_registered and gst_free_ex_gst > 0 and taxable_ex_gst > 0,
        has_gst=gst_registered and gst_amount > 0,
        invoice_number=invoice_number_fmt,
        invoice_number_raw=invoice_number_int,
        invoice_date=invoice_date.strftime("%d %B %Y"),
        subtotal_raw=str(subtotal),
        work_photos=list(form.get("work_photos") or []),
        work_photos_token=(form.get("work_photos_token") or "").strip(),
        **entitlement_guard.preview_context(format_money),
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
