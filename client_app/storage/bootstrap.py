"""AppData paths, PDF folder, and bootstrap identity."""

import json
import os
import shutil
import sys

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

PDF_MARKER_FILENAME = ".frogswork-pdfs"
PDF_SUBFOLDER_NAME = "pdfs"


from app_platform.paths import user_data_dir_path


def get_bootstrap_dir():
    return user_data_dir_path()


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


def get_pdf_dir():
    custom = _load_bootstrap().get("pdf_folder", "").strip()
    if custom:
        path = os.path.abspath(custom)
    else:
        path = os.path.join(get_bootstrap_dir(), "pdfs")
    os.makedirs(path, exist_ok=True)
    _ensure_pdf_marker(path)
    return path


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


def _marker_path(pdf_dir):
    return os.path.join(pdf_dir, PDF_MARKER_FILENAME)


def _ensure_pdf_marker(pdf_dir):
    try:
        marker = _marker_path(pdf_dir)
        if not os.path.exists(marker):
            with open(marker, "w", encoding="utf-8") as f:
                f.write("FrogsWork PDF folder marker.\n")
    except OSError:
        pass


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


def get_config_folder_display():
    return get_bootstrap_dir()


def get_pdf_folder_display():
    return get_pdf_dir()


def is_using_default_pdf_folder():
    return not _load_bootstrap().get("pdf_folder", "").strip()


def normalize_picked_pdf_folder(parent_path):
    """Append a pdfs subfolder to a parent directory chosen in the folder picker."""
    parent = os.path.abspath(parent_path.strip().rstrip("/\\"))
    if not parent:
        return parent
    if os.path.basename(parent).lower() in (PDF_SUBFOLDER_NAME, "pdf"):
        return parent
    return os.path.join(parent, PDF_SUBFOLDER_NAME)


def _pdf_dir_from_bootstrap_no_create():
    custom = _load_bootstrap().get("pdf_folder", "").strip()
    if custom:
        return os.path.abspath(custom)
    return os.path.join(get_bootstrap_dir(), PDF_SUBFOLDER_NAME)


def _find_renamed_pdf_folder(configured_path):
    configured_path = os.path.abspath((configured_path or "").strip())
    if not configured_path:
        return None
    parent = os.path.dirname(configured_path)
    if not os.path.isdir(parent):
        return None
    try:
        candidates = []
        for name in os.listdir(parent):
            full = os.path.join(parent, name)
            if not os.path.isdir(full):
                continue
            if os.path.exists(_marker_path(full)):
                candidates.append(full)
        if len(candidates) == 1:
            return candidates[0]
    except OSError:
        return None
    return None


def _maybe_remove_empty_dir(path):
    try:
        if os.path.isdir(path) and not os.listdir(path):
            os.rmdir(path)
    except OSError:
        pass


def _move_pdf_folder(src_dir, dest_dir):
    src_dir = os.path.abspath(src_dir)
    dest_dir = os.path.abspath(dest_dir)
    if src_dir == dest_dir:
        return
    if not os.path.isdir(src_dir):
        return
    if os.path.exists(dest_dir):
        if not os.path.isdir(dest_dir):
            raise OSError(f"Destination exists and is not a folder: {dest_dir}")
        if os.listdir(dest_dir):
            raise OSError("Destination folder is not empty. Choose an empty folder.")
        _maybe_remove_empty_dir(dest_dir)
    os.makedirs(os.path.dirname(dest_dir), exist_ok=True)
    shutil.move(src_dir, dest_dir)


def set_pdf_folder(path, *, from_picker=False):
    path = path.strip()
    current_pdf_dir = _pdf_dir_from_bootstrap_no_create()
    current_bootstrap = _load_bootstrap().get("pdf_folder", "").strip()
    current_configured = os.path.abspath(current_bootstrap) if current_bootstrap else ""

    if not path:
        default_dir = os.path.join(get_bootstrap_dir(), PDF_SUBFOLDER_NAME)
        if current_configured and not os.path.isdir(current_pdf_dir):
            renamed = _find_renamed_pdf_folder(current_configured)
            if renamed:
                current_pdf_dir = renamed
        if os.path.abspath(current_pdf_dir) != os.path.abspath(default_dir):
            _move_pdf_folder(current_pdf_dir, default_dir)
        _save_bootstrap({"pdf_folder": ""})
        ensure_app_identity()
        return get_pdf_dir()

    abs_path = os.path.abspath(path)
    if from_picker:
        abs_path = normalize_picked_pdf_folder(abs_path)
    if current_configured and not os.path.isdir(current_pdf_dir):
        renamed = _find_renamed_pdf_folder(current_configured)
        if renamed:
            current_pdf_dir = renamed
    if os.path.abspath(current_pdf_dir) != os.path.abspath(abs_path):
        _move_pdf_folder(current_pdf_dir, abs_path)
    os.makedirs(abs_path, exist_ok=True)
    _ensure_pdf_marker(abs_path)
    _save_bootstrap({"pdf_folder": abs_path})
    ensure_app_identity()
    return abs_path


def reset_pdf_folder():
    return set_pdf_folder("", from_picker=False)


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

Australian sole-trader invoicing with a free trial and optional subscription.
Made by {APP_AUTHOR}, {APP_URL}

WHAT THIS FOLDER IS
-------------------
Stores your business settings, customers, invoices, and account cache.
Invoice PDFs are saved separately ({pdf_note}).

FILES HERE
----------
  settings.json          - Business details, bank info, invoice counter
  customers.json         - Saved customers
  invoices.json          - Past invoices and sent/paid status
  account_auth.json      - Login tokens (encrypted)
  entitlement_cache.json - Subscription status (offline grace)
  bootstrap.json         - PDF folder preference
  README.txt             - This file

Config folder: {config_path}

Version {APP_VERSION}
"""
    with open(_readme_path(), "w", encoding="utf-8") as f:
        f.write(content)
