"""Tests for dashboard sales totals."""

from datetime import date
from decimal import Decimal

from invoicing.form import dashboard_totals


def test_dashboard_totals_gst_invoice_month_outstanding_paid(monkeypatch):
    monkeypatch.setattr("storage.is_invoice_deleted", lambda inv: False)
    monkeypatch.setattr("storage.load_settings", lambda: {})

    invoices = {
        "1": {
            "invoice_number": 1,
            "invoice_date": "2026-07-05",
            "status": "sent",
            "amount_ex_gst": "300.00",
            "total_inc_gst": "330.00",
        },
        "2": {
            "invoice_number": 2,
            "invoice_date": "2026-06-01",
            "status": "paid",
            "amount_ex_gst": "100.00",
            "total_inc_gst": "110.00",
        },
        "3": {
            "invoice_number": 3,
            "invoice_date": "2026-07-01",
            "status": "paid",
            "amount_ex_gst": "50.00",
            "total_inc_gst": "55.00",
        },
    }

    totals = dashboard_totals(invoices, today=date(2026, 7, 5))

    assert totals["month"]["inc_gst"] == Decimal("385.00")
    assert totals["month"]["ex_gst"] == Decimal("350.00")
    assert totals["outstanding"]["inc_gst"] == Decimal("330.00")
    assert totals["outstanding"]["ex_gst"] == Decimal("300.00")
    assert totals["outstanding"]["count"] == 1
    assert totals["paid"]["inc_gst"] == Decimal("165.00")
    assert totals["paid"]["ex_gst"] == Decimal("150.00")
