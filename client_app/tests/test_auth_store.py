"""Tests for account auth_store server URL resolution."""

import json
import os
from unittest.mock import patch

import pytest

from account import auth_store


@pytest.fixture
def auth_file(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_store.storage, "get_appdata_path", lambda: str(tmp_path))
    path = tmp_path / "account_auth.json"
    return path


def test_get_server_url_ignores_stale_localhost_when_default_is_production(auth_file):
    auth_file.write_text(
        json.dumps({"server_url": "http://127.0.0.1:8787"}),
        encoding="utf-8",
    )
    with patch.object(auth_store, "DEFAULT_ACCOUNT_API_URL", "https://api.frogswork.com"):
        assert auth_store.get_server_url() == "https://api.frogswork.com"


def test_get_server_url_keeps_localhost_for_local_dev_default(auth_file):
    auth_file.write_text(
        json.dumps({"server_url": "http://127.0.0.1:8787"}),
        encoding="utf-8",
    )
    with patch.object(auth_store, "DEFAULT_ACCOUNT_API_URL", "http://127.0.0.1:8787"):
        assert auth_store.get_server_url() == "http://127.0.0.1:8787"


def test_get_server_url_env_override_wins(auth_file):
    auth_file.write_text(
        json.dumps({"server_url": "http://127.0.0.1:8787"}),
        encoding="utf-8",
    )
    with patch.dict(os.environ, {"FROGSWORK_ACCOUNT_API_URL": "https://staging.example.com"}):
        assert auth_store.get_server_url() == "https://staging.example.com"
