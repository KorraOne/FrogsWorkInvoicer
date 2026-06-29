import json

import copy

import os

import shutil

import sys

import time

from datetime import date

from app_config import (
    APP_BRAND_DEVELOPER,
    APP_BRAND_DEVELOPER_URL,
    APP_BRAND_NAME,
    APP_DATA_DIR_NAME,
    APP_VERSION,
)

APP_NAME = APP_BRAND_NAME
APP_AUTHOR = APP_BRAND_DEVELOPER
APP_URL = APP_BRAND_DEVELOPER_URL



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

    "invoice_counter": 1,

    "welcome_complete": False,

}



DEFAULT_CUSTOMERS = {}



_json_cache = {}



def _file_mtime(path):

    try:

        return os.path.getmtime(path)

    except OSError:

        return None





def _cached_read(path, loader):

    mtime = _file_mtime(path)

    entry = _json_cache.get(path)

    if entry and entry[0] == mtime:

        return copy.deepcopy(entry[1])

    data = loader()

    _json_cache[path] = (mtime, data)

    return copy.deepcopy(data)





def _invalidate_json_cache(path):

    _json_cache.pop(path, None)





def get_bootstrap_dir():

    path = os.path.join(os.environ["APPDATA"], APP_DATA_DIR_NAME)

    os.makedirs(path, exist_ok=True)

    return path





def get_default_data_path():

    return get_bootstrap_dir()





def _bootstrap_path():

    return os.path.join(get_bootstrap_dir(), "bootstrap.json")





def _load_bootstrap():

    path = _bootstrap_path()

    if not os.path.exists(path):

        return {"pdf_folder": ""}

    with open(path, encoding="utf-8") as f:

        data = json.load(f)

    pdf_folder = data.get("pdf_folder", "").strip()

    if not pdf_folder:

        pdf_folder = _legacy_pdf_folder(data.get("data_folder", "").strip())

    return {"pdf_folder": pdf_folder}





def _legacy_pdf_folder(data_folder):

    """Map old data_folder bootstrap value to a PDF directory."""

    if not data_folder:

        return ""

    legacy = os.path.abspath(data_folder)

    legacy_pdfs = os.path.join(legacy, "pdfs")

    if os.path.isdir(legacy_pdfs):

        return legacy_pdfs

    return legacy





def _save_bootstrap(data):

    with open(_bootstrap_path(), "w", encoding="utf-8") as f:

        json.dump(data, f, indent=2)





def get_data_path():

    path = get_bootstrap_dir()

    os.makedirs(path, exist_ok=True)

    os.makedirs(get_pdf_dir(), exist_ok=True)

    return path





def get_appdata_path():

    return get_bootstrap_dir()


def get_or_create_flask_secret():
    import secrets

    path = os.path.join(get_bootstrap_dir(), "local_secrets.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        secret = data.get("flask_secret_key", "")
        if secret:
            return secret
    secret = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"flask_secret_key": secret}, f, indent=2)
    return secret





def get_pdf_dir():

    custom = _load_bootstrap().get("pdf_folder", "").strip()

    if custom:

        path = os.path.abspath(custom)

    else:

        path = os.path.join(get_bootstrap_dir(), "pdfs")

    os.makedirs(path, exist_ok=True)

    return path





def _mark_hidden_if_supported(path):

    if sys.platform != "win32":

        return

    import ctypes

    FILE_ATTRIBUTE_HIDDEN = 0x02

    ctypes.windll.kernel32.SetFileAttributesW(path, FILE_ATTRIBUTE_HIDDEN)





def get_deleted_pdf_dir():

    """AppData archive for soft-deleted invoice PDFs (outside the user-chosen PDF folder)."""

    path = os.path.join(get_bootstrap_dir(), ".deleted")

    os.makedirs(path, exist_ok=True)

    _mark_hidden_if_supported(path)

    return path





def is_invoice_deleted(inv):

    return bool(inv.get("deleted_at"))





def get_config_folder_display():

    return get_bootstrap_dir()





def get_pdf_folder_display():

    return get_pdf_dir()





def is_using_default_pdf_folder():

    return not _load_bootstrap().get("pdf_folder", "").strip()





PDF_SUBFOLDER_NAME = "pdfs"





def normalize_picked_pdf_folder(parent_path):

    """Append a pdfs subfolder to a parent directory chosen in the folder picker."""

    parent = os.path.abspath(parent_path.strip().rstrip("/\\"))

    if not parent:

        return parent

    if os.path.basename(parent).lower() in (PDF_SUBFOLDER_NAME, "pdf"):

        return parent

    return os.path.join(parent, PDF_SUBFOLDER_NAME)





def set_pdf_folder(path, *, from_picker=False):

    path = path.strip()

    if not path:

        _save_bootstrap({"pdf_folder": ""})

        ensure_app_identity()

        return get_pdf_dir()

    abs_path = os.path.abspath(path)

    if from_picker:

        abs_path = normalize_picked_pdf_folder(abs_path)

    os.makedirs(abs_path, exist_ok=True)

    _save_bootstrap({"pdf_folder": abs_path})

    ensure_app_identity()

    return abs_path





def reset_pdf_folder():

    _save_bootstrap({"pdf_folder": ""})

    ensure_app_identity()

    return get_pdf_dir()





# Backwards-compatible aliases used by routes/templates during transition

get_data_folder_display = get_pdf_folder_display

is_using_default_data_folder = is_using_default_pdf_folder

set_data_folder = set_pdf_folder

reset_data_folder = reset_pdf_folder





def _readme_path():

    return os.path.join(get_data_path(), "README.txt")





def ensure_app_identity():

    config_path = get_bootstrap_dir()

    pdf_path = get_pdf_dir()

    pdf_note = (

        "Default: pdfs/ subfolder under this AppData directory."

        if is_using_default_pdf_folder()

        else f"Custom PDF folder: {pdf_path}"

    )

    content = f"""{APP_NAME}

{'=' * len(APP_NAME)}



Australian sole-trader invoicing with usage-based pricing.

Made by {APP_AUTHOR}, {APP_URL}



WHAT THIS FOLDER IS

-------------------

Stores your business settings, customers, invoices, and billing cache.

Invoice PDFs are saved separately ({pdf_note}).



FILES HERE

----------

  settings.json     - Business details, bank info, invoice counter

  customers.json    - Saved customers

  invoices.json     - Past invoices and sent/paid status

  billing.json      - Local usage cache (this month)

  billing_auth.json - Login tokens (encrypted)

  bootstrap.json    - PDF folder preference

  README.txt        - This file



Config folder: {config_path}



Version {APP_VERSION}

"""

    with open(_readme_path(), "w", encoding="utf-8") as f:

        f.write(content)





def _settings_path():

    return os.path.join(get_data_path(), "settings.json")





def _customers_path():

    return os.path.join(get_data_path(), "customers.json")





def _migrate_settings(settings):

    from due_dates import migrate_settings_due_rule

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

    return _cached_read(path, _read)





def save_settings(settings):

    path = _settings_path()

    with open(path, "w", encoding="utf-8") as f:

        json.dump(settings, f, indent=2)

    _invalidate_json_cache(path)





def is_welcome_complete():

    return bool(load_settings().get("welcome_complete", False))





def mark_welcome_complete():

    settings = load_settings()

    settings["welcome_complete"] = True

    save_settings(settings)





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

    return _cached_read(path, _read)





def save_customers(customers):

    path = _customers_path()

    with open(path, "w", encoding="utf-8") as f:

        json.dump(customers, f, indent=2)

    _invalidate_json_cache(path)





def _invoices_path():

    return os.path.join(get_data_path(), "invoices.json")





def _invoice_key(number):

    return f"{int(number):08d}"





VALID_STATUSES = ("not_sent", "sent", "paid")



STATUS_TRANSITIONS = {

    "not_sent": "sent",

    "sent": "paid",

}





def load_invoices():

    path = _invoices_path()

    def _read():
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    if not os.path.exists(path):
        return {}

    return _cached_read(path, _read)





def load_active_invoices():

    return {

        key: inv

        for key, inv in load_invoices().items()

        if not is_invoice_deleted(inv)

    }





def get_invoice(number, *, include_deleted=False):

    inv = load_invoices().get(_invoice_key(number))

    if inv is None:

        return None

    if not include_deleted and is_invoice_deleted(inv):

        return None

    return inv





def save_invoices(invoices):

    path = _invoices_path()

    with open(path, "w", encoding="utf-8") as f:

        json.dump(invoices, f, indent=2)

    _invalidate_json_cache(path)





def add_invoice(record):

    invoices = load_invoices()

    key = _invoice_key(record["invoice_number"])

    invoices[key] = {

        "invoice_number": record["invoice_number"],

        "invoice_date": record["invoice_date"],

        "customer_name": record["customer_name"],

        "description": record["description"],

        "total_inc_gst": record["total_inc_gst"],

        "amount_ex_gst": str(record.get("amount_ex_gst", "0")),

        "gst_amount": str(record.get("gst_amount", "0")),

        "filename": record["filename"],

        "due_date": record.get("due_date"),

        "due_rule_type": record.get("due_rule_type"),

        "due_net_days": record.get("due_net_days"),

        "status": "not_sent",

        "sent_date": None,

        "paid_date": None,

    }

    save_invoices(invoices)





def set_invoice_status(number, status):

    if status not in VALID_STATUSES:

        raise ValueError(f"Invalid status: {status}")



    invoices = load_invoices()

    key = _invoice_key(number)

    if key not in invoices:

        raise KeyError(f"Invoice not found: {number}")



    invoice = invoices[key]

    if is_invoice_deleted(invoice):

        raise KeyError(f"Invoice not found: {number}")



    if invoice["status"] == status:

        return invoice



    today = date.today().isoformat()

    invoice["status"] = status

    if status == "not_sent":

        invoice["sent_date"] = None

        invoice["paid_date"] = None

    elif status == "sent":

        if not invoice.get("sent_date"):

            invoice["sent_date"] = today

        invoice["paid_date"] = None

    elif status == "paid":

        if not invoice.get("sent_date"):

            invoice["sent_date"] = today

        if not invoice.get("paid_date"):

            invoice["paid_date"] = today



    save_invoices(invoices)

    return invoice





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



    return set_invoice_status(number, status)





def soft_delete_invoice(number):

    invoices = load_invoices()

    key = _invoice_key(number)

    if key not in invoices:

        raise KeyError(f"Invoice not found: {number}")



    invoice = invoices[key]

    if is_invoice_deleted(invoice):

        raise ValueError(f"Invoice already deleted: {number}")



    invoice["deleted_at"] = date.today().isoformat()

    save_invoices(invoices)

    return invoice





def hard_delete_invoice(number):

    invoices = load_invoices()

    key = _invoice_key(number)

    if key not in invoices:

        raise KeyError(f"Invoice not found: {number}")



    invoice = invoices.pop(key)

    save_invoices(invoices)

    return invoice





def archive_invoice_pdf(filename):

    """Move a PDF into AppData/.deleted (not the user's PDF folder)."""

    if not filename or ".." in filename or "/" in filename or "\\" in filename:

        return None



    primary = os.path.join(get_pdf_dir(), filename)

    src = primary if os.path.isfile(primary) else None

    if src is None:

        return None



    dest_dir = get_deleted_pdf_dir()

    dest = os.path.join(dest_dir, filename)

    if os.path.isfile(dest):

        base, ext = os.path.splitext(filename)

        dest = os.path.join(dest_dir, f"{base}_{int(time.time())}{ext}")



    shutil.move(src, dest)

    return os.path.basename(dest)





def remove_invoice_pdf(filename):

    """Permanently delete a PDF from the active PDF folder."""

    if not filename or ".." in filename or "/" in filename or "\\" in filename:

        return



    path = os.path.join(get_pdf_dir(), filename)

    if os.path.isfile(path):

        os.remove(path)





def delete_invoice(number):

    """Hard-delete an invoice record (cancel flow)."""

    return hard_delete_invoice(number)





def customer_name_exists(name, exclude=None):

    customers = load_customers()

    for existing in customers:

        if existing.lower() == name.lower() and existing != exclude:

            return True

    return False

