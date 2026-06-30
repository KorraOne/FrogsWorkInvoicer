"""Welcome flow, trial usage context, and dashboard."""

from decimal import Decimal

from flask import redirect, render_template, request, url_for

import storage
from account import auth_store, entitlement_cache, messages, trial_stats
from app_config import (
    SUBSCRIPTION_ANNUAL_DISPLAY,
    SUBSCRIPTION_ANNUAL_SAVINGS,
    SUBSCRIPTION_MONTHLY_DISPLAY,
)

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
        meter = trial_stats.meter_snapshot()
        auth = auth_store.load_auth()
        cache = entitlement_cache.load_cache()
        email = auth.get("email", "") if auth_store.is_authenticated() else ""
        sync_reminder = None
        if auth_store.is_authenticated() and entitlement_cache.sync_status() == "reminder":
            sync_reminder = messages.SYNC_REMINDER
        return {
            "show_trial_usage": not auth_store.is_authenticated(),
            "usage_meter": {
                "lifetime_invoice_count": meter["lifetime_invoice_count"],
                "max_invoices": meter["max_invoices"],
                "lifetime_ex_gst_fmt": format_money(meter["lifetime_ex_gst_total"]),
                "max_ex_gst_fmt": format_money(meter["max_ex_gst"]),
                "invoices_remaining": meter["invoices_remaining"],
                "amount_remaining_fmt": format_money(meter["amount_remaining_ex_gst"]),
                "trial_exhausted": meter["trial_exhausted"],
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
