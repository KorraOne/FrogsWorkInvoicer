"""Tests for multiple business profiles."""

import json

import storage
from account.telemetry import build_usage_snapshot
from invoicing.format import persist_invoice_counter, suggested_invoice_number


def _setup_data_dir(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr("storage.bootstrap.get_data_path", lambda: str(data_dir))
    monkeypatch.setattr("storage.bootstrap.get_bootstrap_dir", lambda: str(data_dir))
    monkeypatch.setattr("storage.settings.get_data_path", lambda: str(data_dir))
    monkeypatch.setattr("storage.businesses.get_data_path", lambda: str(data_dir))
    monkeypatch.setattr("storage.customers.get_data_path", lambda: str(data_dir))
    monkeypatch.setattr("storage.invoices.get_data_path", lambda: str(data_dir))
    return data_dir


def test_migrate_legacy_settings_to_businesses(tmp_path, monkeypatch):
    data_dir = _setup_data_dir(tmp_path, monkeypatch)
    settings = {
        "business_name": "Hire & Sale Pty Ltd",
        "business_address": "1 Main St",
        "business_abn": "51824753605",
        "gst_registered": True,
        "account_name": "Hire & Sale",
        "bsb": "016-001",
        "acc": "123456",
        "invoice_counter": 12,
        "due_rule_type": "net_days",
        "due_net_days": 14,
    }
    (data_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    loaded = storage.load_businesses()

    assert "Hire & Sale Pty Ltd" in loaded
    assert loaded["Hire & Sale Pty Ltd"]["address"] == "1 Main St"
    assert loaded["Hire & Sale Pty Ltd"]["invoice_counter"] == 12

    migrated_settings = storage.load_settings()
    assert migrated_settings["default_business"] == "Hire & Sale Pty Ltd"
    assert "business_name" not in migrated_settings
    assert "invoice_counter" not in migrated_settings


def test_per_business_invoice_numbering(tmp_path, monkeypatch):
    data_dir = _setup_data_dir(tmp_path, monkeypatch)
    storage.save_businesses(
        {
            "Trust": {"address": "", "abn": "", "gst_registered": False, "invoice_counter": 3},
            "Trading": {"address": "", "abn": "", "gst_registered": True, "invoice_counter": 1},
        }
    )
    storage.save_settings({"default_business": "Trust"})
    storage.save_invoices(
        {
            "00000001": {
                "invoice_number": 1,
                "business_name": "Trust",
                "customer_name": "A",
                "status": "not_sent",
            },
            "00000005": {
                "invoice_number": 5,
                "business_name": "Trading",
                "customer_name": "B",
                "status": "sent",
            },
        }
    )

    assert suggested_invoice_number("Trust") == 3
    assert suggested_invoice_number("Trading") == 6


def test_persist_invoice_counter_updates_business_profile(tmp_path, monkeypatch):
    data_dir = _setup_data_dir(tmp_path, monkeypatch)
    storage.save_businesses(
        {"Trust": {"address": "", "abn": "", "gst_registered": False, "invoice_counter": 1}}
    )

    persist_invoice_counter("Trust", 7)

    updated = storage.load_businesses()
    assert updated["Trust"]["invoice_counter"] == 8


def test_invoice_business_name_falls_back_to_default(tmp_path, monkeypatch):
    data_dir = _setup_data_dir(tmp_path, monkeypatch)
    storage.save_businesses({"Trust": {"address": "", "abn": "", "gst_registered": False}})
    storage.save_settings({"default_business": "Trust"})

    assert storage.invoice_business_name({}) == "Trust"
    assert storage.invoice_business_name({"business_name": "Trading"}) == "Trading"


def test_build_usage_snapshot_includes_business_count(tmp_path, monkeypatch):
    data_dir = _setup_data_dir(tmp_path, monkeypatch)
    storage.save_businesses(
        {
            "A": {"address": "", "abn": "", "gst_registered": False},
            "B": {"address": "", "abn": "", "gst_registered": True},
        }
    )
    storage.save_settings({"default_business": "A"})
    (data_dir / "customers.json").write_text("{}", encoding="utf-8")
    (data_dir / "invoices.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("account.trial_stats.lifetime_totals", lambda: (0, __import__("decimal").Decimal("0")))

    snap = build_usage_snapshot()
    assert snap["business_count"] == 2
    assert snap["gst_registered"] is False
