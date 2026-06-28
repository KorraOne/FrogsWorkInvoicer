"""
Developer-editable UI copy and UX parameters.

Edit placeholders and labels here — templates read them via `ph` and `select_labels`.
"""

import os

# How long after the last request before the app shuts down (dev browser mode and idle watchdog).
IDLE_TIMEOUT_SECONDS = int(os.environ.get("FROGWORK_IDLE_TIMEOUT", "90"))

# Inline placeholder text for empty fields (omit key or use "" to leave a field without one).
PLACEHOLDERS = {
    # Customer
    "customer_name": "e.g. Acme Pty Ltd",
    "customer_address": "Street address, suburb, state, postcode",
    "customer_abn": "XX XXX XXX XXX",
    "customer_email": "customer@example.com",
    # Your business (settings / onboarding)
    "business_name": "e.g. Jane Smith Trading",
    "business_address": "PO Box or street, suburb, state, postcode",
    "business_abn": "XX XXX XXX XXX",
    "bank_bsb": "XXX-XXX",
    "bank_account_name": "Name on the bank account",
    "bank_account_number": "XXXXXX",
    "due_net_days": "e.g. 14",
    "invoice_counter": "e.g. 57",
    # Account (platform login)
    "account_email": "you@example.com",
    # Sales invoice
    "line_item_description": "e.g. Consulting – March 2026",
    "line_item_quantity": "1",
    "line_item_amount": "e.g. 4500.00",
    "invoice_comment": "e.g. Payment due within 30 days",
    # Past invoices filter
    "invoice_search": "Customer, description, or invoice number",
    # Billing / caps
    "fee_calculator_amount": "e.g. 8000",
    "cap_amount_ex_gst": "e.g. 5000",
    "cap_fee_amount": "e.g. 1.50",
}

# First / empty options on dropdowns.
SELECT_LABELS = {
    "customer_picker": "Select a customer",
    "invoice_status_all": "All statuses",
    "invoice_customer_all": "All customers",
}
