/** Build cloud auto-send subject/body/filename for invoice / quote / follow-up emails. */

import {
  FROGSWORK_URL,
  brandedFooterHtml,
  brandedFooterText,
} from "./email_branding.js";

function padInvoiceNumber(number) {
  const n = Math.max(1, parseInt(String(number), 10) || 0);
  return String(n).padStart(8, "0");
}

function formatMoneyAud(amount) {
  const n = Number(amount) || 0;
  return `$${n.toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatDateAud(isoDate) {
  const raw = String(isoDate || "").trim().slice(0, 10);
  if (!raw) return "";
  const d = new Date(`${raw}T12:00:00`);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleDateString("en-AU", { day: "numeric", month: "long", year: "numeric" });
}

function invoiceLabel(invoice, business) {
  const gstRegistered = Boolean(
    invoice?.gst_registered ?? business?.gst_registered
  );
  const gstAmount = Number(invoice?.gst_amount || invoice?.total_gst || 0);
  return gstRegistered && gstAmount > 0 ? "Tax Invoice" : "Invoice";
}

function resolveDocKind(opts = {}, doc = {}) {
  return String(opts.docKind || doc.doc_kind || "invoice").toLowerCase();
}

function quoteLabel(docKind) {
  return docKind === "estimate" ? "Price estimate" : "Quote";
}

function businessLookupKey(invoice, settings) {
  const fromInvoice = String(invoice?.business_name || invoice?.business || "").trim();
  if (fromInvoice) return fromInvoice;
  return String(settings?.default_business || "").trim();
}

function businessDisplayName(invoice, settings, businesses) {
  const lookupKey = businessLookupKey(invoice, settings);
  const profile = (lookupKey && businesses[lookupKey]) || {};
  const fromProfile = String(profile.business_name || "").trim();
  if (fromProfile) return fromProfile;
  if (lookupKey) return lookupKey;
  const names = Object.keys(businesses || {});
  if (names.length === 1) {
    const only = businesses[names[0]] || {};
    return String(only.business_name || names[0]).trim() || names[0];
  }
  return "Your business";
}

function howToPayLines(business = {}) {
  const bsb = String(business.bsb || "").trim();
  const acc = String(business.acc || business.account_number || "").trim();
  const accountName = String(business.account_name || "").trim();
  if (!bsb && !acc && !accountName) return [];
  const lines = ["", "How to pay:"];
  if (accountName) lines.push(`Account name: ${accountName}`);
  if (bsb) lines.push(`BSB: ${bsb}`);
  if (acc) lines.push(`Account: ${acc}`);
  return lines;
}

function linesToHtml(lines) {
  const htmlParts = lines.map((line) => {
    if (!line) return "<br>";
    if (line === FROGSWORK_URL) {
      return `<a href="${FROGSWORK_URL}">${FROGSWORK_URL}</a>`;
    }
    if (line === "—") return '<hr style="border:none;border-top:1px solid #ddd;margin:1em 0">';
    const escaped = line
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return `<p style="margin:0 0 0.4em 0">${escaped}</p>`;
  });
  return `<div style="font-family:system-ui,Segoe UI,sans-serif;font-size:15px;line-height:1.45;color:#222">${htmlParts.join(
    "\n"
  )}</div>`;
}

function wrapEmail(bodyLines, footerVariant) {
  const text = [...bodyLines, ...brandedFooterText({ variant: footerVariant })].join("\n");
  const html = `${linesToHtml(bodyLines)}${brandedFooterHtml({ variant: footerVariant })}`;
  return { text, html };
}

/**
 * @returns {{ subject: string, text: string, html: string, filename: string, businessName: string, label: string }}
 */
export function buildInvoiceEmailContent({
  invoice,
  customer = {},
  settings = {},
  businesses = {},
  docKind,
} = {}) {
  const kind = resolveDocKind({ docKind }, invoice);
  const isQuoteDoc = kind === "quote" || kind === "estimate";

  const lookupKey = businessLookupKey(invoice, settings);
  const businessName = businessDisplayName(invoice, settings, businesses);
  const business = (lookupKey && businesses[lookupKey]) || {};
  const label = isQuoteDoc ? quoteLabel(kind) : invoiceLabel(invoice, business);
  const invNum = padInvoiceNumber(
    isQuoteDoc ? invoice?.quote_number ?? invoice?.invoice_number : invoice?.invoice_number
  );
  const customerName = String(invoice?.customer_name || customer?.name || "").trim();
  const totalFmt = formatMoneyAud(invoice?.total_inc_gst);
  const dueFmt = formatDateAud(invoice?.due_date);
  const invDateFmt = formatDateAud(
    isQuoteDoc ? invoice?.quote_date || invoice?.invoice_date : invoice?.invoice_date
  );

  const subject = `${label} #${invNum} from ${businessName}`;

  const greeting = customerName ? `Hi ${customerName},` : "Hi,";
  const lines = [
    greeting,
    "",
    `Please find attached ${label.toLowerCase()} #${invNum} from ${businessName}${
      invDateFmt ? ` dated ${invDateFmt}` : ""
    } for ${totalFmt}.`,
  ];

  if (!isQuoteDoc) {
    lines.push("", `Please use this payment reference: ${invNum}`);
    lines.push(`(Invoice #${invNum})`);
    if (dueFmt) {
      lines.push(`Payment due: ${dueFmt}`);
    } else if (String(settings?.payment_terms || "").trim()) {
      lines.push(`Payment terms: ${String(settings.payment_terms).trim()}`);
    }
    lines.push(...howToPayLines(business));
  }

  lines.push("", "Thank you,", businessName);

  const { text, html } = wrapEmail(lines, isQuoteDoc ? "quote" : "invoice");

  const dateStamp = String(
    (isQuoteDoc ? invoice?.quote_date || invoice?.invoice_date : invoice?.invoice_date) || "draft"
  ).slice(0, 10);
  const defaultName = isQuoteDoc
    ? `Quote_${invNum}_${dateStamp}.pdf`
    : `Invoice_${invNum}_${dateStamp}.pdf`;
  const filename = String(invoice?.filename || "").trim() || defaultName;

  return { subject, text, html, filename, businessName, label };
}

/** Quote / price-estimate email (no payment / how-to-pay). */
export function buildQuoteEmailContent(args = {}) {
  const doc = args.quote || args.invoice || {};
  const kind = resolveDocKind(args, doc);
  return buildInvoiceEmailContent({
    ...args,
    invoice: doc,
    docKind: kind === "estimate" ? "estimate" : "quote",
  });
}

/**
 * Payment follow-up / reminder email for an unpaid sent invoice.
 * @returns {{ subject: string, text: string, html: string, filename: string, businessName: string, label: string }}
 */
export function buildPaymentFollowupEmailContent({
  invoice,
  customer = {},
  settings = {},
  businesses = {},
} = {}) {
  const lookupKey = businessLookupKey(invoice, settings);
  const businessName = businessDisplayName(invoice, settings, businesses);
  const business = (lookupKey && businesses[lookupKey]) || {};
  const label = invoiceLabel(invoice, business);
  const invNum = padInvoiceNumber(invoice?.invoice_number);
  const customerName = String(invoice?.customer_name || customer?.name || "").trim();
  const totalFmt = formatMoneyAud(invoice?.total_inc_gst);
  const dueFmt = formatDateAud(invoice?.due_date);
  const invDateFmt = formatDateAud(invoice?.invoice_date);

  const subject = `Payment reminder: Invoice #${invNum} from ${businessName}`;
  const greeting = customerName ? `Hi ${customerName},` : "Hi,";
  const lines = [
    greeting,
    "",
    `This is a friendly reminder that invoice #${invNum} from ${businessName} is still outstanding.`,
  ];
  if (invDateFmt) lines.push(`Invoice date: ${invDateFmt}`);
  if (dueFmt) lines.push(`Payment due: ${dueFmt}`);
  lines.push(`Amount owing: ${totalFmt}`);
  lines.push("", `Please use this payment reference: ${invNum}`);
  lines.push(`(Invoice #${invNum})`);
  lines.push(...howToPayLines(business));
  lines.push(
    "",
    "If you have already paid this invoice, you can ignore this email."
  );
  lines.push("", "Thank you,", businessName);

  const { text, html } = wrapEmail(lines, "followup");

  const dateStamp = String(invoice?.invoice_date || "draft").slice(0, 10);
  const filename =
    String(invoice?.filename || "").trim() || `Invoice_${invNum}_${dateStamp}.pdf`;

  return { subject, text, html, filename, businessName, label };
}

/** Read email copy prefs from doc_settings. One mode: off, cc, or bcc (default cc). */
export function emailCopyPrefsFromSettings(settings = {}) {
  const raw = String(settings.email_self_copy || "").trim().toLowerCase();
  if (raw === "off" || raw === "none") {
    return { ccSelf: false, bccSelf: false, mode: "off" };
  }
  if (raw === "bcc") {
    return { ccSelf: false, bccSelf: true, mode: "bcc" };
  }
  if (raw === "cc") {
    return { ccSelf: true, bccSelf: false, mode: "cc" };
  }
  // Legacy: separate email_cc_self / email_bcc_self booleans
  const ccSelf = !(
    settings.email_cc_self === false ||
    settings.email_cc_self === 0 ||
    settings.email_cc_self === "0"
  );
  const bccSelf =
    settings.email_bcc_self === true ||
    settings.email_bcc_self === 1 ||
    settings.email_bcc_self === "1" ||
    settings.email_bcc_self === "true";
  if (bccSelf && !ccSelf) return { ccSelf: false, bccSelf: true, mode: "bcc" };
  if (!ccSelf && !bccSelf) return { ccSelf: false, bccSelf: false, mode: "off" };
  return { ccSelf: true, bccSelf: false, mode: "cc" };
}

/**
 * Email used for CC/BCC self-copy on invoice sends.
 * Prefer the invoice's business profile email, then default/first business, then account email.
 */
export function selfCopyEmailFromBusiness({
  invoice = {},
  businesses = {},
  settings = {},
  fallbackUserEmail = "",
} = {}) {
  const map = businesses && typeof businesses === "object" ? businesses : {};
  const keys = Object.keys(map);
  const invoiceBiz = String(invoice.business_name || invoice.business || "").trim();
  const defaultBiz = String(settings.default_business || "").trim();
  const pick =
    (invoiceBiz && map[invoiceBiz]) ||
    (defaultBiz && map[defaultBiz]) ||
    (keys.length ? map[keys[0]] : null) ||
    {};
  const fromBiz = String(pick.email || "").trim();
  if (fromBiz.includes("@")) return fromBiz;
  return String(fallbackUserEmail || "").trim();
}

/** Clamp follow-up offset days to [-14, 14]; default -3. */
export function paymentFollowupOffsetDays(settings = {}) {
  const n = parseInt(String(settings.payment_followup_offset_days ?? "-3"), 10);
  if (!Number.isFinite(n)) return -3;
  return Math.max(-14, Math.min(14, n));
}

export function paymentFollowupsEnabled(settings = {}) {
  return (
    settings.payment_followups_enabled === true ||
    settings.payment_followups_enabled === 1 ||
    settings.payment_followups_enabled === "1" ||
    settings.payment_followups_enabled === "true"
  );
}
