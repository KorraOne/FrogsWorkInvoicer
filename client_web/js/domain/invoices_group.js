import { sentInvoiceSortKey } from "./due_dates.js";

export function isInvoiceDeleted(invoice) {
  return Boolean(invoice?.deleted_at);
}

export function activeInvoices(invoices) {
  return Object.values(invoices || {}).filter((inv) => !isInvoiceDeleted(inv));
}

export function invoicesByStatus(invoices, settings = {}) {
  const groups = { not_sent: [], sent: [], paid: [] };
  for (const invoice of Object.values(invoices || {})) {
    if (isInvoiceDeleted(invoice)) continue;
    const status = invoice.status || "not_sent";
    if (status === "send_queued" || status === "send_failed") groups.not_sent.push(invoice);
    else if (groups[status]) groups[status].push(invoice);
  }
  const sortKey = (inv) => [inv.invoice_date || "", inv.invoice_number || 0];
  for (const status of Object.keys(groups)) {
    if (status === "sent") {
      groups[status].sort((a, b) => {
        const ka = sentInvoiceSortKey(a, settings);
        const kb = sentInvoiceSortKey(b, settings);
        if (ka[0] !== kb[0]) return ka[0] - kb[0];
        if (ka[1] !== kb[1]) return ka[1].localeCompare(kb[1]);
        return kb[2] - ka[2];
      });
    } else {
      groups[status].sort((a, b) => {
        const ka = sortKey(a);
        const kb = sortKey(b);
        if (ka[0] !== kb[0]) return kb[0].localeCompare(ka[0]);
        return kb[1] - ka[1];
      });
    }
  }
  const sentTotal = groups.sent.reduce((s, inv) => s + Number(inv.total_inc_gst || 0), 0);
  return { groups, sentTotal };
}

function invoiceMoney(invoice, key) {
  const n = Number(invoice?.[key]);
  return Number.isFinite(n) ? n : 0;
}

function invoiceInMonth(invoice, year, month) {
  const raw = String(invoice.invoice_date || "");
  if (raw.length < 7) return false;
  return parseInt(raw.slice(0, 4), 10) === year && parseInt(raw.slice(5, 7), 10) === month;
}

export function dashboardTotals(invoices, today = new Date()) {
  const { groups } = invoicesByStatus(invoices);
  const bucket = (items) => ({
    inc_gst: items.reduce((s, inv) => s + invoiceMoney(inv, "total_inc_gst"), 0),
    ex_gst: items.reduce((s, inv) => s + invoiceMoney(inv, "amount_ex_gst"), 0),
    count: items.length,
  });
  const monthItems = activeInvoices(invoices).filter((inv) =>
    invoiceInMonth(inv, today.getFullYear(), today.getMonth() + 1)
  );
  return {
    month: bucket(monthItems),
    outstanding: bucket(groups.sent),
    paid: bucket(groups.paid),
  };
}

export function filterInvoices(invoices, filters = {}) {
  const q = (filters.q || "").trim().toLowerCase();
  const status = filters.status || "";
  const customer = filters.customer || "";
  const business = filters.business || "";
  const from = filters.from || "";
  const to = filters.to || "";

  return activeInvoices(invoices).filter((inv) => {
    if (status) {
      if (status === "not_sent") {
        if (!["not_sent", "send_queued", "send_failed"].includes(inv.status || "not_sent")) return false;
      } else if (inv.status !== status) return false;
    }
    if (customer && inv.customer_name !== customer) return false;
    if (business && (inv.business_name || "") !== business) return false;
    if (from && (inv.invoice_date || "") < from) return false;
    if (to && (inv.invoice_date || "") > to) return false;
    if (q) {
      const hay = [
        String(inv.invoice_number),
        inv.customer_name,
        inv.description,
        (inv.line_items || []).map((i) => i.description).join(" "),
      ]
        .join(" ")
        .toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

export function statusLabel(status) {
  if (status === "send_queued") return "Sending…";
  if (status === "send_failed") return "Send failed";
  if (status === "sent") return "Sent";
  if (status === "paid") return "Paid";
  return "Not sent";
}
