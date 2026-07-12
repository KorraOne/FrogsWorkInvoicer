"""Account login handoff and onboarding routes."""

import logging
import urllib.parse

from flask import flash, redirect, render_template, request, url_for

import storage
from account import auth_store, client, sync
from app_config import WEB_ACCOUNT_LOGIN_URL, WEB_ACCOUNT_SIGNUP_URL, WEB_ACCOUNT_UPGRADE_CLOUD_URL
from app_platform.external_browser import open_external
from invoicing.form import has_invoice_draft
from invoicing.gst_settings import validate_business_gst_settings
from invoicing.address import normalize_au_address
from invoicing.validators import normalize_abn

log = logging.getLogger(__name__)


def register_account_routes(app):
    def _web_signup_url():
        from account import telemetry

        install_id = telemetry.install_id()
        base = WEB_ACCOUNT_SIGNUP_URL
        if install_id:
            return f"{base}?install_id={urllib.parse.quote(install_id)}"
        return base

    def _web_login_url(email=""):
        url = WEB_ACCOUNT_LOGIN_URL
        if email:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}email={urllib.parse.quote(email)}"
        return url

    def _open_in_external_browser(url, *, purpose, retry_endpoint):
        open_external(url)
        return render_template(
            "account_external.html",
            purpose=purpose,
            retry_url=url_for(retry_endpoint),
        )

    def _finish_account_login():
        sync.sync_entitlements_from_server()
        if has_invoice_draft():
            return redirect(url_for("resume_preview"))
        return redirect(url_for("home"))

    @app.route("/account/login", methods=["GET", "POST"])
    def account_login():
        if auth_store.is_authenticated():
            return redirect(url_for("home"))
        email = (request.args.get("email") or request.form.get("email") or "").strip()
        return _open_in_external_browser(
            _web_login_url(email),
            purpose="Sign in",
            retry_endpoint="account_login",
        )

    @app.route("/account/auth/callback")
    def account_auth_callback():
        access = (request.args.get("access_token") or "").strip()
        refresh = (request.args.get("refresh_token") or "").strip()
        email = (request.args.get("email") or "").strip().lower()
        if not access:
            flash("Sign-in link was incomplete. Try signing in again.", "error")
            return redirect(url_for("home"))
        auth_store.save_auth(
            {
                "email": email,
                "access_token": access,
                "refresh_token": refresh,
                "server_url": auth_store.get_server_url(),
            }
        )
        return _finish_account_login()

    @app.route("/account/logout", methods=["POST"])
    def account_logout():
        client.logout()
        return redirect(url_for("home"))

    @app.route("/account/subscribe")
    @app.route("/account/password")
    @app.route("/account/stripe/return")
    def account_subscribe():
        if auth_store.is_authenticated():
            return _open_in_external_browser(
                WEB_ACCOUNT_UPGRADE_CLOUD_URL,
                purpose="Change plan",
                retry_endpoint="account_subscribe",
            )
        return _open_in_external_browser(
            _web_signup_url(),
            purpose="Subscribe",
            retry_endpoint="account_subscribe",
        )

    @app.route("/account/subscribe/status")
    def account_subscribe_status():
        return redirect(url_for("account_subscribe"))

    @app.route("/account/subscribe/restart", methods=["GET", "POST"])
    def account_subscribe_restart():
        return redirect(url_for("account_subscribe"))

    @app.route("/account/onboard/business", methods=["GET", "POST"])
    def account_onboard_business():
        businesses = storage.load_businesses()
        default_name, default_profile = storage.resolve_business()

        if request.method == "POST":
            from routes.businesses import _profile_from_form

            business_name = request.form.get("business_name", "").strip()
            profile = _profile_from_form(request.form, default_profile if default_name else None)

            if business_name:
                gst_err = validate_business_gst_settings(profile)
                if gst_err:
                    return render_template(
                        "account_onboard_business.html",
                        error=gst_err,
                        form={
                            "business_name": business_name,
                            "business_address": profile.get("address", ""),
                            "business_abn": profile.get("abn", ""),
                            "gst_registered": profile.get("gst_registered", False),
                        },
                    )
                try:
                    addr = normalize_au_address(
                        line1=profile.get("address_line1", ""),
                        line2=profile.get("address_line2", ""),
                        suburb=profile.get("suburb", ""),
                        state=profile.get("state", ""),
                        postcode=profile.get("postcode", ""),
                    )
                    profile.update(addr)
                    profile["abn"] = normalize_abn(profile.get("abn", ""))
                except ValueError as exc:
                    return render_template(
                        "account_onboard_business.html",
                        error=str(exc),
                        form={
                            "business_name": business_name,
                            "business_address_line1": profile.get("address_line1", ""),
                            "business_address_line2": profile.get("address_line2", ""),
                            "business_suburb": profile.get("suburb", ""),
                            "business_state": profile.get("state", ""),
                            "business_postcode": profile.get("postcode", ""),
                            "business_abn": profile.get("abn", ""),
                            "gst_registered": profile.get("gst_registered", False),
                        },
                    )

                businesses[business_name] = profile
                if not storage.get_default_business_name():
                    storage.set_default_business(business_name)
                storage.save_businesses(businesses)
            return redirect(url_for("home"))

        return render_template(
            "account_onboard_business.html",
            error=None,
            form={
                "business_name": default_name,
                "business_address_line1": default_profile.get("address_line1", ""),
                "business_address_line2": default_profile.get("address_line2", ""),
                "business_suburb": default_profile.get("suburb", ""),
                "business_state": default_profile.get("state", ""),
                "business_postcode": default_profile.get("postcode", ""),
                "business_abn": default_profile.get("abn", ""),
                "gst_registered": default_profile.get("gst_registered", False),
            },
        )

    @app.route("/account/onboard/customer", methods=["GET", "POST"])
    def account_onboard_customer():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            address_line1 = request.form.get("address_line1", "").strip()
            address_line2 = request.form.get("address_line2", "").strip()
            suburb = request.form.get("suburb", "").strip()
            state = request.form.get("state", "").strip()
            postcode = request.form.get("postcode", "").strip()
            abn = request.form.get("abn", "").strip()
            email = request.form.get("email", "").strip()
            if name:
                if storage.customer_name_exists(name):
                    return render_template(
                        "account_onboard_customer.html",
                        error="A customer with this name already exists.",
                        form={
                            "name": name,
                            "address_line1": address_line1,
                            "address_line2": address_line2,
                            "suburb": suburb,
                            "state": state,
                            "postcode": postcode,
                            "abn": abn,
                            "email": email,
                        },
                    )
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
                    return render_template(
                        "account_onboard_customer.html",
                        error=str(exc),
                        form={
                            "name": name,
                            "address_line1": address_line1,
                            "address_line2": address_line2,
                            "suburb": suburb,
                            "state": state,
                            "postcode": postcode,
                            "abn": abn,
                            "email": email,
                        },
                    )
                customers = storage.load_customers()
                customers[name] = {
                    **addr,
                    "abn": abn,
                    "email": email,
                }
                storage.save_customers(customers)
            return redirect(url_for("customers_list"))
        return render_template(
            "account_onboard_customer.html",
            error=None,
            form={
                "name": "",
                "address_line1": "",
                "address_line2": "",
                "suburb": "",
                "state": "",
                "postcode": "",
                "abn": "",
                "email": "",
            },
        )

