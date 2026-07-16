import { sentInvoiceSortKey } from "./dueDates";

export function isInvoiceDeleted(invoice: Record<string, unknown> | null | undefined): boolean {
  return Boolean(invoice?.deleted_at);
}

export function activeInvoices(invoices: Record<string, Record<string, unknown>> | null | undefined) {
  return Object.values(invoices || {}).filter((inv) => !isInvoiceDeleted(inv));
}

export function invoicesByStatus(
  invoices: Record<string, Record<string, unknown>> | null | undefined,
  settings: Record<string, unknown> = {}
) {
  const groups: {
    not_sent: Record<string, unknown>[];
    sent: Record<string, unknown>[];
    paid: Record<string, unknown>[];
  } = { not_sent: [], sent: [], paid: [] };

  for (const invoice of Object.values(invoices || {})) {
    if (isInvoiceDeleted(invoice)) continue;
    const status = String(invoice.status || "not_sent");
    if (status === "send_queued" || status === "send_failed") groups.not_sent.push(invoice);
    else if (status === "not_sent" || status === "sent" || status === "paid") groups[status].push(invoice);
  }

  const sortKey = (inv: Record<string, unknown>) => [
    String(inv.invoice_date || ""),
    Number(inv.invoice_number || 0),
  ] as const;

  for (const status of Object.keys(groups) as Array<keyof typeof groups>) {
    if (status === "sent") {
      groups.sent.sort((a, b) => {
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

function invoiceMoney(invoice: Record<string, unknown>, key: string): number {
  const n = Number(invoice?.[key]);
  return Number.isFinite(n) ? n : 0;
}

function invoiceInMonth(invoice: Record<string, unknown>, year: number, month: number): boolean {
  const raw = String(invoice.invoice_date || "");
  if (raw.length < 7) return false;
  return parseInt(raw.slice(0, 4), 10) === year && parseInt(raw.slice(5, 7), 10) === month;
}

export function dashboardTotals(
  invoices: Record<string, Record<string, unknown>> | null | undefined,
  today = new Date()
) {
  const { groups } = invoicesByStatus(invoices);
  const bucket = (items: Record<string, unknown>[]) => ({
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

export interface InvoiceFilters {
  q?: string;
  status?: string;
  customer?: string;
  business?: string;
  from?: string;
  to?: string;
}

export function filterInvoices(
  invoices: Record<string, Record<string, unknown>> | null | undefined,
  filters: InvoiceFilters = {}
) {
  const q = (filters.q || "").trim().toLowerCase();
  const status = filters.status || "";
  const customer = filters.customer || "";
  const business = filters.business || "";
  const from = filters.from || "";
  const to = filters.to || "";

  return activeInvoices(invoices).filter((inv) => {
    if (status) {
      if (status === "not_sent") {
        if (!["not_sent", "send_queued", "send_failed"].includes(String(inv.status || "not_sent"))) {
          return false;
        }
      } else if (inv.status !== status) return false;
    }
    if (customer && inv.customer_name !== customer) return false;
    if (business && String(inv.business_name || "") !== business) return false;
    if (from && String(inv.invoice_date || "") < from) return false;
    if (to && String(inv.invoice_date || "") > to) return false;
    if (q) {
      const lineItems = (inv.line_items as Array<Record<string, unknown>> | undefined) || [];
      const hay = [
        String(inv.invoice_number),
        inv.customer_name,
        inv.description,
        lineItems.map((i) => i.description).join(" "),
      ]
        .join(" ")
        .toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

export function statusLabel(status: string): string {
  if (status === "send_queued") return "Sending…";
  if (status === "send_failed") return "Send failed";
  if (status === "sent") return "Sent";
  if (status === "paid") return "Paid";
  return "Not sent";
}

export function countActiveFilters(filters: InvoiceFilters): number {
  return ["q", "status", "customer", "business", "from", "to"].filter((k) =>
    Boolean(String(filters[k as keyof InvoiceFilters] || "").trim())
  ).length;
}
