"""Invoice PDF facade — routes call generate_invoice() only."""

from invoicing.pdf.templates.classic import render_classic_invoice

_DEFAULT_TEMPLATE = "classic"


def generate_invoice(output_dir, invoice_data, template_id=None):
    """Write an invoice PDF; template_id reserved for future user-selectable layouts."""
    template = template_id or _DEFAULT_TEMPLATE
    if template == "classic":
        return render_classic_invoice(output_dir, invoice_data)
    raise ValueError(f"Unknown PDF template: {template}")
