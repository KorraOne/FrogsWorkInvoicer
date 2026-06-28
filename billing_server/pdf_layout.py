"""ReportLab layout for KorraOne platform fee invoices (FrogsWork subtle green accents)."""

import re
from datetime import date, timedelta
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import KORRAONE_BUSINESS

PAGE_WIDTH, _PAGE_HEIGHT = A4
CONTENT_WIDTH = PAGE_WIDTH - 40 * mm

ACCENT = colors.HexColor("#166534")
LIGHT_HEADER = colors.HexColor("#ecfdf5")
LIGHT_GREY = colors.HexColor("#f4f4f4")
BORDER_GREY = colors.HexColor("#cccccc")


def _fmt_money(amount):
    return f"${Decimal(str(amount)):,.2f}"


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


def _p(text, style):
    return Paragraph(text.replace("\n", "<br/>"), style)


def _address_paragraphs(address, style):
    if not address:
        return []
    return [_p(line.strip(), style) for line in address.split("\n") if line.strip()]


def _due_date(invoice_date, payment_terms):
    terms = (payment_terms or "").strip().lower()
    if terms.endswith(" days"):
        try:
            days = int(terms.split()[0])
            return invoice_date + timedelta(days=days)
        except ValueError:
            pass
    return None


def generate_platform_invoice_pdf(
    path,
    *,
    invoice_number,
    bill_to_email,
    cycle_start,
    cycle_end,
    line_items,
    subtotal,
    gst,
    total_due,
    invoice_date=None,
):
    invoice_date = invoice_date or date.today()
    due = _due_date(invoice_date, KORRAONE_BUSINESS.get("payment_terms", ""))

    doc = SimpleDocTemplate(
        path,
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
    amt_right = ParagraphStyle("AmtRight", parent=normal, alignment=TA_RIGHT)
    note_style = ParagraphStyle(
        "Note",
        parent=normal,
        fontSize=9,
        textColor=colors.HexColor("#666666"),
        spaceBefore=4,
    )

    story = []

    business_block = []
    business_name = KORRAONE_BUSINESS.get("name", "")
    if business_name:
        business_block.append(Paragraph(business_name, business_name_style))
    business_block.extend(_address_paragraphs(KORRAONE_BUSINESS.get("address", ""), normal))
    business_abn = KORRAONE_BUSINESS.get("abn", "")
    if business_abn:
        business_block.append(Paragraph(f"ABN: {_fmt_abn(business_abn)}", normal))
    if not business_block:
        business_block.append(Paragraph("&nbsp;", normal))

    period_label = f"{cycle_start} to {cycle_end}"
    meta_rows = [[Paragraph("Tax Invoice", title_style)]]
    meta_rows.append([Paragraph(f"<b>Invoice #</b> {invoice_number}", meta_style)])
    meta_rows.append([Paragraph(f"<b>Date</b> {invoice_date.strftime('%d %B %Y')}", meta_style)])
    meta_rows.append([Paragraph(f"<b>Period</b> {period_label}", meta_style)])
    if due:
        meta_rows.append([Paragraph(f"<b>Due</b> {due.strftime('%d %B %Y')}", meta_style)])
    elif KORRAONE_BUSINESS.get("payment_terms"):
        meta_rows.append(
            [Paragraph(f"<b>Terms</b> {KORRAONE_BUSINESS['payment_terms']}", meta_style)]
        )

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
    bill_to_lines.append(Paragraph(f"<b>{bill_to_email}</b>", normal))
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

    line_data = [
        [
            Paragraph("<b>Description</b>", normal),
            Paragraph("<b>Invoiced (ex GST)</b>", ParagraphStyle("HdrRight", parent=normal, alignment=TA_RIGHT)),
            Paragraph("<b>Platform fee (ex GST)</b>", ParagraphStyle("HdrRight2", parent=normal, alignment=TA_RIGHT)),
        ],
    ]
    for item in line_items:
        invoiced = Decimal(item["invoiced_ex_gst"])
        fee = Decimal(item["fee_ex_gst"])
        desc = (
            f"FrogsWork platform fee for {item['label']} "
            f"(on {_fmt_money(invoiced)} invoiced ex GST)"
        )
        line_data.append(
            [
                Paragraph(desc, normal),
                Paragraph(_fmt_money(invoiced), amt_right),
                Paragraph(_fmt_money(fee), amt_right),
            ]
        )

    line_table = Table(
        line_data,
        colWidths=[CONTENT_WIDTH * 0.56, CONTENT_WIDTH * 0.22, CONTENT_WIDTH * 0.22],
    )
    line_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT_HEADER),
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

    subtotal = Decimal(str(subtotal))
    gst = Decimal(str(gst))
    total_due = Decimal(str(total_due))
    totals_data = [
        [Paragraph("Subtotal (ex GST)", total_label_style), Paragraph(_fmt_money(subtotal), total_value_style)],
        [Paragraph("GST (10%)", total_label_style), Paragraph(_fmt_money(gst), total_value_style)],
        [Paragraph("TOTAL AUD", grand_total_label), Paragraph(_fmt_money(total_due), grand_total_value)],
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

    account_name = KORRAONE_BUSINESS.get("name", "")
    bsb = KORRAONE_BUSINESS.get("bsb", "")
    acc = KORRAONE_BUSINESS.get("acc", "")
    payid = KORRAONE_BUSINESS.get("payid", "")
    payment_terms = KORRAONE_BUSINESS.get("payment_terms", "")
    if account_name or bsb or acc or payid or due or payment_terms:
        payment_lines = [
            Paragraph("<b>How to pay</b>", ParagraphStyle("PayHdr", parent=normal, fontSize=11, spaceAfter=6))
        ]
        if account_name:
            payment_lines.append(Paragraph(f"Account name: {account_name}", normal))
        if bsb:
            payment_lines.append(Paragraph(f"BSB: {bsb}", normal))
        if acc:
            payment_lines.append(Paragraph(f"Account: {_fmt_account(acc)}", normal))
        if payid:
            payment_lines.append(Paragraph(f"PayID: {payid}", normal))
        if due:
            payment_lines.append(Paragraph(f"Payment due: {due.strftime('%d %B %Y')}", normal))
        elif payment_terms:
            payment_lines.append(Paragraph(f"Payment terms: {payment_terms}", normal))
        payment_lines.append(Paragraph(f"Reference: Invoice #{invoice_number}", normal))

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

    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "Platform usage fees for FrogsWork. Separate from sales invoices you issue to your customers.",
            note_style,
        )
    )

    doc.build(story)
    return path
