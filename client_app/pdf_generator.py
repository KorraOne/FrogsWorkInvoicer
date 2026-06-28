from reportlab.lib import colors
from decimal import Decimal
import os
import re
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PAGE_WIDTH, PAGE_HEIGHT = A4
CONTENT_WIDTH = PAGE_WIDTH - 40 * mm

ACCENT = colors.HexColor("#2c3e50")
LIGHT_GREY = colors.HexColor("#f4f4f4")
BORDER_GREY = colors.HexColor("#cccccc")


def _fmt_money(amount):
    return f"${amount:,.2f}"


def _fmt_abn(abn):
    digits = re.sub(r"\D", "", str(abn))
    if len(digits) == 11:
        return f"{digits[0:2]} {digits[2:5]} {digits[5:8]} {digits[8:11]}"
    return abn


def _fmt_account(acc):
    digits = re.sub(r"\D", "", str(acc))
    if len(digits) == 6:
        return f"{digits[0:3]} {digits[3:6]}"
    return acc


def _fmt_invoice_number(number):
    return f"{int(number):08d}"


def _p(text, style):
    return Paragraph(text.replace("\n", "<br/>"), style)


def _address_paragraphs(address, style):
    if not address:
        return []
    return [_p(line.strip(), style) for line in address.split("\n") if line.strip()]


def generate_invoice(output_dir, invoice_data):
    invoice_number = invoice_data["invoice_number"]
    invoice_number_display = _fmt_invoice_number(invoice_number)
    invoice_date = invoice_data["invoice_date"]
    filename = f"Invoice_{invoice_number_display}_{invoice_date.isoformat()}.pdf"
    filepath = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    business_name_style = ParagraphStyle(
        "BusinessName",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        spaceAfter=4,
    )
    normal = ParagraphStyle(
        "NormalText",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=2,
    )
    label_style = ParagraphStyle(
        "Label",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=colors.HexColor("#666666"),
        spaceAfter=4,
    )
    title_style = ParagraphStyle(
        "TaxInvoiceTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=26,
        alignment=TA_RIGHT,
        textColor=ACCENT,
        spaceAfter=0,
    )
    meta_style = ParagraphStyle(
        "Meta",
        parent=normal,
        alignment=TA_RIGHT,
        leading=14,
        spaceAfter=2,
        spaceBefore=0,
    )
    total_label_style = ParagraphStyle(
        "TotalLabel",
        parent=normal,
        alignment=TA_RIGHT,
        fontName="Helvetica-Bold",
        fontSize=10,
    )
    total_value_style = ParagraphStyle(
        "TotalValue",
        parent=normal,
        alignment=TA_RIGHT,
        fontSize=10,
    )
    grand_total_label = ParagraphStyle(
        "GrandTotalLabel",
        parent=total_label_style,
        fontSize=12,
    )
    grand_total_value = ParagraphStyle(
        "GrandTotalValue",
        parent=total_value_style,
        fontName="Helvetica-Bold",
        fontSize=12,
    )

    story = []

    business_block = []
    business_name = invoice_data.get("business_name", "")
    if business_name:
        business_block.append(Paragraph(business_name, business_name_style))
    business_block.extend(_address_paragraphs(invoice_data.get("business_address", ""), normal))
    business_abn = invoice_data.get("business_abn", "")
    if business_abn:
        business_block.append(Paragraph(f"ABN: {_fmt_abn(business_abn)}", normal))
    if not business_block:
        business_block.append(Paragraph("&nbsp;", normal))

    meta_rows = [[Paragraph("Tax Invoice", title_style)]]
    meta_rows.append([Paragraph(f"<b>Invoice #</b> {invoice_number_display}", meta_style)])
    meta_rows.append([Paragraph(f"<b>Date</b> {invoice_date.strftime('%d %B %Y')}", meta_style)])
    due_date_fmt = invoice_data.get("due_date_fmt", "")
    due_rule_label = invoice_data.get("due_rule_label", "")
    payment_terms = invoice_data.get("payment_terms", "")
    if due_date_fmt:
        meta_rows.append([Paragraph(f"<b>Due</b> {due_date_fmt}", meta_style)])
    elif payment_terms:
        meta_rows.append([Paragraph(f"<b>Terms</b> {payment_terms}", meta_style)])

    meta_block = Table(meta_rows, colWidths=[CONTENT_WIDTH * 0.45])
    meta_block.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 10),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 2),
            ]
        )
    )

    header_table = Table(
        [[business_block, meta_block]],
        colWidths=[CONTENT_WIDTH * 0.55, CONTENT_WIDTH * 0.45],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(header_table)
    story.append(Spacer(1, 8))

    divider = Table([[""]], colWidths=[CONTENT_WIDTH], rowHeights=[2])
    divider.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT)]))
    story.append(divider)
    story.append(Spacer(1, 16))

    bill_to_lines = [Paragraph("BILL TO", label_style)]
    bill_to_lines.append(Paragraph(f"<b>{invoice_data['customer_name']}</b>", normal))
    bill_to_lines.extend(_address_paragraphs(invoice_data.get("customer_address", ""), normal))
    customer_abn = invoice_data.get("customer_abn", "")
    if customer_abn:
        bill_to_lines.append(Paragraph(f"ABN: {_fmt_abn(customer_abn)}", normal))

    bill_to_table = Table([[bill_to_lines]], colWidths=[CONTENT_WIDTH])
    bill_to_table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(bill_to_table)
    story.append(Spacer(1, 16))

    amount_ex_gst = invoice_data["amount_ex_gst"]
    gst_amount = invoice_data["gst_amount"]
    total_inc_gst = invoice_data["total_inc_gst"]
    line_items = invoice_data.get("line_items")
    if not line_items:
        line_items = [
            {
                "description": invoice_data.get("description", ""),
                "quantity": Decimal("1"),
                "unit_amount_ex_gst": amount_ex_gst,
                "amount_ex_gst": amount_ex_gst,
            }
        ]

    def _fmt_qty(qty):
        q = Decimal(str(qty))
        if q == q.to_integral_value():
            return str(int(q))
        return format(q, "f").rstrip("0").rstrip(".")

    amt_right = ParagraphStyle("AmtRight", parent=normal, alignment=TA_RIGHT)
    qty_right = ParagraphStyle("QtyRight", parent=normal, alignment=TA_RIGHT)
    line_data = [
        [
            Paragraph("<b>Description</b>", normal),
            Paragraph("<b>Qty</b>", qty_right),
            Paragraph("<b>Unit (ex GST)</b>", ParagraphStyle("HdrRight", parent=normal, alignment=TA_RIGHT)),
            Paragraph("<b>Amount (ex GST)</b>", ParagraphStyle("HdrRight2", parent=normal, alignment=TA_RIGHT)),
        ],
    ]
    for item in line_items:
        qty = item.get("quantity", Decimal("1"))
        unit = item.get("unit_amount_ex_gst", item["amount_ex_gst"])
        line_data.append(
            [
                Paragraph(item["description"], normal),
                Paragraph(_fmt_qty(qty), qty_right),
                Paragraph(_fmt_money(unit), amt_right),
                Paragraph(_fmt_money(item["amount_ex_gst"]), amt_right),
            ]
        )
    line_table = Table(
        line_data,
        colWidths=[
            CONTENT_WIDTH * 0.46,
            CONTENT_WIDTH * 0.10,
            CONTENT_WIDTH * 0.22,
            CONTENT_WIDTH * 0.22,
        ],
    )
    line_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GREY),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_GREY),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_GREY),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(line_table)
    story.append(Spacer(1, 12))

    totals_data = [
        [Paragraph("Subtotal (ex GST)", total_label_style), Paragraph(_fmt_money(amount_ex_gst), total_value_style)],
        [Paragraph("GST (10%)", total_label_style), Paragraph(_fmt_money(gst_amount), total_value_style)],
        [Paragraph("TOTAL AUD", grand_total_label), Paragraph(_fmt_money(total_inc_gst), grand_total_value)],
    ]
    totals_table = Table(totals_data, colWidths=[CONTENT_WIDTH * 0.72, CONTENT_WIDTH * 0.28])
    totals_table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 2), (-1, 2), 1, ACCENT),
                ("TOPPADDING", (0, 2), (-1, 2), 8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(totals_table)
    story.append(Spacer(1, 20))

    account_name = invoice_data.get("account_name", "")
    bsb = invoice_data.get("bsb", "")
    acc = invoice_data.get("acc", "")
    if account_name or bsb or acc or due_date_fmt or payment_terms:
        payment_lines = [Paragraph("<b>How to pay</b>", ParagraphStyle("PayHdr", parent=normal, fontSize=11, spaceAfter=6))]
        if account_name:
            payment_lines.append(Paragraph(f"Account name: {account_name}", normal))
        if bsb:
            payment_lines.append(Paragraph(f"BSB: {bsb}", normal))
        if acc:
            payment_lines.append(Paragraph(f"Account: {_fmt_account(acc)}", normal))
        if due_date_fmt:
            terms_note = f" ({due_rule_label})" if due_rule_label else ""
            payment_lines.append(Paragraph(f"Payment due: {due_date_fmt}{terms_note}", normal))
        elif payment_terms:
            payment_lines.append(Paragraph(f"Payment terms: {payment_terms}", normal))
        payment_lines.append(Paragraph(f"Reference: Invoice #{invoice_number_display}", normal))

        payment_table = Table([[payment_lines]], colWidths=[CONTENT_WIDTH])
        payment_table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 1, BORDER_GREY),
                    ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
                    ("TOPPADDING", (0, 0), (-1, -1), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                    ("LEFTPADDING", (0, 0), (-1, -1), 12),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ]
            )
        )
        story.append(payment_table)

    comment = invoice_data.get("comment", "")
    if comment:
        story.append(Spacer(1, 12))
        story.append(Paragraph("<b>Notes</b>", label_style))
        story.append(Paragraph(comment, normal))

    doc.build(story)
    return filepath
