"""Business profile CRUD routes."""

import os
from urllib.parse import unquote

from flask import flash, redirect, render_template, request, send_file, url_for

import storage
from invoicing.address import normalize_au_address
from invoicing.gst_settings import apply_gst_registered_to_settings, validate_business_gst_settings
from invoicing.validators import normalize_abn, normalize_account_number, normalize_bsb


def _profile_from_form(form, existing=None):
    profile = storage.normalize_business_profile(
        {
            "address_line1": form.get("business_address_line1", ""),
            "address_line2": form.get("business_address_line2", ""),
            "suburb": form.get("business_suburb", ""),
            "state": form.get("business_state", ""),
            "postcode": form.get("business_postcode", ""),
            "abn": form.get("business_abn", ""),
            "account_name": form.get("account_name", ""),
            "bsb": form.get("bsb", ""),
            "acc": form.get("acc", ""),
            "logo_enabled": form.get("logo_enabled"),
            "logo_filename": (existing or {}).get("logo_filename", ""),
        },
        existing,
    )
    apply_gst_registered_to_settings(profile, form)
    return profile


def _validate_and_normalize_profile_for_save(profile):
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
        profile["bsb"] = normalize_bsb(profile.get("bsb", ""))
        profile["acc"] = normalize_account_number(profile.get("acc", ""))
    except ValueError as exc:
        return str(exc)
    return None


def _edit_form_context(name, profile, *, is_add=False, error=None):
    return {
        "business": name if not is_add else None,
        "form": {
            "name": name,
            "business_address_line1": profile.get("address_line1", ""),
            "business_address_line2": profile.get("address_line2", ""),
            "business_suburb": profile.get("suburb", ""),
            "business_state": profile.get("state", ""),
            "business_postcode": profile.get("postcode", ""),
            "business_abn": profile.get("abn", ""),
            "gst_registered": profile.get("gst_registered", False),
            "account_name": profile.get("account_name", ""),
            "bsb": profile.get("bsb", ""),
            "acc": profile.get("acc", ""),
            "logo_enabled": bool(profile.get("logo_enabled")),
            "logo_filename": profile.get("logo_filename", ""),
            "logo_url": url_for("business_logo", name=name) if profile.get("logo_filename") else "",
        },
        "error": error,
        "is_add": is_add,
    }


def register_business_routes(app):
    @app.route("/businesses/logo/<name>")
    def business_logo(name):
        name = unquote(name)
        businesses = storage.load_businesses()
        profile = businesses.get(name) or {}
        filename = (profile.get("logo_filename") or "").strip()
        if not filename:
            return ("", 404)
        path = os.path.join(storage.get_data_path(), "logos", filename)
        if not os.path.isfile(path):
            return ("", 404)
        return send_file(path)

    @app.route("/businesses/add", methods=["GET", "POST"])
    def businesses_add():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            profile = _profile_from_form(request.form)

            if not name:
                return render_template(
                    "edit_business.html",
                    **_edit_form_context(
                        name,
                        profile,
                        is_add=True,
                        error="Enter a business name.",
                    ),
                )

            if storage.business_name_exists(name):
                return render_template(
                    "edit_business.html",
                    **_edit_form_context(
                        name,
                        profile,
                        is_add=True,
                        error="A business with this name already exists.",
                    ),
                )

            gst_err = validate_business_gst_settings(profile)
            if gst_err:
                return render_template(
                    "edit_business.html",
                    **_edit_form_context(name, profile, is_add=True, error=gst_err),
                )
            field_err = _validate_and_normalize_profile_for_save(profile)
            if field_err:
                return render_template(
                    "edit_business.html",
                    **_edit_form_context(name, profile, is_add=True, error=field_err),
                )

            businesses = storage.load_businesses()
            businesses[name] = profile
            storage.save_businesses(businesses)
            if not storage.get_default_business_name():
                storage.set_default_business(name)
            return redirect(url_for("home"))

        return render_template(
            "edit_business.html",
            **_edit_form_context("", {}, is_add=True),
        )

    @app.route("/businesses/edit/<name>", methods=["GET", "POST"])
    def businesses_edit(name):
        name = unquote(name)
        businesses = storage.load_businesses()
        if name not in businesses:
            return redirect(url_for("settings_details"))

        profile = businesses[name]

        if request.method == "POST":
            updated = _profile_from_form(request.form, profile)
            gst_err = validate_business_gst_settings(updated)
            if gst_err:
                return render_template(
                    "edit_business.html",
                    **_edit_form_context(name, updated, error=gst_err),
                )
            field_err = _validate_and_normalize_profile_for_save(updated)
            if field_err:
                return render_template(
                    "edit_business.html",
                    **_edit_form_context(name, updated, error=field_err),
                )
            if request.form.get("remove_logo") == "1":
                storage.remove_business_logo(name, updated.get("logo_filename"))
                updated["logo_filename"] = ""
                updated["logo_enabled"] = False
            else:
                file = request.files.get("logo_file")
                if file and file.filename:
                    updated["logo_filename"] = storage.save_business_logo(name, file)
            businesses[name] = updated
            storage.save_businesses(businesses)
            return redirect(url_for("home"))

        return render_template(
            "edit_business.html",
            **_edit_form_context(name, profile),
        )

    @app.route("/businesses/delete/<name>", methods=["POST"])
    def businesses_delete(name):
        name = unquote(name)
        businesses = storage.load_businesses()
        if name not in businesses:
            return redirect(url_for("settings_details"))

        if len(businesses) <= 1:
            flash("You need at least one business profile.", "error")
            return redirect(url_for("settings_details"))

        del businesses[name]
        storage.save_businesses(businesses)

        if storage.get_default_business_name() == name or name not in businesses:
            if businesses:
                storage.set_default_business(next(iter(businesses)))

        return redirect(url_for("settings_details"))
