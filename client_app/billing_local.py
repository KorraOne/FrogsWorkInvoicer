"""Local anonymous usage tracking (authoritative until account signup)."""

import json
import os
from decimal import Decimal

import billing_core
import billing_ledger
import storage


def _billing_path():
    return os.path.join(storage.get_appdata_path(), "billing.json")


def _empty_state():
    return billing_ledger.attach_signature(
        {
            "usage_month": billing_core.current_usage_month(),
            "total_ex_gst": "0",
            "events": [],
            "cap_enabled": False,
            "cap_amount_ex_gst": None,
        }
    )


def _load_relaxed_mode():
    import billing_auth_store

    return billing_auth_store.is_authenticated()


def load_billing():
    path = _billing_path()
    if not os.path.exists(path):
        data = _empty_state()
        save_billing(data)
        return data
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    month = billing_core.current_usage_month()
    if raw.get("usage_month") != month:
        data = _empty_state()
        save_billing(data)
        return data

    relaxed = _load_relaxed_mode()
    try:
        data = billing_ledger.prepare_ledger(
            raw,
            allow_unsigned_migration=True,
            relaxed=relaxed,
        )
    except billing_ledger.BillingIntegrityError:
        if not relaxed:
            try:
                data = billing_ledger.try_repair_ledger(raw)
                save_billing(data)
                return data
            except billing_ledger.BillingIntegrityError:
                pass
        data = dict(raw)
        data["_integrity_failed"] = True
        return data

    if not data.get("ledger_hmac"):
        data = billing_ledger.attach_signature(data)
        save_billing(data)
    return data


def save_billing(data):
    if not data.get("_integrity_failed"):
        data = billing_ledger.attach_signature(data)
    payload = dict(data)
    payload.pop("_integrity_failed", None)
    with open(_billing_path(), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def is_ledger_invalid():
    data = load_billing()
    return bool(data.get("_integrity_failed"))


def repair_ledger_from_invoices():
    """Rebuild usage cache from invoice records for the current month."""
    existing = {}
    path = _billing_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)
    data = billing_ledger.try_repair_ledger(existing)
    save_billing(data)
    return data


def reset_usage_cache():
    """Clear local usage for the current month (fresh free-tier buffer)."""
    data = _empty_state()
    save_billing(data)
    return data


def month_total():
    data = load_billing()
    if data.get("_integrity_failed"):
        raise billing_ledger.BillingIntegrityError("Usage ledger integrity failed.")
    return Decimal(data["total_ex_gst"])


def record_local_commit(invoice_number, amount_ex_gst):
    data = load_billing()
    if data.get("_integrity_failed"):
        raise billing_ledger.BillingIntegrityError("Usage ledger integrity failed.")
    amount = Decimal(str(amount_ex_gst))
    if amount <= 0:
        raise billing_ledger.BillingIntegrityError("Invoice amount must be positive.")
    data["total_ex_gst"] = str(Decimal(data["total_ex_gst"]) + amount)
    data["events"].append(
        {
            "invoice_number": invoice_number,
            "amount_ex_gst": str(amount),
            "usage_month": data["usage_month"],
        }
    )
    save_billing(data)


def revert_local_commit(invoice_number):
    """Remove a local usage event for the current month. Returns True if one was removed."""
    data = load_billing()
    if data.get("_integrity_failed"):
        raise billing_ledger.BillingIntegrityError("Usage ledger integrity failed.")
    inv_key = str(int(invoice_number))
    month = data["usage_month"]
    removed = Decimal("0")
    kept = []
    found = False
    for event in data["events"]:
        if str(event.get("invoice_number")) == inv_key and event.get("usage_month") == month:
            removed += Decimal(event["amount_ex_gst"])
            found = True
        else:
            kept.append(event)
    if not found:
        return False
    data["events"] = kept
    new_total = Decimal(data["total_ex_gst"]) - removed
    if new_total < 0:
        new_total = Decimal("0")
    data["total_ex_gst"] = str(new_total)
    save_billing(data)
    return True


def set_local_cap(enabled, amount=None):
    data = load_billing()
    if data.get("_integrity_failed"):
        raise billing_ledger.BillingIntegrityError("Usage ledger integrity failed.")
    data["cap_enabled"] = bool(enabled)
    data["cap_amount_ex_gst"] = str(amount) if amount is not None else None
    save_billing(data)


def local_cap_settings():
    data = load_billing()
    if data.get("_integrity_failed"):
        return False, None
    enabled = data.get("cap_enabled", False)
    amount = data.get("cap_amount_ex_gst")
    return enabled, Decimal(amount) if amount else None


def local_usage_snapshot(additional_ex_gst=Decimal("0")):
    data = load_billing()
    snap = _usage_snapshot_from_data(data, additional_ex_gst)
    snap["account_authenticated"] = False
    return snap


def load_billing_for_display():
    """Fast billing.json read for navigation meter — no invoice cross-check."""
    path = _billing_path()
    if not os.path.exists(path):
        return {
            "usage_month": billing_core.current_usage_month(),
            "total_ex_gst": "0",
            "events": [],
            "cap_enabled": False,
            "cap_amount_ex_gst": None,
        }
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if raw.get("usage_month") != billing_core.current_usage_month():
        return {
            "usage_month": billing_core.current_usage_month(),
            "total_ex_gst": "0",
            "events": [],
            "cap_enabled": False,
            "cap_amount_ex_gst": None,
        }
    return raw


def _invalid_usage_snapshot():
    return {
        "usage_month": billing_core.current_usage_month(),
        "month_total_ex_gst": Decimal("0"),
        "fee_so_far": Decimal("0"),
        "projected_fee": Decimal("0"),
        "fee_delta": Decimal("0"),
        "free_remaining": billing_core.FREE_TIER_EX_GST,
        "cap_enabled": False,
        "cap_amount_ex_gst": None,
        "cap_blocked": False,
        "over_by": Decimal("0"),
        "account_required": True,
        "account_authenticated": False,
        "server_required": True,
        "ledger_invalid": True,
    }


def _usage_snapshot_from_data(data, additional_ex_gst=Decimal("0")):
    if data.get("_integrity_failed"):
        return _invalid_usage_snapshot()

    month_total = Decimal(str(data.get("total_ex_gst", "0")))
    additional = Decimal(str(additional_ex_gst))
    total = month_total + additional
    fee = billing_core.compute_monthly_fee(total)
    fee_now = billing_core.compute_monthly_fee(month_total)
    cap_enabled = bool(data.get("cap_enabled", False))
    cap_raw = data.get("cap_amount_ex_gst")
    cap_amount = Decimal(str(cap_raw)) if cap_raw else None
    cap_blocked = False
    over_by = Decimal("0")
    if cap_enabled and cap_amount is not None and total > cap_amount:
        cap_blocked = True
        over_by = total - cap_amount
    account_required = billing_ledger.account_required_for(month_total, additional, cap_enabled)
    return {
        "usage_month": data.get("usage_month", billing_core.current_usage_month()),
        "month_total_ex_gst": total,
        "fee_so_far": fee_now,
        "projected_fee": fee,
        "fee_delta": fee - fee_now,
        "free_remaining": billing_core.free_remaining(total),
        "cap_enabled": cap_enabled,
        "cap_amount_ex_gst": cap_amount,
        "cap_blocked": cap_blocked,
        "over_by": over_by,
        "account_required": account_required,
        "account_authenticated": False,
        "server_required": account_required,
        "ledger_invalid": False,
    }


def meter_snapshot(additional_ex_gst=Decimal("0")):
    """Local-only usage for UI meter (navigation). No network or full ledger audit."""
    import billing_auth_store
    import billing_sync

    authenticated = billing_auth_store.is_authenticated()
    usage = None
    if authenticated:
        cached = billing_sync.load_usage_cache()
        if cached:
            usage = dict(cached["usage"])
    if not usage:
        usage = _usage_snapshot_from_data(load_billing_for_display(), additional_ex_gst)
    usage["account_authenticated"] = authenticated
    return usage


def export_events_for_signup():
    data = load_billing()
    if data.get("_integrity_failed"):
        raise billing_ledger.BillingIntegrityError("Usage ledger integrity failed.")
    return {
        "usage_month": data["usage_month"],
        "total_ex_gst": data["total_ex_gst"],
        "events": data.get("events", []),
        "ledger_hmac": data.get("ledger_hmac"),
        "ledger_version": data.get("ledger_version"),
    }
