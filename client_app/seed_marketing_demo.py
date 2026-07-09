#!/usr/bin/env python3
"""
Seed AppData with fictional farmland lease and hay sales data for marketing videos.

All names, ABNs, addresses, and amounts are invented placeholders.
Do not use real customer or family data on screen when recording.

Usage (from client_app/):
    python seed_marketing_demo.py --reset
"""

import argparse
import os
import sys
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from invoicing import due_dates, pdf_generator
import storage

# Fictional business for marketing walkthrough recordings only.

MARKETING_BUSINESS_NAME = "Boyanup Pasture Co"

MARKETING_SETTINGS = {
    "due_rule_type": "net_days",
    "due_net_days": 14,
    "welcome_complete": True,
}

MARKETING_BUSINESSES = {
    MARKETING_BUSINESS_NAME: {
        "address": "Lot 12 Ferguson Road\nBoyanup WA 6237",
        "abn": "51824753556",
        "gst_registered": True,
        "account_name": "Boyanup Pasture Co",
        "bsb": "016-002",
        "acc": "482910",
        "invoice_counter": 1,
    },
}

MARKETING_CUSTOMERS = {
    "Capel Agistment Pty Ltd": {
        "address": "88 Bussell Highway\nCapel WA 6271",
        "abn": "87123456789",
        "email": "accounts@capelagistment.example",
    },
    "Harvey Hay Merchants": {
        "address": "15 Uduc Road\nHarvey WA 6220",
        "abn": "99631470012",
        "email": "orders@harveyhay.example",
    },
    "South West Equestrian": {
        "address": "3 Riding School Lane\nDardanup WA 6236",
        "abn": "",
        "email": "office@swequestrian.example",
    },
    "Donnybrook Feed Store": {
        "address": "22 Hampton Street\nDonnybrook WA 6239",
        "abn": "53098740001",
        "email": "payables@donnybrookfeed.example",
    },
    "Bunbury Rural Supplies": {
        "address": "9 Sandridge Road\nBunbury WA 6230",
        "abn": "67112233445",
        "email": "invoices@bunburyrural.example",
    },
}


def _days_ago(days):
    return (date.today() - timedelta(days=days)).isoformat()


def _inc_gst(ex_gst):
    ex = Decimal(str(ex_gst))
    total = (ex * Decimal("1.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return str(total)


def _invoice(number, customer, inv_date, description, ex_gst, status, sent_date=None, paid_date=None):
    inv_date = inv_date or _days_ago(7)
    padded = f"{int(number):08d}"
    return {
        "invoice_number": int(number),
        "invoice_date": inv_date,
        "business_name": MARKETING_BUSINESS_NAME,
        "customer_name": customer,
        "description": description,
        "amount_ex_gst": str(ex_gst),
        "total_inc_gst": _inc_gst(ex_gst),
        "filename": f"Invoice_{padded}_{inv_date}.pdf",
        "status": status,
        "sent_date": sent_date,
        "paid_date": paid_date,
    }


def _seed_invoice_specs():
    return [
        _invoice(1, "Capel Agistment Pty Ltd", _days_ago(3), "Paddock lease, Block A, April", 1200, "not_sent"),
        _invoice(2, "Harvey Hay Merchants", _days_ago(1), "Hay bales, 50 x large rounds", 2750, "not_sent"),
        _invoice(3, "South West Equestrian", _days_ago(0), "Agistment, north paddock, May", 880, "not_sent"),
        _invoice(4, "Capel Agistment Pty Ltd", _days_ago(16), "Paddock lease, Block B, March", 1200, "sent", sent_date=_days_ago(14)),
        _invoice(5, "Donnybrook Feed Store", _days_ago(12), "Hay bales, 30 x large rounds", 1650, "sent", sent_date=_days_ago(10)),
        _invoice(6, "Bunbury Rural Supplies", _days_ago(8), "Hay bales, 20 x small squares", 720, "sent", sent_date=_days_ago(6)),
        _invoice(7, "Harvey Hay Merchants", _days_ago(5), "Hay delivery and stacking", 440, "sent", sent_date=_days_ago(4)),
        _invoice(8, "Capel Agistment Pty Ltd", _days_ago(45), "Paddock lease, Block A, January", 1200, "paid", sent_date=_days_ago(42), paid_date=_days_ago(30)),
        _invoice(9, "Harvey Hay Merchants", _days_ago(38), "Hay bales, 40 x large rounds", 2200, "paid", sent_date=_days_ago(36), paid_date=_days_ago(22)),
        _invoice(10, "South West Equestrian", _days_ago(32), "Agistment, south paddock, Q1", 2640, "paid", sent_date=_days_ago(30), paid_date=_days_ago(18)),
        _invoice(11, "Donnybrook Feed Store", _days_ago(28), "Hay bales, 25 x large rounds", 1375, "paid", sent_date=_days_ago(26), paid_date=_days_ago(14)),
        _invoice(12, "Bunbury Rural Supplies", _days_ago(22), "Hay bales, 15 x small squares", 540, "paid", sent_date=_days_ago(20), paid_date=_days_ago(8)),
        _invoice(13, "Capel Agistment Pty Ltd", _days_ago(60), "Paddock lease, Block C, December", 1200, "paid", sent_date=_days_ago(57), paid_date=_days_ago(40)),
        _invoice(14, "Harvey Hay Merchants", _days_ago(55), "Hay bales, 35 x large rounds", 1925, "paid", sent_date=_days_ago(52), paid_date=_days_ago(35)),
        _invoice(15, "South West Equestrian", _days_ago(48), "Agistment, north paddock, December", 880, "paid", sent_date=_days_ago(45), paid_date=_days_ago(28)),
        _invoice(16, "Donnybrook Feed Store", _days_ago(20), "Hay bales, 10 x large rounds", 550, "sent", sent_date=_days_ago(18)),
        _invoice(17, "Bunbury Rural Supplies", _days_ago(14), "Hay bales, 12 x small squares", 432, "sent", sent_date=_days_ago(12)),
        _invoice(18, "Capel Agistment Pty Ltd", _days_ago(70), "Paddock lease, Block A, November", 1200, "paid", sent_date=_days_ago(68), paid_date=_days_ago(50)),
    ]


def _invoice_key(number):
    return f"{int(number):08d}"


def _seed_invoice_numbers():
    return {spec["invoice_number"] for spec in _seed_invoice_specs()}


def _apply_due_fields(invoice, settings):
    inv_date = date.fromisoformat(invoice["invoice_date"])
    due = due_dates.invoice_due_summary(
        inv_date,
        settings.get("due_rule_type"),
        settings.get("due_net_days"),
    )
    invoice["due_date"] = due["due_date_iso"]
    invoice["due_rule_type"] = due["due_rule_type"]
    invoice["due_net_days"] = due["due_net_days"]
    return invoice


def _pdf_data_for_invoice(invoice, businesses, customers, settings):
    business_name = invoice.get("business_name") or MARKETING_BUSINESS_NAME
    profile = businesses.get(business_name, {})
    sender = storage.business_invoice_fields(business_name, profile)
    customer = customers.get(invoice["customer_name"], {})
    inv_date = date.fromisoformat(invoice["invoice_date"])
    ex_gst = Decimal(invoice["amount_ex_gst"])
    gst_amount = (ex_gst * Decimal("0.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total_inc_gst = Decimal(invoice["total_inc_gst"])
    line_items = [
        {
            "description": invoice["description"],
            "quantity": Decimal("1"),
            "unit_amount_ex_gst": ex_gst,
            "amount_ex_gst": ex_gst,
            "gst_applicable": True,
        }
    ]
    due = due_dates.invoice_due_summary(
        inv_date,
        invoice.get("due_rule_type") or settings.get("due_rule_type"),
        invoice.get("due_net_days") or settings.get("due_net_days"),
    )
    return {
        "invoice_number": invoice["invoice_number"],
        "invoice_date": inv_date,
        **sender,
        "due_date": due["due_date"],
        "due_date_fmt": due["due_date_fmt"],
        "due_rule_label": due["due_rule_label"],
        "customer_name": invoice["customer_name"],
        "customer_address": customer.get("address", ""),
        "customer_abn": customer.get("abn", ""),
        "line_items": line_items,
        "amount_ex_gst": ex_gst,
        "taxable_ex_gst": ex_gst,
        "gst_free_ex_gst": Decimal("0"),
        "gst_amount": gst_amount,
        "total_inc_gst": total_inc_gst,
        "gst_registered": sender.get("gst_registered", False),
        "comment": "",
    }


def _ensure_seed_pdfs(invoices, settings, businesses, customers, added_keys, reset=False):
    pdf_dir = storage.get_pdf_dir()
    seed_numbers = _seed_invoice_numbers()
    generated = 0

    for key, invoice in invoices.items():
        if invoice["invoice_number"] not in seed_numbers:
            continue

        filepath = os.path.join(pdf_dir, invoice.get("filename", ""))
        if not reset and key not in added_keys and os.path.isfile(filepath):
            continue

        pdf_path = pdf_generator.generate_invoice(
            pdf_dir,
            _pdf_data_for_invoice(invoice, businesses, customers, settings),
        )
        invoice["filename"] = os.path.basename(pdf_path)
        generated += 1

    if generated:
        storage.save_invoices(invoices)
    return generated


def run_seed(reset=False):
    if reset:
        storage.save_customers({})
        storage.save_invoices({})

    customers = storage.load_customers()
    for name, info in MARKETING_CUSTOMERS.items():
        customers[name] = info
    storage.save_customers(customers)

    settings = storage.load_settings()
    storage.save_businesses(MARKETING_BUSINESSES.copy())
    businesses = storage.load_businesses()
    settings["default_business"] = MARKETING_BUSINESS_NAME
    for key, value in MARKETING_SETTINGS.items():
        settings[key] = value

    invoices = storage.load_invoices()
    added_keys = set()
    if reset:
        invoices = {}
    for spec in _seed_invoice_specs():
        key = _invoice_key(spec["invoice_number"])
        invoices[key] = spec
        added_keys.add(key)

    for invoice in invoices.values():
        if invoice["invoice_number"] in _seed_invoice_numbers():
            _apply_due_fields(invoice, settings)

    storage.save_invoices(invoices)
    storage.save_settings(settings)

    max_number = max((int(k) for k in invoices), default=0)
    profile = businesses.get(MARKETING_BUSINESS_NAME, {})
    profile["invoice_counter"] = max(int(profile.get("invoice_counter", 1)), max_number + 1)
    businesses[MARKETING_BUSINESS_NAME] = profile
    storage.save_businesses(businesses)

    pdfs_generated = _ensure_seed_pdfs(
        invoices,
        settings,
        businesses,
        customers,
        added_keys=added_keys,
        reset=True,
    )

    storage.ensure_app_identity()

    return {
        "customers_total": len(customers),
        "invoices_total": len(invoices),
        "pdfs_generated": pdfs_generated,
        "next_invoice_number": profile["invoice_counter"],
        "data_path": storage.get_bootstrap_dir(),
        "pdf_path": storage.get_pdf_dir(),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Seed fictional marketing demo data (farmland lease and hay sales)."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Replace customers and invoices with marketing demo data",
    )
    args = parser.parse_args()
    if not args.reset:
        print("Use --reset to replace AppData with marketing demo data.")
        return 1

    summary = run_seed(reset=True)
    print("FrogsWork marketing demo seed (fictional data only)")
    print(f"  Data folder: {summary['data_path']}")
    print(f"  Business:    {MARKETING_BUSINESS_NAME}")
    print(f"  Customers:   {summary['customers_total']}")
    print(f"  Invoices:    {summary['invoices_total']}")
    print(f"  PDFs:        {summary['pdfs_generated']} in {summary['pdf_path']}")
    print(f"  Next invoice #: {summary['next_invoice_number']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
