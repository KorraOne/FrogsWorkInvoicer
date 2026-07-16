import { formatMoney, formatInvoiceNumber } from "./invoice_format.js";

function invoiceLabel(invoice, settings) {
  const gst = Boolean(settings?.gst_registered);
  const hasGst = gst && Number(invoice?.total_gst || 0) > 0;
  return hasGst ? "Tax Invoice" : "Invoice";
}

export function buildInvoiceEmailContext(invoice, customer, settings, pdfFilename) {
  const business =
    (invoice?.business_name || settings?.default_business || "").trim() || "Your business";
  const customerName = invoice?.customer_name || "";
  const invNum = formatInvoiceNumber(invoice?.invoice_number);
  const totalFmt = formatMoney(invoice?.total_inc_gst || 0);
  const label = invoiceLabel(invoice, settings);
  const toEmail = String(customer?.email || "").trim();
  const subject = `${label} #${invNum} from ${business}`;

  const bodyLines = [customerName ? `Hi ${customerName},` : "Hi,", ""];
  bodyLines.push(`Attached is ${label.toLowerCase()} #${invNum} for ${totalFmt}.`);
  bodyLines.push(`Payment reference: Invoice #${invNum}`);

  const dueRaw = invoice?.due_date;
  const dueDate = dueRaw == null ? "" : String(dueRaw).trim();
  if (dueDate) {
    const d = new Date(`${dueDate.slice(0, 10)}T12:00:00`);
    if (!Number.isNaN(d.getTime())) {
      bodyLines.push("", `Payment due: ${d.toLocaleDateString("en-AU", { day: "numeric", month: "long", year: "numeric" })}`);
    }
  } else {
    const terms = String(settings?.payment_terms || "").trim();
    if (terms) bodyLines.push("", `Payment terms: ${terms}`);
  }
  bodyLines.push("", "Thank you,", business);

  return {
    to: toEmail,
    subject,
    body: bodyLines.join("\r\n"),
    pdf_filename: pdfFilename || `Invoice_${invNum}.pdf`,
  };
}

export function formatClipboardText(ctx) {
  const lines = [];
  if (ctx.to) {
    lines.push(`To: ${ctx.to}`, "");
  }
  lines.push(`Subject: ${ctx.subject}`, "", "--- Message ---", ctx.body);
  return lines.join("\r\n");
}
