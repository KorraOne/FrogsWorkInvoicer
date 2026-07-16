"""Invoice list, status, send, and delete routes."""

import logging
import os
from urllib.parse import unquote

from flask import abort, flash, g, redirect, render_template, request, session, url_for

import storage
from app_platform import exe_dir, resolve_pdf_path
from invoicing.email_compose import EmailComposeError, build_invoice_email_context, format_clipboard_text, reveal_pdf_in_folder
from invoicing.format import format_invoice_number, format_money
from invoicing.form import invoices_by_status

log = logging.getLogger(__name__)


def register_invoice_manage_routes(app):
    @app.route("/invoices")
    def invoices_list():
        invoices = storage.load_active_invoices()
        q = request.args.get("q", "").strip().lower()
        status_filter = request.args.get("status", "")
        customer_filter = request.args.get("customer", "")
        business_filter = request.args.get("business", "")
        date_from = request.args.get("from", "")
        date_to = request.args.get("to", "")

        businesses = storage.load_businesses()
        default_business = storage.get_default_business_name()
        show_business_filter = len(businesses) >= 2

        if q or status_filter or customer_filter or business_filter or date_from or date_to:
            filtered = {}
            for key, inv in invoices.items():
                if status_filter and inv.get("status") != status_filter:
                    continue
                if customer_filter and inv.get("customer_name") != customer_filter:
                    continue
                if business_filter:
                    inv_business = storage.invoice_business_name(inv) or default_business
                    if inv_business != business_filter:
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

        filters_active = bool(
            q or status_filter or customer_filter or business_filter or date_from or date_to
        )
        filter_summary_parts = []
        if q:
            filter_summary_parts.append(f'Search: "{q}"')
        if status_filter:
            labels = {"not_sent": "Not sent", "sent": "Sent", "paid": "Paid"}
            filter_summary_parts.append(labels.get(status_filter, status_filter))
        if customer_filter:
            filter_summary_parts.append(customer_filter)
        if business_filter:
            filter_summary_parts.append(f"From: {business_filter}")
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
            business_filter=business_filter,
            business_names=sorted(businesses.keys()) if show_business_filter else [],
            show_business_filter=show_business_filter,
            show_business_on_cards=show_business_filter,
            default_business=default_business,
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

        from account import telemetry

        if status == "sent":
            telemetry.send_event("first_invoice_sent")
        elif status == "paid":
            telemetry.send_event("first_paid_marked")

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
        storage.remove_invoice_attachments(number)
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
        storage.archive_invoice_attachments(number)
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

    @app.route("/invoices/<number>/send-integrated", methods=["POST"])
    def invoice_send_integrated(number):
        number = unquote(number)
        inv = storage.get_invoice(number)
        if not inv:
            abort(404)
        next_page = request.form.get("next", "invoices")
        try:
            from storage.context import use_cloud_provider, get_provider

            if use_cloud_provider():
                get_provider().enqueue_email_send(int(number))
            else:
                import base64

                from account import client as account_client

                customer = storage.load_customers().get(inv.get("customer_name", ""), {})
                settings = storage.load_settings()
                pdf_path = resolve_pdf_path(inv.get("filename", ""))
                pdf_b64 = None
                if pdf_path and os.path.isfile(pdf_path):
                    with open(pdf_path, "rb") as f:
                        pdf_b64 = base64.b64encode(f.read()).decode("ascii")
                ctx = build_invoice_email_context(inv, customer, settings, pdf_path or "")
                if not ctx.get("to"):
                    flash("Customer email is required for automatic send. Add an email to the customer first.", "error")
                    if next_page == "done":
                        return redirect(url_for("home"))
                    return redirect(url_for("invoices_list"))
                result = account_client.enqueue_invoice_send(
                    int(number),
                    pdf_b64=pdf_b64,
                    customer_email=ctx.get("to") or None,
                    filename=ctx.get("pdf_filename") or None,
                    subject=ctx.get("subject") or None,
                    body_text=ctx.get("body") or None,
                )
            if not use_cloud_provider() and isinstance(result, dict) and result.get("status") == "sent":
                storage.set_invoice_status(number, "sent")
                flash("Invoice sent by email.", "success")
            else:
                storage.set_invoice_status(number, "send_queued")
                flash("Sending automatically…", "success")
        except Exception:
            log.exception("Integrated send failed for invoice %s", number)
            flash("Couldn't queue email send. Try again when online.", "error")
        if next_page == "done":
            return redirect(url_for("home"))
        return redirect(url_for("invoices_list"))

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
