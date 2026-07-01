"""Business profile persistence (invoice sender / From details)."""

import json
import os

from storage._json_cache import cached_read, invalidate
from storage.bootstrap import get_data_path

DEFAULT_BUSINESS_PROFILE = {
    "address": "",
    "abn": "",
    "gst_registered": False,
    "account_name": "",
    "bsb": "",
    "acc": "",
    "invoice_counter": 1,
}

_LEGACY_SETTINGS_KEYS = (
    "business_name",
    "business_address",
    "business_abn",
    "gst_registered",
    "account_name",
    "bsb",
    "acc",
    "invoice_counter",
)


def _businesses_path():
    return os.path.join(get_data_path(), "businesses.json")


def _profile_from_legacy_settings(settings):
    name = (settings.get("business_name") or "").strip()
    address = (settings.get("business_address") or "").strip()
    abn = (settings.get("business_abn") or "").strip()
    account_name = (settings.get("account_name") or "").strip()
    bsb = (settings.get("bsb") or "").strip()
    acc = (settings.get("acc") or "").strip()
    gst_registered = bool(settings.get("gst_registered"))
    invoice_counter = int(settings.get("invoice_counter", 1) or 1)

    if not any([name, address, abn, account_name, bsb, acc, gst_registered]):
        return None, None

    profile_name = name or "My business"
    profile = {
        "address": address,
        "abn": abn,
        "gst_registered": gst_registered,
        "account_name": account_name,
        "bsb": bsb,
        "acc": acc,
        "invoice_counter": invoice_counter,
    }
    return profile_name, profile


def _migrate_from_settings_if_needed():
    from storage.settings import load_settings, save_settings

    path = _businesses_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            existing = json.load(f)
        if existing:
            return existing

    settings = load_settings()
    profile_name, profile = _profile_from_legacy_settings(settings)
    if not profile:
        return {}

    businesses = {profile_name: profile}
    save_businesses(businesses)

    settings["default_business"] = profile_name
    for key in _LEGACY_SETTINGS_KEYS:
        settings.pop(key, None)
    save_settings(settings)
    return businesses


def load_businesses():
    path = _businesses_path()

    def _read():
        if not os.path.exists(path):
            migrated = _migrate_from_settings_if_needed()
            if migrated:
                return migrated
            return {}
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not data:
            migrated = _migrate_from_settings_if_needed()
            return migrated if migrated else {}
        return data

    if not os.path.exists(path):
        return _read()
    return cached_read(path, _read)


def save_businesses(businesses):
    path = _businesses_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(businesses, f, indent=2)
    invalidate(path)


def business_name_exists(name, exclude=None):
    businesses = load_businesses()
    for existing in businesses:
        if existing.lower() == name.lower() and existing != exclude:
            return True
    return False


def get_default_business_name():
    from storage.settings import load_settings

    settings = load_settings()
    default_name = (settings.get("default_business") or "").strip()
    businesses = load_businesses()
    if default_name in businesses:
        return default_name
    if businesses:
        return next(iter(businesses))
    return ""


def set_default_business(name):
    from storage.settings import load_settings, save_settings

    settings = load_settings()
    settings["default_business"] = name
    save_settings(settings)


def resolve_business(name=None):
    """Return (name, profile dict) for the given or default business."""
    businesses = load_businesses()
    if not businesses:
        return "", {}

    if name:
        name = name.strip()
        if name in businesses:
            return name, dict(businesses[name])

    default_name = get_default_business_name()
    if default_name in businesses:
        return default_name, dict(businesses[default_name])

    first_name = next(iter(businesses))
    return first_name, dict(businesses[first_name])


def invoice_business_name(inv):
    """Business name for an invoice record (handles legacy invoices)."""
    stored = (inv.get("business_name") or "").strip()
    if stored:
        return stored
    return get_default_business_name()


def business_invoice_fields(name, profile=None):
    """Map a business profile to invoice_data sender fields."""
    if profile is None:
        name, profile = resolve_business(name)
    profile = profile or {}
    return {
        "business_name": name,
        "business_address": profile.get("address", ""),
        "business_abn": profile.get("abn", ""),
        "account_name": profile.get("account_name", ""),
        "bsb": profile.get("bsb", ""),
        "acc": profile.get("acc", ""),
        "gst_registered": bool(profile.get("gst_registered")),
    }


def normalize_business_profile(form_data, existing=None):
    """Build a profile dict from form fields."""
    existing = existing or {}
    return {
        "address": form_data.get("address", existing.get("address", "")).strip(),
        "abn": form_data.get("abn", existing.get("abn", "")).strip(),
        "gst_registered": form_data.get("gst_registered", existing.get("gst_registered", False)),
        "account_name": form_data.get("account_name", existing.get("account_name", "")).strip(),
        "bsb": form_data.get("bsb", existing.get("bsb", "")).strip(),
        "acc": form_data.get("acc", existing.get("acc", "")).strip(),
        "invoice_counter": int(existing.get("invoice_counter", 1) or 1),
    }
