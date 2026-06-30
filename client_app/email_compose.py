"""Prepare invoice email details and PDF location for manual sending."""

import logging
import os
import subprocess
import sys

from gst_settings import invoice_uses_tax_invoice

log = logging.getLogger(__name__)


class EmailComposeError(Exception):
    pass


def _invoice_label(invoice, settings):
    return "Tax Invoice" if invoice_uses_tax_invoice(invoice, settings) else "Invoice"


def build_invoice_email_context(invoice, customer, settings, pdf_path):
    business = settings.get("business_name", "").strip() or "Your business"
    customer_name = invoice.get("customer_name", "")
    inv_num = invoice.get("invoice_number", "")
    if isinstance(inv_num, int):
        inv_num_str = f"{inv_num:08d}"
    else:
        inv_num_str = str(inv_num).zfill(8) if str(inv_num).isdigit() else str(inv_num)

    total = invoice.get("total_inc_gst", "0")
    try:
        from decimal import Decimal

        total_fmt = f"${Decimal(str(total)):,.2f}"
    except Exception:
        total_fmt = f"${total}"

    label = _invoice_label(invoice, settings)
    to_email = customer.get("email", "").strip() if customer else ""
    subject = f"{label} #{inv_num_str} from {business}"

    body_lines = [
        f"Hi {customer_name}," if customer_name else "Hi,",
        "",
        f"Attached is {label.lower()} #{inv_num_str} for {total_fmt}.",
        f"Payment reference: Invoice #{inv_num_str}",
    ]
    due_date = invoice.get("due_date", "").strip()
    if due_date:
        try:
            from due_dates import format_due_date
            from datetime import date as date_cls

            parts = due_date.split("-")
            due_fmt = format_due_date(date_cls(int(parts[0]), int(parts[1]), int(parts[2])))
            body_lines.extend(["", f"Payment due: {due_fmt}"])
        except (ValueError, IndexError):
            body_lines.extend(["", f"Payment due: {due_date}"])
    else:
        payment_terms = settings.get("payment_terms", "").strip()
        if payment_terms:
            body_lines.extend(["", f"Payment terms: {payment_terms}"])
    body_lines.extend(["", "Thank you,", business])
    body = "\r\n".join(body_lines)

    return {
        "to": to_email,
        "subject": subject,
        "body": body,
        "pdf_path": os.path.abspath(pdf_path),
        "pdf_filename": os.path.basename(pdf_path),
    }


def format_clipboard_text(ctx):
    lines = [
        f"Subject: {ctx['subject']}",
        "",
        "--- Message ---",
        ctx["body"],
        "",
        "--- Attach this file ---",
        ctx["pdf_path"],
    ]
    if ctx["to"]:
        lines.insert(0, f"To: {ctx['to']}")
        lines.insert(1, "")
    return "\r\n".join(lines)


def _reveal_with_explorer(path):
    subprocess.Popen(["explorer", "/select," + path])


def _reveal_with_shell_api(path):
    import ctypes

    pidl = ctypes.windll.shell32.ILCreateFromPathW(path)
    if not pidl:
        return False
    try:
        ctypes.windll.shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0)
        return True
    finally:
        ctypes.windll.ole32.CoTaskMemFree(pidl)


def reveal_pdf_in_folder(pdf_path):
    """Open Explorer with the PDF selected (Windows only, user-initiated)."""
    if not os.path.isfile(pdf_path):
        raise EmailComposeError("Invoice PDF not found.")
    if sys.platform != "win32":
        raise EmailComposeError("Show in folder is Windows only.")

    path = os.path.normpath(os.path.abspath(pdf_path))

    try:
        _reveal_with_explorer(path)
        return
    except OSError as exc:
        log.warning("explorer /select failed for %s: %s", path, exc)

    try:
        if _reveal_with_shell_api(path):
            return
    except OSError as exc:
        log.warning("SHOpenFolderAndSelectItems failed for %s: %s", path, exc)
    except Exception:
        log.exception("SHOpenFolderAndSelectItems failed for %s", path)

    folder = os.path.dirname(path)
    try:
        os.startfile(folder)
        raise EmailComposeError(
            "Opened the invoice folder but couldn't highlight the PDF. "
            "Find the file in the folder that opened."
        )
    except OSError as exc:
        log.warning("os.startfile failed for %s: %s", folder, exc)
    except EmailComposeError:
        raise
    except Exception:
        log.exception("os.startfile failed for %s", folder)

    raise EmailComposeError(
        "Couldn't open the PDF folder. Close any Explorer windows for this folder and try again, "
        "or open it from Settings → Data storage."
    )
