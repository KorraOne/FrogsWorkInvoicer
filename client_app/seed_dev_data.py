#!/usr/bin/env python3
"""
Populate AppData with realistic dev/test data (customers, invoices, settings).

Usage (from client_app/):
    python seed_dev_data.py           # merge — skip existing customers / invoice numbers
    python seed_dev_data.py --reset   # replace customers, invoices, and seed settings
"""

import argparse
import os
import sys
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

import billing_core
import billing_local
import due_dates
import pdf_generator
import storage

# --- Seed content (edit freely for your dev scenarios) ---

SEED_SETTINGS = {
    "business_name": "Sam Chen — Garden & Property",
    "business_address": "Unit 4, 18 Kingsley Street\nFremantle WA 6160",
    "business_abn": "51824793601",
    "account_name": "Sam Chen",
    "bsb": "016-001",
    "acc": "284719",
    "due_rule_type": "net_days",
    "due_net_days": 14,
    "welcome_complete": True,
}

SEED_CUSTOMERS = {
    "Harbour View Cafe": {
        "address": "42 Marine Terrace\nFremantle WA 6160",
        "abn": "87145632109",
        "email": "accounts@harbourviewcafe.example",
    },
    "Pelican Point Strata": {
        "address": "C/- Ace Body Corporate\nPO Box 120\nNorth Fremantle WA 6159",
        "abn": "99631478523",
        "email": "levies@pelicanpointstrata.example",
    },
    "West Coast Electrical": {
        "address": "7 Forge Street\nO'Connor WA 6163",
        "abn": "",
        "email": "payables@westcoastelectrical.example",
    },
    "Margaret Nguyen": {
        "address": "15 Pine Avenue\nPalmyra WA 6157",
        "abn": "",
        "email": "margaret.nguyen@example.com",
    },
    "Old Port Gallery": {
        "address": "22 Henry Street\nFremantle WA 6160",
        "abn": "53098741256",
        "email": "",
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
        "customer_name": customer,
        "description": description,
        "amount_ex_gst": str(ex_gst),
        "total_inc_gst": _inc_gst(ex_gst),
        "filename": f"Invoice_{padded}_{inv_date}.pdf",
        "status": status,
        "sent_date": sent_date,
        "paid_date": paid_date,
    }


def _mixed_gst_invoice(number, customer, inv_date, lines, status, sent_date=None, paid_date=None):
    """lines: list of (description, ex_gst, gst_free bool)."""
    inv_date = inv_date or _days_ago(7)
    padded = f"{int(number):08d}"
    taxable = Decimal("0")
    gst_free_total = Decimal("0")
    line_items = []
    descriptions = []
    for desc, ex_gst, gst_free in lines:
        ex = Decimal(str(ex_gst))
        gst_applicable = not gst_free
        if gst_applicable:
            taxable += ex
        else:
            gst_free_total += ex
        line_items.append(
            {
                "description": desc,
                "quantity": Decimal("1"),
                "unit_amount_ex_gst": ex,
                "amount_ex_gst": ex,
                "gst_applicable": gst_applicable,
                "gst_free": gst_free,
            }
        )
        descriptions.append(desc)
    gst_amount = (taxable * Decimal("0.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    amount_ex_gst = taxable + gst_free_total
    total_inc_gst = amount_ex_gst + gst_amount
    return {
        "invoice_number": int(number),
        "invoice_date": inv_date,
        "customer_name": customer,
        "description": "; ".join(descriptions[:2]) + (" (+more)" if len(descriptions) > 2 else ""),
        "amount_ex_gst": str(amount_ex_gst),
        "taxable_ex_gst": str(taxable),
        "gst_free_ex_gst": str(gst_free_total),
        "gst_amount": str(gst_amount),
        "total_inc_gst": str(total_inc_gst),
        "line_items": line_items,
        "filename": f"Invoice_{padded}_{inv_date}.pdf",
        "status": status,
        "sent_date": sent_date,
        "paid_date": paid_date,
    }


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


def _pdf_data_for_invoice(invoice, settings, customers):
    customer = customers.get(invoice["customer_name"], {})
    inv_date = date.fromisoformat(invoice["invoice_date"])
    if invoice.get("line_items"):
        line_items = invoice["line_items"]
        taxable_ex_gst = Decimal(invoice.get("taxable_ex_gst", invoice["amount_ex_gst"]))
        gst_free_ex_gst = Decimal(invoice.get("gst_free_ex_gst", "0"))
        amount_ex_gst = Decimal(invoice["amount_ex_gst"])
        gst_amount = Decimal(invoice.get("gst_amount", "0"))
        total_inc_gst = Decimal(invoice["total_inc_gst"])
    else:
        ex_gst = Decimal(invoice["amount_ex_gst"])
        gst_amount = (ex_gst * Decimal("0.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_inc_gst = Decimal(invoice["total_inc_gst"])
        taxable_ex_gst = ex_gst
        gst_free_ex_gst = Decimal("0")
        amount_ex_gst = ex_gst
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
        "business_name": settings.get("business_name", ""),
        "business_address": settings.get("business_address", ""),
        "business_abn": settings.get("business_abn", ""),
        "account_name": settings.get("account_name", ""),
        "bsb": settings.get("bsb", ""),
        "acc": settings.get("acc", ""),
        "due_date": due["due_date"],
        "due_date_fmt": due["due_date_fmt"],
        "due_rule_label": due["due_rule_label"],
        "customer_name": invoice["customer_name"],
        "customer_address": customer.get("address", ""),
        "customer_abn": customer.get("abn", ""),
        "line_items": line_items,
        "amount_ex_gst": amount_ex_gst,
        "taxable_ex_gst": taxable_ex_gst,
        "gst_free_ex_gst": gst_free_ex_gst,
        "gst_amount": gst_amount,
        "total_inc_gst": total_inc_gst,
        "comment": "",
    }


def _seed_invoice_numbers():
    return {spec["invoice_number"] for spec in _seed_invoice_specs()}


def _ensure_seed_pdfs(invoices, settings, customers, added_keys, reset=False):
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
            _pdf_data_for_invoice(invoice, settings, customers),
        )
        invoice["filename"] = os.path.basename(pdf_path)
        generated += 1

    if generated:
        storage.save_invoices(invoices)
    return generated


def _seed_invoice_specs():
    """Variety of statuses, dates, and amounts for dashboard / list / filter testing."""
    return [
        _invoice(1, "Harbour View Cafe", _days_ago(2), "Monthly grounds maintenance — March", 880, "not_sent"),
        _invoice(
            2,
            "Margaret Nguyen",
            _days_ago(0),
            "Hedge trim and green waste removal",
            420,
            "not_sent",
        ),
        _mixed_gst_invoice(
            9,
            "West Coast Electrical",
            _days_ago(1),
            [
                ("Labour — trenching (GST)", 600, False),
                ("Council permit fee (GST-free)", 85, True),
            ],
            "not_sent",
        ),
        _invoice(
            3,
            "Pelican Point Strata",
            _days_ago(18),
            "Common-area garden refresh (+2 more)",
            2400,
            "sent",
            sent_date=_days_ago(15),
        ),
        _invoice(
            4,
            "West Coast Electrical",
            _days_ago(10),
            "Site clearance before cable run",
            650,
            "sent",
            sent_date=_days_ago(8),
        ),
        _invoice(
            5,
            "Old Port Gallery",
            _days_ago(5),
            "Courtyard repaving prep and labour",
            3200,
            "sent",
            sent_date=_days_ago(3),
        ),
        _invoice(
            6,
            "Harbour View Cafe",
            _days_ago(52),
            "Irrigation repair and mulch top-up",
            1500,
            "paid",
            sent_date=_days_ago(49),
            paid_date=_days_ago(35),
        ),
        _invoice(
            7,
            "Pelican Point Strata",
            _days_ago(28),
            "Seasonal prune — north garden bed",
            990,
            "paid",
            sent_date=_days_ago(26),
            paid_date=_days_ago(12),
        ),
        _invoice(
            8,
            "Margaret Nguyen",
            _days_ago(14),
            "Lawn restoration and fertiliser",
            450,
            "paid",
            sent_date=_days_ago(12),
            paid_date=_days_ago(2),
        ),
    ]


def _invoice_key(number):
    return f"{int(number):08d}"


def _seed_billing_from_invoices(invoices, reset):
    """Align local usage cache with this month's seeded invoice totals."""
    month = billing_core.current_usage_month()
    month_total = Decimal("0")
    events = []

    for inv in invoices.values():
        if not inv["invoice_date"].startswith(month):
            continue
        ex = Decimal(inv.get("amount_ex_gst", "0"))
        month_total += ex
        events.append(
            {
                "invoice_number": inv["invoice_number"],
                "amount_ex_gst": str(ex),
                "usage_month": month,
            }
        )

    if month_total == 0 and not reset:
        return

    data = billing_local.load_billing() if not reset else billing_local._empty_state()
    if reset or data.get("usage_month") != month:
        data = billing_local._empty_state()

    data["usage_month"] = month
    data["total_ex_gst"] = str(month_total)
    data["events"] = events
    billing_local.save_billing(data)


def run_seed(reset=False):
    if reset:
        storage.save_customers({})
        storage.save_invoices({})

    customers = storage.load_customers()
    added_customers = 0
    for name, info in SEED_CUSTOMERS.items():
        if name not in customers:
            customers[name] = info
            added_customers += 1
    storage.save_customers(customers)

    invoices = storage.load_invoices()
    added_invoices = 0
    added_keys = set()
    for spec in _seed_invoice_specs():
        key = _invoice_key(spec["invoice_number"])
        if key not in invoices:
            invoices[key] = spec
            added_invoices += 1
            added_keys.add(key)

    settings = storage.load_settings()
    if reset:
        for key, value in SEED_SETTINGS.items():
            settings[key] = value
    else:
        for key, value in SEED_SETTINGS.items():
            if key == "welcome_complete":
                settings[key] = True
            elif not settings.get(key):
                settings[key] = value

    for invoice in invoices.values():
        if invoice["invoice_number"] in _seed_invoice_numbers():
            _apply_due_fields(invoice, settings)

    storage.save_invoices(invoices)
    storage.save_settings(settings)

    max_number = max((int(k) for k in invoices), default=0)
    settings["invoice_counter"] = max(settings.get("invoice_counter", 1), max_number + 1)
    storage.save_settings(settings)

    pdfs_generated = _ensure_seed_pdfs(
        invoices,
        settings,
        customers,
        added_keys=added_keys,
        reset=reset,
    )

    _seed_billing_from_invoices(invoices, reset=reset)
    storage.ensure_app_identity()

    return {
        "customers_total": len(customers),
        "customers_added": added_customers,
        "invoices_total": len(invoices),
        "invoices_added": added_invoices,
        "pdfs_generated": pdfs_generated,
        "next_invoice_number": settings["invoice_counter"],
        "data_path": storage.get_bootstrap_dir(),
        "pdf_path": storage.get_pdf_dir(),
    }


def main():
    parser = argparse.ArgumentParser(description="Seed FrogsWork dev/test data in AppData.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Replace customers and invoices, re-apply seed business settings",
    )
    args = parser.parse_args()

    summary = run_seed(reset=args.reset)

    mode = "reset + seed" if args.reset else "merge seed"
    print(f"FrogsWork dev seed ({mode})")
    print(f"  Data folder: {summary['data_path']}")
    print(f"  Customers: {summary['customers_total']} ({summary['customers_added']} added)")
    print(f"  Invoices:  {summary['invoices_total']} ({summary['invoices_added']} added)")
    print(f"  PDFs:      {summary['pdfs_generated']} generated in {summary['pdf_path']}")
    print(f"  Next invoice #: {summary['next_invoice_number']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
