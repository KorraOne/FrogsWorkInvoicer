"""Invoice creation, list, PDF, and send routes."""

import logging
import os
from datetime import date
from urllib.parse import unquote

from flask import abort, flash, g, redirect, render_template, request, send_file, session, url_for

import entitlement_guard
import storage
from due_dates import due_rule_from_form_data, merge_due_rule_into_form, save_last_due_prefs
from email_compose import EmailComposeError, build_invoice_email_context, format_clipboard_text, reveal_pdf_in_folder
from gst_settings import is_gst_registered, validate_business_gst_settings
from invoice_format import format_invoice_number, format_money, parse_invoice_number_input, persist_invoice_counter
from invoice_form import (
    clear_invoice_draft,
    create_form_from_request,
    create_invoice_template_context,
    due_context_from_form,
    get_invoice_draft,
    invoice_summary_description,
    invoices_by_status,
    line_items_from_request,
    render_create_invoice,
    render_preview_from_form,
    save_invoice_draft,
)
from paths import exe_dir, resolve_pdf_path

log = logging.getLogger(__name__)


def register_invoice_routes(app):
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
        import pdf_generator

        settings = storage.load_settings()
        customers = storage.load_customers()

        customer_name = request.form.get("customer", "").strip()
        comment = request.form.get("comment", "").strip()

        if not customer_name or customer_name not in customers:
            return redirect(url_for("create_invoice", error="Select a customer."))

        gst_err = validate_business_gst_settings(settings)
        if gst_err:
            return redirect(url_for("create_invoice", error=gst_err))

        gst_registered = is_gst_registered(settings)
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
        persist_invoice_counter(settings, invoice_number)
        storage.save_settings(settings)

        storage.add_invoice(
            {
                "invoice_number": invoice_number,
                "invoice_date": invoice_date.isoformat(),
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

    @app.route("/invoices")
    def invoices_list():
        invoices = storage.load_active_invoices()
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
        g.invoice_list_settings = storage.load_settings()

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
                filter_summary_parts.append(f"{date_from} to {date_to}")
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

    def _is_cancel_allowed(inv):
        if storage.is_invoice_deleted(inv):
            return False
        if inv.get("status") != "not_sent":
            return False
        invoices = storage.load_invoices()
        if not invoices:
            return False
        latest = max(int(record["invoice_number"]) for record in invoices.values())
        return int(inv["invoice_number"]) == latest

    def _delete_invoice_files(filename):
        storage.remove_invoice_pdf(filename)
        legacy = os.path.join(exe_dir(), filename)
        if filename and os.path.isfile(legacy):
            try:
                os.remove(legacy)
            except OSError:
                pass

    @app.route("/invoices/<number>/status", methods=["POST"])
    def invoice_update_status(number):
        number = unquote(number)
        status = request.form.get("status", "").strip()
        try:
            storage.set_invoice_status(number, status)
        except (KeyError, ValueError):
            abort(404)

        if status in ("sent", "not_sent"):
            _clear_invoice_send_session(number)

        status_labels = {"not_sent": "Not sent", "sent": "Sent", "paid": "Paid"}
        flash(f"Invoice moved to {status_labels.get(status, status)}.", "success")

        next_page = request.form.get("next", "invoices")
        if next_page == "done" and status == "sent":
            return redirect(url_for("home"))
        return redirect(url_for("invoices_list"))

    @app.route("/invoices/<number>/cancel", methods=["POST"])
    def invoice_cancel(number):
        number = unquote(number)
        inv = storage.get_invoice(number)
        if not inv:
            abort(404)
        if not _is_cancel_allowed(inv):
            flash("Only your newest not-sent invoice can be cancelled.", "error")
            return redirect(url_for("home"))

        filename = inv.get("filename", "")
        storage.hard_delete_invoice(number)
        _clear_invoice_send_session(number)
        _delete_invoice_files(filename)

        flash("Invoice cancelled.", "success")
        return redirect(url_for("home"))

    @app.route("/invoices/<number>/delete", methods=["POST"])
    def invoice_delete(number):
        number = unquote(number)
        inv = storage.get_invoice(number)
        if not inv:
            abort(404)

        filename = inv.get("filename", "")
        try:
            storage.soft_delete_invoice(number)
        except ValueError:
            abort(404)

        storage.archive_invoice_pdf(filename)
        _clear_invoice_send_session(number)

        flash("Invoice removed from your list.", "success")
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

    @app.route("/invoices/<number>/send")
    def invoice_send(number):
        number = unquote(number)
        next_page = request.args.get("next", "invoices")
        inv, ctx = _invoice_email_context(number)
        return render_template(
            "send_invoice.html",
            invoice_number=number,
            email_details=ctx,
            clipboard_text=format_clipboard_text(ctx),
            view_pdf_url=url_for("view_pdf", filename=inv.get("filename", "")),
            reveal_url=url_for("invoice_send_reveal_pdf", number=number),
            next_page=next_page,
            show_send_later=next_page == "done",
        )

    @app.route("/invoices/<number>/send/reveal-pdf", methods=["POST"])
    def invoice_send_reveal_pdf(number):
        number = unquote(number)
        next_page = request.form.get("next", request.args.get("next", "invoices"))
        inv, ctx = _invoice_email_context(number)
        try:
            reveal_pdf_in_folder(ctx["pdf_path"])
            flash("PDF folder opened.", "success")
        except EmailComposeError as exc:
            message = str(exc)
            if message.startswith("Opened the invoice folder"):
                flash(message, "info")
            else:
                flash(message, "error")
        except Exception:
            log.exception("Reveal PDF in folder failed for invoice %s", number)
            flash(
                "Couldn't open the PDF folder. Close any Explorer windows for this folder and try again.",
                "error",
            )
        return redirect(url_for("invoice_send", number=number, next=next_page))

    @app.route("/invoices/<number>/email/send")
    def invoice_email_send(number):
        number = unquote(number)
        next_page = request.args.get("next", "invoices")
        return redirect(url_for("invoice_send", number=number, next=next_page))

    @app.route("/invoices/<number>/send-later")
    def invoice_send_later(number):
        number = unquote(number)
        inv = storage.get_invoice(number)
        if not inv:
            abort(404)
        session[f"send_later_{format_invoice_number(number)}"] = True
        next_page = request.args.get("next", "invoices")
        if next_page == "done":
            return redirect(url_for("home"))
        return redirect(url_for("invoices_list"))
