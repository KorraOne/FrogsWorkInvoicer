"""Invoice routes (create + manage)."""

from routes.invoices_create import register_invoice_create_routes
from routes.invoices_manage import register_invoice_manage_routes


def register_invoice_routes(app):
    register_invoice_create_routes(app)
    register_invoice_manage_routes(app)
