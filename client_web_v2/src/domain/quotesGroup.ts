export function isQuoteDeleted(quote: Record<string, unknown> | null | undefined): boolean {
  return Boolean(quote?.deleted_at);
}

export function activeQuotes(quotes: Record<string, Record<string, unknown>> | null | undefined) {
  return Object.values(quotes || {}).filter((q) => !isQuoteDeleted(q));
}

export interface QuoteFilters {
  q?: string;
  status?: string;
  customer?: string;
  business?: string;
  from?: string;
  to?: string;
}

function paddedDocNumber(raw: unknown): string {
  return String(Math.max(0, parseInt(String(raw), 10) || 0)).padStart(8, "0");
}

export function filterQuotes(
  quotes: Record<string, Record<string, unknown>> | null | undefined,
  filters: QuoteFilters = {}
) {
  const q = (filters.q || "").trim().toLowerCase();
  const status = filters.status || "";
  const customer = filters.customer || "";
  const business = filters.business || "";
  const from = filters.from || "";
  const to = filters.to || "";

  return activeQuotes(quotes).filter((quote) => {
    if (status) {
      if (status === "not_sent") {
        if (!["not_sent", "send_queued", "send_failed"].includes(String(quote.status || "not_sent"))) {
          return false;
        }
      } else if (quote.status !== status) return false;
    }
    if (customer && quote.customer_name !== customer) return false;
    if (business && String(quote.business_name || "") !== business) return false;
    if (from && String(quote.quote_date || "") < from) return false;
    if (to && String(quote.quote_date || "") > to) return false;
    if (q) {
      const lineItems = (quote.line_items as Array<Record<string, unknown>> | undefined) || [];
      const hay = [
        String(quote.quote_number),
        paddedDocNumber(quote.quote_number),
        quote.customer_name,
        quote.description,
        lineItems.map((i) => i.description).join(" "),
      ]
        .join(" ")
        .toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

export function countActiveQuoteFilters(filters: QuoteFilters): number {
  return ["q", "status", "customer", "business", "from", "to"].filter((k) =>
    Boolean(String(filters[k as keyof QuoteFilters] || "").trim())
  ).length;
}

export function quotesByStatus(quotes: Record<string, Record<string, unknown>> | null | undefined) {
  const groups: {
    not_sent: Record<string, unknown>[];
    sent: Record<string, unknown>[];
    closed: Record<string, unknown>[];
    converted: Record<string, unknown>[];
  } = { not_sent: [], sent: [], closed: [], converted: [] };

  for (const quote of Object.values(quotes || {})) {
    if (isQuoteDeleted(quote)) continue;
    const status = String(quote.status || "not_sent");
    if (status === "send_queued" || status === "send_failed" || status === "not_sent") {
      groups.not_sent.push(quote);
    } else if (status === "sent") {
      groups.sent.push(quote);
    } else if (status === "closed") {
      groups.closed.push(quote);
    } else if (status === "converted") {
      groups.converted.push(quote);
    } else {
      groups.not_sent.push(quote);
    }
  }

  const sortKey = (q: Record<string, unknown>) =>
    [String(q.quote_date || q.invoice_date || ""), Number(q.quote_number || 0)] as const;

  for (const status of Object.keys(groups) as Array<keyof typeof groups>) {
    if (status === "sent") {
      groups.sent.sort((a, b) => {
        const da = String(a.sent_date || a.quote_date || "").slice(0, 10);
        const db = String(b.sent_date || b.quote_date || "").slice(0, 10);
        if (da !== db) return db.localeCompare(da);
        return Number(b.quote_number || 0) - Number(a.quote_number || 0);
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

  return { groups };
}

/** Whole days since sent_date (calendar date), or null if missing. */
export function daysSinceSent(
  quote: Record<string, unknown>,
  today: Date = new Date()
): number | null {
  const raw = String(quote.sent_date || "").slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return null;
  const sent = new Date(`${raw}T12:00:00`);
  if (Number.isNaN(sent.getTime())) return null;
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const sentDay = new Date(sent.getFullYear(), sent.getMonth(), sent.getDate());
  return Math.round((start.getTime() - sentDay.getTime()) / 86_400_000);
}

export function statusLabel(status: string): string {
  if (status === "send_queued") return "Sending…";
  if (status === "send_failed") return "Send failed";
  if (status === "sent") return "Sent";
  if (status === "closed") return "Closed";
  if (status === "converted") return "Converted";
  return "Not sent";
}

export function quoteDashboardStats(
  quotes: Record<string, Record<string, unknown>> | null | undefined
): { sentCount: number; convertedCount: number; openSentCount: number } {
  const { groups } = quotesByStatus(quotes);
  const sentCount = groups.sent.length + groups.closed.length + groups.converted.length;
  return {
    sentCount,
    convertedCount: groups.converted.length,
    openSentCount: groups.sent.length,
  };
}

export function docKindLabel(docKind: string): string {
  return String(docKind || "quote").toLowerCase() === "estimate" ? "Price estimate" : "Quote";
}
