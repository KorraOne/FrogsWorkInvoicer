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
            return json.load(f)

    if not os.path.exists(path):
        return _read()
    return cached_read(path, _read)


def save_customers(customers):
    path = _customers_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(customers, f, indent=2)
    invalidate(path)


def customer_name_exists(name, exclude=None):
    customers = load_customers()
    for existing in customers:
        if existing.lower() == name.lower() and existing != exclude:
            return True
    return False
