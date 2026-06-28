import json
import os
from datetime import date

APP_NAME = "Invoice App"
APP_VERSION = "1.0"
APP_AUTHOR = "KorraOne.com"
APP_URL = "https://korraone.com"

DEFAULT_SETTINGS = {
    "business_name": "Marri Downs Holdings Pty Ltd",
    "business_address": "PO Box 200\nBoyanup WA 6237",
    "business_abn": "61164343300",
    "account_name": "Marri Downs Holdings Pty Ltd",
    "bsb": "036-122",
    "acc": "549645",
    "payment_terms": "Net 30th after",
    "invoice_counter": 56,
}

DEFAULT_CUSTOMERS = {
    "Rodwell Farms": {
        "address": "PO Box 72\nBoyanup WA 6230",
        "abn": "65429514308",
    }
}


def get_appdata_path():
    path = os.path.join(os.environ["APPDATA"], "InvoiceApp")
    os.makedirs(path, exist_ok=True)
    return path


def _readme_path():
    return os.path.join(get_appdata_path(), "README.txt")


def ensure_app_identity():
    """Write a plain-text identifier so this AppData folder is self-explanatory."""
    content = f"""{APP_NAME}
{'=' * len(APP_NAME)}

A simple invoicing tool for creating tax invoices and PDF files.
Built for personal and family use.

WHAT THIS FOLDER IS
-------------------
This folder belongs to {APP_NAME}. It stores your business settings
and customer list used by the program. It is created automatically
when you run InvoiceApp.exe.

Your generated invoice PDFs are saved in the same folder as the
InvoiceApp program, not in this AppData folder.

FILES HERE
----------
  settings.json   - Your business details, bank info, invoice counter
  customers.json  - Saved customers
  invoices.json   - Past invoices and their sent/paid status
  README.txt      - This file

Made by {APP_AUTHOR}
{APP_URL}

Please do not edit the JSON files by hand unless you know what you
are doing. Use the Settings, Customers, and Past Invoices screens in
the app instead.

Version {APP_VERSION}
"""
    with open(_readme_path(), "w", encoding="utf-8") as f:
        f.write(content)


def _settings_path():
    return os.path.join(get_appdata_path(), "settings.json")


def _customers_path():
    return os.path.join(get_appdata_path(), "customers.json")


def _migrate_settings(settings):
    changed = False
    for key, value in DEFAULT_SETTINGS.items():
        if key not in settings:
            settings[key] = value
            changed = True
    if changed:
        save_settings(settings)
    return settings


def load_settings():
    path = _settings_path()
    if not os.path.exists(path):
        save_settings(DEFAULT_SETTINGS.copy())
        return DEFAULT_SETTINGS.copy()
    with open(path, encoding="utf-8") as f:
        settings = json.load(f)
    return _migrate_settings(settings)


def save_settings(settings):
    with open(_settings_path(), "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def load_customers():
    path = _customers_path()
    if not os.path.exists(path):
        save_customers(DEFAULT_CUSTOMERS.copy())
        return DEFAULT_CUSTOMERS.copy()
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_customers(customers):
    with open(_customers_path(), "w", encoding="utf-8") as f:
        json.dump(customers, f, indent=2)


def _invoices_path():
    return os.path.join(get_appdata_path(), "invoices.json")


def _invoice_key(number):
    return f"{int(number):08d}"


VALID_STATUSES = ("not_sent", "sent", "paid")

STATUS_TRANSITIONS = {
    "not_sent": "sent",
    "sent": "paid",
}


def load_invoices():
    path = _invoices_path()
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_invoices(invoices):
    with open(_invoices_path(), "w", encoding="utf-8") as f:
        json.dump(invoices, f, indent=2)


def get_invoice(number):
    return load_invoices().get(_invoice_key(number))


def add_invoice(record):
    invoices = load_invoices()
    key = _invoice_key(record["invoice_number"])
    invoices[key] = {
        "invoice_number": record["invoice_number"],
        "invoice_date": record["invoice_date"],
        "customer_name": record["customer_name"],
        "description": record["description"],
        "total_inc_gst": record["total_inc_gst"],
        "filename": record["filename"],
        "status": "not_sent",
        "sent_date": None,
        "paid_date": None,
    }
    save_invoices(invoices)


def update_invoice_status(number, status):
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")

    invoices = load_invoices()
    key = _invoice_key(number)
    if key not in invoices:
        raise KeyError(f"Invoice not found: {number}")

    invoice = invoices[key]
    expected = STATUS_TRANSITIONS.get(invoice["status"])
    if expected != status:
        raise ValueError(
            f"Cannot change status from {invoice['status']} to {status}"
        )

    today = date.today().isoformat()
    invoice["status"] = status
    if status == "sent":
        invoice["sent_date"] = today
    elif status == "paid":
        invoice["paid_date"] = today

    save_invoices(invoices)
    return invoice
