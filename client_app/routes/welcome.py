"""Welcome flow, account usage context, and dashboard."""

from flask import redirect, render_template, request, url_for

import storage
from account import auth_store, entitlement_cache, messages
from app_config import (
    SUBSCRIPTION_ANNUAL_DISPLAY,
    SUBSCRIPTION_ANNUAL_SAVINGS,
    SUBSCRIPTION_MONTHLY_DISPLAY,
)
from invoicing.gst_settings import is_gst_registered

WELCOME_EXEMPT_ENDPOINTS = {
    "welcome_start",
    "welcome_pricing",
    "ping",
    "static",
}


def register_welcome_routes(app, helpers):
    format_money = helpers["format_money"]

    @app.context_processor
    def inject_usage_meter():
        auth = auth_store.load_auth()
        cache = entitlement_cache.load_cache()
        email = auth.get("email", "") if auth_store.is_authenticated() else ""
        sync_reminder = None
        if auth_store.is_authenticated() and entitlement_cache.sync_status() == "reminder":
            sync_reminder = messages.SYNC_REMINDER
        return {
            "usage_meter": {
                "authenticated": auth_store.is_authenticated(),
                "subscription_active": cache.get("active", False),
                "email": email,
            },
            "subscription_monthly_display": SUBSCRIPTION_MONTHLY_DISPLAY,
            "subscription_annual_display": SUBSCRIPTION_ANNUAL_DISPLAY,
            "subscription_annual_savings": SUBSCRIPTION_ANNUAL_SAVINGS,
            "subscription_sync_reminder": sync_reminder,
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

    @app.route("/welcome/pricing", methods=["GET", "POST"])
    def welcome_pricing():
        if request.method == "POST":
            storage.mark_welcome_complete()
            return redirect(url_for("home"))
        return render_template("welcome_pricing.html")

    @app.route("/dashboard")
    def dashboard():
        invoices = storage.load_active_invoices()
        totals = helpers["dashboard_totals"](invoices)
        _, profile = storage.resolve_business()
        gst_registered = is_gst_registered(profile)

        def amount_lines(bucket):
            inc = format_money(bucket["inc_gst"])
            if not gst_registered:
                return inc, None
            return inc, f"({format_money(bucket['ex_gst'])} ex GST)"

        month_primary, month_secondary = amount_lines(totals["month"])
        outstanding_primary, outstanding_secondary = amount_lines(totals["outstanding"])
        paid_primary, paid_secondary = amount_lines(totals["paid"])

        return render_template(
            "dashboard.html",
            month_primary=month_primary,
            month_secondary=month_secondary,
            outstanding_primary=outstanding_primary,
            outstanding_secondary=outstanding_secondary,
            paid_primary=paid_primary,
            paid_secondary=paid_secondary,
            outstanding_count=totals["outstanding"]["count"],
            gst_registered=gst_registered,
        )
