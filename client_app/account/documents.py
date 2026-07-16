"""Document API client methods."""

from .client import AccountError, AccountOfflineError, _refresh_if_needed, _request

__all__ = [
    "documents_bootstrap",
    "documents_sync",
    "documents_migrate",
    "documents_download_pdf",
    "enqueue_invoice_send",
]


def documents_bootstrap():
    try:
        return _request("GET", "/documents/bootstrap", auth=True)
    except AccountError as exc:
        if "401" in str(exc) or "token" in str(exc).lower():
            _refresh_if_needed()
            return _request("GET", "/documents/bootstrap", auth=True)
        raise


def documents_sync(mutations):
    body = {"mutations": mutations}
    try:
        return _request("POST", "/documents/sync", body, auth=True)
    except AccountError as exc:
        if "401" in str(exc) or "token" in str(exc).lower():
            _refresh_if_needed()
            return _request("POST", "/documents/sync", body, auth=True)
        raise


def documents_migrate(backup_payload: dict):
    try:
        return _request("POST", "/documents/migrate", backup_payload, auth=True)
    except AccountError as exc:
        if "401" in str(exc) or "token" in str(exc).lower():
            _refresh_if_needed()
            return _request("POST", "/documents/migrate", backup_payload, auth=True)
        raise


def documents_download_pdf(invoice_number: int):
    path = f"/documents/invoices/{invoice_number}/pdf"
    try:
        return _request("GET", path, auth=True)
    except AccountError as exc:
        if "401" in str(exc) or "token" in str(exc).lower():
            _refresh_if_needed()
            return _request("GET", path, auth=True)
        raise


def enqueue_invoice_send(
    invoice_number: int,
    *,
    pdf_b64: str | None = None,
    customer_email: str | None = None,
    filename: str | None = None,
    subject: str | None = None,
    body_text: str | None = None,
):
    body = {}
    if pdf_b64:
        body["pdf_b64"] = pdf_b64
    if customer_email:
        body["customer_email"] = customer_email
    if filename:
        body["filename"] = filename
    if subject:
        body["subject"] = subject
    if body_text:
        body["body_text"] = body_text
    path = f"/email/invoices/{invoice_number}/send"
    try:
        return _request("POST", path, body, auth=True)
    except AccountError as exc:
        if "401" in str(exc) or "token" in str(exc).lower():
            _refresh_if_needed()
            return _request("POST", path, body, auth=True)
        raise
