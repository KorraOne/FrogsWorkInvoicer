"""Tests for account.trial_stats."""

from decimal import Decimal
from unittest.mock import patch

from account import trial_stats


@patch("account.trial_stats.storage.load_invoices", return_value={})
def test_under_trial_limits_empty(_load):
    assert trial_stats.under_trial_limits() is True


@patch(
    "account.trial_stats.storage.load_invoices",
    return_value={
        "1": {"amount_ex_gst": "20000", "status": "not_sent"},
    },
)
@patch("account.trial_stats.storage.is_invoice_deleted", return_value=False)
def test_trial_gate_reached_by_amount(_deleted, _load):
    assert trial_stats.trial_gate_reached() is True


@patch("account.trial_stats.storage.load_invoices", return_value={})
def test_meter_snapshot(_load):
    snap = trial_stats.meter_snapshot()
    assert snap["invoices_remaining"] == snap["max_invoices"]
    assert snap["amount_remaining_ex_gst"] == Decimal(str(snap["max_ex_gst"]))
