import { PDFDocument, StandardFonts, rgb } from "pdf-lib";

export async function buildInvoicePdf(invoice) {
  const doc = await PDFDocument.create();
  const page = doc.addPage([595.28, 841.89]);
  const font = await doc.embedFont(StandardFonts.Helvetica);
  const bold = await doc.embedFont(StandardFonts.HelveticaBold);
  const { height } = page.getSize();
  let y = height - 50;

  const draw = (text, opts = {}) => {
    const size = opts.size || 11;
    const useFont = opts.bold ? bold : font;
    const line = String(text || "").slice(0, 90);
    page.drawText(line, { x: 50, y, size, font: useFont, color: rgb(0.12, 0.16, 0.22) });
    y -= size + 8;
  };

  const title = Number(invoice.gst_amount || 0) > 0 ? "TAX INVOICE" : "INVOICE";
  draw(title, { size: 16, bold: true });
  draw(`Invoice #: ${String(invoice.invoice_number).padStart(8, "0")}`);
  draw(`Date: ${invoice.invoice_date || ""}`);
  draw(`Customer: ${invoice.customer_name || ""}`);
  if (invoice.business_name) draw(`From: ${invoice.business_name}`);
  y -= 6;

  const lineItems = invoice.line_items?.length
    ? invoice.line_items
    : invoice.description
      ? [{ description: invoice.description, amount_ex_gst: invoice.amount_ex_gst }]
      : [];

  draw("Items", { bold: true });
  for (const item of lineItems) {
    const qty = item.quantity != null ? ` x${item.quantity}` : "";
    const amt = item.amount_ex_gst || item.unit_amount_ex_gst || "";
    draw(`• ${item.description || ""}${qty}  $${amt}`);
  }

  y -= 6;
  draw(`Amount ex GST: $${invoice.amount_ex_gst || "0"}`);
  draw(`GST: $${invoice.gst_amount || "0"}`);
  draw(`Total inc GST: $${invoice.total_inc_gst || "0"}`, { bold: true });
  if (invoice.due_date) draw(`Due: ${invoice.due_date}`);
  if (invoice.comment) {
    y -= 4;
    draw("Notes", { bold: true });
    draw(invoice.comment);
  }

  return doc.save();
}
