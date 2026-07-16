"""Anonymous install telemetry (aggregates only, best-effort)."""

import hashlib
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from decimal import Decimal

import storage
from invoicing.gst_settings import is_gst_registered
from account.install_secret import _install_path, get_install_secret
from app_config import APP_VERSION

log = logging.getLogger(__name__)

TELEMETRY_THROTTLE_HOURS = 24
EVENT_FLAG_PREFIX = "telemetry_event_"


def install_id():
    secret = get_install_secret()
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _load_install_meta():
    path = _install_path()
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _save_install_meta(data):
    path = _install_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _api_url(path):
    from account import auth_store

    return auth_store.get_server_url().rstrip("/") + path


def _post_json(path, body, timeout=5):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        _api_url(path),
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"FrogsWork/{APP_VERSION}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def _is_packaged():
    return getattr(sys, "frozen", False)


def _invoice_ex_gst(invoice):
    raw = invoice.get("amount_ex_gst")
    if raw is not None and str(raw).strip() != "":
        return Decimal(str(raw))
    return Decimal(str(invoice.get("total_inc_gst", "0")))


def _lifetime_totals(invoices):
    count = 0
    total = Decimal("0")
    for invoice in invoices.values():
        if storage.is_invoice_deleted(invoice):
            continue
        count += 1
        total += _invoice_ex_gst(invoice)
    return count, total


def _invoice_status_counts(invoices):
    counts = {"not_sent": 0, "sent": 0, "paid": 0}
    for inv in invoices.values():
        if storage.is_invoice_deleted(inv):
            continue
        status = inv.get("status", "not_sent")
        if status not in counts:
            status = "not_sent"
        counts[status] += 1
    return counts


def _days_since_last_invoice(invoices):
    latest = None
    for inv in invoices.values():
        if storage.is_invoice_deleted(inv):
            continue
        raw = inv.get("invoice_date")
        if not raw:
            continue
        try:
            inv_date = date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        if latest is None or inv_date > latest:
            latest = inv_date
    if latest is None:
        return None
    return (date.today() - latest).days


def _custom_pdf_folder():
    bootstrap_path = os.path.join(storage.get_appdata_path(), "bootstrap.json")
    if not os.path.exists(bootstrap_path):
        return False
    try:
        with open(bootstrap_path, encoding="utf-8") as f:
            data = json.load(f)
        return bool((data.get("pdf_folder") or "").strip())
    except (OSError, json.JSONDecodeError):
        return False


def build_usage_snapshot():
    settings = storage.load_settings()
    customers = storage.load_customers()
    businesses = storage.load_businesses()
    invoices = storage.load_invoices()
    count, total = _lifetime_totals(invoices)
    status_counts = _invoice_status_counts(invoices)

    due_rule = settings.get("due_rule_type") or settings.get("last_due_rule_type") or ""
    _, default_profile = storage.resolve_business()

    return {
        "gst_registered": is_gst_registered(default_profile),
        "welcome_complete": bool(settings.get("welcome_complete")),
        "lifetime_invoice_count": count,
        "lifetime_ex_gst": str(total.quantize(Decimal("0.01"))),
        "customer_count": len(customers),
        "business_count": len(businesses),
        "invoices_not_sent": status_counts["not_sent"],
        "invoices_sent": status_counts["sent"],
        "invoices_paid": status_counts["paid"],
        "due_rule_type": due_rule,
        "custom_pdf_folder": _custom_pdf_folder(),
        "days_since_last_invoice": _days_since_last_invoice(invoices),
    }


def build_signup_snapshot():
    snap = build_usage_snapshot()
    return {
        "lifetime_invoice_count": snap["lifetime_invoice_count"],
        "lifetime_ex_gst_total": snap["lifetime_ex_gst"],
        "gst_registered": snap["gst_registered"],
    }


def _should_send_heartbeat(force=False):
    if force:
        return True
    meta = _load_install_meta()
    last = meta.get("last_telemetry_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return True
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=timezone.utc)
    elapsed = datetime.now(timezone.utc) - last_dt
    return elapsed.total_seconds() >= TELEMETRY_THROTTLE_HOURS * 3600


def send_heartbeat(*, force=False):
    if not _should_send_heartbeat(force=force):
        return
    body = {
        "install_id": install_id(),
        "app_version": APP_VERSION,
        "schema_version": 1,
        "is_packaged": _is_packaged(),
        "usage_snapshot": build_usage_snapshot(),
    }
    try:
        _post_json("/telemetry/heartbeat", body)
        meta = _load_install_meta()
        meta["last_telemetry_at"] = datetime.now(timezone.utc).isoformat()
        _save_install_meta(meta)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        log.debug("Telemetry heartbeat skipped", exc_info=True)


def _event_sent(event):
    meta = _load_install_meta()
    return bool(meta.get(f"{EVENT_FLAG_PREFIX}{event}"))


def _mark_event_sent(event):
    meta = _load_install_meta()
    meta[f"{EVENT_FLAG_PREFIX}{event}"] = True
    _save_install_meta(meta)


def send_event(event, *, timeout=5):
    if _event_sent(event):
        return
    body = {
        "install_id": install_id(),
        "event": event,
        "app_version": APP_VERSION,
    }
    try:
        _post_json("/telemetry/event", body, timeout=timeout)
        _mark_event_sent(event)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        log.debug("Telemetry event %s skipped", event, exc_info=True)


def after_invoice_generated():
    send_event("first_invoice")
    send_heartbeat(force=True)


def send_uninstall_event():
    send_event("uninstall", timeout=2)
