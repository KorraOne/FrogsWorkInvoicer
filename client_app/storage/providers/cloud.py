"""Cloud document API provider with local cache and offline sync queue."""

from __future__ import annotations

import json
import logging
import os
import shutil
from typing import Any

from account import client as account_client
from storage import sync_queue
from storage.bootstrap import get_appdata_path, get_pdf_dir
from storage.providers.local import LocalProvider

log = logging.getLogger(__name__)

_CACHE_DIR = "cloud_cache"


class CloudProvider:
    """HTTP-backed storage with AppData cache mirror and offline queue."""

    name = "cloud"

    def __init__(self):
        self._local = LocalProvider()
        self._cache_root = os.path.join(get_appdata_path(), _CACHE_DIR)
        os.makedirs(self._cache_root, exist_ok=True)

    def _cache_path(self, name: str) -> str:
        return os.path.join(self._cache_root, name)

    def _read_cache(self, name: str, default):
        path = self._cache_path(name)
        if not os.path.exists(path):
            return default
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _write_cache(self, name: str, data) -> None:
        path = self._cache_path(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _bootstrap_if_online(self) -> None:
        try:
            payload = account_client.documents_bootstrap()
        except account_client.AccountOfflineError:
            return
        except Exception:
            log.exception("Cloud bootstrap failed")
            return
        if payload.get("businesses") is not None:
            self._write_cache("businesses.json", payload["businesses"])
        if payload.get("customers") is not None:
            self._write_cache("customers.json", payload["customers"])
        if payload.get("invoices") is not None:
            self._write_cache("invoices.json", payload["invoices"])
        if payload.get("settings") is not None:
            self._write_cache("settings.json", payload["settings"])

    def load_businesses(self) -> dict[str, Any]:
        self._bootstrap_if_online()
        return self._read_cache("businesses.json", self._local.load_businesses())

    def save_businesses(self, businesses: dict[str, Any]) -> None:
        self._write_cache("businesses.json", businesses)
        try:
            account_client.documents_sync(
                [{"type": "upsert_business", "payload": {"businesses": businesses}}]
            )
        except account_client.AccountOfflineError:
            sync_queue.enqueue("upsert_business", {"businesses": businesses})

    def load_customers(self) -> dict[str, Any]:
        self._bootstrap_if_online()
        return self._read_cache("customers.json", self._local.load_customers())

    def save_customers(self, customers: dict[str, Any]) -> None:
        self._write_cache("customers.json", customers)
        try:
            account_client.documents_sync(
                [{"type": "upsert_customer", "payload": {"customers": customers}}]
            )
        except account_client.AccountOfflineError:
            sync_queue.enqueue("upsert_customer", {"customers": customers})

    def load_invoices(self) -> dict[str, Any]:
        self._bootstrap_if_online()
        return self._read_cache("invoices.json", {})

    def load_active_invoices(self) -> dict[str, Any]:
        from storage.invoices import is_invoice_deleted

        return {
            key: inv
            for key, inv in self.load_invoices().items()
            if not is_invoice_deleted(inv)
        }

    def save_invoices(self, invoices: dict[str, Any]) -> None:
        self._write_cache("invoices.json", invoices)

    def get_invoice(self, number, *, include_deleted: bool = False):
        from storage.invoices import is_invoice_deleted

        key = f"{int(number):08d}"
        inv = self.load_invoices().get(key)
        if inv is None:
            return None
        if not include_deleted and is_invoice_deleted(inv):
            return None
        return inv

    def add_invoice(self, record: dict[str, Any]) -> None:
        invoices = self.load_invoices()
        key = f"{int(record['invoice_number']):08d}"
        invoices[key] = {
            "invoice_number": record["invoice_number"],
            "invoice_date": record["invoice_date"],
            "customer_name": record["customer_name"],
            "business_name": record.get("business_name", ""),
            "description": record["description"],
            "total_inc_gst": record["total_inc_gst"],
            "amount_ex_gst": str(record.get("amount_ex_gst", "0")),
            "gst_amount": str(record.get("gst_amount", "0")),
            "filename": record.get("filename", ""),
            "due_date": record.get("due_date"),
            "due_rule_type": record.get("due_rule_type"),
            "due_net_days": record.get("due_net_days"),
            "attachments": list(record.get("attachments") or []),
            "status": record.get("status", "not_sent"),
            "sent_date": record.get("sent_date"),
            "paid_date": record.get("paid_date"),
            "pdf_status": record.get("pdf_status", "pending"),
        }
        self.save_invoices(invoices)
        mutation = {"type": "create_invoice", "payload": {"invoice": invoices[key]}}
        try:
            account_client.documents_sync([mutation])
        except account_client.AccountOfflineError:
            sync_queue.enqueue("create_invoice", mutation["payload"])

    def update_invoice_status(self, number, status: str) -> bool:
        invoices = self.load_invoices()
        key = f"{int(number):08d}"
        if key not in invoices:
            return False
        invoices[key]["status"] = status
        self.save_invoices(invoices)
        payload = {"invoice_number": int(number), "status": status}
        try:
            account_client.documents_sync(
                [{"type": "update_invoice_status", "payload": payload}]
            )
        except account_client.AccountOfflineError:
            sync_queue.enqueue("update_invoice_status", payload)
        return True

    def soft_delete_invoice(self, number) -> bool:
        from datetime import datetime, timezone

        invoices = self.load_invoices()
        key = f"{int(number):08d}"
        if key not in invoices:
            return False
        invoices[key]["deleted_at"] = datetime.now(timezone.utc).isoformat()
        self.save_invoices(invoices)
        return True

    def load_settings(self) -> dict[str, Any]:
        self._bootstrap_if_online()
        cached = self._read_cache("settings.json", None)
        if cached is not None:
            return cached
        return self._local.load_settings()

    def save_settings(self, settings: dict[str, Any]) -> None:
        self._write_cache("settings.json", settings)
        self._local.save_settings(settings)

    def get_pdf_dir(self) -> str:
        pdf_cache = os.path.join(self._cache_root, "pdfs")
        os.makedirs(pdf_cache, exist_ok=True)
        return pdf_cache

    def pdf_available(self, number) -> bool:
        inv = self.get_invoice(number)
        if not inv:
            return False
        if inv.get("pdf_status") == "pending":
            return False
        filename = inv.get("filename") or ""
        if not filename:
            return False
        path = os.path.join(self.get_pdf_dir(), filename)
        return os.path.isfile(path)

    def cache_pdf(self, filename: str, source_path: str) -> None:
        dest = os.path.join(self.get_pdf_dir(), filename)
        shutil.copy2(source_path, dest)

    def download_pdf(self, number) -> str | None:
        """Fetch PDF from API into local cache; return path or None."""
        inv = self.get_invoice(number)
        if not inv:
            return None
        try:
            result = account_client.documents_download_pdf(int(number))
        except Exception:
            log.exception("PDF download failed for invoice %s", number)
            return None
        filename = result.get("filename") or inv.get("filename")
        if not filename:
            return None
        dest = os.path.join(self.get_pdf_dir(), filename)
        content = result.get("content_b64")
        if content:
            import base64

            with open(dest, "wb") as f:
                f.write(base64.b64decode(content))
            invoices = self.load_invoices()
            key = f"{int(number):08d}"
            if key in invoices:
                invoices[key]["pdf_status"] = "ready"
                invoices[key]["filename"] = filename
                self.save_invoices(invoices)
            return dest
        return None

    def enqueue_email_send(self, number: int) -> None:
        payload = {"invoice_number": number}
        invoices = self.load_invoices()
        key = f"{int(number):08d}"
        if key in invoices:
            invoices[key]["status"] = "send_queued"
            self.save_invoices(invoices)
        try:
            account_client.documents_sync(
                [{"type": "enqueue_email_send", "payload": payload}]
            )
        except account_client.AccountOfflineError:
            sync_queue.enqueue("enqueue_email_send", payload)

    def has_pending_sync(self) -> bool:
        return sync_queue.has_pending()

    def flush_sync_queue(self) -> dict[str, Any]:
        items = sync_queue.peek_all()
        if not items:
            return {"flushed": 0, "errors": []}
        mutations = [{"type": item["type"], "payload": item["payload"]} for item in items]
        errors = []
        flushed_ids = set()
        try:
            result = account_client.documents_sync(mutations)
            flushed_ids = {item["id"] for item in items}
            errors = result.get("errors") or []
        except account_client.AccountOfflineError as exc:
            return {"flushed": 0, "errors": [str(exc)]}
        except Exception as exc:
            log.exception("Sync flush failed")
            return {"flushed": 0, "errors": [str(exc)]}
        sync_queue.remove_ids(flushed_ids)
        self._bootstrap_if_online()
        return {"flushed": len(flushed_ids), "errors": errors}
