"""FrogsWork client routes: billing UI, account, dashboard, backup."""

import io
import logging
import os
import shutil
import zipfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import (
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

import billing_auth_store
import billing_client
import billing_core
import billing_ledger
import billing_local
import billing_messages
import storage
from billing_client import BillingError, BillingOfflineError
from gst_settings import apply_gst_registered_to_settings, validate_business_gst_settings

log = logging.getLogger(__name__)


def _settings_have_business(settings):
    return bool((settings.get("business_name") or "").strip())


def _has_any_customers():
    return bool(storage.load_customers())


def register_client_routes(app, helpers):
    """Register FrogsWork routes on the Flask app."""
    format_money = helpers["format_money"]
    format_invoice_number = helpers["format_invoice_number"]
    exe_dir = helpers["exe_dir"]

    @app.context_processor
    def inject_usage_meter():
        usage = billing_local.meter_snapshot()
        cap = usage.get("cap_amount_ex_gst")
        cap_label = "off"
        cap_detail = ""
        if usage.get("cap_enabled") and cap:
            cap_label = format_money(cap)
            room = cap - usage.get("month_total_ex_gst", Decimal("0"))
            if room < 0:
                room = Decimal("0")
            max_fee = billing_core.max_fee_at_cap(cap)
            cap_detail = f"({format_money(room)} room · ~{format_money(max_fee)} max fee)"
        auth = billing_auth_store.load_auth()
        email = auth.get("email", "") if usage.get("account_authenticated") else ""
        month_total = Decimal(str(usage.get("month_total_ex_gst", 0)))
        free_tier = billing_core.FREE_TIER_EX_GST
        free_remaining = Decimal(str(usage.get("free_remaining", billing_core.free_remaining(month_total))))
        free_used = month_total if month_total <= free_tier else free_tier
        used_pct = int((free_used / free_tier * 100).quantize(Decimal("1"))) if free_tier else 0
        if used_pct < 0:
            used_pct = 0
        if used_pct > 100:
            used_pct = 100
        free_allowance_full = free_remaining <= 0
        free_allowance_over = month_total > free_tier
        return {
            "billing_constants": {
                "free_tier": str(billing_core.FREE_TIER_EX_GST),
                "fee_rate": str(billing_core.FEE_RATE),
            },
            "usage_meter": {
                "month_invoiced_fmt": format_money(month_total),
                "fee_so_far_fmt": format_money(usage.get("fee_so_far", 0)),
                "free_remaining_fmt": format_money(free_remaining),
                "free_allowance_used_fmt": format_money(free_used),
                "free_allowance_used_pct": used_pct,
                "free_allowance_full": free_allowance_full,
                "free_allowance_over": free_allowance_over,
                "cap_label": cap_label,
                "cap_detail": cap_detail,
                "authenticated": usage.get("account_authenticated", False),
                "email": email,
            },
        }

    WELCOME_EXEMPT_ENDPOINTS = {
        "welcome_start",
        "welcome_pricing",
        "welcome_done",
        "ping",
        "static",
    }

    @app.before_request
    def require_welcome_complete():
        if storage.is_welcome_complete():
            return None
        endpoint = request.endpoint
        if endpoint in WELCOME_EXEMPT_ENDPOINTS:
            return None
        if request.path == "/shutdown":
            return None
        return redirect(url_for("welcome_start"))

    @app.route("/welcome")
    def welcome_start():
        return render_template("welcome_start.html")

    @app.route("/welcome/pricing")
    def welcome_pricing():
        return render_template("welcome_pricing.html")

    @app.route("/welcome/data")
    def welcome_data():
        return redirect(url_for("welcome_done"))

    @app.route("/welcome/done", methods=["GET", "POST"])
    def welcome_done():
        if request.method == "POST":
            storage.mark_welcome_complete()
            if request.form.get("next") == "account":
                return redirect(url_for("account_create"))
            return redirect(url_for("home"))
        return render_template("welcome_done.html")

    @app.route("/dashboard")
    def dashboard():
        invoices = storage.load_active_invoices()
        groups, sent_total = helpers["invoices_by_status"](invoices)
        usage = billing_local.meter_snapshot()
        paid_total = sum(Decimal(inv.get("total_inc_gst", "0")) for inv in groups["paid"])
        month_invoiced = Decimal("0")
        month_prefix = date.today().strftime("%Y-%m")
        for inv in storage.load_invoices().values():
            if inv.get("invoice_date", "").startswith(month_prefix):
                month_invoiced += Decimal(inv.get("amount_ex_gst", inv.get("total_inc_gst", "0")))
        return render_template(
            "dashboard.html",
            month_invoiced_fmt=format_money(month_invoiced),
            sent_total_fmt=format_money(sent_total),
            paid_total_fmt=format_money(paid_total),
            outstanding_count=len(groups["sent"]),
            usage=usage,
            usage_fmt={
                "month_invoiced": format_money(usage.get("month_total_ex_gst", 0)),
                "fee_so_far": format_money(usage.get("fee_so_far", 0)),
                "free_remaining": format_money(usage.get("free_remaining", 0)),
            },
        )

    def _redirect_after_business_onboard():
        if _has_any_customers():
            return redirect(url_for("account_cap"))
        return redirect(url_for("account_onboard_customer"))

    def _redirect_after_email_signup():
        settings = storage.load_settings()
        if not _settings_have_business(settings):
            return redirect(url_for("account_onboard_business"))
        return _redirect_after_business_onboard()

    @app.route("/account/login", methods=["GET", "POST"])
    def account_login():
        if request.method == "POST":
            try:
                billing_client.login(request.form.get("email", ""), request.form.get("password", ""))
                import billing_sync

                billing_sync.sync_usage_from_server()
                if session.get("invoice_draft"):
                    return redirect(url_for("resume_preview"))
                return redirect(url_for("home"))
            except BillingOfflineError:
                return render_template(
                    "account_login.html",
                    error=billing_messages.OFFLINE_CONNECT,
                )
            except BillingError as exc:
                return render_template(
                    "account_login.html",
                    error=billing_messages.map_http_auth_error(str(exc)),
                )
            except Exception:
                return render_template(
                    "account_login.html",
                    error=billing_messages.GENERIC_BILLING_ERROR,
                )
        return render_template("account_login.html", error=None)

    @app.route("/account/logout", methods=["POST"])
    def account_logout():
        billing_client.logout()
        return redirect(url_for("home"))

    @app.route("/account/create", methods=["GET", "POST"])
    def account_create():
        if request.method == "POST":
            email = request.form.get("email", "").strip()
            if not email:
                return render_template("account_create.html", error="Email is required.")
            session["signup_email"] = email
            return _redirect_after_email_signup()
        return render_template("account_create.html", error=None)

    def _require_signup_session():
        if not session.get("signup_email"):
            return redirect(url_for("account_create"))
        return None

    @app.route("/account/onboard/business", methods=["GET", "POST"])
    def account_onboard_business():
        guard = _require_signup_session()
        if guard:
            return guard
        settings = storage.load_settings()
        if request.method == "GET" and _settings_have_business(settings):
            return _redirect_after_business_onboard()
        if request.method == "POST":
            business_name = request.form.get("business_name", "").strip()
            business_address = request.form.get("business_address", "").strip()
            business_abn = request.form.get("business_abn", "").strip()
            if business_name:
                settings["business_name"] = business_name
            if business_address:
                settings["business_address"] = business_address
            settings["business_abn"] = business_abn
            apply_gst_registered_to_settings(settings, request.form)
            gst_err = validate_business_gst_settings(settings)
            if gst_err:
                return render_template(
                    "account_onboard_business.html",
                    error=gst_err,
                    form={
                        "business_name": business_name or settings.get("business_name", ""),
                        "business_address": business_address or settings.get("business_address", ""),
                        "business_abn": business_abn,
                        "gst_registered": settings.get("gst_registered", False),
                    },
                )
            storage.save_settings(settings)
            return _redirect_after_business_onboard()
        return render_template(
            "account_onboard_business.html",
            error=None,
            form={
                "business_name": settings.get("business_name", ""),
                "business_address": settings.get("business_address", ""),
                "business_abn": settings.get("business_abn", ""),
                "gst_registered": settings.get("gst_registered", False),
            },
        )

    @app.route("/account/onboard/customer", methods=["GET", "POST"])
    def account_onboard_customer():
        guard = _require_signup_session()
        if guard:
            return guard
        if request.method == "GET" and _has_any_customers():
            return redirect(url_for("account_cap"))
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            address = request.form.get("address", "").strip()
            abn = request.form.get("abn", "").strip()
            email = request.form.get("email", "").strip()
            if name:
                if storage.customer_name_exists(name):
                    return render_template(
                        "account_onboard_customer.html",
                        error="A customer with this name already exists.",
                        form={"name": name, "address": address, "abn": abn, "email": email},
                    )
                customers = storage.load_customers()
                customers[name] = {"address": address, "abn": abn, "email": email}
                storage.save_customers(customers)
            return redirect(url_for("account_cap"))
        return render_template(
            "account_onboard_customer.html",
            error=None,
            form={"name": "", "address": "", "abn": "", "email": ""},
        )

    @app.route("/account/cap", methods=["GET", "POST"])
    def account_cap():
        email = session.get("signup_email", "")
        if request.method == "POST":
            cap_choice = request.form.get("cap_choice", "off")
            cap_amount = request.form.get("cap_amount", "").strip()
            email = request.form.get("email", email).strip()
            billing_cycle = request.form.get("billing_cycle", "quarterly")
            cap_enabled = cap_choice == "on"
            cap_val = None
            if cap_enabled:
                try:
                    cap_val = Decimal(cap_amount)
                    if cap_val <= 0:
                        raise ValueError
                except (ValueError, InvalidOperation):
                    return render_template(
                        "account_cap.html",
                        error="Enter a valid cap amount.",
                        email=email,
                        form=request.form,
                    )
            session["signup_email"] = email
            session["signup_cap"] = {
                "cap_enabled": cap_enabled,
                "cap_amount": str(cap_val) if cap_val is not None else None,
                "billing_cycle": billing_cycle,
            }
            return redirect(url_for("account_password"))
        if not email:
            return redirect(url_for("account_create"))
        return render_template("account_cap.html", error=None, email=email, form={})

    @app.route("/account/password", methods=["GET", "POST"])
    def account_password():
        email = session.get("signup_email", "")
        cap_data = session.get("signup_cap")
        if not email or not cap_data:
            return redirect(url_for("account_create"))
        if request.method == "POST":
            password = request.form.get("password", "")
            password_confirm = request.form.get("password_confirm", "")
            if not password or len(password) < 8:
                return render_template(
                    "account_password.html",
                    error="Password must be at least 8 characters.",
                    email=email,
                )
            if password != password_confirm:
                return render_template(
                    "account_password.html",
                    error="Passwords do not match.",
                    email=email,
                )
            cap_enabled = cap_data.get("cap_enabled", False)
            cap_val = None
            if cap_enabled and cap_data.get("cap_amount"):
                cap_val = Decimal(cap_data["cap_amount"])
            billing_cycle = cap_data.get("billing_cycle", "quarterly")
            try:
                billing_client.register(email, password, cap_enabled, cap_val, billing_cycle)
                billing_local.set_local_cap(cap_enabled, cap_val)
                import billing_sync

                billing_sync.sync_usage_from_server()
                session.pop("signup_email", None)
                session.pop("signup_cap", None)
                return redirect(url_for("account_done"))
            except BillingOfflineError:
                return render_template(
                    "account_password.html",
                    error=billing_messages.SIGNUP_OFFLINE,
                    email=email,
                )
            except BillingError as exc:
                return render_template(
                    "account_password.html",
                    error=billing_messages.map_http_auth_error(str(exc)),
                    email=email,
                )
            except billing_ledger.BillingIntegrityError:
                return render_template(
                    "account_password.html",
                    error=billing_messages.LEDGER_INVALID,
                    email=email,
                )
            except Exception:
                log.exception("Account signup failed")
                return render_template(
                    "account_password.html",
                    error=billing_messages.GENERIC_BILLING_ERROR,
                    email=email,
                )
        return render_template("account_password.html", error=None, email=email)

    @app.route("/account/done")
    def account_done():
        return render_template("account_done.html")

    @app.route("/account/cap-settings", methods=["GET", "POST"])
    def account_cap_settings():
        if not billing_auth_store.is_authenticated():
            return redirect(url_for("account_create"))
        if request.method == "POST":
            cap_choice = request.form.get("cap_choice", "off")
            cap_amount = request.form.get("cap_amount", "").strip()
            cap_enabled = cap_choice == "on"
            cap_val = None
            if cap_enabled:
                cap_val = Decimal(cap_amount)
            try:
                billing_client.update_cap(cap_enabled, cap_val)
                billing_local.set_local_cap(cap_enabled, cap_val)
                return redirect(url_for("settings_billing"))
            except BillingOfflineError:
                return render_template(
                    "account_cap_settings.html",
                    error=billing_messages.OFFLINE_SYNC,
                    cap_enabled=cap_enabled,
                    cap_amount=cap_amount,
                )
            except BillingError as exc:
                return render_template(
                    "account_cap_settings.html",
                    error=billing_messages.map_http_auth_error(str(exc)),
                    cap_enabled=cap_enabled,
                    cap_amount=cap_amount,
                )
        enabled, amount = billing_local.local_cap_settings()
        return render_template(
            "account_cap_settings.html",
            cap_enabled=enabled,
            cap_amount=str(amount) if amount else "",
            error=None,
        )

    @app.route("/account/repair-ledger", methods=["POST"])
    def account_repair_ledger():
        action = request.form.get("action", "rebuild")
        try:
            if action == "reset":
                billing_local.reset_usage_cache()
                flash(billing_messages.LEDGER_RESET, "success")
            else:
                billing_local.repair_ledger_from_invoices()
                flash(billing_messages.LEDGER_REPAIRED, "success")
        except billing_ledger.BillingIntegrityError:
            flash(billing_messages.LEDGER_REPAIR_FAILED, "error")
        return redirect(url_for("settings_account"))

    @app.route("/backup/export")
    def backup_export():
        buf = io.BytesIO()
        data_path = storage.get_data_path()
        pdf_dir = storage.get_pdf_dir()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in os.listdir(data_path):
                path = os.path.join(data_path, name)
                if os.path.isfile(path):
                    zf.write(path, name)
            if os.path.isdir(pdf_dir):
                for name in os.listdir(pdf_dir):
                    if name.lower().endswith(".pdf"):
                        zf.write(os.path.join(pdf_dir, name), f"pdfs/{name}")
            legacy_dir = exe_dir()
            if legacy_dir != pdf_dir and os.path.isdir(legacy_dir):
                for name in os.listdir(legacy_dir):
                    if name.lower().endswith(".pdf"):
                        arc = f"pdfs/{name}"
                        if arc not in zf.namelist():
                            zf.write(os.path.join(legacy_dir, name), arc)
        buf.seek(0)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return send_file(buf, mimetype="application/zip", as_attachment=True, download_name=f"backup_{stamp}.zip")

    @app.route("/backup/import", methods=["GET", "POST"])
    def backup_import():
        if request.method == "POST":
            file = request.files.get("backup_file")
            if not file:
                return render_template("backup_import.html", error="Choose a backup ZIP file.")
            data_path = storage.get_data_path()
            pdf_dir = storage.get_pdf_dir()
            os.makedirs(pdf_dir, exist_ok=True)
            with zipfile.ZipFile(file) as zf:
                for member in zf.namelist():
                    if member.startswith("pdfs/"):
                        target = os.path.join(pdf_dir, os.path.basename(member))
                        with zf.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                    elif not member.endswith("/"):
                        target = os.path.join(data_path, os.path.basename(member))
                        with zf.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
            return redirect(url_for("home"))
        return render_template("backup_import.html", error=None)

