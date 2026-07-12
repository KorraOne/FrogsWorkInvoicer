"""Local AppData JSON storage — wraps existing storage modules."""

from __future__ import annotations

from typing import Any

import storage.businesses as businesses_mod
import storage.customers as customers_mod
import storage.invoices as invoices_mod
import storage.settings as settings_mod
from storage.bootstrap import get_pdf_dir
from app_platform.paths import resolve_pdf_path


class LocalProvider:
    name = "local"

    def load_businesses(self) -> dict[str, Any]:
        return businesses_mod.load_businesses()

    def save_businesses(self, businesses: dict[str, Any]) -> None:
        businesses_mod.save_businesses(businesses)

    def load_customers(self) -> dict[str, Any]:
        return customers_mod.load_customers()

    def save_customers(self, customers: dict[str, Any]) -> None:
        customers_mod.save_customers(customers)

    def load_invoices(self) -> dict[str, Any]:
        return invoices_mod.load_invoices()

    def load_active_invoices(self) -> dict[str, Any]:
        return invoices_mod.load_active_invoices()

    def save_invoices(self, invoices: dict[str, Any]) -> None:
        invoices_mod.save_invoices(invoices)

    def get_invoice(self, number, *, include_deleted: bool = False):
        return invoices_mod.get_invoice(number, include_deleted=include_deleted)

    def add_invoice(self, record: dict[str, Any]) -> None:
        invoices_mod.add_invoice(record)

    def update_invoice_status(self, number, status: str) -> bool:
        return invoices_mod.update_invoice_status(number, status)

    def soft_delete_invoice(self, number) -> bool:
        return invoices_mod.soft_delete_invoice(number)

    def load_settings(self) -> dict[str, Any]:
        return settings_mod.load_settings()

    def save_settings(self, settings: dict[str, Any]) -> None:
        settings_mod.save_settings(settings)

    def get_pdf_dir(self) -> str:
        return get_pdf_dir()

    def pdf_available(self, number) -> bool:
        inv = invoices_mod.get_invoice(number)
        if not inv:
            return False
        filename = inv.get("filename")
        if not filename:
            return False
        return resolve_pdf_path(filename) is not None

    def has_pending_sync(self) -> bool:
        return False

    def flush_sync_queue(self) -> dict[str, Any]:
        return {"flushed": 0, "errors": []}
