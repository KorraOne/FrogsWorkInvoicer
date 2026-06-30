"""Tests for anonymous install telemetry."""

import hashlib

from account.install_secret import get_install_secret
from account.telemetry import build_signup_snapshot, install_id


def test_install_id_is_stable_hex(monkeypatch, tmp_path):
    secret_path = tmp_path / "account_install.json"
    secret_path.write_text('{"install_secret": "abc123"}', encoding="utf-8")
    monkeypatch.setattr("account.install_secret._install_path", lambda: str(secret_path))

    expected = hashlib.sha256(b"abc123").hexdigest()
    assert install_id() == expected
    assert install_id() == expected
    assert len(install_id()) == 64


def test_build_signup_snapshot_keys(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "invoices.json").write_text("{}", encoding="utf-8")
    (data_dir / "customers.json").write_text("{}", encoding="utf-8")
    (data_dir / "settings.json").write_text('{"gst_registered": true}', encoding="utf-8")

    monkeypatch.setattr("storage.get_data_path", lambda: str(data_dir))
    monkeypatch.setattr("storage.get_appdata_path", lambda: str(data_dir))
    monkeypatch.setattr("storage.load_invoices", lambda: {})
    monkeypatch.setattr("storage.load_customers", lambda: {})
    monkeypatch.setattr("storage.load_settings", lambda: {"gst_registered": True, "welcome_complete": False})

    snap = build_signup_snapshot()
    assert snap["lifetime_invoice_count"] == 0
    assert snap["gst_registered"] is True
    assert snap["trial_gate_hit"] == "none"
