import logging
import os
import re
import sys
import threading
import time
import urllib.request
import webbrowser
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote

from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from werkzeug.serving import make_server

import storage
from due_dates import due_rule_from_form_data, merge_due_rule_into_form, invoice_due_summary
from email_compose import EmailComposeError, build_invoice_email_context, prepare_manual_send
from folder_picker import process_pending_picks
from ui_config import IDLE_TIMEOUT_SECONDS, PLACEHOLDERS, SELECT_LABELS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

logging.getLogger("werkzeug").setLevel(logging.ERROR)

server = None
last_request_time = time.time()
shutdown_requested = False


def resource_path(relative):
    base = sys._MEIPASS if getattr(sys, "frozen", False) else BASE_DIR
    return os.path.join(base, relative)


def exe_dir():
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def resolve_pdf_path(filename):
    if ".." in filename or "/" in filename or "\\" in filename:
        abort(404)
    primary = os.path.join(storage.get_pdf_dir(), filename)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(exe_dir(), filename)
    if os.path.isfile(legacy):
        return legacy
    abort(404)


app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static"),
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or storage.get_or_create_flask_secret()


@app.context_processor
def _inject_ui_defaults():
    return {
        "ph": PLACEHOLDERS,
        "select_labels": SELECT_LABELS,
    }


@app.context_processor
def _inject_brand():
    from app_config import (
        APP_BRAND_DEVELOPER,
        APP_BRAND_DEVELOPER_URL,
        APP_BRAND_NAME,
        APP_BRAND_TAGLINE,
        APP_BRAND_URL,
        APP_SUPPORT_URL,
        SHOW_LOGO_DESIGN_SETTINGS,
    )

    return {
        "brand_name": APP_BRAND_NAME,
        "brand_tagline": APP_BRAND_TAGLINE,
        "brand_url": APP_BRAND_URL,
        "brand_developer": APP_BRAND_DEVELOPER,
        "brand_developer_url": APP_BRAND_DEVELOPER_URL,
        "brand_support_url": APP_SUPPORT_URL,
        "show_logo_design_settings": SHOW_LOGO_DESIGN_SETTINGS,
    }


@app.context_processor
def _inject_update():
    import app_update
    from app_config import APP_VERSION

    pending = app_update.get_pending_update()
    return {
        "app_version": APP_VERSION,
        "pending_update": pending,
        "show_update_banner": bool(pending and not pending.get("banner_hidden")),
    }


@app.context_processor
def _inject_email_started_helper():
    def email_started_for(number):
        return session.get(f"email_started_{format_invoice_number(number)}", False)

    return {"email_started_for": email_started_for}


@app.template_filter("fmt_invoice_number")
def _fmt_invoice_number(number):
    return format_invoice_number(number)


@app.template_filter("fmt_invoice_date")
def _fmt_invoice_date(iso_date):
    return format_invoice_date(iso_date)


@app.template_filter("fmt_invoice_amount")
def _fmt_invoice_amount(inv):
    return format_money(Decimal(inv["total_inc_gst"]))


@app.template_filter("invoice_due_countdown")
def _invoice_due_countdown(inv):
    from due_dates import due_countdown_for_invoice

    return due_countdown_for_invoice(inv)


@app.before_request
def touch_last_request():
    global last_request_time
    if request.path != "/shutdown":
        last_request_time = time.time()


def format_money(amount):
    return f"${amount:,.2f}"


def format_invoice_number(number):
    return f"{int(number):08d}"


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
        raise ValueError("Please enter an amount.")
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


def parse_line_items(descriptions, amounts, quantities=None):
    """Parse parallel description/amount/qty lists into validated line items."""
    if quantities is None:
        quantities = []
    items = []
    row_num = 0
    for i, (desc_raw, amt_raw) in enumerate(zip(descriptions, amounts)):
        desc = desc_raw.strip()
        amt = amt_raw.strip()
        qty_raw = quantities[i] if i < len(quantities) else ""
        if not desc and not amt and not qty_raw.strip():
            continue
        row_num += 1
        if not desc:
            raise ValueError(f"Item {row_num}: please enter a description.")
        try:
            unit_amount_ex_gst = parse_amount(amt)
        except (ValueError, InvalidOperation):
            raise ValueError(
                f"Item {row_num}: please enter a valid amount (for example: 4500.00)."
            )
        try:
            qty = parse_quantity(qty_raw)
        except (ValueError, InvalidOperation):
            raise ValueError(f"Item {row_num}: please enter a valid quantity (for example: 1).")
        line_total = (qty * unit_amount_ex_gst).quantize(Decimal("0.01"))
        items.append(
            {
                "description": desc,
                "quantity": qty,
                "unit_amount_ex_gst": unit_amount_ex_gst,
                "amount_ex_gst": line_total,
            }
        )

    if not items:
        raise ValueError("Please add at least one item with a description and amount.")

    subtotal = sum(item["amount_ex_gst"] for item in items)
    gst_amount, total_inc_gst = compute_gst(subtotal)
    return items, subtotal, gst_amount, total_inc_gst


def line_items_from_request(form):
    return parse_line_items(
        form.getlist("item_description"),
        form.getlist("item_amount"),
        form.getlist("item_quantity"),
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
        customer = req.form.get("customer", "").strip()
        comment = req.form.get("comment", "").strip()
        due_rule_type = req.form.get("due_rule_type", "").strip()
        due_net_days = req.form.get("due_net_days", "").strip()
    else:
        descriptions = req.args.getlist("item_description")
        amounts = req.args.getlist("item_amount")
        quantities = req.args.getlist("item_quantity")
        customer = req.args.get("customer", "")
        comment = req.args.get("comment", "")
        due_rule_type = req.args.get("due_rule_type", "")
        due_net_days = req.args.get("due_net_days", "")

    items = []
    for i, (desc, amt) in enumerate(zip(descriptions, amounts)):
        qty = quantities[i] if i < len(quantities) else "1"
        items.append({"description": desc, "amount": amt, "qty": qty or "1"})
    if not items:
        items = [{"description": "", "amount": "", "qty": "1"}]
    return {
        "customer": customer,
        "comment": comment,
        "line_items": items,
        "due_rule_type": due_rule_type,
        "due_net_days": due_net_days,
    }


def save_invoice_draft(form):
    session["invoice_draft"] = form
    session.modified = True


def get_invoice_draft():
    return session.get("invoice_draft")


def clear_invoice_draft():
    session.pop("invoice_draft", None)
    session.modified = True


def has_invoice_draft():
    return bool(session.get("invoice_draft"))


def _line_items_from_form_dict(form):
    descriptions = [item["description"] for item in form["line_items"]]
    amounts = [item["amount"] for item in form["line_items"]]
    quantities = [item["qty"] for item in form["line_items"]]
    return parse_line_items(descriptions, amounts, quantities)


def _render_preview_from_form(form):
    settings = storage.load_settings()
    customers = storage.load_customers()
    customer_name = form["customer"]
    comment = form["comment"]

    if not customer_name or customer_name not in customers:
        return render_create_invoice(form, error="Please select a customer.")

    try:
        items, subtotal, gst_amount, total_inc_gst = _line_items_from_form_dict(form)
    except ValueError as exc:
        return render_create_invoice(form, error=str(exc))

    save_invoice_draft(form)
    customer = customers[customer_name]
    invoice_date = date.today()
    due = _due_context_from_form(form, invoice_date)
    preview_items = [
        {
            "description": item["description"],
            "qty": format_qty(item["quantity"]),
            "qty_raw": str(item["quantity"]),
            "unit_amount_fmt": format_money(item["unit_amount_ex_gst"]),
            "unit_amount_raw": str(item["unit_amount_ex_gst"]),
            "amount_fmt": format_money(item["amount_ex_gst"]),
            "amount_raw": str(item["unit_amount_ex_gst"]),
        }
        for item in items
    ]

    return render_template(
        "preview_invoice.html",
        business_name=settings.get("business_name", ""),
        business_address=settings.get("business_address", ""),
        business_abn=format_abn(settings.get("business_abn", "")),
        account_name=settings.get("account_name", ""),
        bsb=settings.get("bsb", ""),
        acc=format_account(settings.get("acc", "")),
        due_date_fmt=due["due_date_fmt"],
        due_rule_label=due["due_rule_label"],
        due_rule_type=due["due_rule_type"],
        due_net_days=due["due_net_days"],
        customer_name=customer_name,
        customer_address=customer.get("address", ""),
        customer_abn=format_abn(customer.get("abn", "")),
        items=preview_items,
        comment=comment,
        amount_ex_gst_fmt=format_money(subtotal),
        gst_amount_fmt=format_money(gst_amount),
        total_inc_gst_fmt=format_money(total_inc_gst),
        invoice_number=format_invoice_number(settings["invoice_counter"]),
        invoice_date=invoice_date.strftime("%d %B %Y"),
        subtotal_raw=str(subtotal),
        **_billing_preview_template(subtotal),
    )


NAV_PARENTS = {
    "create_invoice": ("home", "Home"),
    "resume_preview": ("create_invoice", "Edit invoice"),
    "dashboard": ("home", "Home"),
    "invoices_list": ("home", "Home"),
    "customers_list": ("home", "Home"),
    "customers_add": ("customers_list", "Customers"),
    "customers_edit": ("customers_list", "Customers"),
    "settings_page": ("home", "Home"),
    "settings_details": ("settings_page", "Settings"),
    "settings_account": ("settings_page", "Settings"),
    "settings_billing": ("settings_page", "Settings"),
    "settings_fee_calculator": ("settings_page", "Settings"),
    "settings_storage": ("settings_page", "Settings"),
    "settings_logo_design": ("settings_page", "Settings"),
    "settings_updates": ("settings_page", "Settings"),
    "backup_import": ("settings_account", "Your account"),
    "account_cap": ("account_onboard_customer", "First customer"),
    "account_onboard_business": ("account_create", "Account"),
    "account_onboard_customer": ("account_onboard_business", "Your business"),
    "account_cap_settings": ("settings_billing", "Billing"),
    "account_repair_ledger": ("settings_account", "Your account"),
    "welcome_pricing": ("welcome_start", "Welcome"),
    "welcome_data": ("welcome_pricing", "Pricing"),
    "welcome_done": ("welcome_data", "Your data"),
}


@app.context_processor
def inject_navigation():
    endpoint = request.endpoint
    back_url = url_for("home")
    back_label = "Home"

    if endpoint in ("account_create", "account_login", "account_onboard_business", "account_onboard_customer", "account_cap") and has_invoice_draft():
        back_url = url_for("resume_preview")
        back_label = "Back to invoice review"
    elif endpoint in NAV_PARENTS:
        parent_endpoint, label = NAV_PARENTS[endpoint]
        back_url = url_for(parent_endpoint)
        back_label = label

    return {
        "back_url": back_url,
        "back_label": back_label,
        "has_invoice_draft": has_invoice_draft(),
    }


def _due_context_from_form(form, invoice_date=None):
    settings = storage.load_settings()
    invoice_date = invoice_date or date.today()
    rule = due_rule_from_form_data(form, settings)
    return invoice_due_summary(invoice_date, rule["due_rule_type"], rule["due_net_days"])


def _create_invoice_template_context(form, error=None):
    settings = storage.load_settings()
    customers = storage.load_customers()
    merge_due_rule_into_form(form, settings)
    due = _due_context_from_form(form)
    return {
        "customers": customers,
        "invoice_counter": format_invoice_number(settings["invoice_counter"]),
        "form": form,
        "error": error,
        "due_rule_type": due["due_rule_type"],
        "due_net_days": due["due_net_days"],
        "due_date_preview": due["due_date_fmt"],
        "invoice_date_iso": date.today().isoformat(),
    }


def render_create_invoice(form, error=None):
    ctx = _create_invoice_template_context(form, error=error)
    return render_template("create_invoice.html", **ctx)


def invoices_by_status(invoices):
    from due_dates import sent_invoice_sort_key

    groups = {"not_sent": [], "sent": [], "paid": []}
    for invoice in invoices.values():
        status = invoice.get("status", "not_sent")
        if status in groups:
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


def format_invoice_date(iso_date):
    try:
        parts = iso_date.split("-")
        d = date(int(parts[0]), int(parts[1]), int(parts[2]))
        return d.strftime("%d %B %Y")
    except (ValueError, IndexError):
        return iso_date


def request_shutdown():
    global shutdown_requested
    if shutdown_requested:
        return
    shutdown_requested = True

    def _exit():
        if server is not None:
            server.shutdown()
        os._exit(0)

    threading.Timer(0.3, _exit).start()


def idle_watchdog():
    while not shutdown_requested:
        time.sleep(60)
        if time.time() - last_request_time > IDLE_TIMEOUT_SECONDS:
            request_shutdown()
            break


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/create", methods=["GET", "POST"])
def create_invoice():
    if request.method == "POST":
        form = create_form_from_request(request)
        save_invoice_draft(form)
        return render_create_invoice(form)

    if request.args.get("fresh"):
        clear_invoice_draft()

    if request.args.get("customer"):
        form = {
            "customer": request.args.get("customer", ""),
            "comment": request.args.get("comment", ""),
            "line_items": [{"description": "", "amount": "", "qty": "1"}],
        }
    elif get_invoice_draft():
        form = get_invoice_draft()
    else:
        form = {
            "customer": "",
            "comment": "",
            "line_items": [{"description": "", "amount": "", "qty": "1"}],
        }

    settings = storage.load_settings()
    customers = storage.load_customers()
    merge_due_rule_into_form(form, settings)
    ctx = _create_invoice_template_context(form, error=request.args.get("error"))
    ctx["customer_added"] = request.args.get("customer_added") == "1"
    return render_template("create_invoice.html", **ctx)


@app.route("/create/add-customer", methods=["POST"])
def create_invoice_add_customer():
    form = create_form_from_request(request)
    save_invoice_draft(form)

    name = request.form.get("new_customer_name", "").strip()
    address = request.form.get("new_customer_address", "").strip()
    abn = request.form.get("new_customer_abn", "").strip()
    email = request.form.get("new_customer_email", "").strip()

    if not name:
        return redirect(url_for("create_invoice", error="Please enter a customer name."))

    if storage.customer_name_exists(name):
        return redirect(url_for("create_invoice", error="A customer with this name already exists."))

    customers = storage.load_customers()
    customers[name] = {"address": address, "abn": abn, "email": email}
    storage.save_customers(customers)

    form["customer"] = name
    save_invoice_draft(form)
    return redirect(url_for("create_invoice", customer_added=1))


@app.route("/preview", methods=["POST"])
def preview_invoice():
    form = create_form_from_request(request)
    return _render_preview_from_form(form)


@app.route("/preview/resume", methods=["GET"])
def resume_preview():
    draft = get_invoice_draft()
    if not draft:
        return redirect(url_for("create_invoice"))
    return _render_preview_from_form(draft)


def _billing_preview_template(subtotal):
    import billing_auth_store
    import billing_client
    import billing_local
    import billing_messages

    authenticated = billing_auth_store.is_authenticated()

    def _with_preview(preview, notice_title=None, notice_message=None, notice_kind="error"):
        if preview.get("ledger_invalid"):
            return {
                "billing_preview": preview,
                "fee_delta_fmt": format_money(preview.get("fee_delta", 0)),
                "projected_fee_fmt": format_money(preview.get("projected_fee", 0)),
                "cap_blocked": preview.get("cap_blocked", False),
                "over_by_fmt": format_money(preview.get("over_by", 0)),
                "account_required": False,
                "account_required_message": None,
                "billing_notice_title": "Usage records invalid",
                "billing_notice_message": billing_messages.LEDGER_INVALID,
                "billing_notice_kind": "error",
            }
        account_required = preview.get("account_required", False) and not authenticated
        return {
            "billing_preview": preview,
            "fee_delta_fmt": format_money(preview.get("fee_delta", 0)),
            "projected_fee_fmt": format_money(preview.get("projected_fee", 0)),
            "cap_blocked": preview.get("cap_blocked", False),
            "over_by_fmt": format_money(preview.get("over_by", 0)),
            "account_required": account_required,
            "account_required_message": billing_messages.ACCOUNT_REQUIRED if account_required else None,
            "billing_notice_title": notice_title,
            "billing_notice_message": notice_message,
            "billing_notice_kind": notice_kind,
        }

    try:
        preview = billing_client.preview(subtotal)
    except billing_client.BillingOfflineError:
        preview = billing_local.local_usage_snapshot(subtotal)
        if preview.get("ledger_invalid"):
            return _with_preview(preview)
        account_required = preview.get("account_required", False) and not authenticated
        notice = billing_messages.offline_for_preview(
            authenticated=authenticated,
            account_required=account_required or preview.get("cap_enabled"),
        )
        if notice:
            return _with_preview(preview, "Connection needed", notice, "warning")
        return _with_preview(preview)
    except billing_client.BillingError as exc:
        preview = billing_local.local_usage_snapshot(subtotal)
        if preview.get("ledger_invalid"):
            return _with_preview(preview)
        if authenticated:
            return _with_preview(
                preview,
                "Could not update usage",
                billing_messages.map_http_auth_error(str(exc)),
            )
        return _with_preview(preview)

    return _with_preview(preview)


@app.route("/generate", methods=["POST"])
def generate():
    import billing_client
    import pdf_generator

    settings = storage.load_settings()
    customers = storage.load_customers()

    customer_name = request.form.get("customer", "").strip()
    comment = request.form.get("comment", "").strip()
    cap_bypassed = request.form.get("cap_bypass_confirm") == "1"

    if not customer_name or customer_name not in customers:
        return redirect(url_for("create_invoice", error="Please select a customer."))

    try:
        items, subtotal, gst_amount, total_inc_gst = line_items_from_request(request.form)
    except ValueError as exc:
        return redirect(url_for("create_invoice", error=str(exc)))

    guard_result, guard_status = _billing_generate_guard(
        settings["invoice_counter"], subtotal, cap_bypassed
    )
    if guard_status == "ledger_invalid":
        save_invoice_draft(create_form_from_request(request))
        flash(guard_result, "error")
        return redirect(url_for("resume_preview"))
    if guard_status == "account_required":
        save_invoice_draft(create_form_from_request(request))
        flash(guard_result, "info")
        return redirect(url_for("account_create"))
    if guard_status == "cap_blocked":
        form = create_form_from_request(request)
        return render_create_invoice(form, error="Cap exceeded. Review on the preview page.")
    if guard_status == "offline":
        save_invoice_draft(create_form_from_request(request))
        flash(guard_result, "error")
        return redirect(url_for("resume_preview"))
    if guard_status == "error":
        save_invoice_draft(create_form_from_request(request))
        flash(guard_result, "error")
        return redirect(url_for("resume_preview"))

    customer = customers[customer_name]
    invoice_number = settings["invoice_counter"]
    invoice_date = date.today()
    due = _due_context_from_form(create_form_from_request(request), invoice_date)

    invoice_data = {
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "business_name": settings.get("business_name", ""),
        "business_address": settings.get("business_address", ""),
        "business_abn": settings.get("business_abn", ""),
        "account_name": settings.get("account_name", ""),
        "bsb": settings.get("bsb", ""),
        "acc": settings.get("acc", ""),
        "due_date": due["due_date"],
        "due_date_fmt": due["due_date_fmt"],
        "due_rule_label": due["due_rule_label"],
        "customer_name": customer_name,
        "customer_address": customer.get("address", ""),
        "customer_abn": customer.get("abn", ""),
        "line_items": items,
        "amount_ex_gst": subtotal,
        "gst_amount": gst_amount,
        "total_inc_gst": total_inc_gst,
        "comment": comment,
    }

    filepath = pdf_generator.generate_invoice(storage.get_pdf_dir(), invoice_data)
    filename = os.path.basename(filepath)

    settings["invoice_counter"] = invoice_number + 1
    storage.save_settings(settings)

    storage.add_invoice(
        {
            "invoice_number": invoice_number,
            "invoice_date": invoice_date.isoformat(),
            "customer_name": customer_name,
            "description": invoice_summary_description(items),
            "total_inc_gst": str(total_inc_gst),
            "amount_ex_gst": str(subtotal),
            "filename": filename,
            "due_date": due["due_date_iso"],
            "due_rule_type": due["due_rule_type"],
            "due_net_days": due["due_net_days"],
        }
    )

    clear_invoice_draft()
    return redirect(
        url_for(
            "done",
            file=filename,
            invoice=format_invoice_number(invoice_number),
            customer=customer_name,
        )
    )


@app.route("/view-pdf/<filename>")
def view_pdf(filename):
    filepath = resolve_pdf_path(filename)
    return send_file(filepath, mimetype="application/pdf")


@app.route("/done")
def done():
    filename = request.args.get("file", "")
    invoice_number = request.args.get("invoice", "")
    customer = request.args.get("customer", "")
    marked_sent = request.args.get("sent") == "1"
    sent_date = None
    send_later = False
    email_started = False
    inv = None

    if invoice_number:
        inv = storage.get_invoice(invoice_number)
        inv_key = format_invoice_number(invoice_number)
        if inv:
            if not filename:
                filename = inv.get("filename", "")
            if not customer:
                customer = inv.get("customer_name", "")
            if inv.get("status") in ("sent", "paid"):
                marked_sent = True
                sent_date = inv.get("sent_date")
            email_started = session.get(f"email_started_{inv_key}", False)
            send_later = session.get(f"send_later_{inv_key}", False)

    step2_complete = marked_sent or send_later
    email_details = None

    if invoice_number and inv and not step2_complete:
        _, ctx = _invoice_email_context(invoice_number)
        email_details = ctx

    return render_template(
        "done.html",
        filename=filename,
        invoice_number=invoice_number,
        customer=customer,
        marked_sent=marked_sent,
        sent_date=sent_date,
        send_later=send_later,
        email_started=email_started,
        step2_complete=step2_complete,
        email_details=email_details,
    )




@app.route("/ping", methods=["GET", "POST"])
def ping():
    return "", 204


@app.route("/shutdown", methods=["GET", "POST"])
def shutdown():
    request_shutdown()
    return "OK", 200


@app.route("/invoices")
def invoices_list():
    invoices = storage.load_invoices()
    q = request.args.get("q", "").strip().lower()
    status_filter = request.args.get("status", "")
    customer_filter = request.args.get("customer", "")
    date_from = request.args.get("from", "")
    date_to = request.args.get("to", "")

    if q or status_filter or customer_filter or date_from or date_to:
        filtered = {}
        for key, inv in invoices.items():
            if status_filter and inv.get("status") != status_filter:
                continue
            if customer_filter and inv.get("customer_name") != customer_filter:
                continue
            if date_from and inv.get("invoice_date", "") < date_from:
                continue
            if date_to and inv.get("invoice_date", "") > date_to:
                continue
            if q:
                hay = " ".join(
                    [
                        str(inv.get("invoice_number", "")),
                        inv.get("customer_name", ""),
                        inv.get("description", ""),
                    ]
                ).lower()
                if q not in hay:
                    continue
            filtered[key] = inv
        invoices = filtered

    groups, sent_total = invoices_by_status(invoices)
    customers = sorted(storage.load_customers().keys())

    filters_active = bool(q or status_filter or customer_filter or date_from or date_to)
    filter_summary_parts = []
    if q:
        filter_summary_parts.append(f'Search: "{q}"')
    if status_filter:
        labels = {"not_sent": "Not sent", "sent": "Sent", "paid": "Paid"}
        filter_summary_parts.append(labels.get(status_filter, status_filter))
    if customer_filter:
        filter_summary_parts.append(customer_filter)
    if date_from or date_to:
        if date_from and date_to:
            filter_summary_parts.append(f"{date_from} – {date_to}")
        elif date_from:
            filter_summary_parts.append(f"From {date_from}")
        else:
            filter_summary_parts.append(f"Until {date_to}")

    return render_template(
        "invoices.html",
        not_sent=groups["not_sent"],
        sent=groups["sent"],
        paid=groups["paid"],
        sent_total_fmt=format_money(sent_total),
        sent_count=len(groups["sent"]),
        q=q,
        status_filter=status_filter,
        customer_filter=customer_filter,
        date_from=date_from,
        date_to=date_to,
        customers=customers,
        filters_active=filters_active,
        filter_summary=filter_summary_parts,
    )


def _clear_invoice_send_session(number):
    key = format_invoice_number(number)
    session.pop(f"email_started_{key}", None)
    session.pop(f"send_later_{key}", None)


@app.route("/invoices/<number>/status", methods=["POST"])
def invoice_update_status(number):
    number = unquote(number)
    status = request.form.get("status", "").strip()
    try:
        storage.update_invoice_status(number, status)
    except (KeyError, ValueError):
        abort(404)

    if status == "sent":
        _clear_invoice_send_session(number)

    next_page = request.form.get("next", "invoices")
    if next_page == "done" and status == "sent":
        inv = storage.get_invoice(number)
        if inv:
            return redirect(
                url_for(
                    "done",
                    file=inv.get("filename", ""),
                    invoice=format_invoice_number(number),
                    customer=inv.get("customer_name", ""),
                    sent=1,
                )
            )
    return redirect(url_for("invoices_list"))


def _invoice_email_redirect(next_page, inv):
    if next_page == "done":
        return redirect(
            url_for(
                "done",
                file=inv.get("filename", ""),
                invoice=format_invoice_number(inv["invoice_number"]),
                customer=inv.get("customer_name", ""),
            )
        )
    return redirect(url_for("invoices_list"))


def _invoice_email_context(number):
    inv = storage.get_invoice(number)
    if not inv:
        abort(404)
    customer = storage.load_customers().get(inv.get("customer_name", ""), {})
    settings = storage.load_settings()
    pdf_path = resolve_pdf_path(inv.get("filename", ""))
    ctx = build_invoice_email_context(inv, customer, settings, pdf_path)
    return inv, ctx


@app.route("/invoices/<number>/email/send")
def invoice_email_send(number):
    number = unquote(number)
    next_page = request.args.get("next", "invoices")
    inv, ctx = _invoice_email_context(number)
    try:
        prepare_manual_send(ctx)
        session[f"email_started_{format_invoice_number(number)}"] = True
        flash(
            "Email details copied and PDF folder opened. Paste into your email, attach the PDF, and mark as sent.",
            "success",
        )
    except EmailComposeError as exc:
        flash(f"Could not prepare email: {exc}", "error")
    return _invoice_email_redirect(next_page, inv)


@app.route("/invoices/<number>/send-later")
def invoice_send_later(number):
    number = unquote(number)
    inv = storage.get_invoice(number)
    if not inv:
        abort(404)
    session[f"send_later_{format_invoice_number(number)}"] = True
    next_page = request.args.get("next", "invoices")
    if next_page == "done":
        return redirect(
            url_for(
                "done",
                file=inv.get("filename", ""),
                invoice=format_invoice_number(number),
                customer=inv.get("customer_name", ""),
            )
        )
    return redirect(url_for("invoices_list"))


@app.route("/customers")
def customers_list():
    customers = storage.load_customers()
    return render_template("customers.html", customers=customers)


@app.route("/customers/add", methods=["GET", "POST"])
def customers_add():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()
        abn = request.form.get("abn", "").strip()
        email = request.form.get("email", "").strip()

        if not name:
            return render_template(
                "edit_customer.html",
                customer=None,
                form={"name": name, "address": address, "abn": abn, "email": email},
                error="Please enter a customer name.",
                is_add=True,
            )

        if storage.customer_name_exists(name):
            return render_template(
                "edit_customer.html",
                customer=None,
                form={"name": name, "address": address, "abn": abn, "email": email},
                error="A customer with this name already exists.",
                is_add=True,
            )

        customers = storage.load_customers()
        customers[name] = {"address": address, "abn": abn, "email": email}
        storage.save_customers(customers)
        return redirect(url_for("customers_list"))

    return render_template(
        "edit_customer.html",
        customer=None,
        form={"name": "", "address": "", "abn": "", "email": ""},
        error=None,
        is_add=True,
    )


@app.route("/customers/edit/<name>", methods=["GET", "POST"])
def customers_edit(name):
    name = unquote(name)
    customers = storage.load_customers()

    if name not in customers:
        return redirect(url_for("customers_list"))

    customer = customers[name]

    if request.method == "POST":
        address = request.form.get("address", "").strip()
        abn = request.form.get("abn", "").strip()
        email = request.form.get("email", "").strip()
        customers[name] = {"address": address, "abn": abn, "email": email}
        storage.save_customers(customers)
        return redirect(url_for("customers_list"))

    return render_template(
        "edit_customer.html",
        customer=name,
        form={"name": name, "address": customer.get("address", ""), "abn": customer.get("abn", ""), "email": customer.get("email", "")},
        error=None,
        is_add=False,
    )


@app.route("/customers/delete/<name>", methods=["POST"])
def customers_delete(name):
    name = unquote(name)
    customers = storage.load_customers()
    if name in customers:
        del customers[name]
        storage.save_customers(customers)
    return redirect(url_for("customers_list"))


@app.route("/settings")
def settings_page():
    return render_template("settings.html")


@app.route("/updates/dismiss", methods=["POST"])
def updates_dismiss():
    import app_update

    version = request.form.get("version", "").strip()
    if version:
        app_update.dismiss_update(version)
    return redirect(request.referrer or url_for("home"))


@app.route("/updates/apply", methods=["POST"])
def updates_apply():
    import app_update

    pending = app_update.get_pending_update(force_check=True)
    if not pending:
        flash("No update is available right now.", "info")
        return redirect(request.referrer or url_for("home"))
    try:
        app_update.apply_update(pending, request_shutdown)
        flash("Downloading update. The app will restart shortly.", "info")
    except Exception as exc:
        flash(f"Update failed: {exc}", "error")
    return redirect(request.referrer or url_for("settings_updates"))


@app.route("/settings/updates", methods=["GET", "POST"])
def settings_updates():
    import app_update
    import billing_client

    error = None
    server_unreachable = False
    force_check = request.method == "GET" or request.form.get("action") in ("check", "apply")
    pending = app_update.get_pending_update(force_check=force_check)

    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "check":
            if not billing_client.check_server_available():
                server_unreachable = True
            else:
                pending = app_update.get_pending_update(force_check=True)
        elif action == "apply" and pending:
            try:
                app_update.apply_update(pending, request_shutdown)
                flash("Downloading update. The app will restart shortly.", "info")
                return redirect(url_for("settings_updates"))
            except Exception as exc:
                error = str(exc)

    return render_template(
        "settings_updates.html",
        pending=pending,
        error=error,
        packaged=app_update.is_packaged(),
        server_unreachable=server_unreachable,
    )


LOGO_DESIGN_BRIEF = """FrogsWork logo brief:
- Whimsical, business-capable frog (not corporate clipart)
- Static image, but should feel lively and animated in character
- Artsy and distinctive, not generic SaaS branding
- Must read clearly at 16px (taskbar icon) and on a startup splash
- Green palette aligned with FrogsWork (see frogswork.com)"""


@app.route("/settings/logo-design", methods=["GET", "POST"])
def settings_logo_design():
    from urllib.parse import quote

    from app_config import APP_SUPPORT_EMAIL, APP_SUPPORT_URL, SHOW_LOGO_DESIGN_SETTINGS

    if not SHOW_LOGO_DESIGN_SETTINGS:
        abort(404)

    error = None
    submitted = False
    mailto_href = None
    composed_text = None

    if request.method == "POST":
        contact = request.form.get("contact", "").strip()
        message = request.form.get("message", "").strip()
        if not message:
            error = "Add a short message about your interest or ideas."
        else:
            submitted = True
            composed_text = (
                "FrogsWork logo design help\n\n"
                f"Contact: {contact or 'not provided'}\n\n"
                f"{message}\n\n"
                f"---\n{LOGO_DESIGN_BRIEF}"
            )
            if APP_SUPPORT_EMAIL:
                mailto_href = (
                    f"mailto:{APP_SUPPORT_EMAIL}"
                    f"?subject={quote('FrogsWork logo design help')}"
                    f"&body={quote(composed_text)}"
                )

    return render_template(
        "settings_logo_design.html",
        error=error,
        submitted=submitted,
        mailto_href=mailto_href,
        composed_text=composed_text,
        support_url=APP_SUPPORT_URL,
        form_contact=request.form.get("contact", "") if request.method == "POST" else "",
        form_message=request.form.get("message", "") if request.method == "POST" else "",
    )


@app.route("/settings/details", methods=["GET", "POST"])
def settings_details():
    if request.method == "POST":
        settings = storage.load_settings()
        settings["business_name"] = request.form.get("business_name", "").strip()
        settings["business_address"] = request.form.get("business_address", "").strip()
        settings["business_abn"] = request.form.get("business_abn", "").strip()
        settings["account_name"] = request.form.get("account_name", "").strip()
        settings["bsb"] = request.form.get("bsb", "").strip()
        settings["acc"] = request.form.get("acc", "").strip()
        settings["due_rule_type"] = request.form.get("due_rule_type", "net_days").strip()
        settings["due_net_days"] = due_rule_from_form_data(request.form, settings)["due_net_days"]

        counter_raw = request.form.get("invoice_counter", "").strip()
        try:
            counter = int(counter_raw)
            if counter < 1:
                raise ValueError
            settings["invoice_counter"] = counter
        except ValueError:
            due = invoice_due_summary(
                date.today(),
                settings.get("due_rule_type"),
                settings.get("due_net_days"),
            )
            return render_template(
                "settings_details.html",
                settings=settings,
                error="Invoice number must be a whole number of 1 or more.",
                due_rule_type=due["due_rule_type"],
                due_net_days=due["due_net_days"],
                due_date_preview=due["due_date_fmt"],
            )

        storage.save_settings(settings)
        return redirect(url_for("settings_details"))

    settings = storage.load_settings()
    due = invoice_due_summary(
        date.today(),
        settings.get("due_rule_type"),
        settings.get("due_net_days"),
    )
    return render_template(
        "settings_details.html",
        settings=settings,
        error=None,
        due_rule_type=due["due_rule_type"],
        due_net_days=due["due_net_days"],
        due_date_preview=due["due_date_fmt"],
    )


@app.route("/settings/account")
def settings_account():
    import billing_auth_store
    import billing_client
    import billing_local

    services_ok = None
    if billing_auth_store.is_authenticated():
        services_ok = billing_client.check_server_available()
    return render_template(
        "settings_account.html",
        account_services_ok=services_ok,
        ledger_invalid=billing_local.is_ledger_invalid(),
    )


@app.route("/settings/billing", methods=["GET", "POST"])
def settings_billing():
    import billing_auth_store
    import billing_client
    import billing_messages

    if not billing_auth_store.is_authenticated():
        return render_template(
            "settings_billing.html",
            authenticated=False,
            billing=None,
            error=None,
            services_ok=billing_client.check_server_available(),
        )

    error = None
    if request.method == "POST":
        billing_cycle = request.form.get("billing_cycle", "quarterly")
        try:
            billing_client.update_billing_cycle(billing_cycle)
            flash("Billing cycle updated.", "success")
            return redirect(url_for("settings_billing"))
        except billing_client.BillingOfflineError:
            error = billing_messages.OFFLINE_SYNC
        except billing_client.BillingError as exc:
            error = billing_messages.map_http_auth_error(str(exc))

    try:
        billing = billing_client.get_billing_overview()
        services_ok = True
    except billing_client.BillingOfflineError:
        billing = None
        services_ok = False
        error = error or billing_messages.OFFLINE_SYNC
    except billing_client.BillingError as exc:
        billing = None
        services_ok = billing_client.check_server_available()
        error = error or billing_messages.map_http_auth_error(str(exc))

    return render_template(
        "settings_billing.html",
        authenticated=True,
        billing=billing,
        error=error,
        services_ok=services_ok,
    )


@app.route("/settings/fee-calculator")
def settings_fee_calculator():
    return render_template("settings_fee_calculator.html")


@app.route("/settings/storage", methods=["GET"])
def settings_storage():
    return render_template(
        "settings_storage.html",
        config_folder=storage.get_config_folder_display(),
        pdf_folder=storage.get_pdf_folder_display(),
        using_default=storage.is_using_default_pdf_folder(),
        default_pdf_folder=os.path.join(storage.get_default_data_path(), "pdfs"),
    )


@app.route("/settings/storage/pick", methods=["POST"])
def settings_storage_pick():
    from folder_picker import FolderPickerError, pick_folder

    try:
        path = pick_folder("Choose where to save invoice PDFs")
        if path:
            storage.set_pdf_folder(path)
            flash("PDF folder updated.", "success")
    except FolderPickerError as exc:
        flash(f"Could not open folder picker: {exc}", "error")
    return redirect(url_for("settings_storage"))


@app.route("/settings/storage/reset", methods=["POST"])
def settings_storage_reset():
    storage.reset_pdf_folder()
    flash("PDF folder reset to the default AppData location.", "success")
    return redirect(url_for("settings_storage"))


def _billing_generate_guard(invoice_number, subtotal, cap_bypassed=False):
    import billing_auth_store
    import billing_client
    import billing_local
    import billing_messages

    try:
        preview = billing_client.preview(subtotal)
    except billing_client.BillingOfflineError:
        preview = billing_local.local_usage_snapshot(subtotal)
        if preview.get("ledger_invalid"):
            return billing_messages.LEDGER_INVALID, "ledger_invalid"
        blocked = preview.get("account_required") or billing_auth_store.is_authenticated()
        if blocked:
            return (
                billing_messages.offline_for_generate(
                    authenticated=billing_auth_store.is_authenticated()
                ),
                "offline",
            )
    except billing_client.BillingError:
        preview = billing_local.local_usage_snapshot(subtotal)

    if preview.get("ledger_invalid"):
        return billing_messages.LEDGER_INVALID, "ledger_invalid"

    if preview.get("account_required") and not billing_auth_store.is_authenticated():
        return billing_messages.ACCOUNT_REQUIRED, "account_required"

    if preview.get("cap_blocked") and not cap_bypassed:
        return preview, "cap_blocked"

    if not billing_auth_store.is_authenticated() and not preview.get("server_required"):
        billing_local.record_local_commit(invoice_number, subtotal)
        return preview, None

    try:
        billing_client.commit(invoice_number, subtotal, cap_bypassed=cap_bypassed)
    except billing_client.CapBlockedError as exc:
        return exc.preview, "cap_blocked"
    except billing_client.BillingOfflineError:
        return (
            billing_messages.offline_for_generate(
                authenticated=billing_auth_store.is_authenticated()
            ),
            "offline",
        )
    except billing_client.AccountRequiredError:
        return billing_messages.ACCOUNT_REQUIRED, "account_required"
    except billing_client.BillingError as exc:
        return billing_messages.GENERIC_BILLING_ERROR, "error"
    return preview, None


def open_browser_when_ready():
    from app_config import LOCAL_APP_URL

    url = LOCAL_APP_URL
    for _ in range(60):
        try:
            urllib.request.urlopen(url, timeout=0.2)
            webbrowser.open(url)
            return
        except OSError:
            time.sleep(0.05)
    webbrowser.open(url)


def use_dev_browser():
    return os.environ.get("FROGSWORK_DEV_BROWSER") == "1" or "--dev-browser" in sys.argv


def _show_already_running_message():
    if sys.platform != "win32":
        return
    try:
        import ctypes

        from app_config import APP_BRAND_NAME

        ctypes.windll.user32.MessageBoxW(
            0,
            f"{APP_BRAND_NAME} is already running.\n\n"
            "Check your taskbar for an open window.",
            APP_BRAND_NAME,
            0x40,
        )
    except Exception:
        pass


def _register_client_routes():
    from client_routes import register_client_routes

    register_client_routes(
        app,
        {
            "format_money": format_money,
            "format_invoice_number": format_invoice_number,
            "exe_dir": exe_dir,
            "invoices_by_status": invoices_by_status,
            "unquote": unquote,
        },
    )


def _start_flask_server():
    """Start the local server. Returns None on success, or 'port_in_use'."""
    global server
    from app_config import LOCAL_APP_HOST, LOCAL_APP_PORT

    _register_client_routes()
    storage.ensure_app_identity()
    try:
        server = make_server(LOCAL_APP_HOST, LOCAL_APP_PORT, app, threaded=True)
    except OSError:
        return "port_in_use"
    threading.Thread(target=server.serve_forever, daemon=True, name="flask-server").start()
    threading.Thread(target=idle_watchdog, daemon=True, name="idle-watchdog").start()
    return None


def _start_backend(startup_error):
    startup_error["code"] = _start_flask_server()


def main():
    from app_config import LOCAL_APP_URL

    if sys.platform == "win32" and getattr(sys, "frozen", False):
        from install_bootstrap import maybe_relocate_install

        maybe_relocate_install()

    if use_dev_browser():
        if _start_flask_server() == "port_in_use":
            _show_already_running_message()
            return
        threading.Thread(target=open_browser_when_ready, daemon=True).start()
        try:
            while not shutdown_requested:
                process_pending_picks()
                time.sleep(0.05)
        except KeyboardInterrupt:
            request_shutdown()
    else:
        startup_error = {"code": None}
        threading.Thread(
            target=_start_backend,
            args=(startup_error,),
            daemon=True,
            name="flask-backend",
        ).start()
        from desktop_shell import run_desktop_app

        run_desktop_app(LOCAL_APP_URL, request_shutdown, startup_error=startup_error)


if __name__ == "__main__":
    main()
