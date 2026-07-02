"""Classic tax-invoice PDF layout (ReportLab)."""

from decimal import Decimal
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from invoicing.format import (
    format_abn,
    format_account,
    format_bsb,
    format_invoice_number,
    format_money,
    format_qty,
)
from invoicing.gst_settings import invoice_uses_tax_invoice

PAGE_WIDTH, PAGE_HEIGHT = A4
CONTENT_WIDTH = PAGE_WIDTH - 40 * mm

ACCENT = colors.HexColor("#2c3e50")
LIGHT_GREY = colors.HexColor("#f4f4f4")
BORDER_GREY = colors.HexColor("#cccccc")


def _p(text, style):
    return Paragraph(text.replace("\n", "<br/>"), style)


def _address_paragraphs(address, style):
    if not address:
        return []
    return [_p(line.strip(), style) for line in address.split("\n") if line.strip()]


def render_classic_invoice(output_dir, invoice_data):
    invoice_number = invoice_data["invoice_number"]
    invoice_number_display = format_invoice_number(invoice_number)
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

    gst_registered = invoice_uses_tax_invoice(invoice_data)
    invoice_title = "Tax Invoice" if gst_registered else "Invoice"

    meta_rows = [[Paragraph(invoice_title, title_style)]]
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

    logo_block = [Paragraph("&nbsp;", normal)]
    if invoice_data.get("logo_enabled"):
        logo_path = invoice_data.get("logo_path")
        if logo_path and os.path.isfile(logo_path):
            try:
                img = Image(logo_path)
                max_w = 45 * mm
                max_h = 25 * mm
                iw, ih = float(img.imageWidth), float(img.imageHeight)
                scale = min(max_w / iw, max_h / ih, 1.0) if iw and ih else 1.0
                img.drawWidth = iw * scale
                img.drawHeight = ih * scale
                logo_block = [img]
            except Exception:
                logo_block = [Paragraph("&nbsp;", normal)]

    header_table = Table(
        [[logo_block, meta_block]],
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

    business_block = []
    business_name = invoice_data.get("business_name", "")
    if business_name:
        business_block.append(Paragraph(business_name, business_name_style))
    business_block.extend(_address_paragraphs(invoice_data.get("business_address", ""), normal))
    business_abn = invoice_data.get("business_abn", "")
    if business_abn:
        business_block.append(Paragraph(f"ABN: {format_abn(business_abn)}", normal))
    if not business_block:
        business_block.append(Paragraph("&nbsp;", normal))

    normal_right = ParagraphStyle("NormalRight", parent=normal, alignment=TA_RIGHT)
    label_style_right = ParagraphStyle("LabelRight", parent=label_style, alignment=TA_RIGHT)
    bill_to_lines = [Paragraph("BILL TO", label_style_right)]
    bill_to_lines.append(Paragraph(f"<b>{invoice_data['customer_name']}</b>", normal_right))
    bill_to_lines.extend(_address_paragraphs(invoice_data.get("customer_address", ""), normal_right))
    customer_abn = invoice_data.get("customer_abn", "")
    if customer_abn:
        bill_to_lines.append(Paragraph(f"ABN: {format_abn(customer_abn)}", normal_right))

    details_table = Table(
        [[business_block, bill_to_lines]],
        colWidths=[CONTENT_WIDTH * 0.55, CONTENT_WIDTH * 0.45],
    )
    details_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(details_table)
    story.append(Spacer(1, 16))

    amount_ex_gst = invoice_data["amount_ex_gst"]
    gst_amount = invoice_data["gst_amount"]
    total_inc_gst = invoice_data["total_inc_gst"]
    taxable_ex_gst = invoice_data.get("taxable_ex_gst", amount_ex_gst)
    gst_free_ex_gst = invoice_data.get("gst_free_ex_gst", Decimal("0"))
    line_items = invoice_data.get("line_items")
    if not line_items:
        line_items = [
            {
                "description": invoice_data.get("description", ""),
                "quantity": Decimal("1"),
                "unit_amount_ex_gst": amount_ex_gst,
                "amount_ex_gst": amount_ex_gst,
                "gst_applicable": gst_amount > 0,
            }
        ]


    amt_right = ParagraphStyle("AmtRight", parent=normal, alignment=TA_RIGHT)
    qty_right = ParagraphStyle("QtyRight", parent=normal, alignment=TA_RIGHT)
    hdr_right = ParagraphStyle("HdrRight", parent=normal, alignment=TA_RIGHT)

    if gst_registered:
        line_data = [
            [
                Paragraph("<b>Description</b>", normal),
                Paragraph("<b>Qty</b>", qty_right),
                Paragraph("<b>Unit (ex GST)</b>", hdr_right),
                Paragraph("<b>GST</b>", hdr_right),
                Paragraph("<b>Amount (ex GST)</b>", hdr_right),
            ],
        ]
        for item in line_items:
            qty = item.get("quantity", Decimal("1"))
            unit = item.get("unit_amount_ex_gst", item["amount_ex_gst"])
            gst_applicable = item.get("gst_applicable", True)
            gst_label = "10%" if gst_applicable else "No"
            line_data.append(
                [
                    Paragraph(item["description"], normal),
                    Paragraph(format_qty(qty), qty_right),
                    Paragraph(format_money(unit), amt_right),
                    Paragraph(gst_label, amt_right),
                    Paragraph(format_money(item["amount_ex_gst"]), amt_right),
                ]
            )
        line_col_widths = [
            CONTENT_WIDTH * 0.38,
            CONTENT_WIDTH * 0.08,
            CONTENT_WIDTH * 0.18,
            CONTENT_WIDTH * 0.08,
            CONTENT_WIDTH * 0.18,
        ]
    else:
        line_data = [
            [
                Paragraph("<b>Description</b>", normal),
                Paragraph("<b>Qty</b>", qty_right),
                Paragraph("<b>Unit price</b>", hdr_right),
                Paragraph("<b>Amount</b>", hdr_right),
            ],
        ]
        for item in line_items:
            qty = item.get("quantity", Decimal("1"))
            unit = item.get("unit_amount_ex_gst", item["amount_ex_gst"])
            line_data.append(
                [
                    Paragraph(item["description"], normal),
                    Paragraph(format_qty(qty), qty_right),
                    Paragraph(format_money(unit), amt_right),
                    Paragraph(format_money(item["amount_ex_gst"]), amt_right),
                ]
            )
        line_col_widths = [
            CONTENT_WIDTH * 0.46,
            CONTENT_WIDTH * 0.10,
            CONTENT_WIDTH * 0.22,
            CONTENT_WIDTH * 0.22,
        ]

    line_table = Table(line_data, colWidths=line_col_widths)
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

    totals_data = []
    if gst_registered:
        if gst_free_ex_gst > 0 and taxable_ex_gst > 0:
            totals_data.append(
                [Paragraph("Taxable subtotal (ex GST)", total_label_style), Paragraph(format_money(taxable_ex_gst), total_value_style)]
            )
            totals_data.append(
                [Paragraph("GST-free subtotal (ex GST)", total_label_style), Paragraph(format_money(gst_free_ex_gst), total_value_style)]
            )
        totals_data.append(
            [Paragraph("Subtotal (ex GST)", total_label_style), Paragraph(format_money(amount_ex_gst), total_value_style)]
        )
        gst_label = "GST (10%)" if gst_amount > 0 else "GST not applicable"
        totals_data.append(
            [Paragraph(gst_label, total_label_style), Paragraph(format_money(gst_amount), total_value_style)]
        )
        totals_data.append(
            [Paragraph("TOTAL AUD", grand_total_label), Paragraph(format_money(total_inc_gst), grand_total_value)]
        )
    else:
        totals_data.append(
            [Paragraph("TOTAL AUD", grand_total_label), Paragraph(format_money(total_inc_gst), grand_total_value)]
        )
    totals_table = Table(totals_data, colWidths=[CONTENT_WIDTH * 0.72, CONTENT_WIDTH * 0.28])
    totals_table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, len(totals_data) - 1), (-1, len(totals_data) - 1), 1, ACCENT),
                ("TOPPADDING", (0, len(totals_data) - 1), (-1, len(totals_data) - 1), 8),
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
            payment_lines.append(Paragraph(f"BSB: {format_bsb(bsb)}", normal))
        if acc:
            payment_lines.append(Paragraph(f"Account: {format_account(acc)}", normal))
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

    work_photos = invoice_data.get("work_photos") or []
    if work_photos:
        story.append(Spacer(1, 16))
        story.append(Paragraph("<b>Work completed</b>", label_style))
        for photo_path in work_photos:
            if not photo_path or not os.path.isfile(photo_path):
                continue
            try:
                img = Image(photo_path)
                max_w = CONTENT_WIDTH
                max_h = 80 * mm
                iw, ih = float(img.imageWidth), float(img.imageHeight)
                scale = min(max_w / iw, max_h / ih, 1.0) if iw and ih else 1.0
                img.drawWidth = iw * scale
                img.drawHeight = ih * scale
                story.append(Spacer(1, 8))
                story.append(img)
            except Exception:
                continue

    doc.build(story)
    return filepath
