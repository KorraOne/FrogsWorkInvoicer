import os
import sys

from flask import abort

import storage

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def resource_path(relative):
    base = sys._MEIPASS if getattr(sys, "frozen", False) else BASE_DIR
    return os.path.join(base, relative)


def exe_dir():
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def resolve_pdf_path(filename):
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
