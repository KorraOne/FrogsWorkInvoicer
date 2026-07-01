"""Business profile CRUD routes."""

from urllib.parse import unquote

from flask import flash, redirect, render_template, request, url_for

import storage
from invoicing.gst_settings import apply_gst_registered_to_settings, validate_business_gst_settings


def _profile_from_form(form, existing=None):
    profile = storage.normalize_business_profile(
        {
            "address": form.get("business_address", ""),
            "abn": form.get("business_abn", ""),
            "account_name": form.get("account_name", ""),
            "bsb": form.get("bsb", ""),
            "acc": form.get("acc", ""),
        },
        existing,
    )
    apply_gst_registered_to_settings(profile, form)
    return profile


def _edit_form_context(name, profile, *, is_add=False, error=None):
    return {
        "business": name if not is_add else None,
        "form": {
            "name": name,
            "business_address": profile.get("address", ""),
            "business_abn": profile.get("abn", ""),
            "gst_registered": profile.get("gst_registered", False),
            "account_name": profile.get("account_name", ""),
            "bsb": profile.get("bsb", ""),
            "acc": profile.get("acc", ""),
        },
        "error": error,
        "is_add": is_add,
    }


def register_business_routes(app):
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

            businesses = storage.load_businesses()
            businesses[name] = profile
            storage.save_businesses(businesses)
            if not storage.get_default_business_name():
                storage.set_default_business(name)
            return redirect(url_for("settings_details"))

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
            businesses[name] = updated
            storage.save_businesses(businesses)
            return redirect(url_for("settings_details"))

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
