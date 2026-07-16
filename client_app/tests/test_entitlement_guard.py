"""Tests for account.entitlement_guard."""

from unittest.mock import patch

from account import entitlement_guard


@patch("account.entitlement_guard.auth_store.is_authenticated", return_value=False)
def test_check_generate_access_account_required(_auth):
    allowed, status, message = entitlement_guard.check_generate_access()
    assert allowed is False
    assert status == "account_required"
    assert message is not None


@patch("account.entitlement_guard.auth_store.is_authenticated", return_value=True)
@patch("account.entitlement_guard.entitlement_cache.subscription_active_with_grace", return_value=True)
@patch("account.entitlement_guard.entitlement_cache.sync_status", return_value="ok")
def test_check_generate_access_subscribed(_sync, _active, _auth):
    allowed, status, message = entitlement_guard.check_generate_access()
    assert allowed is True
    assert status == "subscribed"
    assert message is None


@patch("account.entitlement_guard.auth_store.is_authenticated", return_value=True)
@patch("account.entitlement_guard.entitlement_cache.subscription_active_with_grace", return_value=False)
@patch("account.entitlement_guard.entitlement_cache.load_cache", return_value={"active": False, "last_verified_at": "2026-01-01"})
@patch("account.entitlement_guard.entitlement_cache.sync_status", return_value="ok")
def test_check_generate_access_subscription_inactive(_sync, _cache, _active, _auth):
    allowed, status, _message = entitlement_guard.check_generate_access()
    assert allowed is False
    assert status == "subscription_inactive"
