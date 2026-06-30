"""Tests for account.entitlement_guard."""

from unittest.mock import patch

from account import entitlement_guard


@patch("account.entitlement_guard.trial_stats.under_trial_limits", return_value=True)
def test_check_generate_access_trial_ok(_under):
    allowed, status, message = entitlement_guard.check_generate_access()
    assert allowed is True
    assert status == "trial_ok"
    assert message is None


@patch("account.entitlement_guard.trial_stats.under_trial_limits", return_value=False)
@patch("account.entitlement_guard.auth_store.is_authenticated", return_value=False)
def test_check_generate_access_account_required(_auth, _under):
    allowed, status, _message = entitlement_guard.check_generate_access()
    assert allowed is False
    assert status == "account_required"


@patch("account.entitlement_guard.trial_stats.under_trial_limits", return_value=False)
@patch("account.entitlement_guard.auth_store.is_authenticated", return_value=True)
@patch("account.entitlement_guard.entitlement_cache.subscription_active_with_grace", return_value=True)
@patch("account.entitlement_guard.entitlement_cache.sync_status", return_value="ok")
def test_check_generate_access_subscribed(_sync, _active, _auth, _under):
    allowed, status, message = entitlement_guard.check_generate_access()
    assert allowed is True
    assert status == "subscribed"
    assert message is None
