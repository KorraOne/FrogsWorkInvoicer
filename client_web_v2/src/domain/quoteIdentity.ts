/** Stable quote identity — display number is not unique. */

export function newQuoteId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `quo_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

/** Map / D1 key for a quote record. */
export function quoteStorageKey(quote: Record<string, unknown>, fallbackKey?: string): string {
  const id = String(quote.quote_id || "").trim();
  if (id) return id;
  if (fallbackKey) return fallbackKey;
  const n = parseInt(String(quote.quote_number), 10);
  if (Number.isFinite(n) && n >= 1) return String(n).padStart(8, "0");
  return newQuoteId();
}

/** Ensure every quote has quote_id; rekey map by quote_id. */
export function normalizeQuotesMap(
  quotes: Record<string, Record<string, unknown>> | null | undefined
): Record<string, Record<string, unknown>> {
  const out: Record<string, Record<string, unknown>> = {};
  for (const [mapKey, quote] of Object.entries(quotes || {})) {
    if (!quote || typeof quote !== "object") continue;
    const id = quoteStorageKey(quote, mapKey);
    const next: Record<string, unknown> = { ...quote, quote_id: id };
    if (out[id] && out[id].deleted_at && !next.deleted_at) {
      out[id] = next;
    } else if (!out[id]) {
      out[id] = next;
    }
  }
  return out;
}

export function suggestedQuoteNumber(
  businessName: string,
  businessProfile: Record<string, unknown>,
  quotes: Record<string, Record<string, unknown>>
): number {
  const counter = parseInt(String(businessProfile?.quote_counter), 10) || 1;
  const matching = Object.values(quotes || {})
    .filter((q) => !q.deleted_at && String(q.business_name || q.business || "") === businessName)
    .map((q) => parseInt(String(q.quote_number), 10) || 0);
  const deletedMatching = Object.values(quotes || {})
    .filter((q) => q.deleted_at && String(q.business_name || q.business || "") === businessName)
    .map((q) => parseInt(String(q.quote_number), 10) || 0);
  const allUsed = [...matching, ...deletedMatching];
  return !allUsed.length ? counter : Math.max(counter, Math.max(...allUsed) + 1);
}
