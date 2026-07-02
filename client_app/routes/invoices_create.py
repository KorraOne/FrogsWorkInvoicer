"""Invoice create, preview, and generate routes."""

import os
import re
import shutil
import uuid
from datetime import date

from flask import abort, flash, redirect, render_template, request, send_file, session, url_for

import storage
from account import entitlement_guard
from invoicing.address import format_address_multiline, normalize_au_address
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
from invoicing.validators import normalize_abn


def _staging_photos_dir(token):
    base = os.path.join(storage.get_data_path(), "staging", "invoice_attachments", token)
    os.makedirs(base, exist_ok=True)
    return base


def _safe_photo_filename(index, ext):
    ext = (ext or "").lower().strip(".")
    if ext not in ("jpg", "jpeg", "png"):
        ext = "jpg"
    return f"photo_{index:02d}.{ext if ext != 'jpeg' else 'jpg'}"


def _save_uploaded_work_photos(form, files):
    files = list(files or [])
    if not files:
        return

    token = (form.get("work_photos_token") or "").strip()
    if not token:
        token = uuid.uuid4().hex
        form["work_photos_token"] = token

    existing = list(form.get("work_photos") or [])
    if len(existing) >= 6:
        raise ValueError("You can attach up to 6 photos.")

    from PIL import Image

    out_dir = _staging_photos_dir(token)
    for f in files:
        if len(existing) >= 6:
            break
        if not f or not getattr(f, "filename", ""):
            continue
        ext = os.path.splitext(f.filename)[1].lower().strip(".")
        out_name = _safe_photo_filename(len(existing) + 1, ext)
        out_path = os.path.join(out_dir, out_name)

        try:
            img = Image.open(f.stream)
            if img.mode in ("RGBA", "LA"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1])
                img = bg
            else:
                img = img.convert("RGB")
            max_w = 1600
            max_h = 1600
            if img.width > max_w or img.height > max_h:
                img.thumbnail((max_w, max_h))
            img.save(out_path, format="JPEG", quality=85, optimize=True)
        except Exception:
            continue

        existing.append(out_name)

    form["work_photos"] = existing


def _delete_staged_photo(token, filename):
    if not re.fullmatch(r"[a-f0-9]{32}", token or ""):
        return
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return
    path = os.path.join(_staging_photos_dir(token), filename)
    if os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


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
        address_line1 = request.form.get("new_customer_address_line1", "").strip()
        address_line2 = request.form.get("new_customer_address_line2", "").strip()
        suburb = request.form.get("new_customer_suburb", "").strip()
        state = request.form.get("new_customer_state", "").strip()
        postcode = request.form.get("new_customer_postcode", "").strip()
        abn = request.form.get("new_customer_abn", "").strip()
        email = request.form.get("new_customer_email", "").strip()

        if not name:
            return redirect(url_for("create_invoice", error="Enter a customer name."))

        if storage.customer_name_exists(name):
            return redirect(url_for("create_invoice", error="A customer with this name already exists."))

        try:
            addr = normalize_au_address(
                line1=address_line1,
                line2=address_line2,
                suburb=suburb,
                state=state,
                postcode=postcode,
            )
            abn = normalize_abn(abn)
        except ValueError as exc:
            return redirect(url_for("create_invoice", error=str(exc)))

        customers = storage.load_customers()
        customers[name] = {**addr, "abn": abn, "email": email}
        storage.save_customers(customers)
        from account import telemetry

        telemetry.send_event("first_customer")

        form["customer"] = name
        save_invoice_draft(form)
        return redirect(url_for("create_invoice", customer_added=1))

    @app.route("/preview", methods=["POST"])
    def preview_invoice():
        form = create_form_from_request(request)
        try:
            _save_uploaded_work_photos(form, request.files.getlist("work_photos"))
        except ValueError as exc:
            save_invoice_draft(form)
            return redirect(url_for("create_invoice", error=str(exc)))
        return render_preview_from_form(form)

    @app.route("/preview/resume", methods=["GET"])
    def resume_preview():
        draft = get_invoice_draft()
        if not draft:
            return redirect(url_for("create_invoice"))
        return render_preview_from_form(draft)

    @app.route("/preview/photo/<token>/<filename>")
    def preview_photo(token, filename):
        if not re.fullmatch(r"[a-f0-9]{32}", token or ""):
            abort(404)
        if not filename or ".." in filename or "/" in filename or "\\" in filename:
            abort(404)
        path = os.path.join(_staging_photos_dir(token), filename)
        if not os.path.isfile(path):
            abort(404)
        return send_file(path)

    @app.route("/preview/remove-photo", methods=["POST"])
    def preview_remove_photo():
        draft = get_invoice_draft() or {}
        token = (draft.get("work_photos_token") or "").strip()
        filename = (request.form.get("filename") or "").strip()
        photos = list(draft.get("work_photos") or [])
        if filename in photos:
            photos = [p for p in photos if p != filename]
            draft["work_photos"] = photos
            save_invoice_draft(draft)
            _delete_staged_photo(token, filename)
        return redirect(url_for("resume_preview"))

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
            "customer_address": format_address_multiline(customer) or customer.get("address", ""),
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

        draft = get_invoice_draft() or {}
        token = (draft.get("work_photos_token") or "").strip()
        staged_files = list(draft.get("work_photos") or [])
        attachments = []
        work_photo_paths = []
        if token and staged_files:
            dest_dir = storage.invoice_attachments_dir(invoice_number)
            staging_dir = _staging_photos_dir(token)
            for name in staged_files:
                if not name or ".." in name or "/" in name or "\\" in name:
                    continue
                src = os.path.join(staging_dir, name)
                if not os.path.isfile(src):
                    continue
                dest = os.path.join(dest_dir, name)
                shutil.copyfile(src, dest)
                attachments.append(name)
                work_photo_paths.append(dest)
            try:
                shutil.rmtree(staging_dir, ignore_errors=True)
            except Exception:
                pass

        if work_photo_paths:
            invoice_data["work_photos"] = work_photo_paths

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
                "attachments": attachments,
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
