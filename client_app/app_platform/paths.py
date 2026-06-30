"""Frozen bundle paths, user data directory, and PDF file resolution."""

import os
import sys

from app_config import APP_DATA_DIR_NAME
from platformdirs import user_data_dir

_CLIENT_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def user_data_dir_path():
    """Per-user app data directory (Roaming AppData on Windows)."""
    roaming = sys.platform == "win32"
    path = user_data_dir(APP_DATA_DIR_NAME, False, roaming=roaming)
    os.makedirs(path, exist_ok=True)
    return path


def resource_path(relative):
    base = sys._MEIPASS if getattr(sys, "frozen", False) else _CLIENT_APP_DIR
    return os.path.join(base, relative)


def exe_dir():
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def resolve_pdf_path(filename):
    from flask import abort

    import storage

    if ".." in filename or "/" in filename or "\\" in filename:
        abort(404)
    for inv in storage.load_invoices().values():
        if inv.get("filename") == filename and storage.is_invoice_deleted(inv):
            abort(404)
    primary = os.path.join(storage.get_pdf_dir(), filename)
    if os.path.isfile(primary):
        return primary
    legacy = os.path.join(exe_dir(), filename)
    if os.path.isfile(legacy):
        return legacy
    abort(404)
