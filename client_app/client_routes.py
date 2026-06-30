"""FrogsWork client routes: account, dashboard, backup."""

import io
import logging
import os
import shutil
import sys
import webbrowser
import zipfile
from datetime import date, datetime
from decimal import Decimal

from flask import (
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

import account_client
import account_sync
import billing_auth_store
import checkout_handoff
import entitlement_cache
import storage
import subscription_messages
import trial_stats
from account_client import AccountError, AccountOfflineError
from app_config import (
    SUBSCRIPTION_ANNUAL_DISPLAY,
    SUBSCRIPTION_ANNUAL_SAVINGS,
    SUBSCRIPTION_MONTHLY_DISPLAY,
)
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
        meter = trial_stats.meter_snapshot()
        auth = billing_auth_store.load_auth()
        cache = entitlement_cache.load_cache()
        email = auth.get("email", "") if billing_auth_store.is_authenticated() else ""
        sync_reminder = None
        if billing_auth_store.is_authenticated() and entitlement_cache.sync_status() == "reminder":
            sync_reminder = subscription_messages.SYNC_REMINDER
        return {
            "show_trial_usage": not billing_auth_store.is_authenticated(),
            "usage_meter": {
                "lifetime_invoice_count": meter["lifetime_invoice_count"],
                "max_invoices": meter["max_invoices"],
                "lifetime_ex_gst_fmt": format_money(meter["lifetime_ex_gst_total"]),
                "max_ex_gst_fmt": format_money(meter["max_ex_gst"]),
                "invoices_remaining": meter["invoices_remaining"],
                "amount_remaining_fmt": format_money(meter["amount_remaining_ex_gst"]),
                "trial_exhausted": meter["trial_exhausted"],
                "authenticated": billing_auth_store.is_authenticated(),
                "subscription_active": cache.get("active", False),
                "email": email,
            },
            "subscription_monthly_display": SUBSCRIPTION_MONTHLY_DISPLAY,
            "subscription_annual_display": SUBSCRIPTION_ANNUAL_DISPLAY,
            "subscription_annual_savings": SUBSCRIPTION_ANNUAL_SAVINGS,
            "subscription_sync_reminder": sync_reminder,
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
        # Finish the welcome flow by landing directly on Home.
        storage.mark_welcome_complete()
        return redirect(url_for("home"))

    @app.route("/dashboard")
    def dashboard():
        invoices = storage.load_active_invoices()
        groups, sent_total = helpers["invoices_by_status"](invoices)
        paid_total = sum(Decimal(inv.get("total_inc_gst", "0")) for inv in groups["paid"])
        meter = trial_stats.meter_snapshot()
        return render_template(
            "dashboard.html",
            month_invoiced_fmt=format_money(meter["lifetime_ex_gst_total"]),
            sent_total_fmt=format_money(sent_total),
            paid_total_fmt=format_money(paid_total),
            outstanding_count=len(groups["sent"]),
            usage=meter,
            usage_fmt={
                "lifetime_invoices": str(meter["lifetime_invoice_count"]),
                "lifetime_ex_gst": format_money(meter["lifetime_ex_gst_total"]),
            },
        )

    SIGNUP_STEPS = 3

    def _clear_signup_checkout_state():
        session.pop("signup_checkout_session_id", None)
        session.pop("signup_checkout_url", None)
        session.pop("awaiting_stripe_payment", None)
        checkout_handoff.clear_pending_checkout()

    def _merge_pending_checkout_into_session():
        pending = checkout_handoff.consume_pending_checkout()
        if pending:
            session["signup_checkout_session_id"] = pending["session_id"]
            session.pop("awaiting_stripe_payment", None)
            return pending["session_id"]
        return session.get("signup_checkout_session_id")

    def _checkout_session_info(checkout_session_id):
        """Return checkout session payload from API, or None if invalid."""
        if not checkout_session_id:
            return None
        try:
            return account_client.get_checkout_session_info(checkout_session_id)
        except (AccountError, AccountOfflineError):
            return None

    def _verified_checkout_session(checkout_session_id):
        """Return checkout email if paid and subscribed, else None."""
        info = _checkout_session_info(checkout_session_id)
        return info.get("email") if info else None

    def _finish_account_login():
        checkout_session_id = (session.get("signup_checkout_session_id") or "").strip()
        if checkout_session_id:
            try:
                account_client.attach_checkout_session(checkout_session_id)
            except AccountError:
                log.warning("Could not attach checkout after sign-in", exc_info=True)
            _clear_signup_checkout_state()
        account_sync.sync_entitlements_from_server()
        if session.get("invoice_draft"):
            return redirect(url_for("resume_preview"))
        return redirect(url_for("home"))

    def _finish_account_signup():
        _clear_signup_checkout_state()
        account_sync.sync_entitlements_from_server()
        if session.get("invoice_draft"):
            return redirect(url_for("resume_preview"))
        return redirect(url_for("home"))

    @app.route("/account/create", methods=["GET", "POST"])
    def account_create():
        if billing_auth_store.is_authenticated():
            return redirect(url_for("settings_account"))
        _clear_signup_checkout_state()
        return redirect(url_for("account_subscribe"))

    @app.route("/account/login", methods=["GET", "POST"])
    def account_login():
        if request.method == "POST":
            try:
                account_client.login(request.form.get("email", ""), request.form.get("password", ""))
                return _finish_account_login()
            except AccountOfflineError:
                return render_template(
                    "account_login.html",
                    error=subscription_messages.OFFLINE_CONNECT,
                    email=(request.form.get("email") or "").strip(),
                )
            except AccountError as exc:
                return render_template(
                    "account_login.html",
                    error=account_client.map_http_auth_error(str(exc)),
                    email=(request.form.get("email") or "").strip(),
                )
            except Exception:
                return render_template(
                    "account_login.html",
                    error=subscription_messages.GENERIC_ACCOUNT_ERROR,
                    email=(request.form.get("email") or "").strip(),
                )
        email = (request.args.get("email") or "").strip()
        return render_template("account_login.html", error=None, email=email)

    @app.route("/account/logout", methods=["POST"])
    def account_logout():
        account_client.logout()
        return redirect(url_for("home"))

    @app.route("/account/onboard/business", methods=["GET", "POST"])
    def account_onboard_business():
        """Optional business setup — not part of the subscribe wizard."""
        settings = storage.load_settings()
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
            return redirect(url_for("settings_page"))
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
        """Optional first customer — not part of the subscribe wizard."""
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
            return redirect(url_for("customers_list"))
        return render_template(
            "account_onboard_customer.html",
            error=None,
            form={"name": "", "address": "", "abn": "", "email": ""},
        )

    @app.route("/account/subscribe", methods=["GET", "POST"])
    def account_subscribe():
        if billing_auth_store.is_authenticated():
            return redirect(url_for("settings_account"))

        awaiting_payment = bool(session.get("awaiting_stripe_payment"))

        if request.method == "GET" and not awaiting_payment:
            _clear_signup_checkout_state()
        elif awaiting_payment:
            checkout_session_id = (
                _merge_pending_checkout_into_session()
                or session.get("signup_checkout_session_id")
                or ""
            )
            if checkout_session_id and _verified_checkout_session(checkout_session_id):
                return redirect(url_for("account_password"))

        checkout_url = session.get("signup_checkout_url")
        error = None
        opened_checkout = False

        if request.method == "POST":
            if not request.form.get("accept_terms"):
                error = "Accept the Terms and Privacy Policy to continue."
            else:
                plan = request.form.get("plan", "monthly")
                link = account_client.payment_link_for_plan(plan)
                if not link:
                    error = (
                        "Payment links are not configured. "
                        "Set STRIPE_PAYMENT_LINK_MONTHLY and STRIPE_PAYMENT_LINK_ANNUAL, then restart the app."
                    )
                else:
                    checkout_url = link
                    session["signup_checkout_url"] = link
                    session["awaiting_stripe_payment"] = True
                    webbrowser.open(link)
                    opened_checkout = True
                    awaiting_payment = True

        return render_template(
            "account_subscribe.html",
            error=error,
            checkout_url=checkout_url,
            opened_checkout=opened_checkout,
            awaiting_payment=awaiting_payment,
            has_monthly_link=bool(account_client.payment_link_for_plan("monthly")),
            has_annual_link=bool(account_client.payment_link_for_plan("annual")),
            signup_steps=SIGNUP_STEPS,
        )

    @app.route("/account/subscribe/status")
    def account_subscribe_status():
        if not session.get("awaiting_stripe_payment"):
            return {"ready": False}
        checkout_session_id = (
            _merge_pending_checkout_into_session()
            or session.get("signup_checkout_session_id")
            or ""
        )
        if checkout_session_id and _verified_checkout_session(checkout_session_id):
            return {"ready": True, "redirect": url_for("account_password")}
        if checkout_session_id and not _verified_checkout_session(checkout_session_id):
            _clear_signup_checkout_state()
        return {"ready": False}

    @app.route("/account/subscribe/restart", methods=["POST"])
    def account_subscribe_restart():
        if billing_auth_store.is_authenticated():
            return redirect(url_for("settings_account"))
        _clear_signup_checkout_state()
        flash(
            "Start again and use a different email at Stripe checkout if you need a new account.",
            "info",
        )
        return redirect(url_for("account_subscribe"))

    @app.route("/account/stripe/return")
    def account_stripe_return():
        session_id = request.args.get("session_id", "").strip()
        if not session_id.startswith("cs_"):
            return render_template(
                "account_stripe_return.html",
                ok=False,
                message="Payment return missing a valid session ID. Try paying again from the app.",
            )
        checkout_handoff.save_pending_checkout(session_id)
        return render_template(
            "account_stripe_return.html",
            ok=True,
            message="Payment received. Switch back to the FrogsWork window. It will continue automatically.",
        )

    @app.route("/account/password", methods=["GET", "POST"])
    def account_password():
        if billing_auth_store.is_authenticated():
            return redirect(url_for("home"))

        checkout_session_id = (
            request.args.get("checkout_session_id")
            or _merge_pending_checkout_into_session()
            or session.get("signup_checkout_session_id")
            or ""
        ).strip()
        if not checkout_session_id:
            return redirect(url_for("account_subscribe"))

        checkout_info = _checkout_session_info(checkout_session_id)
        email = checkout_info.get("email") if checkout_info else None
        if not email:
            _clear_signup_checkout_state()
            flash(
                "Payment could not be verified. Choose a plan and pay again.",
                "error",
            )
            return redirect(url_for("account_subscribe"))

        session["signup_checkout_session_id"] = checkout_session_id
        account_exists = bool(checkout_info.get("account_exists"))

        if request.method == "POST" and not account_exists:
            password = request.form.get("password", "")
            password_confirm = request.form.get("password_confirm", "")
            checkout_session_id = request.form.get("checkout_session_id", checkout_session_id).strip()
            if not password or len(password) < 8:
                return render_template(
                    "account_password.html",
                    error="Password must be at least 8 characters.",
                    email=email,
                    checkout_session_id=checkout_session_id,
                    signup_steps=SIGNUP_STEPS,
                    account_exists=False,
                )
            if password != password_confirm:
                return render_template(
                    "account_password.html",
                    error="Passwords do not match.",
                    email=email,
                    checkout_session_id=checkout_session_id,
                    signup_steps=SIGNUP_STEPS,
                    account_exists=False,
                )
            try:
                account_client.register(password, checkout_session_id)
                return _finish_account_signup()
            except AccountOfflineError:
                return render_template(
                    "account_password.html",
                    error=subscription_messages.SIGNUP_OFFLINE,
                    email=email,
                    checkout_session_id=checkout_session_id,
                    signup_steps=SIGNUP_STEPS,
                    account_exists=False,
                )
            except AccountError as exc:
                err_text = str(exc)
                already_registered = "already" in err_text.lower() and "registered" in err_text.lower()
                return render_template(
                    "account_password.html",
                    error=account_client.map_http_auth_error(err_text) if not already_registered else None,
                    email=email,
                    checkout_session_id=checkout_session_id,
                    signup_steps=SIGNUP_STEPS,
                    account_exists=already_registered,
                )
            except Exception:
                log.exception("Account signup failed")
                return render_template(
                    "account_password.html",
                    error=subscription_messages.GENERIC_ACCOUNT_ERROR,
                    email=email,
                    checkout_session_id=checkout_session_id,
                    signup_steps=SIGNUP_STEPS,
                    account_exists=False,
                )

        return render_template(
            "account_password.html",
            error=None,
            email=email,
            checkout_session_id=checkout_session_id,
            signup_steps=SIGNUP_STEPS,
            account_exists=account_exists,
        )

    @app.route("/account/done")
    def account_done():
        return _finish_account_signup()

    @app.route("/account/cap-settings")
    def account_cap_settings():
        return redirect(url_for("settings_account"))

    @app.route("/account/cap")
    def account_cap():
        return redirect(url_for("account_subscribe"))

    @app.route("/account/repair-ledger", methods=["POST"])
    def account_repair_ledger():
        flash("Trial totals come from your invoices automatically.", "info")
        return redirect(url_for("settings_account"))

    @app.route("/backup/export", methods=["POST"])
    def backup_export():
        from backup_service import BackupExportError, build_backup_zip, export_backup_with_dialog
        from desktop_shell import is_desktop_mode

        if is_desktop_mode() or sys.platform == "win32":
            try:
                path = export_backup_with_dialog(exe_dir())
                if path:
                    flash(f"Backup saved to {path}", "success")
                else:
                    flash("Backup cancelled.", "info")
            except BackupExportError as exc:
                flash(str(exc), "error")
            return redirect(url_for("backup_import"))

        buf, stamp = build_backup_zip(exe_dir())
        return send_file(
            buf,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"FrogsWork-backup_{stamp}.zip",
        )

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
            flash("Backup restored. Your data was replaced from the ZIP.", "success")
            return redirect(url_for("backup_import"))
        return render_template("backup_import.html", error=None)

