import { PDFDocument, StandardFonts, rgb } from "pdf-lib";
import {
  ACCENT,
  BORDER_GREY,
  CONTENT_WIDTH,
  HEADER_SLOT_FRACTION,
  LIGHT_GREY,
  MUTED,
  PAGE_HEIGHT,
  PAGE_MARGIN,
  PAGE_WIDTH,
  TEXT,
} from "../geometry.js";
import {
  formatAbn,
  formatAccount,
  formatAddressMultiline,
  formatBsb,
  formatDisplayDate,
  formatInvoiceNumber,
  formatMoney,
  formatQty,
} from "../format.js";

function dataUrlToBytes(dataUrl) {
  const raw = String(dataUrl || "");
  const comma = raw.indexOf(",");
  const b64 = comma >= 0 ? raw.slice(comma + 1) : raw;
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

async function embedImage(doc, dataUrl) {
  if (!dataUrl) return null;
  const bytes = dataUrlToBytes(dataUrl);
  try {
    if (String(dataUrl).includes("image/png")) return await doc.embedPng(bytes);
    return await doc.embedJpg(bytes);
  } catch {
    try {
      return await doc.embedPng(bytes);
    } catch {
      return null;
    }
  }
}

function color(c) {
  return rgb(c.r, c.g, c.b);
}

/**
 * Classic AU tax-invoice layout (pdf-lib port of desktop classic.py).
 * @param {object} invoice
 * @param {object} business
 * @param {object} [customer]
 */
export async function renderClassicInvoice(invoice, business = {}, customer = {}) {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  const bold = await doc.embedFont(StandardFonts.HelveticaBold);

  let page = doc.addPage([PAGE_WIDTH, PAGE_HEIGHT]);
  let y = PAGE_HEIGHT - PAGE_MARGIN;

  const ensure = (need) => {
    if (y < PAGE_MARGIN + need) {
      page = doc.addPage([PAGE_WIDTH, PAGE_HEIGHT]);
      y = PAGE_HEIGHT - PAGE_MARGIN;
    }
  };

  const drawText = (text, x, yy, size, useBold = false, col = TEXT, maxW = CONTENT_WIDTH) => {
    const f = useBold ? bold : font;
    let line = String(text || "");
    while (line && f.widthOfTextAtSize(line, size) > maxW) {
      line = line.slice(0, -1);
    }
    page.drawText(line, { x, y: yy, size, font: f, color: color(col) });
    return f.heightAtSize(size);
  };

  const drawRight = (text, rightX, yy, size, useBold = false, col = TEXT) => {
    const f = useBold ? bold : font;
    const tw = f.widthOfTextAtSize(String(text || ""), size);
    page.drawText(String(text || ""), {
      x: rightX - tw,
      y: yy,
      size,
      font: f,
      color: color(col),
    });
  };

  const gstRegistered = Boolean(
    invoice.gst_registered ?? (Number(invoice.gst_amount || 0) > 0 || business.gst_registered)
  );
  const title = gstRegistered ? "Tax Invoice" : "Invoice";
  const invNum = formatInvoiceNumber(invoice.invoice_number);
  const dueFmt = invoice.due_date_fmt || formatDisplayDate(invoice.due_date);
  const leftW = CONTENT_WIDTH * HEADER_SLOT_FRACTION;
  const rightW = CONTENT_WIDTH * (1 - HEADER_SLOT_FRACTION);
  const leftX = PAGE_MARGIN;
  const rightX = PAGE_MARGIN + leftW;

  // Header: logo | meta
  let headerBottom = y;
  const metaLines = [
    { text: title, size: 18, bold: true },
    { text: `Invoice # ${invNum}`, size: 10, bold: false },
    { text: `Date ${formatDisplayDate(invoice.invoice_date)}`, size: 10, bold: false },
  ];
  if (dueFmt) metaLines.push({ text: `Due ${dueFmt}`, size: 10, bold: false });

  let metaY = y - 4;
  for (const line of metaLines) {
    drawRight(line.text, PAGE_MARGIN + CONTENT_WIDTH, metaY - line.size, line.size, line.bold, ACCENT);
    metaY -= line.size + (line.bold ? 10 : 4);
  }
  const metaHeight = y - metaY;

  let logoHeight = 0;
  const logoEnabled = business.logo_enabled !== false && Boolean(business.logo_b64);
  if (logoEnabled && business.logo_b64) {
    const img = await embedImage(doc, business.logo_b64);
    if (img) {
      const maxW = leftW - 4;
      const scale = Math.min(1, maxW / img.width, (metaHeight || 80) / img.height * 1.2);
      const w = img.width * Math.min(scale, maxW / img.width);
      const h = img.height * (w / img.width);
      logoHeight = h;
      page.drawImage(img, { x: leftX, y: y - h, width: w, height: h });
    }
  }

  y -= Math.max(metaHeight, logoHeight, 48) + 8;

  // Divider
  ensure(20);
  page.drawRectangle({
    x: PAGE_MARGIN,
    y: y - 2,
    width: CONTENT_WIDTH,
    height: 2,
    color: color(ACCENT),
  });
  y -= 18;

  // Parties
  ensure(80);
  const bizName = business.business_name || invoice.business_name || "";
  const bizLines = [bizName, ...formatAddressMultiline(business)];
  const abn = business.business_abn || business.abn || "";
  if (abn) bizLines.push(`ABN: ${formatAbn(abn)}`);

  let partyY = y;
  for (let i = 0; i < bizLines.length; i++) {
    if (!bizLines[i]) continue;
    drawText(bizLines[i], leftX, partyY - 11, i === 0 ? 12 : 10, i === 0);
    partyY -= i === 0 ? 16 : 13;
  }

  const cust = customer || {};
  const billLines = ["BILL TO", String(invoice.customer_name || ""), ...formatAddressMultiline(cust)];
  const custAbn = cust.abn || cust.business_abn || "";
  if (custAbn) billLines.push(`ABN: ${formatAbn(custAbn)}`);

  let billY = y;
  for (let i = 0; i < billLines.length; i++) {
    if (!billLines[i]) continue;
    const size = i === 0 ? 9 : 10;
    const isBold = i === 1;
    drawRight(billLines[i], PAGE_MARGIN + CONTENT_WIDTH, billY - size, size, isBold, i === 0 ? MUTED : TEXT);
    billY -= size + 3;
  }

  y = Math.min(partyY, billY) - 16;

  // Line items table
  const items = invoice.line_items?.length
    ? invoice.line_items
    : invoice.description
      ? [
          {
            description: invoice.description,
            quantity: 1,
            unit_amount_ex_gst: invoice.amount_ex_gst,
            amount_ex_gst: invoice.amount_ex_gst,
            gst_applicable: Number(invoice.gst_amount || 0) > 0,
          },
        ]
      : [];

  const cols = gstRegistered
    ? [
        { key: "desc", label: "Description", w: CONTENT_WIDTH * (38 / 90), align: "left" },
        { key: "qty", label: "Qty", w: CONTENT_WIDTH * (8 / 90), align: "right" },
        { key: "unit", label: "Unit (ex GST)", w: CONTENT_WIDTH * (18 / 90), align: "right" },
        { key: "gst", label: "GST", w: CONTENT_WIDTH * (8 / 90), align: "right" },
        { key: "amt", label: "Amount (ex GST)", w: CONTENT_WIDTH * (18 / 90), align: "right" },
      ]
    : [
        { key: "desc", label: "Description", w: CONTENT_WIDTH * 0.46, align: "left" },
        { key: "qty", label: "Qty", w: CONTENT_WIDTH * 0.1, align: "right" },
        { key: "unit", label: "Unit price", w: CONTENT_WIDTH * 0.22, align: "right" },
        { key: "amt", label: "Amount", w: CONTENT_WIDTH * 0.22, align: "right" },
      ];

  const rowH = 22;
  ensure(rowH * (items.length + 2) + 40);

  // Header row
  page.drawRectangle({
    x: PAGE_MARGIN,
    y: y - rowH,
    width: CONTENT_WIDTH,
    height: rowH,
    color: color(LIGHT_GREY),
    borderColor: color(BORDER_GREY),
    borderWidth: 0.5,
  });
  let cx = PAGE_MARGIN;
  for (const col of cols) {
    const labelY = y - 15;
    if (col.align === "right") drawRight(col.label, cx + col.w - 6, labelY, 8, true);
    else drawText(col.label, cx + 6, labelY, 8, true);
    cx += col.w;
  }
  y -= rowH;

  for (const item of items) {
    ensure(rowH + 10);
    page.drawRectangle({
      x: PAGE_MARGIN,
      y: y - rowH,
      width: CONTENT_WIDTH,
      height: rowH,
      borderColor: color(BORDER_GREY),
      borderWidth: 0.5,
    });
    const qty = item.quantity ?? 1;
    const unit = item.unit_amount_ex_gst ?? item.amount_ex_gst;
    const amt = item.amount_ex_gst ?? unit;
    const gstLabel = item.gst_applicable === false ? "No" : "10%";
    const cells = gstRegistered
      ? {
          desc: item.description || "",
          qty: formatQty(qty),
          unit: formatMoney(unit),
          gst: gstLabel,
          amt: formatMoney(amt),
        }
      : {
          desc: item.description || "",
          qty: formatQty(qty),
          unit: formatMoney(unit),
          amt: formatMoney(amt),
        };
    cx = PAGE_MARGIN;
    for (const col of cols) {
      const labelY = y - 15;
      const val = cells[col.key] || "";
      if (col.align === "right") drawRight(val, cx + col.w - 6, labelY, 9);
      else drawText(val, cx + 6, labelY, 9, false, TEXT, col.w - 12);
      cx += col.w;
    }
    y -= rowH;
  }

  y -= 12;

  // Totals
  const amountEx = Number(invoice.amount_ex_gst || 0);
  const gstAmt = Number(invoice.gst_amount || 0);
  const total = Number(invoice.total_inc_gst || 0);
  const taxable = Number(invoice.taxable_ex_gst ?? amountEx);
  const gstFree = Number(invoice.gst_free_ex_gst || 0);

  const totals = [];
  if (gstRegistered) {
    if (gstFree > 0 && taxable > 0) {
      totals.push(["Taxable subtotal (ex GST)", formatMoney(taxable)]);
      totals.push(["GST-free subtotal (ex GST)", formatMoney(gstFree)]);
    }
    totals.push(["Subtotal (ex GST)", formatMoney(amountEx)]);
    totals.push([gstAmt > 0 ? "GST (10%)" : "GST not applicable", formatMoney(gstAmt)]);
    totals.push(["TOTAL AUD", formatMoney(total)]);
  } else {
    totals.push(["TOTAL AUD", formatMoney(total)]);
  }

  ensure(totals.length * 16 + 20);
  for (let i = 0; i < totals.length; i++) {
    const [label, val] = totals[i];
    const isGrand = i === totals.length - 1;
    if (isGrand) {
      // Clear previous totals row before the TOTAL rule (GST-on only; GST-off has one row).
      if (i > 0) y -= 8;
      page.drawLine({
        start: { x: PAGE_MARGIN + CONTENT_WIDTH * 0.5, y: y + 4 },
        end: { x: PAGE_MARGIN + CONTENT_WIDTH, y: y + 4 },
        thickness: 1,
        color: color(ACCENT),
      });
      y -= 4;
    }
    drawRight(label, PAGE_MARGIN + CONTENT_WIDTH * 0.72, y - 11, isGrand ? 11 : 10, true);
    drawRight(val, PAGE_MARGIN + CONTENT_WIDTH, y - 11, isGrand ? 11 : 10, isGrand);
    y -= isGrand ? 18 : 14;
  }

  y -= 12;

  // How to pay
  const accountName = business.account_name || "";
  const bsb = business.bsb || "";
  const acc = business.acc || "";
  if (accountName || bsb || acc || dueFmt) {
    ensure(100);
    const boxH = 14 * (4 + (dueFmt ? 1 : 0) + 1) + 16;
    page.drawRectangle({
      x: PAGE_MARGIN,
      y: y - boxH,
      width: CONTENT_WIDTH,
      height: boxH,
      color: color(LIGHT_GREY),
      borderColor: color(BORDER_GREY),
      borderWidth: 1,
    });
    let py = y - 16;
    drawText("How to pay", PAGE_MARGIN + 12, py, 11, true);
    py -= 16;
    if (accountName) {
      drawText(`Account name: ${accountName}`, PAGE_MARGIN + 12, py, 10);
      py -= 14;
    }
    if (bsb) {
      drawText(`BSB: ${formatBsb(bsb)}`, PAGE_MARGIN + 12, py, 10);
      py -= 14;
    }
    if (acc) {
      drawText(`Account: ${formatAccount(acc)}`, PAGE_MARGIN + 12, py, 10);
      py -= 14;
    }
    if (dueFmt) {
      drawText(`Payment due: ${dueFmt}`, PAGE_MARGIN + 12, py, 10);
      py -= 14;
    }
    drawText(`Reference: Invoice #${invNum}`, PAGE_MARGIN + 12, py, 10);
    y -= boxH + 12;
  }

  if (invoice.comment) {
    ensure(40);
    drawText("Notes", PAGE_MARGIN, y - 10, 9, true, MUTED);
    y -= 16;
    drawText(String(invoice.comment), PAGE_MARGIN, y - 10, 10);
    y -= 20;
  }

  const photos = invoice.work_photos_b64 || [];
  if (photos.length) {
    ensure(30);
    drawText("Work completed", PAGE_MARGIN, y - 10, 9, true, MUTED);
    y -= 16;
    for (const src of photos.slice(0, 6)) {
      const img = await embedImage(doc, src);
      if (!img) continue;
      const maxW = CONTENT_WIDTH;
      const maxH = 226; // ~80mm
      const scale = Math.min(1, maxW / img.width, maxH / img.height);
      const w = img.width * scale;
      const h = img.height * scale;
      ensure(h + 16);
      page.drawImage(img, { x: PAGE_MARGIN, y: y - h, width: w, height: h });
      y -= h + 12;
    }
  }

  return doc.save();
}
