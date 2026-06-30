"""Settings, updates, storage, and account pages."""

import os
import webbrowser
from datetime import date
from urllib.parse import quote

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

import storage
from account import auth_store, client, entitlement_cache, sync
from invoicing.due_dates import due_rule_from_form_data, due_rule_template_context
from app_platform.folder_picker import FolderPickerError, pick_folder
from invoicing.gst_settings import apply_gst_registered_to_settings, validate_business_gst_settings


def register_settings_routes(app, request_shutdown):
    @app.route("/settings")
    def settings_page():
        return render_template("settings.html")

    @app.route("/updates/dismiss", methods=["POST"])
    def updates_dismiss():
        from app_platform import updates as app_update

        version = request.form.get("version", "").strip()
        if version:
            app_update.dismiss_update(version)
        return redirect(request.referrer or url_for("home"))

    @app.route("/updates/apply", methods=["POST"])
    def updates_apply():
        from app_platform import updates as app_update

        pending = app_update.get_pending_update(force_check=True)
        if not pending:
            flash("No update is available right now.", "info")
            return redirect(request.referrer or url_for("home"))
        try:
            app_update.apply_update(pending, request_shutdown)
            flash("Downloading update. The app will restart shortly.", "info")
        except Exception as exc:
            flash(f"Update failed: {exc}", "error")
        return redirect(request.referrer or url_for("settings_updates"))

    @app.route("/settings/updates", methods=["GET", "POST"])
    def settings_updates():
        from app_platform import updates as app_update

        error = None
        server_unreachable = False
        force_check = request.method == "POST" and request.form.get("action") in ("check", "apply")
        pending = app_update.get_pending_update(force_check=force_check)

        if request.method == "POST":
            action = request.form.get("action", "")
            if action == "check":
                if not client.check_server_available():
                    server_unreachable = True
                else:
                    pending = app_update.get_pending_update(force_check=True)
            elif action == "apply" and pending:
                try:
                    app_update.apply_update(pending, request_shutdown)
                    flash("Downloading update. The app will restart shortly.", "info")
                    return redirect(url_for("settings_updates"))
                except Exception as exc:
                    error = str(exc)

        return render_template(
            "settings_updates.html",
            pending=pending,
            error=error,
            packaged=app_update.is_packaged(),
            server_unreachable=server_unreachable,
        )

    @app.route("/settings/logo-design", methods=["GET"])
    def settings_logo_design():
        from app_config import APP_LOGO_DESIGN_EMAIL, SHOW_LOGO_DESIGN_SETTINGS

        if not SHOW_LOGO_DESIGN_SETTINGS:
            abort(404)

        mailto_href = f"mailto:{APP_LOGO_DESIGN_EMAIL}?subject={quote('FrogsWork logo design')}"

        return render_template(
            "settings_logo_design.html",
            contact_email=APP_LOGO_DESIGN_EMAIL,
            mailto_href=mailto_href,
        )

    @app.route("/settings/details", methods=["GET", "POST"])
    def settings_details():
        def _render(settings, error=None, form=None):
            ctx = due_rule_template_context(date.today(), settings, form)
            return render_template(
                "settings_details.html",
                settings=settings,
                error=error,
                **ctx,
            )

        if request.method == "POST":
            settings = storage.load_settings()
            settings["business_name"] = request.form.get("business_name", "").strip()
            settings["business_address"] = request.form.get("business_address", "").strip()
            settings["business_abn"] = request.form.get("business_abn", "").strip()
            apply_gst_registered_to_settings(settings, request.form)
            settings["account_name"] = request.form.get("account_name", "").strip()
            settings["bsb"] = request.form.get("bsb", "").strip()
            settings["acc"] = request.form.get("acc", "").strip()
            rule = due_rule_from_form_data(request.form, settings)
            settings["due_rule_type"] = rule["due_rule_type"]
            settings["due_net_days"] = rule["due_net_days"]

            gst_err = validate_business_gst_settings(settings)
            if gst_err:
                return _render(settings, error=gst_err, form=request.form)

            storage.save_settings(settings)
            flash("Saved.", "success")
            return redirect(url_for("settings_page"))

        settings = storage.load_settings()
        return _render(settings)

    @app.route("/settings/account", methods=["GET", "POST"])
    def settings_account():
        verify_message = None
        entitlement_just_synced = False
        if request.method == "POST":
            action = request.form.get("action", "")
            if action == "verify":
                try:
                    sync.sync_entitlements_from_server()
                    verify_message = ("Subscription verified.", "success")
                    entitlement_just_synced = True
                except client.AccountOfflineError:
                    verify_message = ("Couldn't reach the server. Check your connection.", "error")
                except client.AccountError as exc:
                    verify_message = (client.map_http_auth_error(str(exc)), "error")
            elif action == "portal":
                try:
                    payload = sync.sync_entitlements_from_server() or {}
                    entitlement_just_synced = True
                    portal_url = payload.get("portal_url") or entitlement_cache.load_cache().get("portal_url")
                    if portal_url:
                        webbrowser.open(portal_url)
                        verify_message = ("Opened Stripe billing portal in your browser.", "success")
                    else:
                        verify_message = (
                            "Billing portal not available yet. Try Verify subscription first.",
                            "error",
                        )
                except client.AccountOfflineError:
                    verify_message = ("Couldn't reach the server. Check your connection.", "error")
                except client.AccountError as exc:
                    verify_message = (client.map_http_auth_error(str(exc)), "error")

        cache = entitlement_cache.load_cache()
        return render_template(
            "settings_account.html",
            account_services_ok=None,
            entitlement=cache or {},
            verify_flash=verify_message,
            entitlement_sync_async=auth_store.is_authenticated() and not entitlement_just_synced,
        )

    @app.route("/settings/account/status")
    def settings_account_status():
        if not auth_store.is_authenticated():
            return jsonify({"authenticated": False})

        sync.sync_entitlements_from_server()
        cache = entitlement_cache.load_cache() or {}
        auth = auth_store.load_auth()
        return jsonify(
            {
                "authenticated": True,
                "email": auth.get("email", ""),
                "account_services_ok": client.check_server_available(),
                "entitlement": cache,
            }
        )

    @app.route("/settings/storage", methods=["GET"])
    def settings_storage():
        return render_template(
            "settings_storage.html",
            config_folder=storage.get_config_folder_display(),
            pdf_folder=storage.get_pdf_folder_display(),
            using_default=storage.is_using_default_pdf_folder(),
            default_pdf_folder=os.path.join(storage.get_default_data_path(), "pdfs"),
        )

    @app.route("/settings/storage/set", methods=["POST"])
    def settings_storage_set():
        path = request.form.get("pdf_folder", "").strip()
        if not path:
            flash("Enter a folder path or use Browse.", "error")
        else:
            try:
                storage.set_pdf_folder(path, from_picker=False)
                flash("PDF folder moved.", "success")
            except OSError as exc:
                flash(f"Couldn't move the PDF folder: {exc}", "error")
        return redirect(url_for("settings_page"))

    @app.route("/settings/storage/pick", methods=["POST"])
    def settings_storage_pick():
        try:
            path = pick_folder("Choose where to save invoice PDFs")
            if path:
                try:
                    storage.set_pdf_folder(path, from_picker=True)
                    flash("PDF folder moved.", "success")
                except OSError as exc:
                    flash(f"Couldn't move the PDF folder: {exc}", "error")
        except FolderPickerError as exc:
            flash(f"Couldn't open the folder picker: {exc}", "error")
        return redirect(url_for("settings_page"))

    @app.route("/settings/storage/reset", methods=["POST"])
    def settings_storage_reset():
        try:
            storage.reset_pdf_folder()
            flash("PDF folder moved back to default location.", "success")
        except OSError as exc:
            flash(f"Couldn't move the PDF folder: {exc}", "error")
        return redirect(url_for("settings_page"))
