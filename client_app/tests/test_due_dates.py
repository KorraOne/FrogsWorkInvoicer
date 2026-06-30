"""Tests for invoicing.due_dates."""

from datetime import date

from invoicing.due_dates import compute_due_date, due_rule_label, normalize_due_net_days


def test_net_days_due_date():
    inv = date(2026, 6, 1)
    due = compute_due_date(inv, "net_days", net_days=14)
    assert due == date(2026, 6, 15)


def test_normalize_due_net_days_invalid():
    assert normalize_due_net_days("nope", default=7) == 7


def test_due_rule_label_net_days():
    assert due_rule_label("net_days", net_days=1) == "Net 1 day"
    assert due_rule_label("net_days", net_days=14) == "Net 14 days"
