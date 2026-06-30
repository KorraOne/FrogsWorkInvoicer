"""Business settings persistence."""

import json
import os

from storage._json_cache import cached_read, invalidate
from storage.bootstrap import get_data_path

DEFAULT_SETTINGS = {
    "business_name": "",
    "business_address": "",
    "business_abn": "",
    "gst_registered": False,
    "account_name": "",
    "bsb": "",
    "acc": "",
    "payment_terms": "",
    "due_rule_type": "net_days",
    "due_net_days": 14,
    "last_due_rule_type": "",
    "last_due_net_days": 14,
    "last_due_fixed_date": "",
    "invoice_counter": 1,
    "welcome_complete": False,
}


def _settings_path():
    return os.path.join(get_data_path(), "settings.json")


def _migrate_settings(settings):
    from invoicing.due_dates import migrate_settings_due_rule

    changed = False
    for key, value in DEFAULT_SETTINGS.items():
        if key not in settings:
            settings[key] = value
            changed = True
    if migrate_settings_due_rule(settings):
        changed = True
    if changed:
        save_settings(settings)
    return settings


def load_settings():
    path = _settings_path()

    def _read():
        if not os.path.exists(path):
            save_settings(DEFAULT_SETTINGS.copy())
            return DEFAULT_SETTINGS.copy()
        with open(path, encoding="utf-8") as f:
            return _migrate_settings(json.load(f))

    if not os.path.exists(path):
        return _read()
    return cached_read(path, _read)


def save_settings(settings):
    path = _settings_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    invalidate(path)


def is_welcome_complete():
    return bool(load_settings().get("welcome_complete", False))


def mark_welcome_complete():
    settings = load_settings()
    settings["welcome_complete"] = True
    save_settings(settings)
