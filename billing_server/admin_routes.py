"""Operator admin web UI routes."""

import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

import admin_service
from config import ADMIN_PASSWORD, ADMIN_SESSION_HOURS, PLATFORM_INVOICE_DIR

admin_bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="templates")


def admin_configured():
    return bool(ADMIN_PASSWORD)


def _session_valid():
    if not session.get("admin_authenticated"):
        return False
    expires_at = session.get("admin_expires_at")
    if not expires_at:
        return False
    try:
        expiry = datetime.fromisoformat(expires_at)
    except ValueError:
        return False
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < expiry


def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not admin_configured():
            return render_template(
                "admin/login.html",
                error="ADMIN_PASSWORD is not set on the server.",
            ), 503
        if not _session_valid():
            return redirect(url_for("admin.login", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if not admin_configured():
        return render_template(
            "admin/login.html",
            error="ADMIN_PASSWORD is not set on the server.",
        ), 503

    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            expires = datetime.now(timezone.utc) + timedelta(hours=ADMIN_SESSION_HOURS)
            session["admin_authenticated"] = True
            session["admin_expires_at"] = expires.isoformat()
            next_url = request.args.get("next") or url_for("admin.dashboard")
            return redirect(next_url)
        flash("Invalid password.", "error")

    if _session_valid():
        return redirect(url_for("admin.dashboard"))
    return render_template("admin/login.html")


@admin_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("admin_authenticated", None)
    session.pop("admin_expires_at", None)
    return redirect(url_for("admin.login"))


@admin_bp.route("/")
@require_admin
def dashboard():
    stats = admin_service.dashboard_stats()
    return render_template("admin/dashboard.html", stats=stats)


@admin_bp.route("/accounts")
@require_admin
def accounts():
    month = request.args.get("month") or admin_service.current_month()
    rows = admin_service.list_accounts(month)
    return render_template("admin/accounts.html", accounts=rows, month=month)


@admin_bp.route("/accounts/<int:account_id>")
@require_admin
def account_detail(account_id):
    data = admin_service.get_account(account_id)
    if not data:
        abort(404)
    return render_template("admin/account_detail.html", **data)


@admin_bp.route("/usage")
@require_admin
def usage():
    month = request.args.get("month") or admin_service.current_month()
    rows = admin_service.list_usage_for_month(month)
    return render_template("admin/usage.html", rows=rows, month=month)


@admin_bp.route("/platform-invoices")
@require_admin
def platform_invoices():
    paid_filter = request.args.get("filter")
    rows = admin_service.list_platform_invoices(paid_filter=paid_filter)
    return render_template(
        "admin/platform_invoices.html",
        invoices=rows,
        paid_filter=paid_filter or "all",
    )


@admin_bp.route("/platform-invoices/<int:invoice_id>/pdf")
@require_admin
def platform_invoice_pdf(invoice_id):
    invoice = admin_service.get_platform_invoice(invoice_id)
    if not invoice or not invoice.get("pdf_filename"):
        abort(404)
    pdf_path = os.path.join(PLATFORM_INVOICE_DIR, invoice["pdf_filename"])
    pdf_path = os.path.normpath(pdf_path)
    base_dir = os.path.normpath(PLATFORM_INVOICE_DIR)
    if not pdf_path.startswith(base_dir) or not os.path.isfile(pdf_path):
        abort(404)
    return send_file(
        pdf_path,
        as_attachment=False,
        download_name=invoice["pdf_filename"],
    )


@admin_bp.route("/platform-invoices/<int:invoice_id>/mark-paid", methods=["POST"])
@require_admin
def mark_paid(invoice_id):
    if not admin_service.mark_invoice_paid(invoice_id):
        abort(404)
    flash("Invoice marked as paid.", "success")
    return redirect(url_for("admin.platform_invoices"))


@admin_bp.route("/generate", methods=["GET", "POST"])
@require_admin
def generate():
    from datetime import date

    from billing_schedule import BILLING_ANNUAL, BILLING_QUARTERLY

    today = date.today()
    billing_mode = request.values.get("mode", BILLING_QUARTERLY)
    if billing_mode not in (BILLING_QUARTERLY, BILLING_ANNUAL):
        billing_mode = BILLING_QUARTERLY
    year = int(request.values.get("year", today.year))
    quarter = int(request.values.get("quarter", (today.month - 1) // 3 + 1))

    preview = admin_service.preview_generation(
        year, quarter=quarter, billing_mode=billing_mode
    )

    if request.method == "POST" and request.form.get("action") == "generate":
        regenerate = bool(request.form.get("regenerate"))
        created = admin_service.run_generation(
            year,
            quarter=quarter,
            billing_mode=billing_mode,
            regenerate=regenerate,
        )
        flash(f"Generated {len(created)} platform invoice(s).", "success")
        return redirect(url_for("admin.platform_invoices"))

    return render_template(
        "admin/generate.html",
        preview=preview,
        year=year,
        quarter=quarter,
        billing_mode=billing_mode,
    )


def register_admin_routes(app):
    app.register_blueprint(admin_bp)
