"""Tamper-evident local usage ledger (offline free-tier integrity)."""

import hashlib
import hmac
import json
import os
import secrets
from decimal import Decimal, InvalidOperation

import billing_core
import storage

LEDGER_VERSION = 1
INSTALL_SECRET_FILE = "billing_install.json"
AMOUNT_TOLERANCE = Decimal("0.01")


class BillingIntegrityError(Exception):
    """Local usage data failed integrity checks."""


def _install_secret_path():
    return os.path.join(storage.get_appdata_path(), INSTALL_SECRET_FILE)


def get_install_secret():
    return _load_or_create_install_secret()


def _load_or_create_install_secret():
    path = _install_secret_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        secret = data.get("secret", "")
        if secret:
            return secret
    secret = secrets.token_hex(32)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"secret": secret}, f, indent=2)
    return secret


def _signing_key():
    install = _load_or_create_install_secret().encode()
    pepper = os.environ.get(
        "FROGSWORK_LEDGER_PEPPER",
        "frogswork-ledger-v1",
    ).encode()
    return hashlib.sha256(install + pepper).digest()


def _canonical_payload(data):
    body = {
        "v": LEDGER_VERSION,
        "usage_month": data.get("usage_month", ""),
        "total_ex_gst": str(Decimal(str(data.get("total_ex_gst", "0")))),
        "cap_enabled": bool(data.get("cap_enabled", False)),
        "cap_amount_ex_gst": data.get("cap_amount_ex_gst"),
        "events": _normalize_events(data.get("events", [])),
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def _normalize_events(events):
    normalized = []
    for event in events or []:
        normalized.append(
            {
                "invoice_number": int(event["invoice_number"]),
                "amount_ex_gst": str(Decimal(str(event["amount_ex_gst"]))),
                "usage_month": event.get("usage_month", ""),
            }
        )
    normalized.sort(key=lambda e: (e["invoice_number"], e["amount_ex_gst"]))
    return normalized


def events_total(events):
    total = Decimal("0")
    for event in events or []:
        amount = Decimal(str(event["amount_ex_gst"]))
        if amount < 0:
            raise BillingIntegrityError("Negative usage event amount.")
        total += amount
    return total


def invoice_month_total_ex_gst(usage_month):
    total = Decimal("0")
    for inv in storage.load_invoices().values():
        inv_date = inv.get("invoice_date", "")
        if not inv_date.startswith(usage_month):
            continue
        try:
            total += Decimal(str(inv.get("amount_ex_gst", "0")))
        except (InvalidOperation, TypeError):
            raise BillingIntegrityError("Invalid invoice amount in records.") from None
    return total


def validate_core_invariants(data):
    if not data.get("usage_month"):
        raise BillingIntegrityError("Missing usage month.")

    try:
        total = Decimal(str(data.get("total_ex_gst", "0")))
    except (InvalidOperation, TypeError) as exc:
        raise BillingIntegrityError("Invalid usage total.") from exc

    if total < 0:
        raise BillingIntegrityError("Usage total cannot be negative.")

    event_sum = events_total(data.get("events", []))
    if abs(total - event_sum) > AMOUNT_TOLERANCE:
        raise BillingIntegrityError("Usage total does not match event history.")


def validate_invoice_cross_check(data):
    invoice_total = invoice_month_total_ex_gst(data["usage_month"])
    total = Decimal(str(data.get("total_ex_gst", "0")))
    if invoice_total > 0 and abs(total - invoice_total) > AMOUNT_TOLERANCE:
        raise BillingIntegrityError("Usage total does not match invoice records for this month.")


def validate_ledger_invariants(data, *, check_invoices=True):
    validate_core_invariants(data)
    if check_invoices:
        validate_invoice_cross_check(data)


def events_from_invoices(usage_month):
    events = []
    total = Decimal("0")
    invoices = storage.load_invoices()
    for key in sorted(invoices.keys(), key=lambda k: int(invoices[k].get("invoice_number", 0))):
        inv = invoices[key]
        inv_date = inv.get("invoice_date", "")
        if not inv_date.startswith(usage_month):
            continue
        try:
            amount = Decimal(str(inv.get("amount_ex_gst", "0")))
        except (InvalidOperation, TypeError):
            raise BillingIntegrityError("Invalid invoice amount in records.") from None
        if amount <= 0:
            continue
        events.append(
            {
                "invoice_number": int(inv["invoice_number"]),
                "amount_ex_gst": str(amount),
                "usage_month": usage_month,
            }
        )
        total += amount
    return events, total


def rebuild_ledger_from_invoices(existing=None):
    """Rebuild a signed ledger from invoice records for the current month."""
    month = billing_core.current_usage_month()
    source = existing or {}
    events, total = events_from_invoices(month)
    return attach_signature(
        {
            "usage_month": month,
            "total_ex_gst": str(total),
            "events": events,
            "cap_enabled": bool(source.get("cap_enabled", False)),
            "cap_amount_ex_gst": source.get("cap_amount_ex_gst"),
        }
    )


def try_repair_ledger(existing):
    """Rebuild from invoices; raises if invoice data cannot produce a valid ledger."""
    rebuilt = rebuild_ledger_from_invoices(existing)
    validate_core_invariants(rebuilt)
    return rebuilt


def attach_signature(data):
    data = dict(data)
    data["ledger_version"] = LEDGER_VERSION
    data["events"] = _normalize_events(data.get("events", []))
    data["total_ex_gst"] = str(Decimal(str(data.get("total_ex_gst", "0"))))
    digest = hmac.new(_signing_key(), _canonical_payload(data).encode(), hashlib.sha256).hexdigest()
    data["ledger_hmac"] = digest
    return data


def verify_signature(data):
    if not data.get("ledger_hmac"):
        return False
    expected = data["ledger_hmac"]
    copy = dict(data)
    copy.pop("ledger_hmac", None)
    digest = hmac.new(_signing_key(), _canonical_payload(copy).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, digest)


def prepare_ledger(
    data,
    *,
    allow_unsigned_migration=False,
    check_invoices=True,
    require_signature=True,
    relaxed=False,
):
    """Validate and normalize ledger; migrate unsigned files when consistent."""
    data = dict(data)
    month = billing_core.current_usage_month()
    if data.get("usage_month") != month:
        return attach_signature(_empty_state())

    if relaxed:
        check_invoices = False
        require_signature = False

    has_sig = bool(data.get("ledger_hmac"))
    if has_sig and require_signature and not verify_signature(data):
        raise BillingIntegrityError("Usage ledger signature invalid.")

    if not has_sig:
        if not allow_unsigned_migration:
            raise BillingIntegrityError("Usage ledger is not signed.")
        validate_ledger_invariants(data, check_invoices=check_invoices)
    else:
        try:
            validate_ledger_invariants(data, check_invoices=check_invoices)
        except BillingIntegrityError:
            if relaxed:
                return attach_signature(_empty_state())
            raise

    return attach_signature(data)


def account_required_for(month_total, additional_ex_gst, cap_enabled):
    additional = Decimal(str(additional_ex_gst))
    projected = month_total + additional
    if cap_enabled:
        return True
    if additional > billing_core.FREE_TIER_EX_GST:
        return True
    return projected > billing_core.FREE_TIER_EX_GST


def _empty_state():
    return {
        "usage_month": billing_core.current_usage_month(),
        "total_ex_gst": "0",
        "events": [],
        "cap_enabled": False,
        "cap_amount_ex_gst": None,
    }
