"""Tests for offline billing ledger integrity."""

import json
import os
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch

import billing_core
import billing_ledger


class BillingLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.month = billing_core.current_usage_month()

    def _patch_storage(self, invoices=None):
        return patch.multiple(
            "billing_ledger.storage",
            get_appdata_path=lambda: self.tempdir.name,
            load_invoices=lambda: invoices or {},
        )

    def test_negative_total_rejected(self):
        with self._patch_storage():
            data = {
                "usage_month": self.month,
                "total_ex_gst": "-50000",
                "events": [],
                "cap_enabled": False,
                "cap_amount_ex_gst": None,
            }
            with self.assertRaises(billing_ledger.BillingIntegrityError):
                billing_ledger.prepare_ledger(data, allow_unsigned_migration=True)

    def test_single_invoice_over_free_tier_requires_account(self):
        self.assertTrue(
            billing_ledger.account_required_for(
                Decimal("0"),
                Decimal("2500"),
                False,
            )
        )

    def test_tampered_hmac_rejected(self):
        with self._patch_storage():
            data = billing_ledger.attach_signature(
                {
                    "usage_month": self.month,
                    "total_ex_gst": "100",
                    "events": [
                        {
                            "invoice_number": 1,
                            "amount_ex_gst": "100",
                            "usage_month": self.month,
                        }
                    ],
                    "cap_enabled": False,
                    "cap_amount_ex_gst": None,
                }
            )
            data["total_ex_gst"] = "0"
            with self.assertRaises(billing_ledger.BillingIntegrityError):
                billing_ledger.prepare_ledger(data)

    def test_repair_from_invoices_fixes_mismatch(self):
        invoices = {
            "Acme": {
                "invoice_number": 1,
                "invoice_date": f"{self.month}-15",
                "amount_ex_gst": "500",
            }
        }
        with self._patch_storage(invoices):
            bad = billing_ledger.attach_signature(
                {
                    "usage_month": self.month,
                    "total_ex_gst": "0",
                    "events": [],
                    "cap_enabled": False,
                    "cap_amount_ex_gst": None,
                }
            )
            repaired = billing_ledger.try_repair_ledger(bad)
            self.assertEqual(Decimal(repaired["total_ex_gst"]), Decimal("500"))
            self.assertEqual(len(repaired["events"]), 1)

    def test_relaxed_mode_skips_invoice_cross_check(self):
        invoices = {
            "Acme": {
                "invoice_number": 1,
                "invoice_date": f"{self.month}-15",
                "amount_ex_gst": "500",
            }
        }
        with self._patch_storage(invoices):
            data = billing_ledger.attach_signature(
                {
                    "usage_month": self.month,
                    "total_ex_gst": "0",
                    "events": [],
                    "cap_enabled": False,
                    "cap_amount_ex_gst": None,
                }
            )
            result = billing_ledger.prepare_ledger(data, relaxed=True)
            self.assertEqual(Decimal(result["total_ex_gst"]), Decimal("0"))

    def test_signed_ledger_roundtrip(self):
        with self._patch_storage():
            data = billing_ledger.attach_signature(
                {
                    "usage_month": self.month,
                    "total_ex_gst": "500",
                    "events": [
                        {
                            "invoice_number": 1,
                            "amount_ex_gst": "500",
                            "usage_month": self.month,
                        }
                    ],
                    "cap_enabled": False,
                    "cap_amount_ex_gst": None,
                }
            )
            path = os.path.join(self.tempdir.name, "billing.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            restored = billing_ledger.prepare_ledger(data)
            self.assertTrue(restored.get("ledger_hmac"))


if __name__ == "__main__":
    unittest.main()
