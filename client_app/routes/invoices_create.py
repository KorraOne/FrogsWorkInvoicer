"""Invoice create, preview, and generate routes."""

import os
from datetime import date

from flask import flash, redirect, render_template, request, url_for

import storage
from account import entitlement_guard
from invoicing.due_dates import due_rule_from_form_data, merge_due_rule_into_form, save_last_due_prefs
from invoicing.format import format_invoice_number, parse_invoice_number_input, persist_invoice_counter
from invoicing.form import (
    clear_invoice_draft,
    create_form_from_request,
    create_invoice_template_context,
    due_context_from_form,
    get_invoice_draft,
    invoice_summary_description,
    line_items_from_request,
    render_create_invoice,
    render_preview_from_form,
    save_invoice_draft,
)
from invoicing.gst_settings import is_gst_registered, validate_business_gst_settings


def register_invoice_create_routes(app):
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
                "business": "",
                "comment": "",
                "line_items": [{"description": "", "amount": "", "qty": "1"}],
            }

        settings = storage.load_settings()
        merge_due_rule_into_form(form, settings)
        ctx = create_invoice_template_context(form, error=request.args.get("error"))
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
            return redirect(url_for("create_invoice", error="Enter a customer name."))

        if storage.customer_name_exists(name):
            return redirect(url_for("create_invoice", error="A customer with this name already exists."))

        customers = storage.load_customers()
        customers[name] = {"address": address, "abn": abn, "email": email}
        storage.save_customers(customers)
        from account import telemetry

        telemetry.send_event("first_customer")

        form["customer"] = name
        save_invoice_draft(form)
        return redirect(url_for("create_invoice", customer_added=1))

    @app.route("/preview", methods=["POST"])
    def preview_invoice():
        form = create_form_from_request(request)
        return render_preview_from_form(form)

    @app.route("/preview/resume", methods=["GET"])
    def resume_preview():
        draft = get_invoice_draft()
        if not draft:
            return redirect(url_for("create_invoice"))
        return render_preview_from_form(draft)

    @app.route("/generate", methods=["POST"])
    def generate():
        from invoicing import pdf_generator

        settings = storage.load_settings()
        customers = storage.load_customers()
        businesses = storage.load_businesses()

        if not businesses:
            return redirect(
                url_for("create_invoice", error="Set up your business details before creating an invoice.")
            )

        customer_name = request.form.get("customer", "").strip()
        business_name, business_profile = storage.resolve_business(request.form.get("business", "").strip())
        comment = request.form.get("comment", "").strip()

        if not business_name:
            return redirect(url_for("create_invoice", error="Select which business to invoice from."))

        if not customer_name or customer_name not in customers:
            return redirect(url_for("create_invoice", error="Select a customer."))

        gst_err = validate_business_gst_settings(business_profile)
        if gst_err:
            return redirect(url_for("create_invoice", error=gst_err))

        gst_registered = is_gst_registered(business_profile)
        try:
            items, subtotal, gst_amount, total_inc_gst, taxable_ex_gst, gst_free_ex_gst = line_items_from_request(
                request.form, gst_registered=gst_registered
            )
        except ValueError as exc:
            return redirect(url_for("create_invoice", error=str(exc)))

        allowed, gate_status, gate_message = entitlement_guard.check_generate_access()
        if not allowed:
            save_invoice_draft(create_form_from_request(request))
            if gate_status in ("account_required", "subscribe_required"):
                flash(gate_message, "info")
                return redirect(url_for("account_subscribe"))
            flash(gate_message, "error")
            return redirect(url_for("resume_preview"))

        customer = customers[customer_name]
        invoice_date = date.today()
        form_data = create_form_from_request(request)
        due = due_context_from_form(form_data, invoice_date)

        try:
            invoice_number = parse_invoice_number_input(request.form.get("invoice_number"))
        except ValueError as exc:
            save_invoice_draft(form_data)
            return redirect(url_for("create_invoice", error=str(exc)))

        if storage.get_invoice(invoice_number):
            save_invoice_draft(form_data)
            return redirect(
                url_for(
                    "create_invoice",
                    error=f"Invoice number {format_invoice_number(invoice_number)} is already used.",
                )
            )

        invoice_data = {
            "invoice_number": invoice_number,
            "invoice_date": invoice_date,
            **storage.business_invoice_fields(business_name, business_profile),
            "due_date": due["due_date"],
            "due_date_fmt": due["due_date_fmt"],
            "due_rule_label": due["due_rule_label"],
            "customer_name": customer_name,
            "customer_address": customer.get("address", ""),
            "customer_abn": customer.get("abn", ""),
            "line_items": items,
            "amount_ex_gst": subtotal,
            "taxable_ex_gst": taxable_ex_gst,
            "gst_free_ex_gst": gst_free_ex_gst,
            "gst_amount": gst_amount,
            "total_inc_gst": total_inc_gst,
            "comment": comment,
            "gst_registered": gst_registered,
        }

        filepath = pdf_generator.generate_invoice(storage.get_pdf_dir(), invoice_data)
        filename = os.path.basename(filepath)

        rule = due_rule_from_form_data(form_data, settings)
        save_last_due_prefs(settings, rule)
        storage.save_settings(settings)
        persist_invoice_counter(business_name, invoice_number)

        storage.add_invoice(
            {
                "invoice_number": invoice_number,
                "invoice_date": invoice_date.isoformat(),
                "business_name": business_name,
                "customer_name": customer_name,
                "description": invoice_summary_description(items),
                "total_inc_gst": str(total_inc_gst),
                "amount_ex_gst": str(subtotal),
                "gst_amount": str(gst_amount),
                "gst_registered": gst_registered,
                "filename": filename,
                "due_date": due["due_date_iso"],
                "due_rule_type": due["due_rule_type"],
                "due_net_days": due["due_net_days"],
                "due_fixed_date": due.get("due_fixed_date"),
            }
        )

        clear_invoice_draft()
        from account import telemetry

        telemetry.after_invoice_generated()
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
        from app_platform import resolve_pdf_path
        from flask import send_file

        filepath = resolve_pdf_path(filename)
        return send_file(filepath, mimetype="application/pdf")

    @app.route("/done")
    def done():
        from flask import session

        filename = request.args.get("file", "")
        invoice_number = request.args.get("invoice", "")
        customer = request.args.get("customer", "")
        marked_sent = request.args.get("sent") == "1"
        sent_date = None
        send_later = False

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
                send_later = session.get(f"send_later_{inv_key}", False)

        step2_complete = marked_sent or send_later

        return render_template(
            "done.html",
            filename=filename,
            invoice_number=invoice_number,
            customer=customer,
            marked_sent=marked_sent,
            sent_date=sent_date,
            send_later=send_later,
            step2_complete=step2_complete,
        )
