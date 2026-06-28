"""Prepare invoice email details and PDF location for manual sending."""

import os
import subprocess


class EmailComposeError(Exception):
    pass


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

    to_email = customer.get("email", "").strip() if customer else ""
    subject = f"Tax Invoice #{inv_num_str} from {business}"

    body_lines = [
        f"Hi {customer_name}," if customer_name else "Hi,",
        "",
        f"Please find attached tax invoice #{inv_num_str} for {total_fmt}.",
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
    }


def format_clipboard_text(ctx):
    lines = [f"Subject: {ctx['subject']}", "", "--- Message ---", ctx["body"], "", "--- Attach this file ---", ctx["pdf_path"]]
    if ctx["to"]:
        lines.insert(0, f"To: {ctx['to']}")
        lines.insert(1, "")
    return "\r\n".join(lines)


def prepare_manual_send(ctx):
    if not os.path.isfile(ctx["pdf_path"]):
        raise EmailComposeError("Invoice PDF not found.")

    _copy_to_clipboard(format_clipboard_text(ctx))
    subprocess.Popen(["explorer", "/select,", ctx["pdf_path"]])


def _copy_to_clipboard(text):
    escaped = text.replace("'", "''")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"Set-Clipboard -Value '{escaped}'"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise EmailComposeError("Could not copy to clipboard.")
