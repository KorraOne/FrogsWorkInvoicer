"""Invoice records and PDF lifecycle."""

import json
import os
import shutil
import time
from datetime import date

from storage._json_cache import cached_read, invalidate
from storage.bootstrap import get_deleted_pdf_dir, get_data_path, get_pdf_dir

VALID_STATUSES = ("not_sent", "send_queued", "send_failed", "sent", "paid")

STATUS_TRANSITIONS = {
    "not_sent": "sent",
    "sent": "paid",
}


def is_invoice_deleted(inv):
    return bool(inv.get("deleted_at"))


def _invoices_path():
    return os.path.join(get_data_path(), "invoices.json")


def _invoice_key(number):
    return f"{int(number):08d}"


def load_invoices():
    from storage.context import active_provider

    provider = active_provider()
    if provider is not None:
        return provider.load_invoices()
    path = _invoices_path()

    def _read():
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    if not os.path.exists(path):
        return {}
    return cached_read(path, _read)


def load_active_invoices():
    from storage.context import active_provider

    provider = active_provider()
    if provider is not None:
        return provider.load_active_invoices()
    return {
        key: inv
        for key, inv in load_invoices().items()
        if not is_invoice_deleted(inv)
    }


def get_invoice(number, *, include_deleted=False):
    from storage.context import active_provider

    provider = active_provider()
    if provider is not None:
        return provider.get_invoice(number, include_deleted=include_deleted)
    inv = load_invoices().get(_invoice_key(number))
    if inv is None:
        return None
    if not include_deleted and is_invoice_deleted(inv):
        return None
    return inv


def save_invoices(invoices):
    from storage.context import active_provider

    provider = active_provider()
    if provider is not None:
        provider.save_invoices(invoices)
        return
    path = _invoices_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(invoices, f, indent=2)
    invalidate(path)


def add_invoice(record):
    from storage.context import active_provider

    provider = active_provider()
    if provider is not None:
        provider.add_invoice(record)
        return
    invoices = load_invoices()
    key = _invoice_key(record["invoice_number"])
    invoices[key] = {
        "invoice_number": record["invoice_number"],
        "invoice_date": record["invoice_date"],
        "customer_name": record["customer_name"],
        "business_name": record.get("business_name", ""),
        "description": record["description"],
        "total_inc_gst": record["total_inc_gst"],
        "amount_ex_gst": str(record.get("amount_ex_gst", "0")),
        "gst_amount": str(record.get("gst_amount", "0")),
        "filename": record["filename"],
        "due_date": record.get("due_date"),
        "due_rule_type": record.get("due_rule_type"),
        "due_net_days": record.get("due_net_days"),
        "attachments": list(record.get("attachments") or []),
        "status": "not_sent",
        "sent_date": None,
        "paid_date": None,
    }
    save_invoices(invoices)


def invoice_attachments_dir(number):
    key = _invoice_key(number)
    path = os.path.join(get_data_path(), "attachments", key)
    os.makedirs(path, exist_ok=True)
    return path


def remove_invoice_attachments(number):
    key = _invoice_key(number)
    path = os.path.join(get_data_path(), "attachments", key)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def archive_invoice_attachments(number):
    key = _invoice_key(number)
    src = os.path.join(get_data_path(), "attachments", key)
    if not os.path.isdir(src):
        return None
    dest_root = os.path.join(get_deleted_pdf_dir(), "attachments")
    os.makedirs(dest_root, exist_ok=True)
    dest = os.path.join(dest_root, key)
    if os.path.isdir(dest):
        dest = os.path.join(dest_root, f"{key}_{int(time.time())}")
    shutil.move(src, dest)
    return os.path.basename(dest)


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
    elif status == "send_queued":
        pass
    elif status == "send_failed":
        pass
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
