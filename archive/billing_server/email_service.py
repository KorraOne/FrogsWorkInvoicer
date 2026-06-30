"""Send platform fee invoice emails."""

import logging
import os
import smtplib
from datetime import date
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from billing_schedule import _payment_due, parse_payment_terms_days
from config import (
    BILLING_EMAIL_ENABLED,
    KORRAONE_BUSINESS,
    PLATFORM_INVOICE_DIR,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USER,
)

logger = logging.getLogger(__name__)


def email_configured():
    return BILLING_EMAIL_ENABLED and bool(SMTP_HOST)


def send_platform_invoice_email(to_email, invoice_row, pdf_path):
    """Email a platform invoice PDF. Returns True if sent."""
    if not email_configured():
        logger.warning("SMTP not configured — skipping email to %s", to_email)
        return False

    invoice_number = invoice_row.get("invoice_number") or invoice_row["id"]
    amount_due = invoice_row.get("amount_due", "")
    try:
        created = date.fromisoformat(str(invoice_row.get("created_at", date.today().isoformat()))[:10])
    except ValueError:
        created = date.today()
    payment_due = _payment_due(created, parse_payment_terms_days())

    subject = f"FrogsWork platform fee invoice {invoice_number}"
    body = (
        f"Hi,\n\n"
        f"Please find attached your FrogsWork platform usage fee invoice ({invoice_number}).\n\n"
        f"Amount due (inc GST): ${amount_due}\n"
        f"Payment due: {payment_due.strftime('%d %B %Y')}\n\n"
        f"{KORRAONE_BUSINESS.get('name', 'KorraOne')}\n"
    )

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(body, "plain"))

    with open(pdf_path, "rb") as handle:
        attachment = MIMEApplication(handle.read(), _subtype="pdf")
    attachment.add_header(
        "Content-Disposition",
        "attachment",
        filename=os.path.basename(pdf_path),
    )
    msg.attach(attachment)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            if SMTP_USE_TLS:
                server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("Failed to send platform invoice email to %s", to_email)
        return False


def mark_invoice_emailed(conn, invoice_id):
    conn.execute(
        "UPDATE platform_invoices SET emailed_at = ? WHERE id = ?",
        (date.today().isoformat(), invoice_id),
    )
