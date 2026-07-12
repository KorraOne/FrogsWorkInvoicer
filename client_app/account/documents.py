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


def enqueue_invoice_send(invoice_number: int, *, pdf_b64: str | None = None):
    body = {"invoice_number": invoice_number}
    if pdf_b64:
        body["pdf_b64"] = pdf_b64
    try:
        return _request("POST", f"/documents/invoices/{invoice_number}/send", body, auth=True)
    except AccountError as exc:
        if "401" in str(exc) or "token" in str(exc).lower():
            _refresh_if_needed()
            return _request("POST", f"/documents/invoices/{invoice_number}/send", body, auth=True)
        raise
