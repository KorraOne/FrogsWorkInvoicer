"""Customer records persistence."""

import json
import os

from storage._json_cache import cached_read, invalidate
from storage.bootstrap import get_data_path

DEFAULT_CUSTOMERS = {}


def _customers_path():
    return os.path.join(get_data_path(), "customers.json")


def load_customers():
    path = _customers_path()

    def _read():
        if not os.path.exists(path):
            save_customers({})
            return {}
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if _migrate_structured_addresses_if_needed(data):
            save_customers(data)
        return data

    if not os.path.exists(path):
        return _read()
    return cached_read(path, _read)


def save_customers(customers):
    path = _customers_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(customers, f, indent=2)
    invalidate(path)


def _migrate_structured_addresses_if_needed(customers):
    from invoicing.address import migrate_legacy_address

    changed = False
    for name, rec in (customers or {}).items():
        if not isinstance(rec, dict):
            continue
        if any(k in rec for k in ("address_line1", "suburb", "state", "postcode")):
            continue
        legacy = (rec.get("address") or "").strip()
        if not legacy:
            rec.setdefault("address_line1", "")
            rec.setdefault("address_line2", "")
            rec.setdefault("suburb", "")
            rec.setdefault("state", "")
            rec.setdefault("postcode", "")
            changed = True
            continue
        rec.update(migrate_legacy_address(legacy))
        changed = True
    return changed


def customer_name_exists(name, exclude=None):
    customers = load_customers()
    for existing in customers:
        if existing.lower() == name.lower() and existing != exclude:
            return True
    return False
