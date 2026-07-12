"""Tests for storage provider abstraction and sync queue."""

import json

import storage
from storage import sync_queue
from storage.context import get_storage_mode, set_storage_mode, use_cloud_provider
from storage.providers.local import LocalProvider


def _setup_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    monkeypatch.setattr("storage.bootstrap.get_data_path", lambda: str(data_dir))
    monkeypatch.setattr("storage.bootstrap.get_appdata_path", lambda: str(appdata))
    monkeypatch.setattr("storage.bootstrap.get_bootstrap_dir", lambda: str(data_dir))
    monkeypatch.setattr("storage.settings.get_data_path", lambda: str(data_dir))
    monkeypatch.setattr("storage.customers.get_data_path", lambda: str(data_dir))
    monkeypatch.setattr("storage.businesses.get_data_path", lambda: str(data_dir))
    monkeypatch.setattr("storage.invoices.get_data_path", lambda: str(data_dir))
    return data_dir


def test_local_provider_roundtrip(tmp_path, monkeypatch):
    _setup_data_dir(tmp_path, monkeypatch)
    provider = LocalProvider()
    provider.save_customers({"Acme": {"email": "a@example.com"}})
    assert provider.load_customers()["Acme"]["email"] == "a@example.com"


def test_sync_queue_fifo(tmp_path, monkeypatch):
    _setup_data_dir(tmp_path, monkeypatch)
    sync_queue.enqueue("create_invoice", {"invoice": {"invoice_number": 1}})
    assert sync_queue.pending_count() == 1
    items = sync_queue.peek_all()
    sync_queue.remove_ids({items[0]["id"]})
    assert sync_queue.pending_count() == 0


def test_storage_mode_default_local(tmp_path, monkeypatch):
    _setup_data_dir(tmp_path, monkeypatch)
    assert get_storage_mode() == "local"
    assert use_cloud_provider() is False


def test_storage_mode_persisted(tmp_path, monkeypatch):
    _setup_data_dir(tmp_path, monkeypatch)
    set_storage_mode("cloud")
    assert storage.load_settings()["storage_mode"] == "cloud"
