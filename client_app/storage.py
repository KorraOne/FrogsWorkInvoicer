import json

import os

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





def get_config_folder_display():

    return get_bootstrap_dir()





def get_pdf_folder_display():

    return get_pdf_dir()





def is_using_default_pdf_folder():

    return not _load_bootstrap().get("pdf_folder", "").strip()





def set_pdf_folder(path):

    path = path.strip()

    if not path:

        _save_bootstrap({"pdf_folder": ""})

        ensure_app_identity()

        return get_pdf_dir()

    abs_path = os.path.abspath(path)

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

    if not os.path.exists(path):

        save_settings(DEFAULT_SETTINGS.copy())

        return DEFAULT_SETTINGS.copy()

    with open(path, encoding="utf-8") as f:

        settings = json.load(f)

    return _migrate_settings(settings)





def save_settings(settings):

    with open(_settings_path(), "w", encoding="utf-8") as f:

        json.dump(settings, f, indent=2)





def is_welcome_complete():

    return bool(load_settings().get("welcome_complete", False))





def mark_welcome_complete():

    settings = load_settings()

    settings["welcome_complete"] = True

    save_settings(settings)





def load_customers():

    path = _customers_path()

    if not os.path.exists(path):

        save_customers({})

        return {}

    with open(path, encoding="utf-8") as f:

        return json.load(f)





def save_customers(customers):

    with open(_customers_path(), "w", encoding="utf-8") as f:

        json.dump(customers, f, indent=2)





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

        "amount_ex_gst": str(record.get("amount_ex_gst", "0")),

        "filename": record["filename"],

        "due_date": record.get("due_date"),

        "due_rule_type": record.get("due_rule_type"),

        "due_net_days": record.get("due_net_days"),

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





def customer_name_exists(name, exclude=None):

    customers = load_customers()

    for existing in customers:

        if existing.lower() == name.lower() and existing != exclude:

            return True

    return False

