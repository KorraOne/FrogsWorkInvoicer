import sys

# Uninstall helper must exit before Flask/desktop imports (Inno runs: FrogsWork.exe --export-uninstall-data).
if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--export-uninstall-data":
    from app_platform.win.uninstall import export_for_uninstall

    raise SystemExit(export_for_uninstall())

import logging
import os
import threading
import time
import urllib.request
import webbrowser
from decimal import Decimal
from urllib.parse import unquote, quote as urlquote

from flask import Flask, g, render_template, request, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.serving import make_server

import storage
from invoicing.format import (
    format_invoice_date,
    format_invoice_number,
    format_iso_date,
    format_iso_datetime,
    format_money,
)
from invoicing.form import dashboard_totals, has_invoice_draft, invoices_by_status
from app_platform import exe_dir, resource_path
from routes.account import register_account_routes
from routes.backup import register_backup_routes
from routes.businesses import register_business_routes
from routes.customers import register_customer_routes
from routes.invoices import register_invoice_routes
from routes.settings import register_settings_routes
from routes.system import idle_watchdog, register_system_routes, request_shutdown
from routes.welcome import register_welcome_routes
from ui_config import PLACEHOLDERS, SELECT_LABELS

logging.getLogger("werkzeug").setLevel(logging.ERROR)

app = Flask(
    __name__,
    template_folder=resource_path("templates"),
    static_folder=resource_path("static"),
)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or storage.get_or_create_flask_secret()

log = logging.getLogger(__name__)

NAV_PARENTS = {
    "create_invoice": ("home", "Home"),
    "resume_preview": ("create_invoice", "Edit invoice"),
    "dashboard": ("home", "Home"),
    "invoices_list": ("home", "Home"),
    "invoice_send": ("invoices_list", "Past invoices"),
    "customers_list": ("home", "Home"),
    "customers_add": ("customers_list", "Customers"),
    "customers_edit": ("customers_list", "Customers"),
    "settings_page": ("home", "Home"),
    "businesses_add": ("settings_details", "Business details"),
    "businesses_edit": ("settings_details", "Business details"),
    "settings_details": ("home", "Home"),
    "settings_account": ("settings_page", "Settings"),
    "settings_storage": ("settings_page", "Settings"),
    "settings_logo_design": ("settings_page", "Settings"),
    "settings_updates": ("settings_page", "Settings"),
    "backup_import": ("settings_page", "Settings"),
    "welcome_pricing": ("welcome_start", "Welcome"),
}


@app.errorhandler(404)
def page_not_found(exc):
    return (
        render_template(
            "error.html",
            code=404,
            message="Page not found.",
        ),
        404,
    )


@app.errorhandler(500)
def internal_server_error(exc):
    log.exception("Internal server error")
    return (
        render_template(
            "error.html",
            code=500,
            message="Something went wrong. Your invoices and settings are safe on this PC.",
        ),
        500,
    )


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    if isinstance(exc, HTTPException):
        return exc
    log.exception("Unhandled application error")
    return (
        render_template(
            "error.html",
            code=500,
            message="Something went wrong. Your invoices and settings are safe on this PC.",
        ),
        500,
    )


@app.context_processor
def _inject_ui_defaults():
    from invoicing.address import AU_STATES

    return {
        "ph": PLACEHOLDERS,
        "select_labels": SELECT_LABELS,
        "au_states": AU_STATES,
    }


@app.context_processor
def _inject_brand():
    from app_config import (
        APP_BRAND_DEVELOPER,
        APP_BRAND_DEVELOPER_URL,
        APP_BRAND_NAME,
        APP_BRAND_TAGLINE,
        APP_BRAND_URL,
        APP_PRIVACY_URL,
        APP_SUPPORT_EMAIL,
        APP_SUPPORT_URL,
        APP_TERMS_URL,
        SHOW_LOGO_DESIGN_SETTINGS,
        WEB_ACCOUNT_LOGIN_URL,
        WEB_ACCOUNT_SIGNUP_URL,
        WEB_ACCOUNT_SUBSCRIBE_URL,
        WEB_ACCOUNT_UPGRADE_CLOUD_URL,
    )
    from account import telemetry

    install_id = telemetry.install_id()
    web_subscribe = WEB_ACCOUNT_SUBSCRIBE_URL
    if install_id:
        web_subscribe = f"{web_subscribe}?install_id={urlquote(install_id)}"

    return {
        "brand_name": APP_BRAND_NAME,
        "brand_tagline": APP_BRAND_TAGLINE,
        "brand_url": APP_BRAND_URL,
        "brand_developer": APP_BRAND_DEVELOPER,
        "brand_developer_url": APP_BRAND_DEVELOPER_URL,
        "brand_support_url": APP_SUPPORT_URL,
        "brand_support_email": APP_SUPPORT_EMAIL,
        "brand_privacy_url": APP_PRIVACY_URL,
        "brand_terms_url": APP_TERMS_URL,
        "show_logo_design_settings": SHOW_LOGO_DESIGN_SETTINGS,
        "web_account_subscribe_url": web_subscribe,
        "web_account_signup_url": WEB_ACCOUNT_SIGNUP_URL,
        "web_account_upgrade_cloud_url": WEB_ACCOUNT_UPGRADE_CLOUD_URL,
        "web_account_login_url": WEB_ACCOUNT_LOGIN_URL,
    }


@app.context_processor
def _inject_update():
    from app_platform import updates as app_update
    from app_config import APP_VERSION

    pending = app_update.get_pending_update()
    apply_failure = app_update.get_apply_failure()
    return {
        "app_version": APP_VERSION,
        "pending_update": pending,
        "update_apply_failed": apply_failure,
        "show_update_banner": bool(pending and not pending.get("banner_hidden")),
    }


@app.template_filter("fmt_invoice_number")
def _fmt_invoice_number(number):
    return format_invoice_number(number)


@app.template_filter("fmt_invoice_date")
def _fmt_invoice_date(iso_date):
    return format_invoice_date(iso_date)


@app.template_filter("fmt_iso_datetime")
def _fmt_iso_datetime(iso):
    return format_iso_datetime(iso)


@app.template_filter("fmt_iso_date")
def _fmt_iso_date(iso):
    return format_iso_date(iso)


@app.template_filter("fmt_invoice_amount")
def _fmt_invoice_amount(inv):
    return format_money(Decimal(inv["total_inc_gst"]))


@app.template_filter("invoice_due_countdown")
def _invoice_due_countdown(inv):
    from invoicing.due_dates import due_countdown_for_invoice

    settings = getattr(g, "invoice_list_settings", None)
    return due_countdown_for_invoice(inv, settings=settings)


@app.context_processor
def inject_navigation():
    endpoint = request.endpoint
    back_url = url_for("home")
    back_label = "Home"

    if endpoint in (
        "account_login",
        "account_onboard_business",
        "account_onboard_customer",
    ) and has_invoice_draft():
        back_url = url_for("resume_preview")
        back_label = "Back to invoice review"
    elif endpoint in NAV_PARENTS:
        parent_endpoint, label = NAV_PARENTS[endpoint]
        back_url = url_for(parent_endpoint)
        back_label = label

    return {
        "back_url": back_url,
        "back_label": back_label,
        "has_invoice_draft": has_invoice_draft(),
    }


@app.context_processor
def inject_storage_tier_context():
    from account import auth_store, entitlement_cache
    from app_config import WEB_ACCOUNT_UPGRADE_CLOUD_URL
    from storage.context import cloud_entitled, get_storage_tier, use_cloud_provider
    from storage import sync_queue

    cache = entitlement_cache.load_cache() or {}
    local_tier_banner = None
    show_cloud_upgrade_cta = False
    show_cloud_migrate_cta = False
    if auth_store.is_authenticated() and cache.get("active") and get_storage_tier() == "local":
        local_tier_banner = (
            "This computer has its own invoice data. Local plan doesn't sync. "
            "Import a backup or upgrade to Cloud for the same records everywhere."
        )
        show_cloud_upgrade_cta = True
        show_cloud_migrate_cta = cloud_entitled()
    cloud_sync_pending = None
    if use_cloud_provider() and sync_queue.has_pending():
        cloud_sync_pending = f"{sync_queue.pending_count()} change(s) waiting to sync"
    return {
        "local_tier_banner": local_tier_banner,
        "show_cloud_upgrade_cta": show_cloud_upgrade_cta,
        "show_cloud_migrate_cta": show_cloud_migrate_cta,
        "web_account_upgrade_cloud_url": WEB_ACCOUNT_UPGRADE_CLOUD_URL,
        "cloud_sync_pending": cloud_sync_pending,
    }


def _register_all_routes():
    helpers = {
        "format_money": format_money,
        "format_invoice_number": format_invoice_number,
        "exe_dir": exe_dir,
        "invoices_by_status": invoices_by_status,
        "dashboard_totals": dashboard_totals,
        "unquote": unquote,
    }
    register_system_routes(app)
    register_invoice_routes(app)
    register_customer_routes(app)
    register_business_routes(app)
    register_settings_routes(app, request_shutdown)
    register_welcome_routes(app, helpers)
    register_account_routes(app)
    register_backup_routes(app, helpers)


def open_browser_when_ready():
    from app_config import LOCAL_APP_URL

    url = LOCAL_APP_URL
    for _ in range(60):
        try:
            urllib.request.urlopen(url, timeout=0.2)
            webbrowser.open(url)
            return
        except OSError:
            time.sleep(0.05)
    webbrowser.open(url)


def use_dev_browser():
    return os.environ.get("FROGSWORK_DEV_BROWSER") == "1" or "--dev-browser" in sys.argv


def _show_already_running_message():
    if sys.platform != "win32":
        return
    try:
        import ctypes

        from app_config import APP_BRAND_NAME

        ctypes.windll.user32.MessageBoxW(
            0,
            f"{APP_BRAND_NAME} is already running.\n\n"
            "Check your taskbar for an open window.",
            APP_BRAND_NAME,
            0x40,
        )
    except Exception:
        pass


def _start_flask_server():
    """Start the local server. Returns None on success, or 'port_in_use'."""
    import routes.system as system

    from app_config import LOCAL_APP_HOST, LOCAL_APP_PORT

    storage.ensure_app_identity()
    try:
        system.server = make_server(LOCAL_APP_HOST, LOCAL_APP_PORT, app, threaded=True)
    except OSError:
        return "port_in_use"
    threading.Thread(target=system.server.serve_forever, daemon=True, name="flask-server").start()
    threading.Thread(target=idle_watchdog, daemon=True, name="idle-watchdog").start()
    return None


def _start_backend(startup_error):
    startup_error["code"] = _start_flask_server()


def main():
    from app_config import LOCAL_APP_URL
    from app_platform.folder_picker import process_pending_picks

    def _telemetry_on_start():
        from account import telemetry

        telemetry.send_heartbeat()

    threading.Thread(target=_telemetry_on_start, daemon=True, name="telemetry-heartbeat").start()

    if use_dev_browser():
        if _start_flask_server() == "port_in_use":
            _show_already_running_message()
            return
        threading.Thread(target=open_browser_when_ready, daemon=True).start()
        from account import sync as account_sync

        account_sync.start_background_sync()
        try:
            import routes.system as system

            while not system.shutdown_requested:
                process_pending_picks()
                time.sleep(0.05)
        except KeyboardInterrupt:
            request_shutdown()
    else:
        startup_error = {"code": None}
        threading.Thread(
            target=_start_backend,
            args=(startup_error,),
            daemon=True,
            name="flask-backend",
        ).start()
        from account import sync as account_sync

        account_sync.start_background_sync()
        from desktop_shell import run_desktop_app

        run_desktop_app(LOCAL_APP_URL, request_shutdown, startup_error=startup_error)


_register_all_routes()


if __name__ == "__main__":
    main()
