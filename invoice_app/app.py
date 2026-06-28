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

from flask import Flask, abort, redirect, render_template, request, send_file, url_for
from werkzeug.serving import make_server

import storage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IDLE_TIMEOUT_SECONDS = 90

logging.getLogger("werkzeug").setLevel(logging.ERROR)

server = None
last_request_time = time.time()
shutdown_requested = False


def resource_path(relative):
    base = sys._MEIPASS if getattr(sys, "frozen", False) else BASE_DIR
    return os.path.join(base, relative)


def exe_dir():
    return os.path.dirname(os.path.abspath(sys.argv[0]))


app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static"),
)


@app.template_filter("fmt_invoice_number")
def _fmt_invoice_number(number):
    return format_invoice_number(number)


@app.template_filter("fmt_invoice_date")
def _fmt_invoice_date(iso_date):
    return format_invoice_date(iso_date)


@app.template_filter("fmt_invoice_amount")
def _fmt_invoice_amount(inv):
    return format_money(Decimal(inv["total_inc_gst"]))


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
    else:
        descriptions = req.args.getlist("item_description")
        amounts = req.args.getlist("item_amount")
        quantities = req.args.getlist("item_quantity")
        customer = req.args.get("customer", "")
        comment = req.args.get("comment", "")

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
    }


def render_create_invoice(form, error=None):
    settings = storage.load_settings()
    customers = storage.load_customers()
    return render_template(
        "create_invoice.html",
        customers=customers,
        invoice_counter=format_invoice_number(settings["invoice_counter"]),
        form=form,
        error=error,
    )


def invoices_by_status(invoices):
    groups = {"not_sent": [], "sent": [], "paid": []}
    for invoice in invoices.values():
        status = invoice.get("status", "not_sent")
        if status in groups:
            groups[status].append(invoice)

    def sort_key(inv):
        return (inv.get("invoice_date", ""), inv.get("invoice_number", 0))

    for status in groups:
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
        return render_create_invoice(form)

    settings = storage.load_settings()
    customers = storage.load_customers()
    form = {
        "customer": request.args.get("customer", ""),
        "comment": request.args.get("comment", ""),
        "line_items": [{"description": "", "amount": "", "qty": "1"}],
    }
    return render_template(
        "create_invoice.html",
        customers=customers,
        invoice_counter=format_invoice_number(settings["invoice_counter"]),
        form=form,
        error=request.args.get("error"),
    )


@app.route("/preview", methods=["POST"])
def preview_invoice():
    settings = storage.load_settings()
    customers = storage.load_customers()
    form = create_form_from_request(request)

    customer_name = form["customer"]
    comment = form["comment"]

    if not customer_name or customer_name not in customers:
        return render_create_invoice(form, error="Please select a customer.")

    try:
        items, subtotal, gst_amount, total_inc_gst = line_items_from_request(request.form)
    except ValueError as exc:
        return render_create_invoice(form, error=str(exc))

    customer = customers[customer_name]
    invoice_date = date.today()
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
        payment_terms=settings.get("payment_terms", ""),
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
    )


@app.route("/generate", methods=["POST"])
def generate():
    import pdf_generator

    settings = storage.load_settings()
    customers = storage.load_customers()

    customer_name = request.form.get("customer", "").strip()
    comment = request.form.get("comment", "").strip()

    if not customer_name or customer_name not in customers:
        return redirect(url_for("create_invoice", error="Please select a customer."))

    try:
        items, subtotal, gst_amount, total_inc_gst = line_items_from_request(request.form)
    except ValueError as exc:
        return redirect(url_for("create_invoice", error=str(exc)))

    customer = customers[customer_name]
    invoice_number = settings["invoice_counter"]
    invoice_date = date.today()

    invoice_data = {
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "business_name": settings.get("business_name", ""),
        "business_address": settings.get("business_address", ""),
        "business_abn": settings.get("business_abn", ""),
        "account_name": settings.get("account_name", ""),
        "bsb": settings.get("bsb", ""),
        "acc": settings.get("acc", ""),
        "payment_terms": settings.get("payment_terms", ""),
        "customer_name": customer_name,
        "customer_address": customer.get("address", ""),
        "customer_abn": customer.get("abn", ""),
        "line_items": items,
        "amount_ex_gst": subtotal,
        "gst_amount": gst_amount,
        "total_inc_gst": total_inc_gst,
        "comment": comment,
    }

    filepath = pdf_generator.generate_invoice(exe_dir(), invoice_data)
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
            "filename": filename,
        }
    )

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
    if ".." in filename or "/" in filename or "\\" in filename:
        abort(404)
    filepath = os.path.join(exe_dir(), filename)
    if not os.path.isfile(filepath):
        abort(404)
    return send_file(filepath, mimetype="application/pdf")


@app.route("/done")
def done():
    filename = request.args.get("file", "")
    invoice_number = request.args.get("invoice", "")
    customer = request.args.get("customer", "")
    marked_sent = request.args.get("sent") == "1"
    return render_template(
        "done.html",
        filename=filename,
        invoice_number=invoice_number,
        customer=customer,
        marked_sent=marked_sent,
    )


@app.route("/ping", methods=["POST"])
def ping():
    return "", 204


@app.route("/shutdown", methods=["GET", "POST"])
def shutdown():
    request_shutdown()
    return "OK", 200


@app.route("/invoices")
def invoices_list():
    invoices = storage.load_invoices()
    groups, sent_total = invoices_by_status(invoices)
    return render_template(
        "invoices.html",
        not_sent=groups["not_sent"],
        sent=groups["sent"],
        paid=groups["paid"],
        sent_total_fmt=format_money(sent_total),
        sent_count=len(groups["sent"]),
    )


@app.route("/invoices/<number>/status", methods=["POST"])
def invoice_update_status(number):
    number = unquote(number)
    status = request.form.get("status", "").strip()
    try:
        storage.update_invoice_status(number, status)
    except (KeyError, ValueError):
        abort(404)

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

        if not name:
            return render_template(
                "edit_customer.html",
                customer=None,
                form={"name": name, "address": address, "abn": abn},
                error="Please enter a customer name.",
                is_add=True,
            )

        customers = storage.load_customers()
        customers[name] = {"address": address, "abn": abn}
        storage.save_customers(customers)
        return redirect(url_for("customers_list"))

    return render_template(
        "edit_customer.html",
        customer=None,
        form={"name": "", "address": "", "abn": ""},
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
        customers[name] = {"address": address, "abn": abn}
        storage.save_customers(customers)
        return redirect(url_for("customers_list"))

    return render_template(
        "edit_customer.html",
        customer=name,
        form={"name": name, "address": customer.get("address", ""), "abn": customer.get("abn", "")},
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


@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    if request.method == "POST":
        settings = storage.load_settings()
        settings["business_name"] = request.form.get("business_name", "").strip()
        settings["business_address"] = request.form.get("business_address", "").strip()
        settings["business_abn"] = request.form.get("business_abn", "").strip()
        settings["account_name"] = request.form.get("account_name", "").strip()
        settings["bsb"] = request.form.get("bsb", "").strip()
        settings["acc"] = request.form.get("acc", "").strip()
        settings["payment_terms"] = request.form.get("payment_terms", "").strip()

        counter_raw = request.form.get("invoice_counter", "").strip()
        try:
            counter = int(counter_raw)
            if counter < 1:
                raise ValueError
            settings["invoice_counter"] = counter
        except ValueError:
            return render_template(
                "settings.html",
                settings=settings,
                error="Invoice number must be a whole number of 1 or more.",
            )

        storage.save_settings(settings)
        return redirect(url_for("home"))

    settings = storage.load_settings()
    return render_template("settings.html", settings=settings, error=None)


def open_browser_when_ready():
    url = "http://127.0.0.1:5000/"
    for _ in range(60):
        try:
            urllib.request.urlopen(url, timeout=0.2)
            webbrowser.open(url)
            return
        except OSError:
            time.sleep(0.05)
    webbrowser.open(url)


def main():
    global server
    storage.ensure_app_identity()
    server = make_server("127.0.0.1", 5000, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=idle_watchdog, daemon=True).start()
    threading.Thread(target=open_browser_when_ready, daemon=True).start()
    try:
        while not shutdown_requested:
            time.sleep(0.5)
    except KeyboardInterrupt:
        request_shutdown()


if __name__ == "__main__":
    main()
