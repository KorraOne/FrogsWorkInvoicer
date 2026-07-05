"""Business profile CRUD routes."""

import os
from urllib.parse import unquote

from flask import flash, redirect, render_template, request, send_file, url_for

import storage
from invoicing.address import normalize_au_address
from invoicing.gst_settings import apply_gst_registered_to_settings, validate_business_gst_settings
from invoicing.logo import default_placement, editor_config, parse_placement
from invoicing.validators import normalize_abn, normalize_account_number, normalize_bsb


def _logo_fields_for_form(name, profile):
    from datetime import date, timedelta

    placement = profile.get("logo_placement") or default_placement()
    has_baked = bool((profile.get("logo_filename") or "").strip())
    has_source = bool((profile.get("logo_source_filename") or "").strip())
    preview_date = date.today()
    preview_due = preview_date + timedelta(days=14)
    return {
        "logo_enabled": bool(profile.get("logo_enabled")),
        "logo_filename": profile.get("logo_filename", ""),
        "logo_source_filename": profile.get("logo_source_filename", ""),
        "logo_placement": placement,
        "logo_url": url_for("business_logo", name=name) if has_baked else "",
        "logo_source_url": url_for("business_logo_source", name=name) if has_source else "",
        "logo_has_image": has_baked or has_source,
        "logo_editor_config": editor_config(),
        "logo_preview_date": preview_date.strftime("%d %B %Y"),
        "logo_preview_due": preview_due.strftime("%d %B %Y"),
    }


def apply_logo_from_request(name, profile):
    if request.form.get("remove_logo") == "1":
        storage.remove_business_logo(name, profile)
        profile["logo_filename"] = ""
        profile["logo_source_filename"] = ""
        profile["logo_placement"] = default_placement()
        profile["logo_enabled"] = False
        return None

    profile["logo_enabled"] = request.form.get("logo_enabled") == "on"
    file = request.files.get("logo_file")
    has_existing = (profile.get("logo_source_filename") or profile.get("logo_filename"))
    if not has_existing and not (file and file.filename):
        return None

    placement = parse_placement(form=request.form)
    profile["logo_placement"] = placement
    try:
        if file and file.filename:
            storage.apply_business_logo(name, file_storage=file, placement=placement, profile=profile)
        elif (profile.get("logo_source_filename") or profile.get("logo_filename")):
            storage.rebake_business_logo(name, placement, profile)
    except ValueError as exc:
        return str(exc)
    return None


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
            "logo_source_filename": (existing or {}).get("logo_source_filename", ""),
            "logo_placement": (existing or {}).get("logo_placement"),
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


def _save_business_profile(old_name, new_name, profile, *, is_add=False):
    new_name = (new_name or "").strip()
    if not new_name:
        return "Enter a business name."
    if is_add:
        if storage.business_name_exists(new_name):
            return "A business with this name already exists."
        businesses = storage.load_businesses()
        businesses[new_name] = profile
        storage.save_businesses(businesses)
        return None
    try:
        storage.rename_business(old_name, new_name, profile)
    except ValueError as exc:
        return str(exc)
    return None


def _edit_form_context(name, profile, *, is_add=False, error=None):
    from datetime import date, timedelta

    preview_date = date.today()
    preview_due = preview_date + timedelta(days=14)
    preview_dates = {
        "logo_preview_date": preview_date.strftime("%d %B %Y"),
        "logo_preview_due": preview_due.strftime("%d %B %Y"),
    }
    logo_fields = _logo_fields_for_form(name, profile) if name and not is_add else {
        "logo_enabled": bool(profile.get("logo_enabled")),
        "logo_filename": profile.get("logo_filename", ""),
        "logo_source_filename": profile.get("logo_source_filename", ""),
        "logo_placement": profile.get("logo_placement") or default_placement(),
        "logo_url": "",
        "logo_source_url": "",
        "logo_has_image": False,
        "logo_editor_config": editor_config(),
        **preview_dates,
    }
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
            **logo_fields,
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

    @app.route("/businesses/logo-source/<name>")
    def business_logo_source(name):
        name = unquote(name)
        _, profile = storage.resolve_business(name)
        filename = (profile.get("logo_source_filename") or "").strip()
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

        _, profile = storage.resolve_business(name)

        if request.method == "POST":
            updated = _profile_from_form(request.form, profile)
            new_name = request.form.get("name", "").strip() or name
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
            logo_err = apply_logo_from_request(name, updated)
            if logo_err:
                return render_template(
                    "edit_business.html",
                    **_edit_form_context(name, updated, error=logo_err),
                )
            save_err = _save_business_profile(name, new_name, updated, is_add=False)
            if save_err:
                return render_template(
                    "edit_business.html",
                    **_edit_form_context(name, updated, error=save_err),
                )
            flash("Saved.", "success")
            return redirect(url_for("businesses_edit", name=new_name))

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
